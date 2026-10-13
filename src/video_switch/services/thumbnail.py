"""Generate and cache video thumbnail images with ffmpeg."""

import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QStandardPaths, QTimer, Signal

from video_switch.models.media_task import MediaTask
from video_switch.services.qt_process import detach_process

THUMBNAIL_WIDTH = 1920
THUMBNAIL_TIMEOUT_MS = 20_000
THUMBNAIL_CACHE_VERSION = "v3"


@dataclass(frozen=True, slots=True)
class ThumbnailResult:
    """Generated thumbnail associated with one media task."""

    task_key: str
    thumbnail_path: Path | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _ThumbnailJob:
    task_key: str
    source_path: Path
    output_path: Path
    ffmpeg_path: Path
    positions: tuple[float, ...]


def default_thumbnail_cache_dir() -> Path:
    """Return the application thumbnail cache directory."""
    cache_root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    base = Path(cache_root) if cache_root else Path(tempfile.gettempdir())
    return base / "VideoSwitch" / "thumbnails"


def thumbnail_positions(duration_seconds: float | None) -> tuple[float, ...]:
    """Return deduplicated seek positions ordered from best to fallback."""
    duration = max(0.0, duration_seconds or 0.0)
    candidates = [
        max(0.1, duration * 0.1) if duration else 1.0,
        1.0,
        duration / 2 if duration else 0.0,
        max(0.0, duration - 0.5) if duration else 0.0,
        0.0,
    ]

    positions: list[float] = []
    for candidate in candidates:
        if duration:
            candidate = min(candidate, max(0.0, duration - 0.05))
        if not any(abs(candidate - existing) < 0.05 for existing in positions):
            positions.append(round(candidate, 3))
    return tuple(positions)


def thumbnail_cache_path(cache_dir: Path, content_signature: str) -> Path:
    """Return a stable cache path derived from the content fingerprint."""
    return cache_dir / f"{THUMBNAIL_CACHE_VERSION}-{content_signature}.jpg"


class ThumbnailService(QObject):
    """Generate thumbnails one at a time without blocking the UI."""

    task_started = Signal(str)
    task_finished = Signal(object)

    def __init__(self, cache_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._queue: deque[_ThumbnailJob] = deque()
        self._queued_keys: set[str] = set()
        self._current: _ThumbnailJob | None = None
        self._current_index = 0
        self._process: QProcess | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._start_next)
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._start_attempt)

    def enqueue(self, task: MediaTask, ffmpeg_path: Path) -> bool:
        """Queue thumbnail generation unless it is cached or already pending."""
        output_path = thumbnail_cache_path(
            self.cache_dir,
            task.content_signature,
        )
        if output_path.is_file() and output_path.stat().st_size > 0:
            self.task_finished.emit(ThumbnailResult(task_key=task.key, thumbnail_path=output_path))
            return True

        if task.key in self._queued_keys:
            return False

        self._queued_keys.add(task.key)
        self._queue.append(
            _ThumbnailJob(
                task_key=task.key,
                source_path=task.path,
                output_path=output_path,
                ffmpeg_path=ffmpeg_path,
                positions=thumbnail_positions(
                    task.media_info.duration_seconds if task.media_info else None
                ),
            )
        )
        if self._current is None:
            self._start_next()
        return True

    def cancel_task(self, task_key: str) -> None:
        """Cancel a pending or active thumbnail job."""
        self._queue = deque(job for job in self._queue if job.task_key != task_key)
        self._queued_keys.discard(task_key)
        if self._current is not None and self._current.task_key == task_key:
            self._cancel_current()
            self._start_next()

    def cancel_all(self) -> None:
        """Cancel all pending and active thumbnail jobs."""
        self._next_timer.stop()
        self._retry_timer.stop()
        self._queue.clear()
        self._queued_keys.clear()
        self._cancel_current()

    def delete_cached(self, content_signature: str) -> None:
        """Delete one cached thumbnail if it exists."""
        thumbnail_cache_path(self.cache_dir, content_signature).unlink(missing_ok=True)
        (self.cache_dir / f"v2-{content_signature}.jpg").unlink(missing_ok=True)
        (self.cache_dir / f"{content_signature}.jpg").unlink(missing_ok=True)

    def _start_next(self) -> None:
        if self._current is not None or not self._queue:
            return
        self._current = self._queue.popleft()
        self._current_index = 0
        self.task_started.emit(self._current.task_key)
        self._start_attempt()

    def _start_attempt(self) -> None:
        if self._current is None:
            return
        if self._current_index >= len(self._current.positions):
            self._finish(
                ThumbnailResult(
                    task_key=self._current.task_key,
                    error="多次截取缩略图均失败",
                )
            )
            return

        output_path = self._current.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
        position = self._current.positions[self._current_index]

        process = QProcess(self)
        process.finished.connect(self._on_process_finished)
        process.errorOccurred.connect(self._on_process_error)
        self._process = process
        process.start(
            str(self._current.ffmpeg_path),
            [
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{position:.3f}",
                "-i",
                str(self._current.source_path),
                "-frames:v",
                "1",
                "-an",
                "-sn",
                "-dn",
                "-vf",
                f"scale='min({THUMBNAIL_WIDTH},iw)':-2",
                "-q:v",
                "1",
                "-y",
                str(output_path),
            ],
        )
        self._timer.start(THUMBNAIL_TIMEOUT_MS)

    def _on_process_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        del exit_status
        if self._current is None or self._process is None:
            return

        output_path = self._current.output_path
        if exit_code == 0 and output_path.is_file() and output_path.stat().st_size > 0:
            self._finish(
                ThumbnailResult(
                    task_key=self._current.task_key,
                    thumbnail_path=output_path,
                )
            )
            return

        self._current_index += 1
        self._restart_attempt()

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart or self._current is None:
            return
        self._finish(
            ThumbnailResult(
                task_key=self._current.task_key,
                error="无法启动 ffmpeg，请检查环境设置",
            )
        )

    def _on_timeout(self) -> None:
        if self._current is None:
            return
        self._current_index += 1
        self._restart_attempt()

    def _restart_attempt(self) -> None:
        self._timer.stop()
        process = self._detach_process()
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
        self._retry_timer.start(0)

    def _finish(self, result: ThumbnailResult) -> None:
        self._timer.stop()
        self._detach_process()
        self._queued_keys.discard(result.task_key)
        self._current = None
        self.task_finished.emit(result)
        self._next_timer.start(0)

    def _cancel_current(self) -> None:
        self._timer.stop()
        self._retry_timer.stop()
        process = self._detach_process()
        self._current = None
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def _detach_process(self) -> QProcess | None:
        process = self._process
        self._process = None
        if process is None:
            return None
        detach_process(process)
        return process
