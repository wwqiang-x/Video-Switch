"""Unit tests for FFmpeg command-line tool detection."""

from pathlib import Path

from video_switch.services.toolchain import (
    ToolchainStatus,
    ToolInfo,
    executable_name,
    parse_tool_version,
    resolve_tool,
)
from video_switch.ui.settings_dialog import SettingsDialog


def test_parse_ffmpeg_version() -> None:
    output = "ffmpeg version 8.0.1-essentials_build-www.gyan.dev Copyright"
    assert parse_tool_version("ffmpeg", output) == "8.0.1-essentials_build-www.gyan.dev"
    tool = ToolInfo(
        name="ffmpeg",
        executable=Path("ffmpeg.exe"),
        version="8.0.1-essentials_build-www.gyan.dev",
    )
    assert tool.display_version == "8.0.1"


def test_resolve_tool_from_bundled_directory(tmp_path: Path) -> None:
    executable = tmp_path / "tools" / "ffmpeg" / "bin" / executable_name("ffmpeg")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test")

    resolved, source = resolve_tool("ffmpeg", roots=(tmp_path,))

    assert resolved == executable
    assert source == "应用内置"


def test_missing_toolchain_summary() -> None:
    status = ToolchainStatus(
        ffmpeg=ToolInfo(name="ffmpeg", error="未找到 ffmpeg"),
        ffprobe=ToolInfo(name="ffprobe", error="未找到 ffprobe"),
    )

    assert status.ready is False
    assert status.summary == "未找到 FFmpeg 和 ffprobe，请打开设置"


def test_settings_dialog_can_be_created(qtbot) -> None:
    dialog = SettingsDialog(auto_detect=False)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "FFmpeg 环境设置"
    assert dialog.save_button.isEnabled() is False
