"""Regressions that only reproduce with a real FFmpeg process."""

import time
from datetime import datetime
from pathlib import Path

import pytest

from video_switch.models.conversion_settings import ConversionSettings
from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import MediaTask, TaskStatus
from video_switch.services.conversion_runner import ConversionRunner

pytestmark = pytest.mark.slow


def _task(source: Path, duration: float) -> MediaTask:
    return MediaTask(
        path=source,
        size_bytes=source.stat().st_size,
        content_signature=f"e2e-{source.name}",
        imported_at=datetime.now(),
        media_info=MediaInfo(duration_seconds=duration, width=320, height=240),
        status=TaskStatus.METADATA_READY,
    )


def test_segmented_run_does_not_leak_progress_into_the_next_one(
    qtbot,
    tmp_path: Path,
    ffmpeg_path: Path,
    make_clip,
) -> None:
    """MP3 (segmented) followed by GIF (single) used to start at 100%."""
    source = make_clip(tmp_path / "clip.mp4", 40.0)
    output_dir = tmp_path / "out"
    runner = ConversionRunner()
    first_done: list = []
    runner.finished.connect(first_done.append)
    runner.start(
        _task(source, 40.0),
        ConversionSettings(output_format="MP3", video_codec="", audio_codec="MP3"),
        output_dir,
        ffmpeg_path,
    )
    qtbot.waitUntil(lambda: bool(first_done), timeout=120_000)
    assert first_done[-1].success is True, first_done[-1].error

    gif_progress: list = []
    gif_done: list = []
    runner.finished.disconnect()
    runner.progress.connect(gif_progress.append)
    runner.finished.connect(gif_done.append)
    runner.start(
        _task(source, 40.0),
        ConversionSettings(output_format="GIF", video_codec="GIF", audio_codec=""),
        output_dir,
        ffmpeg_path,
    )
    qtbot.waitUntil(lambda: len(gif_progress) >= 2, timeout=120_000)

    assert gif_progress[0].percent < 10
    runner.cancel()
    qtbot.waitUntil(lambda: bool(gif_done), timeout=30_000)


def test_cancel_stops_the_process_quickly(
    qtbot,
    tmp_path: Path,
    ffmpeg_path: Path,
    make_clip,
) -> None:
    source = make_clip(tmp_path / "clip.mp4", 60.0, size="640x480", rate=30)
    runner = ConversionRunner()
    progress: list = []
    finished: list = []
    runner.progress.connect(progress.append)
    runner.finished.connect(finished.append)
    runner.start(
        _task(source, 60.0),
        ConversionSettings(output_format="WebM", video_codec="VP9", audio_codec="Opus"),
        tmp_path / "out",
        ffmpeg_path,
    )
    qtbot.waitUntil(lambda: bool(progress), timeout=120_000)

    started = time.monotonic()
    runner.cancel()
    qtbot.waitUntil(lambda: bool(finished), timeout=10_000)
    elapsed = time.monotonic() - started

    assert finished[-1].cancelled is True
    assert elapsed < 1.0, f"取消耗时 {elapsed:.2f}s，超过预期"
