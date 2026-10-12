"""Tests for FFmpeg conversion progress parsing."""

from PySide6.QtCore import QProcess

from video_switch.services.conversion_runner import (
    CANCEL_KILL_TIMEOUT_MS,
    ConversionRunner,
    build_progress,
    parse_ffmpeg_time,
    parse_microseconds,
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


def test_av_nopts_value_is_not_treated_as_progress() -> None:
    """ffmpeg's first progress block reports AV_NOPTS_VALUE for every timestamp."""
    sentinel = "-9223372036854775807"
    progress = build_progress(
        "task-key",
        {
            "bitrate": "  -0.0kbits/s",
            "out_time_us": sentinel,
            "out_time_ms": sentinel,
            "out_time": "-577014:32:22.775807",
            "speed": "N/A",
            "progress": "continue",
        },
        duration_seconds=4.0,
    )

    assert progress is not None
    assert progress.processed_seconds is None
    assert progress.percent == 0.0
    assert progress.eta_seconds is None


def test_parse_microseconds_rejects_sentinels_and_garbage() -> None:
    assert parse_microseconds("3984979") == 3.984979
    assert parse_microseconds("-9223372036854775807") is None
    assert parse_microseconds("-1") is None
    assert parse_microseconds("N/A") is None
    assert parse_microseconds("") is None
    assert parse_microseconds(None) is None


def test_cancel_uses_a_short_kill_fallback(qtbot) -> None:
    """The kill fallback is what actually stops FFmpeg on Windows."""
    del qtbot  # only needed so a QApplication exists for QProcess and QTimer
    runner = ConversionRunner()
    runner._process = QProcess()

    runner.cancel()

    assert runner._cancel_requested is True
    assert runner._kill_timer.isActive()
    assert runner._kill_timer.interval() == CANCEL_KILL_TIMEOUT_MS
    assert CANCEL_KILL_TIMEOUT_MS <= 500
