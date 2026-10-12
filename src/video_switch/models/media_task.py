"""Data model for an imported media file."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from video_switch.models.media_info import MediaInfo


class TaskStatus(StrEnum):
    """Current processing state for one media task."""

    WAITING_FOR_METADATA = "待读取"
    PROBING_METADATA = "读取中"
    METADATA_READY = "已读取"
    CONVERTING = "转换中"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"


@dataclass(slots=True)
class MediaTask:
    """One imported file shown in the conversion queue."""

    path: Path
    size_bytes: int
    content_signature: str
    imported_at: datetime
    status: TaskStatus = TaskStatus.WAITING_FOR_METADATA
    media_info: MediaInfo | None = None
    probe_error: str | None = None
    raw_probe_output: str | None = None
    thumbnail_path: Path | None = None
    thumbnail_error: str | None = None
    thumbnail_generating: bool = False
    output_path: Path | None = None
    conversion_progress: float = 0.0
    conversion_speed: str | None = None
    conversion_eta_seconds: float | None = None
    conversion_log: str = ""
    conversion_error: str | None = None
    conversion_format: str | None = None
    conversion_summary: str | None = None

    @property
    def display_name(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix.removeprefix(".").upper()

    @property
    def key(self) -> str:
        return str(self.path.resolve()).casefold()

    @property
    def status_text(self) -> str:
        return self.status.value
