"""Tests for FFmpeg conversion progress parsing."""

from video_switch.services.conversion_runner import (
    build_progress,
    parse_ffmpeg_time,
)


def test_parse_ffmpeg_time() -> None:
    assert parse_ffmpeg_time("01:02:03.500") == 3723.5
    assert parse_ffmpeg_time("invalid") is None


def test_build_conversion_progress() -> None:
    progress = build_progress(
        "task-key",
        {
            "out_time_us": "30000000",
            "speed": "2.0x",
            "progress": "continue",
        },
        duration_seconds=60.0,
    )

    assert progress is not None
    assert progress.percent == 50.0
    assert progress.processed_seconds == 30.0
    assert progress.speed == "2.0x"
    assert progress.eta_seconds == 15.0


def test_progress_end_is_complete() -> None:
    progress = build_progress(
        "task-key",
        {
            "out_time_us": "60000000",
            "speed": "1.0x",
            "progress": "end",
        },
        duration_seconds=60.0,
    )

    assert progress is not None
    assert progress.percent == 100.0
