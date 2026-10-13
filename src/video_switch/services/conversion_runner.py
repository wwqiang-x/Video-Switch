"""Run FFmpeg conversions with progress, cancellation, and resumable segments."""

import hashlib
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from video_switch.models.conversion_settings import ConversionSettings
from video_switch.models.media_task import MediaTask
from video_switch.services.error_messages import describe_conversion_error
from video_switch.services.ffmpeg_command import (
    build_ffmpeg_args,
    unique_output_path,
)

# Qt's terminate() only posts WM_CLOSE on Windows, which a console FFmpeg process
# never receives, so the fallback kill defines the real cancel latency. The
# in-flight segment is discarded anyway, so a long grace period buys nothing.
CANCEL_KILL_TIMEOUT_MS = 250
MAX_LOG_CHARACTERS = 200_000
SEGMENT_DURATION_SECONDS = 30.0
RESUMABLE_FORMATS = {"MP4", "MKV", "WebM", "MP3", "WAV"}


@dataclass(frozen=True, slots=True)
class ConversionProgress:
    """Parsed conversion progress for one task."""

    task_key: str
    percent: float
    processed_seconds: float | None
    speed: str | None
    eta_seconds: float | None


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """Final result of one conversion run."""

    task_key: str
    source_key: str
    source_path: Path
    output_format: str
    output_path: Path
    success: bool
    cancelled: bool
    error: str | None
    log: str
    elapsed_seconds: float
    can_resume: bool = False
    progress_percent: float = 0.0


def parse_ffmpeg_time(value: str) -> float | None:
    """Parse an FFmpeg ``HH:MM:SS.micro`` timestamp."""
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (TypeError, ValueError):
        return None


def parse_speed(value: str) -> float | None:
    """Parse a speed value such as ``1.25x``."""
    try:
        return float(value.rstrip("x"))
    except (TypeError, ValueError):
        return None


def _non_negative(value: float | None) -> float | None:
    """Drop ``AV_NOPTS_VALUE`` sentinels and other negative timestamps."""
    if value is None or value < 0:
        return None
    return value


def parse_microseconds(value: str | None) -> float | None:
    """Parse an ffmpeg microsecond timestamp, ignoring its "no value" sentinel."""
    if not value:
        return None
    try:
        return _non_negative(int(value) / 1_000_000)
    except (TypeError, ValueError, OverflowError):
        return None


def build_progress(
    task_key: str,
    data: dict[str, str],
    duration_seconds: float | None,
) -> ConversionProgress | None:
    """Convert one FFmpeg progress key/value block into UI progress."""
    progress_value = data.get("progress")
    if progress_value is None:
        return None

    # The first block ffmpeg emits carries AV_NOPTS_VALUE (-9223372036854775807)
    # for every timestamp, which must never be treated as real progress.
    processed_seconds = parse_microseconds(data.get("out_time_us"))
    if processed_seconds is None:
        processed_seconds = parse_microseconds(data.get("out_time_ms"))
    if processed_seconds is None:
        processed_seconds = _non_negative(parse_ffmpeg_time(data.get("out_time") or ""))

    if progress_value == "end":
        percent = 100.0
    elif duration_seconds and processed_seconds is not None and duration_seconds > 0:
        percent = min(99.9, max(0.0, processed_seconds / duration_seconds * 100))
    else:
        percent = 0.0

    speed_text = data.get("speed")
    speed_value = parse_speed(speed_text)
    eta_seconds: float | None = None
    if duration_seconds and processed_seconds is not None and speed_value and speed_value > 0:
        eta_seconds = max(0.0, (duration_seconds - processed_seconds) / speed_value)

    return ConversionProgress(
        task_key=task_key,
        percent=percent,
        processed_seconds=processed_seconds,
        speed=speed_text,
        eta_seconds=eta_seconds,
    )


class ConversionRunner(QObject):
    """Execute one conversion, optionally using resumable 30-second segments."""

    started = Signal(str, object)
    progress = Signal(object)
    log_line = Signal(str, str)
    finished = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._task: MediaTask | None = None
        self._task_key = ""
        self._source_key = ""
        self._source_path = Path()
        self._output_format = ""
        self._output_path: Path | None = None
        self._ffmpeg_path: Path | None = None
        self._settings: ConversionSettings | None = None
        self._total_duration = 0.0
        self._completed_duration = 0.0
        self._segment_limit = 0.0
        self._part_dir: Path | None = None
        self._part_paths: list[Path] = []
        self._current_part: Path | None = None
        self._concat_list: Path | None = None
        self._mode = ""
        self._cancel_requested = False
        self._completed = False
        self._started_at = 0.0
        self._stdout_buffer = ""
        self._log_parts: list[str] = []
        self._progress_data: dict[str, str] = {}
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._force_kill)

    @property
    def is_running(self) -> bool:
        return self._process is not None

    def start(
        self,
        task: MediaTask,
        settings: ConversionSettings,
        output_directory: Path | None,
        ffmpeg_path: Path,
    ) -> Path:
        """Start or resume one conversion and return the final output path."""
        if self.is_running:
            raise RuntimeError("已有转换任务正在执行")
        if task.media_info is None:
            raise ValueError("任务尚未读取媒体信息")

        output_path = unique_output_path(task.path, settings, output_directory)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self._task = task
        self._task_key = task.key
        self._source_key = task.content_signature
        self._source_path = task.path
        self._output_format = settings.output_format
        self._output_path = output_path
        self._ffmpeg_path = ffmpeg_path
        self._settings = settings
        self._total_duration = task.media_info.duration_seconds or 0.0
        self._cancel_requested = False
        self._completed = False
        self._started_at = time.monotonic()
        self._stdout_buffer = ""
        self._log_parts = []
        self._progress_data = {}
        self._part_paths = []
        self._current_part = None
        self._concat_list = None
        # A previous segmented run leaves its finished duration behind; without
        # this reset a following single-process run starts out at ~100%.
        self._completed_duration = 0.0
        self._segment_limit = 0.0

        self.started.emit(task.key, output_path)
        if (
            settings.output_format in RESUMABLE_FORMATS
            and self._total_duration > SEGMENT_DURATION_SECONDS
        ):
            self._mode = "segment"
            self._prepare_segmented_resume(task, settings, output_path)
        else:
            self._mode = "single"
            task.conversion_resumable = False
            self._start_single(output_path)
        return output_path

    def cancel(self) -> None:
        """Request a graceful stop, then force kill if needed."""
        if self._process is None:
            return
        self._cancel_requested = True
        self._process.terminate()
        self._kill_timer.start(CANCEL_KILL_TIMEOUT_MS)

    def shutdown(self) -> None:
        """Stop immediately and remove only the incomplete current output."""
        self._cancel_requested = True
        self._kill_timer.stop()
        if self._process is not None:
            self._process.kill()
            self._process.waitForFinished(2000)
        self._remove_current_part()
        self._remove_output()
        self._release_process()

    def _prepare_segmented_resume(
        self,
        task: MediaTask,
        settings: ConversionSettings,
        output_path: Path,
    ) -> None:
        digest = hashlib.sha256(repr(settings).encode("utf-8")).hexdigest()[:16]
        part_dir = output_path.parent / f".{output_path.stem}.{digest}.parts"
        resume_matches = (
            task.conversion_part_dir == part_dir and task.conversion_settings_key == digest
        )
        if not resume_matches:
            if task.conversion_part_dir is not None and task.conversion_part_dir != part_dir:
                shutil.rmtree(task.conversion_part_dir, ignore_errors=True)
            if part_dir.exists():
                shutil.rmtree(part_dir, ignore_errors=True)
            task.conversion_parts_completed = 0

        part_dir.mkdir(parents=True, exist_ok=True)
        task.conversion_part_dir = part_dir
        task.conversion_settings_key = digest
        task.conversion_resumable = True
        self._part_dir = part_dir
        self._part_paths = sorted(part_dir.glob(f"part_*{output_path.suffix}"))
        task.conversion_parts_completed = len(self._part_paths)
        self._completed_duration = min(
            self._total_duration,
            len(self._part_paths) * SEGMENT_DURATION_SECONDS,
        )

        if self._completed_duration >= self._total_duration:
            self._start_concat()
        else:
            self._start_next_segment()

    def _start_next_segment(self) -> None:
        if self._output_path is None or self._part_dir is None or self._settings is None:
            return
        segment_start = self._completed_duration
        segment_duration = min(
            SEGMENT_DURATION_SECONDS,
            max(0.01, self._total_duration - segment_start),
        )
        self._segment_limit = segment_duration
        self._current_part = self._part_dir / (
            f"part_{len(self._part_paths):05d}{self._output_path.suffix}"
        )
        self._current_part.unlink(missing_ok=True)
        args = build_ffmpeg_args(
            self._settings,
            self._source_path,
            self._current_part,
            report_progress=True,
            start_seconds=segment_start,
            segment_duration=segment_duration,
        )
        self._start_process(args)

    def _start_concat(self) -> None:
        if self._output_path is None or self._part_dir is None:
            return
        self._mode = "concat"
        self._concat_list = self._part_dir / "parts.txt"
        lines = []
        for part in self._part_paths:
            escaped = part.as_posix().replace("'", "'\\''")
            lines.append(f"file '{escaped}'")
        self._concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.progress.emit(
            ConversionProgress(
                task_key=self._task_key,
                percent=99.9,
                processed_seconds=self._total_duration,
                speed=None,
                eta_seconds=0.0,
            )
        )
        self._start_process(
            [
                "-hide_banner",
                "-loglevel",
                "warning",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(self._concat_list),
                "-c",
                "copy",
                str(self._output_path),
            ]
        )

    def _start_single(self, output_path: Path) -> None:
        if self._settings is None:
            return
        args = build_ffmpeg_args(
            self._settings,
            self._source_path,
            output_path,
            report_progress=True,
        )
        self._start_process(args)

    def _start_process(self, args: list[str]) -> None:
        if self._ffmpeg_path is None:
            return
        self._release_process()
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        process.start(str(self._ffmpeg_path), args)

    def _release_process(self) -> None:
        """Let Qt destroy the QProcess of a finished step.

        A long video is converted in 30-second segments, so without this the
        runner would keep one QProcess object per segment alive for the whole
        session (240 objects for a two-hour file).
        """
        process = self._process
        self._process = None
        if process is not None:
            process.deleteLater()

    def _read_stdout(self) -> None:
        if self._process is None or self.sender() is not self._process:
            return
        chunk = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8",
            errors="replace",
        )
        self._stdout_buffer += chunk
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", maxsplit=1)
            self._handle_progress_line(line.strip())

    def _read_stderr(self) -> None:
        if self._process is None or self.sender() is not self._process:
            return
        chunk = bytes(self._process.readAllStandardError()).decode(
            "utf-8",
            errors="replace",
        )
        if chunk:
            self._append_log(chunk)

    def _handle_progress_line(self, line: str) -> None:
        if not line or "=" not in line or self._mode == "concat":
            return
        key, value = line.split("=", maxsplit=1)
        self._progress_data[key] = value
        if key != "progress":
            return
        self._emit_segment_progress()
        self._progress_data = {}

    def _emit_segment_progress(self) -> None:
        parsed = build_progress(
            self._task_key,
            self._progress_data,
            self._segment_limit,
        )
        if parsed is None:
            return
        segment_processed = parsed.processed_seconds or 0.0
        total_processed = max(
            0.0,
            min(
                self._total_duration,
                self._completed_duration + segment_processed,
            ),
        )
        percent = (
            100.0
            if self._total_duration <= 0
            else min(99.9, max(0.0, total_processed / self._total_duration * 100))
        )
        speed_value = parse_speed(parsed.speed or "")
        eta = None
        if speed_value and speed_value > 0:
            eta = max(0.0, (self._total_duration - total_processed) / speed_value)
        self.progress.emit(
            ConversionProgress(
                task_key=self._task_key,
                percent=percent,
                processed_seconds=total_processed,
                speed=parsed.speed,
                eta_seconds=eta,
            )
        )

    def _append_log(self, text: str) -> None:
        self._log_parts.append(text)
        current_length = sum(len(part) for part in self._log_parts)
        while current_length > MAX_LOG_CHARACTERS and len(self._log_parts) > 1:
            current_length -= len(self._log_parts.pop(0))
        self.log_line.emit(self._task_key, text)

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        del exit_status
        if self._completed or self._process is None:
            return
        self._completed = True
        self._kill_timer.stop()
        self._read_stderr()
        elapsed = max(0.0, time.monotonic() - self._started_at)
        log = "".join(self._log_parts)

        if self._mode == "single":
            self._finish_single(exit_code, log, elapsed)
        elif self._mode == "segment":
            self._finish_segment(exit_code, log, elapsed)
        else:
            self._finish_concat(exit_code, log, elapsed)

    def _finish_single(self, exit_code: int, log: str, elapsed: float) -> None:
        if self._output_path is None:
            return
        if self._cancel_requested:
            self._remove_output()
            self._emit_result(cancelled=True, error="转换已取消", log=log, elapsed=elapsed)
        elif exit_code == 0 and self._output_path.is_file():
            self._emit_result(cancelled=False, error=None, log=log, elapsed=elapsed)
        else:
            self._remove_output()
            self._emit_result(
                cancelled=False,
                error=describe_conversion_error(log, "FFmpeg 转换失败"),
                log=log,
                elapsed=elapsed,
            )

    def _finish_segment(self, exit_code: int, log: str, elapsed: float) -> None:
        if self._cancel_requested:
            self._remove_current_part()
            self._emit_result(
                cancelled=True,
                error="转换已取消",
                log=log,
                elapsed=elapsed,
                can_resume=True,
            )
            return
        if exit_code != 0 or self._current_part is None or not self._current_part.is_file():
            self._remove_current_part()
            self._emit_result(
                cancelled=False,
                error=describe_conversion_error(log, "分段转换失败"),
                log=log,
                elapsed=elapsed,
                can_resume=bool(self._part_paths),
            )
            return

        self._part_paths.append(self._current_part)
        self._completed_duration = min(
            self._total_duration,
            self._completed_duration + self._segment_limit,
        )
        if self._task is not None:
            self._task.conversion_parts_completed = len(self._part_paths)
        self._current_part = None
        self._completed = False
        if self._completed_duration >= self._total_duration:
            self._start_concat()
        else:
            self._start_next_segment()

    def _finish_concat(self, exit_code: int, log: str, elapsed: float) -> None:
        if self._output_path is None:
            return
        if self._cancel_requested:
            self._remove_output()
            self._emit_result(
                cancelled=True,
                error="转换已取消",
                log=log,
                elapsed=elapsed,
                can_resume=True,
            )
            return
        if exit_code == 0 and self._output_path.is_file():
            self._cleanup_parts()
            self._emit_result(cancelled=False, error=None, log=log, elapsed=elapsed)
        else:
            self._remove_output()
            self._emit_result(
                cancelled=False,
                error=describe_conversion_error(log, "合并输出失败"),
                log=log,
                elapsed=elapsed,
                can_resume=True,
            )

    def _emit_result(
        self,
        cancelled: bool,
        error: str | None,
        log: str,
        elapsed: float,
        can_resume: bool = False,
    ) -> None:
        if self._output_path is None:
            return
        if self._task is not None:
            self._task.conversion_resumable = can_resume
        result = ConversionResult(
            task_key=self._task_key,
            source_key=self._source_key,
            source_path=self._source_path,
            output_format=self._output_format,
            output_path=self._output_path,
            success=not cancelled and error is None,
            cancelled=cancelled,
            error=error,
            log=log,
            elapsed_seconds=elapsed,
            can_resume=can_resume,
            progress_percent=(
                100.0
                if not cancelled and error is None
                else (
                    min(99.9, self._completed_duration / self._total_duration * 100)
                    if self._total_duration > 0
                    else 0.0
                )
            ),
        )
        self._release_process()
        self._output_path = None
        self.finished.emit(result)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart or self._completed:
            return
        self._completed = True
        self._kill_timer.stop()
        self._emit_result(
            cancelled=False,
            error="无法启动 FFmpeg，请检查环境设置",
            log="".join(self._log_parts),
            elapsed=max(0.0, time.monotonic() - self._started_at),
            can_resume=bool(self._part_paths),
        )

    def _force_kill(self) -> None:
        if self._process is not None:
            self._process.kill()

    def _remove_output(self) -> None:
        if self._output_path is None:
            return
        try:
            self._output_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _remove_current_part(self) -> None:
        if self._current_part is None:
            return
        try:
            self._current_part.unlink(missing_ok=True)
        except OSError:
            pass

    def _cleanup_parts(self) -> None:
        if self._part_dir is not None:
            shutil.rmtree(self._part_dir, ignore_errors=True)
        if self._task is not None:
            self._task.conversion_part_dir = None
            self._task.conversion_parts_completed = 0
            self._task.conversion_settings_key = ""
            self._task.conversion_resumable = False
