"""Data model for an imported media file."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class TaskStatus(StrEnum):
    """Current processing state for one media task."""

    WAITING_FOR_METADATA = "待读取信息"
    METADATA_READY = "信息已读取"
    CONVERTING = "转换中"
    COMPLETED = "已完成"
    FAILED = "失败"


@dataclass(slots=True)
class MediaTask:
    """One imported file shown in the conversion queue."""

    path: Path
    size_bytes: int
    content_signature: str
    imported_at: datetime
    status: TaskStatus = TaskStatus.WAITING_FOR_METADATA

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
