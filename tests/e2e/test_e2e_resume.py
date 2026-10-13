"""Cancelling a segmented conversion and continuing it from the kept segments."""

from datetime import datetime
from pathlib import Path

import pytest

from video_switch.models.conversion_settings import ConversionSettings
from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import MediaTask, TaskStatus
from video_switch.services.conversion_runner import ConversionRunner

pytestmark = pytest.mark.slow

CLIP_SECONDS = 45.0


def test_cancelled_conversion_continues_from_its_segments(
    qtbot,
    tmp_path: Path,
    ffmpeg_path: Path,
    duration_of,
    make_clip,
) -> None:
    source = make_clip(tmp_path / "long.mp4", CLIP_SECONDS)
    task = MediaTask(
        path=source,
        size_bytes=source.stat().st_size,
        content_signature="e2e-resume",
        imported_at=datetime.now(),
        media_info=MediaInfo(duration_seconds=CLIP_SECONDS, width=320, height=240),
        status=TaskStatus.METADATA_READY,
    )
    settings = ConversionSettings()
    output_dir = tmp_path / "out"

    runner = ConversionRunner()
    progress: list = []
    results: list = []
    runner.progress.connect(progress.append)
    runner.finished.connect(results.append)
    runner.start(task, settings, output_dir, ffmpeg_path)

    # 等第一段真正落盘后再取消，这样能留下可续转的分段。
    qtbot.waitUntil(lambda: task.conversion_parts_completed >= 1, timeout=120_000)
    runner.cancel()
    qtbot.waitUntil(lambda: bool(results), timeout=30_000)

    cancelled = results[-1]
    assert cancelled.cancelled is True
    assert cancelled.can_resume is True
    part_dir = task.conversion_part_dir
    assert part_dir is not None and part_dir.is_dir()
    parts = sorted(part_dir.glob("part_*"))
    assert parts, "取消后没有留下已完成分段"
    assert cancelled.output_path.exists() is False

    resumed = ConversionRunner()
    resumed_results: list = []
    resumed_progress: list = []
    resumed.progress.connect(resumed_progress.append)
    resumed.finished.connect(resumed_results.append)
    resumed.start(task, settings, output_dir, ffmpeg_path)
    qtbot.waitUntil(lambda: bool(resumed_results), timeout=180_000)

    finished = resumed_results[-1]
    assert finished.success is True, finished.error
    assert duration_of(finished.output_path) == pytest.approx(CLIP_SECONDS, abs=0.6)
    assert resumed_progress[0].percent > 30, "续转没有从已完成的进度开始"
    assert list(part_dir.glob("part_*")) == []
    assert task.conversion_resumable is False
