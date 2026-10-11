"""Asynchronous ffprobe integration for imported media tasks."""

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import MediaTask

PROBE_TIMEOUT_MS = 30_000
CONTAINER_NAMES = {
    ".3gp": "3GP",
    ".avi": "AVI",
    ".flv": "FLV",
    ".m4v": "M4V",
    ".mkv": "MKV",
    ".mov": "MOV",
    ".mp4": "MP4",
    ".mpeg": "MPEG",
    ".mpg": "MPEG",
    ".ts": "TS",
    ".webm": "WebM",
    ".wmv": "WMV",
}


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """ffprobe result associated with one media task."""

    task_key: str
    path: Path
    info: MediaInfo | None = None
    error: str | None = None
    raw_output: str = ""


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _parse_frame_rate(value: object) -> float | None:
    text = str(value or "").strip()
    if not text or text in {"0/0", "N/A"}:
        return None
    if "/" in text:
        numerator, denominator = text.split("/", maxsplit=1)
        numerator_value = _as_float(numerator)
        denominator_value = _as_float(denominator)
        if not numerator_value or not denominator_value:
            return None
        return numerator_value / denominator_value
    return _as_float(text)


def _container_name(path: Path, format_name: str) -> str | None:
    suffix_name = CONTAINER_NAMES.get(path.suffix.lower())
    if suffix_name:
        return suffix_name
    normalized = format_name.lower()
    for name, label in (
        ("webm", "WebM"),
        ("matroska", "MKV"),
        ("mp4", "MP4"),
        ("mov", "MOV"),
        ("avi", "AVI"),
        ("flv", "FLV"),
        ("mpegts", "TS"),
        ("mpeg", "MPEG"),
    ):
        if name in normalized:
            return label
    return format_name.split(",", maxsplit=1)[0].upper() or None


def parse_ffprobe_output(output: str, source_path: Path) -> MediaInfo:
    """Parse ffprobe JSON output into a compact media information object."""
    payload = json.loads(output)
    streams = payload.get("streams") or []
    format_data = payload.get("format") or {}

    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        {},
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        {},
    )

    duration = _as_float(format_data.get("duration"))
    if duration is None:
        duration = _as_float(video_stream.get("duration"))

    bit_rate = _as_int(format_data.get("bit_rate"))
    if bit_rate is None:
        bit_rate = _as_int(video_stream.get("bit_rate"))

    format_name = str(format_data.get("format_name") or "")
    return MediaInfo(
        duration_seconds=duration,
        width=_as_int(video_stream.get("width")),
        height=_as_int(video_stream.get("height")),
        frame_rate=_parse_frame_rate(
            video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
        ),
        video_codec=str(video_stream.get("codec_name") or "") or None,
        audio_codec=str(audio_stream.get("codec_name") or "") or None,
        audio_sample_rate=_as_int(audio_stream.get("sample_rate")),
        audio_channels=_as_int(audio_stream.get("channels")),
        pixel_format=str(video_stream.get("pix_fmt") or "") or None,
        container=_container_name(source_path, format_name),
        bit_rate=bit_rate,
    )


class MediaProbeService(QObject):
    """Read media information with one ffprobe process at a time."""

    task_started = Signal(str)
    task_finished = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: deque[tuple[str, Path, Path]] = deque()
        self._queued_keys: set[str] = set()
        self._current: tuple[str, Path, Path] | None = None
        self._process: QProcess | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._start_next)

    def enqueue(self, task: MediaTask, ffprobe_path: Path) -> None:
        """Queue a task unless it is already pending or active."""
        if task.key in self._queued_keys:
            return
        self._queued_keys.add(task.key)
        self._queue.append((task.key, task.path, ffprobe_path))
        if self._current is None:
            self._start_next()

    def cancel_task(self, task_key: str) -> None:
        """Remove a queued task or terminate it when active."""
        self._queue = deque(item for item in self._queue if item[0] != task_key)
        self._queued_keys.discard(task_key)
        if self._current is not None and self._current[0] == task_key:
            self._cancel_current()
            self._start_next()

    def cancel_all(self) -> None:
        """Cancel all pending and active probe operations."""
        self._next_timer.stop()
        self._queue.clear()
        self._queued_keys.clear()
        self._cancel_current()

    def _start_next(self) -> None:
        if self._current is not None or not self._queue:
            return

        self._current = self._queue.popleft()
        task_key, source_path, ffprobe_path = self._current
        process = QProcess(self)
        process.finished.connect(self._on_process_finished)
        process.errorOccurred.connect(self._on_process_error)
        self._process = process
        self.task_started.emit(task_key)
        process.start(
            str(ffprobe_path),
            [
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(source_path),
            ],
        )
        self._timer.start(PROBE_TIMEOUT_MS)

    def _on_process_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        del exit_status
        if self._current is None or self._process is None:
            return

        task_key, source_path, _ = self._current
        stdout = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8",
            errors="replace",
        )
        stderr = bytes(self._process.readAllStandardError()).decode(
            "utf-8",
            errors="replace",
        )

        if exit_code == 0:
            try:
                info = parse_ffprobe_output(stdout, source_path)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                self._finish(
                    ProbeResult(
                        task_key=task_key,
                        path=source_path,
                        error=f"视频信息解析失败：{error}",
                        raw_output=stdout or stderr,
                    )
                )
                return
            self._finish(
                ProbeResult(
                    task_key=task_key,
                    path=source_path,
                    info=info,
                    raw_output=stdout,
                )
            )
            return

        error_text = stderr.strip() or stdout.strip() or "ffprobe 执行失败"
        self._finish(
            ProbeResult(
                task_key=task_key,
                path=source_path,
                error=error_text.splitlines()[-1],
                raw_output=stderr or stdout,
            )
        )

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart or self._current is None:
            return
        task_key, source_path, _ = self._current
        self._finish(
            ProbeResult(
                task_key=task_key,
                path=source_path,
                error="无法启动 ffprobe，请检查环境设置",
            )
        )

    def _on_timeout(self) -> None:
        if self._current is None:
            return
        task_key, source_path, _ = self._current
        process = self._process
        self._process = None
        if process is not None:
            try:
                process.finished.disconnect()
                process.errorOccurred.disconnect()
            except (RuntimeError, TypeError):
                pass
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
        self._finish(
            ProbeResult(
                task_key=task_key,
                path=source_path,
                error="读取视频信息超时",
            )
        )

    def _finish(self, result: ProbeResult) -> None:
        self._timer.stop()
        self._queued_keys.discard(result.task_key)
        self._current = None
        self._process = None
        self.task_finished.emit(result)
        self._next_timer.start(0)

    def _cancel_current(self) -> None:
        self._timer.stop()
        process = self._process
        self._process = None
        self._current = None
        if process is None:
            return
        try:
            process.finished.disconnect()
            process.errorOccurred.disconnect()
        except (RuntimeError, TypeError):
            pass
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
