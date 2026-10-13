"""Tests for FFmpeg conversion progress parsing."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess

from video_switch.models.conversion_settings import ConversionSettings
from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import MediaTask
from video_switch.services.conversion_runner import (
    CANCEL_KILL_TIMEOUT_MS,
    ConversionRunner,
    build_progress,
    parse_ffmpeg_time,
    parse_microseconds,
)

FFMPEG_STUB = Path("ffmpeg.exe")


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


def test_single_run_forgets_the_previous_segmented_progress(
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    """MP3 (segmented) followed by GIF (single) used to jump straight to 100%."""
    del qtbot
    monkeypatch.setattr(ConversionRunner, "_start_single", lambda self, path: None)
    task = MediaTask(
        path=tmp_path / "clip.mp4",
        size_bytes=1024,
        content_signature="signature",
        imported_at=datetime.now(),
        media_info=MediaInfo(duration_seconds=750.0, width=1920, height=1080),
    )
    runner = ConversionRunner()
    runner._completed_duration = 750.0  # left behind by the finished MP3 run
    runner._segment_limit = 30.0
    captured: list = []
    runner.progress.connect(captured.append)

    runner.start(
        task,
        ConversionSettings(output_format="GIF", video_codec="GIF", audio_codec=""),
        tmp_path,
        FFMPEG_STUB,
    )

    assert runner._completed_duration == 0.0
    assert runner._segment_limit == 0.0

    runner._progress_data = {
        "progress": "continue",
        "out_time_us": "5000000",
        "speed": "20x",
    }
    runner._emit_segment_progress()

    assert captured, "进度信号没有发出"
    assert captured[-1].percent < 5
