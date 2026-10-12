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

ENCODING_SPEED_FACTORS = {
    "H.264": 6.0,
    "H.265": 2.5,
    "AV1": 0.8,
    "VP9": 0.8,
    "GIF": 1.5,
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
    start_seconds: float | None = None,
    segment_duration: float | None = None,
) -> list[str]:
    """Build ffmpeg arguments without executing a conversion."""
    args = [
        "-hide_banner",
        "-loglevel",
        "warning",
    ]
    if start_seconds is not None:
        args.extend(["-ss", f"{start_seconds:.3f}"])
    args.extend(
        [
            "-y",
            "-i",
            str(input_path) if input_path is not None else "<输入文件>",
        ]
    )
    if segment_duration is not None:
        args.extend(["-t", f"{segment_duration:.3f}"])

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


def estimate_conversion_seconds(
    settings: ConversionSettings,
    duration_seconds: float | None,
    source_width: int | None = None,
    source_height: int | None = None,
    source_frame_rate: float | None = None,
) -> float | None:
    """Estimate conversion time using format and workload factors."""
    if not duration_seconds or duration_seconds <= 0:
        return None
    del source_width

    if settings.output_format in {"MP3", "WAV"}:
        encoding_speed = 25.0
    else:
        encoding_speed = ENCODING_SPEED_FACTORS.get(
            settings.video_codec,
            3.0,
        )

    if settings.resolution != "保持原始" and source_height:
        target_height = int(settings.resolution.removesuffix("p"))
        scale_factor = max(0.1, target_height / source_height)
        encoding_speed /= max(0.1, scale_factor * scale_factor)

    if settings.frame_rate != "保持原始" and source_frame_rate:
        target_frame_rate = float(settings.frame_rate.removesuffix(" FPS"))
        frame_rate_factor = max(0.1, target_frame_rate / source_frame_rate)
        encoding_speed /= frame_rate_factor

    return max(1.0, duration_seconds / max(0.1, encoding_speed))
