"""Tests for conversion settings and FFmpeg command generation."""

from pathlib import Path

from video_switch.models.conversion_settings import ConversionSettings
from video_switch.services.ffmpeg_command import (
    build_ffmpeg_args,
    estimate_conversion_seconds,
    unique_output_path,
)


def test_default_mp4_command() -> None:
    settings = ConversionSettings()
    args = build_ffmpeg_args(settings, Path("input.mp4"), Path("output.mp4"))

    assert "-c:v" in args
    assert "libx264" in args
    assert "-crf" in args
    assert "23" in args
    assert "aac" in args
    assert "+faststart" in args


def test_progress_command_options() -> None:
    args = build_ffmpeg_args(
        ConversionSettings(),
        Path("input.mp4"),
        Path("output.mp4"),
        report_progress=True,
    )

    assert "-progress" in args
    assert "pipe:1" in args
    assert "-nostats" in args
    assert args[-1] == "output.mp4"


def test_audio_only_command() -> None:
    settings = ConversionSettings(
        output_format="MP3",
        video_codec="",
        audio_codec="MP3",
    )
    args = build_ffmpeg_args(settings, Path("input.mp4"), Path("output.mp3"))

    assert "-vn" in args
    assert "libmp3lame" in args
    assert "192k" in args


def test_webm_command_uses_vp9_and_opus() -> None:
    settings = ConversionSettings(
        output_format="WebM",
        video_codec="VP9",
        audio_codec="Opus",
    )
    args = build_ffmpeg_args(settings, Path("input.mp4"), Path("output.webm"))

    assert "libvpx-vp9" in args
    assert "libopus" in args
    assert "+faststart" not in args


def test_unique_output_path_adds_index(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output_directory = tmp_path / "converted"
    output_directory.mkdir()
    first_output = output_directory / "source_converted.mp4"
    first_output.write_bytes(b"existing")

    result = unique_output_path(
        source,
        ConversionSettings(),
        output_directory,
    )

    assert result == output_directory / "source_converted_1.mp4"


def test_estimate_conversion_seconds_uses_codec_and_workload() -> None:
    h264 = estimate_conversion_seconds(
        ConversionSettings(),
        duration_seconds=60,
        source_height=1080,
        source_frame_rate=30,
    )
    vp9 = estimate_conversion_seconds(
        ConversionSettings(
            output_format="WebM",
            video_codec="VP9",
            audio_codec="Opus",
        ),
        duration_seconds=60,
        source_height=1080,
        source_frame_rate=30,
    )
    lower_resolution = estimate_conversion_seconds(
        ConversionSettings(resolution="720p"),
        duration_seconds=60,
        source_height=1080,
        source_frame_rate=30,
    )

    assert h264 == 10.0
    assert vp9 == 75.0
    assert lower_resolution is not None
    assert lower_resolution < h264
