"""Build deterministic FFmpeg command arguments from conversion settings."""

import subprocess
from pathlib import Path

from video_switch.models.conversion_settings import ConversionSettings

VIDEO_ENCODERS = {
    "H.264": "libx264",
    "H.265": "libx265",
    "AV1": "libaom-av1",
    "VP9": "libvpx-vp9",
    "GIF": "gif",
}

AUDIO_ENCODERS = {
    "AAC": "aac",
    "MP3": "libmp3lame",
    "Opus": "libopus",
    "Vorbis": "libvorbis",
    "PCM": "pcm_s16le",
}

QUALITY_DEFAULTS = {
    "平衡（推荐）": (23, "medium"),
    "高质量": (18, "slow"),
    "小体积": (28, "veryfast"),
}


def _ffmpeg_bitrate(value: str) -> str:
    """Convert a user-facing bitrate such as ``192 kbps`` to ``192k``."""
    number = value.split(maxsplit=1)[0]
    return f"{number}k"


def unique_output_path(
    source_path: Path,
    settings: ConversionSettings,
    output_directory: Path | None = None,
) -> Path:
    """Return a non-conflicting output path for one source file."""
    directory = output_directory or source_path.parent / "converted"
    candidate = directory / f"{source_path.stem}_converted{settings.output_extension}"
    index = 1
    while candidate.exists():
        candidate = directory / f"{source_path.stem}_converted_{index}{settings.output_extension}"
        index += 1
    return candidate


def build_ffmpeg_args(
    settings: ConversionSettings,
    input_path: Path | None,
    output_path: Path,
    report_progress: bool = False,
) -> list[str]:
    """Build ffmpeg arguments without executing a conversion."""
    args = [
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-i",
        str(input_path) if input_path is not None else "<输入文件>",
    ]

    if settings.output_format == "GIF":
        args.extend(
            [
                "-an",
                "-vf",
                "fps=12,scale=-2:720:flags=lanczos",
            ]
        )
    elif settings.output_format in {"MP3", "WAV"}:
        args.append("-vn")
        audio_encoder = AUDIO_ENCODERS[settings.audio_codec]
        args.extend(["-c:a", audio_encoder])
        if settings.audio_codec != "PCM":
            args.extend(["-b:a", _ffmpeg_bitrate(settings.audio_bitrate)])
    else:
        video_encoder = VIDEO_ENCODERS[settings.video_codec]
        args.extend(["-c:v", video_encoder])

        if settings.video_codec in {"H.264", "H.265"}:
            _, preset = QUALITY_DEFAULTS.get(
                settings.quality,
                QUALITY_DEFAULTS["平衡（推荐）"],
            )
            args.extend(["-preset", preset])
        if settings.video_codec in {"H.264", "H.265", "AV1", "VP9"}:
            args.extend(["-crf", str(settings.crf)])
        if settings.output_format == "WebM" and settings.video_codec == "VP9":
            args.extend(["-b:v", "0", "-deadline", "good", "-cpu-used", "2"])

        video_filters: list[str] = []
        if settings.resolution != "保持原始":
            target_height = settings.resolution.removesuffix("p")
            video_filters.append(f"scale=-2:{target_height}")
        if video_filters:
            args.extend(["-vf", ",".join(video_filters)])
        if settings.frame_rate != "保持原始":
            target_fps = settings.frame_rate.removesuffix(" FPS")
            args.extend(["-r", target_fps])

        if settings.keep_audio and settings.audio_codec:
            args.extend(["-c:a", AUDIO_ENCODERS[settings.audio_codec]])
            if settings.audio_codec != "PCM":
                args.extend(["-b:a", _ffmpeg_bitrate(settings.audio_bitrate)])
        else:
            args.append("-an")

        if settings.output_format == "MP4":
            args.extend(["-movflags", "+faststart"])

    if report_progress:
        args.extend(["-progress", "pipe:1", "-nostats"])
    args.append(str(output_path))
    return args


def build_command_preview(
    settings: ConversionSettings,
    input_path: Path | None,
    output_path: Path,
    executable: Path | None = None,
) -> str:
    """Return a readable command preview for the user."""
    executable_name = str(executable) if executable is not None else "ffmpeg"
    args = build_ffmpeg_args(settings, input_path, output_path)
    return subprocess.list2cmdline([executable_name, *args])
