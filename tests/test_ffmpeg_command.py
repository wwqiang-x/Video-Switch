"""Tests for conversion settings and FFmpeg command generation."""

from pathlib import Path

from video_switch.models.conversion_settings import ConversionSettings
from video_switch.services.ffmpeg_command import build_ffmpeg_args, unique_output_path


def test_default_mp4_command() -> None:
    settings = ConversionSettings()
    args = build_ffmpeg_args(settings, Path("input.mp4"), Path("output.mp4"))

    assert "-c:v" in args
    assert "libx264" in args
    assert "-crf" in args
    assert "23" in args
    assert "aac" in args
    assert "+faststart" in args


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
