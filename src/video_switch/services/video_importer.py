"""Validate and convert filesystem paths into media tasks."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from video_switch.models.media_task import MediaTask

SUPPORTED_VIDEO_EXTENSIONS = frozenset(
    {
        ".3gp",
        ".avi",
        ".flv",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".ts",
        ".webm",
        ".wmv",
    }
)


@dataclass(frozen=True)
class ImportIssue:
    """One path that could not be added to the queue."""

    path: Path
    reason: str


@dataclass
class ImportResult:
    """Summary of one import operation."""

    added: list[MediaTask] = field(default_factory=list)
    duplicates: list[Path] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.duplicates) + len(self.issues)


def format_file_size(size_bytes: int) -> str:
    """Format a file size for compact display in the task list."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class VideoImporter:
    """Turn file paths into validated media tasks."""

    def import_paths(
        self,
        paths: list[str] | tuple[str, ...],
        existing_keys: set[str] | None = None,
    ) -> ImportResult:
        result = ImportResult()
        seen_keys = set(existing_keys or ())
        seen_request_keys: set[str] = set()

        for raw_path in paths:
            path = Path(raw_path).expanduser()
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                result.issues.append(ImportIssue(path, "文件不存在或无法访问"))
                continue

            if not resolved.is_file():
                result.issues.append(ImportIssue(resolved, "目标不是文件"))
                continue

            if resolved.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
                result.issues.append(ImportIssue(resolved, "不支持该文件格式"))
                continue

            key = str(resolved).casefold()
            if key in seen_keys or key in seen_request_keys:
                result.duplicates.append(resolved)
                continue

            try:
                size_bytes = resolved.stat().st_size
            except OSError:
                result.issues.append(ImportIssue(resolved, "无法读取文件信息"))
                continue

            task = MediaTask(
                path=resolved,
                size_bytes=size_bytes,
                imported_at=datetime.now(),
            )
            result.added.append(task)
            seen_keys.add(task.key)
            seen_request_keys.add(key)

        return result
