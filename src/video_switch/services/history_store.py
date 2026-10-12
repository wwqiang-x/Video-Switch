"""Load and persist conversion history records as JSON."""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from video_switch.models.conversion_history import ConversionHistoryRecord

HISTORY_LIMIT = 300


def default_history_path() -> Path:
    """Return the per-user history JSON path."""
    data_root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    base = Path(data_root) if data_root else Path(tempfile.gettempdir())
    return base / "conversion_history.json"


class ConversionHistoryStore:
    """Read and write conversion history without touching the UI."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[ConversionHistoryRecord]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []

        records: list[ConversionHistoryRecord] = []
        for item in payload:
            try:
                records.append(
                    ConversionHistoryRecord(
                        record_id=str(item["record_id"]),
                        timestamp=str(item["timestamp"]),
                        source_path=Path(item["source_path"]),
                        output_path=Path(item["output_path"]),
                        output_format=str(item["output_format"]),
                        status=str(item["status"]),
                        error=item.get("error"),
                        file_size=item.get("file_size"),
                        elapsed_seconds=float(item.get("elapsed_seconds", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return records[:HISTORY_LIMIT]

    def add(
        self,
        record: ConversionHistoryRecord,
    ) -> list[ConversionHistoryRecord]:
        records = [record, *self.load()][:HISTORY_LIMIT]
        self._write(records)
        return records

    def clear(self) -> None:
        self._write([])

    def _write(self, records: list[ConversionHistoryRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for record in records:
            item = asdict(record)
            item["source_path"] = str(record.source_path)
            item["output_path"] = str(record.output_path)
            payload.append(item)

        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
