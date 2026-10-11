"""User-facing conversion configuration."""

from dataclasses import dataclass

VIDEO_CODEC_OPTIONS = {
    "MP4": ("H.264", "H.265", "AV1"),
    "MKV": ("H.264", "H.265", "AV1", "VP9"),
    "WebM": ("VP9", "AV1"),
    "MP3": (),
    "WAV": (),
    "GIF": ("GIF",),
}

AUDIO_CODEC_OPTIONS = {
    "MP4": ("AAC", "MP3", "Opus"),
    "MKV": ("AAC", "MP3", "Opus"),
    "WebM": ("Opus", "Vorbis"),
    "MP3": ("MP3",),
    "WAV": ("PCM",),
    "GIF": (),
}

FORMAT_DEFAULTS = {
    "MP4": ("H.264", "AAC"),
    "MKV": ("H.264", "AAC"),
    "WebM": ("VP9", "Opus"),
    "MP3": ("", "MP3"),
    "WAV": ("", "PCM"),
    "GIF": ("GIF", ""),
}

OUTPUT_EXTENSIONS = {
    "MP4": ".mp4",
    "MKV": ".mkv",
    "WebM": ".webm",
    "MP3": ".mp3",
    "WAV": ".wav",
    "GIF": ".gif",
}


@dataclass(frozen=True, slots=True)
class ConversionSettings:
    """Complete conversion settings used by the command builder."""

    output_format: str = "MP4"
    quality: str = "平衡（推荐）"
    resolution: str = "保持原始"
    frame_rate: str = "保持原始"
    video_codec: str = "H.264"
    audio_codec: str = "AAC"
    audio_bitrate: str = "192 kbps"
    crf: int = 23
    keep_audio: bool = True

    @property
    def output_extension(self) -> str:
        return OUTPUT_EXTENSIONS.get(self.output_format, ".mp4")
