"""Tests for thumbnail positioning and cache paths."""

from pathlib import Path

from video_switch.services.thumbnail import (
    thumbnail_cache_path,
    thumbnail_positions,
)


def test_thumbnail_positions_for_long_video() -> None:
    positions = thumbnail_positions(600)

    assert positions[0] == 60.0
    assert 1.0 in positions
    assert 300.0 in positions
    assert positions[-1] == 0.0


def test_thumbnail_positions_for_short_video_are_bounded() -> None:
    positions = thumbnail_positions(0.5)

    assert positions
    assert all(0 <= position <= 0.45 for position in positions)


def test_thumbnail_cache_path() -> None:
    cache_dir = Path("cache")

    result = thumbnail_cache_path(cache_dir, "abc123")

    assert result == cache_dir / "v3-abc123.jpg"
