"""Real FFmpeg conversions driven through the runner."""

import subprocess
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
        media_info=MediaInfo(
            duration_seconds=duration,
            width=320,
            height=240,
            frame_rate=15.0,
            video_codec="h264",
            audio_codec="aac",
        ),
        status=TaskStatus.METADATA_READY,
    )


def _run_until_finished(runner: ConversionRunner, task: MediaTask, settings, out, ffmpeg):
    """Start a conversion and return the list that receives the result."""
    results: list = []
    runner.finished.connect(results.append)
    runner.start(task, settings, out, ffmpeg)
    return results


def test_single_conversion_writes_a_playable_file(
    qtbot,
    tmp_path: Path,
    ffmpeg_path: Path,
    ffprobe_path: Path,
    duration_of,
    make_clip,
) -> None:
    source = make_clip(tmp_path / "input.mp4", 2.0)
    runner = ConversionRunner()

    results = _run_until_finished(
        runner,
        _task(source, 2.0),
        ConversionSettings(),
        tmp_path / "out",
        ffmpeg_path,
    )
    qtbot.waitUntil(lambda: bool(results), timeout=120_000)
    result = results[-1]

    assert result.success is True, result.error
    assert result.cancelled is False
    assert result.output_path.is_file()
    assert duration_of(result.output_path) == pytest.approx(2.0, abs=0.4)


def test_audio_only_conversion_drops_the_video_stream(
    qtbot,
    tmp_path: Path,
    ffmpeg_path: Path,
    ffprobe_path: Path,
    make_clip,
) -> None:
    source = make_clip(tmp_path / "input.mp4", 2.0)
    runner = ConversionRunner()
    settings = ConversionSettings(output_format="MP3", video_codec="", audio_codec="MP3")

    results = _run_until_finished(
        runner, _task(source, 2.0), settings, tmp_path / "out", ffmpeg_path
    )
    qtbot.waitUntil(lambda: bool(results), timeout=120_000)
    result = results[-1]

    assert result.success is True, result.error
    probe = subprocess.run(
        [
            str(ffprobe_path),
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(result.output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "video" not in probe.stdout
    assert "audio" in probe.stdout


def test_broken_source_is_reported_in_plain_language(
    qtbot,
    tmp_path: Path,
    ffmpeg_path: Path,
) -> None:
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"this is not a video file")
    runner = ConversionRunner()

    results = _run_until_finished(
        runner, _task(broken, 5.0), ConversionSettings(), tmp_path / "out", ffmpeg_path
    )
    qtbot.waitUntil(lambda: bool(results), timeout=120_000)
    result = results[-1]

    assert result.success is False
    assert result.error
    assert "Invalid" not in result.error
