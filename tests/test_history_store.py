"""Tests for persistent conversion history."""

from pathlib import Path

from video_switch.models.conversion_history import ConversionHistoryRecord
from video_switch.services.history_store import ConversionHistoryStore


def test_history_store_round_trip(tmp_path: Path) -> None:
    store = ConversionHistoryStore(tmp_path / "history.json")
    first = ConversionHistoryRecord(
        record_id="first",
        timestamp="2026-10-12T15:30:00+08:00",
        source_path=tmp_path / "source.mp4",
        output_path=tmp_path / "converted" / "source_converted.mkv",
        output_format="MKV",
        status="已完成",
        file_size=1234,
        elapsed_seconds=2.5,
    )
    second = ConversionHistoryRecord(
        record_id="second",
        timestamp="2026-10-12T15:35:00+08:00",
        source_path=tmp_path / "other.mp4",
        output_path=tmp_path / "converted" / "other_converted.mp4",
        output_format="MP4",
        status="失败",
        error="FFmpeg 转换失败",
    )

    store.add(first)
    records = store.add(second)

    assert [record.record_id for record in records] == ["second", "first"]
    loaded = store.load()
    assert loaded[0].output_format == "MP4"
    assert loaded[1].file_size == 1234

    store.clear()
    assert store.load() == []
