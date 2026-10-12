"""Run one FFmpeg conversion at a time and report progress."""

import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from video_switch.models.conversion_settings import ConversionSettings
from video_switch.models.media_task import MediaTask
from video_switch.services.ffmpeg_command import (
    build_ffmpeg_args,
    unique_output_path,
)

CANCEL_KILL_TIMEOUT_MS = 1500
MAX_LOG_CHARACTERS = 200_000


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
    source_path: Path
    output_format: str
    output_path: Path
    success: bool
    cancelled: bool
    error: str | None
    log: str
    elapsed_seconds: float


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


def build_progress(
    task_key: str,
    data: dict[str, str],
    duration_seconds: float | None,
) -> ConversionProgress | None:
    """Convert one FFmpeg progress key/value block into UI progress."""
    progress_value = data.get("progress")
    if progress_value is None:
        return None

    processed_seconds: float | None = None
    if data.get("out_time_us"):
        try:
            processed_seconds = int(data["out_time_us"]) / 1_000_000
        except ValueError:
            processed_seconds = None
    if processed_seconds is None and data.get("out_time_ms"):
        try:
            processed_seconds = int(data["out_time_ms"]) / 1_000_000
        except ValueError:
            processed_seconds = None
    if processed_seconds is None and data.get("out_time"):
        processed_seconds = parse_ffmpeg_time(data["out_time"])

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
    """Execute a single FFmpeg conversion and publish live progress."""

    started = Signal(str, object)
    progress = Signal(object)
    log_line = Signal(str, str)
    finished = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._task_key = ""
        self._source_path = Path()
        self._output_format = ""
        self._output_path: Path | None = None
        self._duration_seconds: float | None = None
        self._cancel_requested = False
        self._completed = False
        self._started_at = 0.0
        self._stdout_buffer = ""
        self._stderr_buffer = ""
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
        """Start one conversion and return the chosen output path."""
        if self.is_running:
            raise RuntimeError("已有转换任务正在执行")
        if task.media_info is None:
            raise ValueError("任务尚未读取媒体信息")

        output_path = unique_output_path(
            task.path,
            settings,
            output_directory,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        args = build_ffmpeg_args(
            settings,
            task.path,
            output_path,
            report_progress=True,
        )

        self._task_key = task.key
        self._source_path = task.path
        self._output_format = settings.output_format
        self._output_path = output_path
        self._duration_seconds = task.media_info.duration_seconds
        self._cancel_requested = False
        self._completed = False
        self._started_at = time.monotonic()
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._log_parts = []
        self._progress_data = {}

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        self.started.emit(task.key, output_path)
        process.start(str(ffmpeg_path), args)
        return output_path

    def cancel(self) -> None:
        """Request a graceful stop, then force kill if needed."""
        if self._process is None:
            return
        self._cancel_requested = True
        self._process.terminate()
        self._kill_timer.start(CANCEL_KILL_TIMEOUT_MS)

    def shutdown(self) -> None:
        """Stop FFmpeg immediately and remove any partial output."""
        self._cancel_requested = True
        self._kill_timer.stop()
        if self._process is not None:
            self._process.kill()
            self._process.waitForFinished(2000)
        self._remove_output()
        self._process = None
        self._output_path = None

    def _read_stdout(self) -> None:
        if self._process is None:
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
        if self._process is None:
            return
        chunk = bytes(self._process.readAllStandardError()).decode(
            "utf-8",
            errors="replace",
        )
        if not chunk:
            return
        self._stderr_buffer += chunk
        self._append_log(chunk)

    def _handle_progress_line(self, line: str) -> None:
        if not line or "=" not in line:
            return
        key, value = line.split("=", maxsplit=1)
        self._progress_data[key] = value
        if key != "progress":
            return
        parsed = build_progress(
            self._task_key,
            self._progress_data,
            self._duration_seconds,
        )
        self._progress_data = {}
        if parsed is not None:
            self.progress.emit(parsed)

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
        if self._completed or self._process is None or self._output_path is None:
            return
        self._completed = True
        self._kill_timer.stop()
        self._read_stderr()
        log = "".join(self._log_parts)
        elapsed = max(0.0, time.monotonic() - self._started_at)

        if self._cancel_requested:
            self._remove_output()
            self._finish_result(
                ConversionResult(
                    task_key=self._task_key,
                    source_path=self._source_path,
                    output_format=self._output_format,
                    output_path=self._output_path,
                    success=False,
                    cancelled=True,
                    error="转换已取消",
                    log=log,
                    elapsed_seconds=elapsed,
                )
            )
            return

        if exit_code == 0 and self._output_path.is_file():
            self._finish_result(
                ConversionResult(
                    task_key=self._task_key,
                    source_path=self._source_path,
                    output_format=self._output_format,
                    output_path=self._output_path,
                    success=True,
                    cancelled=False,
                    error=None,
                    log=log,
                    elapsed_seconds=elapsed,
                )
            )
            return

        self._remove_output()
        error = self._last_log_line(log) or "FFmpeg 转换失败"
        self._finish_result(
            ConversionResult(
                task_key=self._task_key,
                source_path=self._source_path,
                output_format=self._output_format,
                output_path=self._output_path,
                success=False,
                cancelled=False,
                error=error,
                log=log,
                elapsed_seconds=elapsed,
            )
        )

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart or self._completed:
            return
        self._completed = True
        self._kill_timer.stop()
        output_path = self._output_path or Path()
        self._finish_result(
            ConversionResult(
                task_key=self._task_key,
                source_path=self._source_path,
                output_format=self._output_format,
                output_path=output_path,
                success=False,
                cancelled=False,
                error="无法启动 FFmpeg，请检查环境设置",
                log="".join(self._log_parts),
                elapsed_seconds=max(0.0, time.monotonic() - self._started_at),
            )
        )

    def _force_kill(self) -> None:
        if self._process is not None:
            self._process.kill()

    def _finish_result(self, result: ConversionResult) -> None:
        self._process = None
        self._output_path = None
        self.finished.emit(result)

    def _remove_output(self) -> None:
        if self._output_path is None:
            return
        try:
            self._output_path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _last_log_line(log: str) -> str:
        for line in reversed(log.splitlines()):
            if line.strip():
                return line.strip()
        return ""
