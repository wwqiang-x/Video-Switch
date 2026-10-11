"""Tests for parsing ffprobe JSON into user-facing media information."""

from pathlib import Path

from video_switch.services.media_probe import parse_ffprobe_output

FFPROBE_JSON = """
{
  "streams": [
    {
      "codec_type": "video",
      "codec_name": "h264",
      "width": 1920,
      "height": 1080,
      "avg_frame_rate": "30000/1001",
      "pix_fmt": "yuv420p"
    },
    {
      "codec_type": "audio",
      "codec_name": "aac",
      "sample_rate": "48000",
      "channels": 2
    }
  ],
  "format": {
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "duration": "62.5",
    "bit_rate": "5000000"
  }
}
"""


def test_parse_ffprobe_output() -> None:
    info = parse_ffprobe_output(FFPROBE_JSON, Path("sample.mp4"))

    assert info.duration_text == "01:02"
    assert info.resolution_text == "1920 × 1080"
    assert info.frame_rate_text == "29.97 FPS"
    assert info.video_codec_text == "H264"
    assert info.audio_codec_text == "AAC · 2 声道"
    assert info.bit_rate_text == "5.0 Mbps"
    assert info.container_text == "MP4"
    assert info.pixel_format == "yuv420p"
    assert info.audio_sample_rate == 48000


def test_parse_video_without_audio() -> None:
    output = """
    {
      "streams": [
        {
          "codec_type": "video",
          "codec_name": "vp9",
          "width": 1280,
          "height": 720,
          "r_frame_rate": "30/1"
        }
      ],
      "format": {
        "format_name": "matroska,webm",
        "duration": "5.0"
      }
    }
    """

    info = parse_ffprobe_output(output, Path("sample.webm"))

    assert info.resolution_text == "1280 × 720"
    assert info.frame_rate_text == "30 FPS"
    assert info.audio_codec_text == "无音频"
    assert info.container_text == "WebM"
