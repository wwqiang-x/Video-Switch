"""Structured media metadata returned by ffprobe."""

from dataclasses import dataclass

from video_switch.formatting import format_duration


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """User-facing metadata for one media file."""

    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    pixel_format: str | None = None
    container: str | None = None
    bit_rate: int | None = None

    @property
    def duration_text(self) -> str:
        return format_duration(self.duration_seconds)

    @property
    def resolution_text(self) -> str:
        if self.width is None or self.height is None:
            return "--"
        return f"{self.width} × {self.height}"

    @property
    def frame_rate_text(self) -> str:
        if self.frame_rate is None:
            return "--"
        return f"{self.frame_rate:.2f}".rstrip("0").rstrip(".") + " FPS"

    @property
    def video_codec_text(self) -> str:
        return self.video_codec.upper() if self.video_codec else "--"

    @property
    def audio_codec_text(self) -> str:
        if not self.audio_codec:
            return "无音频"
        codec = self.audio_codec.upper()
        if self.audio_channels:
            return f"{codec} · {self.audio_channels} 声道"
        return codec

    @property
    def bit_rate_text(self) -> str:
        if not self.bit_rate:
            return "--"
        if self.bit_rate >= 1_000_000:
            return f"{self.bit_rate / 1_000_000:.1f} Mbps"
        return f"{self.bit_rate / 1_000:.0f} kbps"

    @property
    def container_text(self) -> str:
        return self.container or "--"
