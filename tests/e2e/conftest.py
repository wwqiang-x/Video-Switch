"""Fixtures for the end-to-end tests that need a real FFmpeg build.

Every test in this folder is skipped automatically when no FFmpeg is available,
so `uv run pytest` stays green on a machine without the bundled tools.
"""

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN_DIRS = (ROOT / ".tools" / "ffmpeg" / "bin",)


def _find_tool(name: str) -> Path | None:
    filename = f"{name}.exe" if os.name == "nt" else name
    for directory in BIN_DIRS:
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    return Path(found) if found else None


@pytest.fixture(scope="session")
def ffmpeg_path() -> Path:
    """Path to a usable ffmpeg, or skip the test."""
    path = _find_tool("ffmpeg")
    if path is None:
        pytest.skip("本机没有可用的 ffmpeg，跳过端到端测试")
    return path


@pytest.fixture(scope="session")
def ffprobe_path() -> Path:
    """Path to a usable ffprobe, or skip the test."""
    path = _find_tool("ffprobe")
    if path is None:
        pytest.skip("本机没有可用的 ffprobe，跳过端到端测试")
    return path


@pytest.fixture
def make_clip(ffmpeg_path: Path) -> Callable[..., Path]:
    """Return a factory that renders a small test clip with real FFmpeg."""

    def build(
        path: Path,
        seconds: float,
        size: str = "320x240",
        rate: int = 15,
        audio: bool = True,
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate={rate}",
        ]
        if audio:
            command += [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100",
            ]
        command += [
            "-t",
            f"{seconds:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
        ]
        if audio:
            command += ["-c:a", "aac", "-shortest"]
        command.append(str(path))
        subprocess.run(command, check=True, capture_output=True)
        return path

    return build


def media_duration(ffprobe_path: Path, path: Path) -> float:
    """Read the container duration of a media file with real ffprobe."""
    result = subprocess.run(
        [
            str(ffprobe_path),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


@pytest.fixture
def duration_of(ffprobe_path: Path) -> Callable[[Path], float]:
    """Return a helper that reads the duration of a produced file."""

    def read(path: Path) -> float:
        return media_duration(ffprobe_path, path)

    return read
