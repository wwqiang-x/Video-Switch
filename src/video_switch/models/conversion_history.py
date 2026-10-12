"""Persistent conversion history records."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ConversionHistoryRecord:
    """One completed, cancelled, or failed conversion attempt."""

    record_id: str
    timestamp: str
    source_key: str
    source_path: Path
    output_path: Path
    output_format: str
    status: str
    error: str | None = None
    file_size: int | None = None
    elapsed_seconds: float = 0.0

    @property
    def source_name(self) -> str:
        return self.source_path.name

    @property
    def output_directory(self) -> Path:
        return self.output_path.parent
