"""Tests for step 10 batch three: contrast, history rows, fade, throttle, guide."""

from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMessageBox

from video_switch.models.conversion_history import ConversionHistoryRecord
from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import TaskStatus
from video_switch.services.conversion_runner import ConversionProgress
from video_switch.services.history_store import ConversionHistoryStore
from video_switch.services.toolchain import ToolchainStatus, ToolInfo
from video_switch.ui.main_window import (
    PROGRESS_UI_INTERVAL_MS,
    MainWindow,
)
from video_switch.ui.theme import get_palette


def _luminance(color: str) -> float:
    value = color.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _window(qtbot, tmp_path, isolated_settings, count: int = 1):
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    sources = []
    for index in range(count):
        video = tmp_path / f"clip_{index}.mp4"
        video.write_bytes(f"video {index}".encode())
        sources.append(video)
    window._import_paths([str(path) for path in sources], show_feedback=False)
    tasks = window._tasks_in_list_order()
    for task in tasks:
        task.media_info = MediaInfo(duration_seconds=90.0, width=1280, height=720)
        task.status = TaskStatus.METADATA_READY
        window._update_task_item(task)
    window._available_ffmpeg_path = lambda: Path("ffmpeg.exe")
    return window, tasks


def test_text_colours_reach_the_contrast_threshold() -> None:
    for theme in ("light", "dark"):
        palette = get_palette(theme)
        backgrounds = (palette.surface, palette.surface_alt, palette.primary_soft)
        foregrounds = (
            palette.text,
            palette.muted,
            palette.primary,
            palette.success,
            palette.warning,
            palette.danger,
        )
        for background in backgrounds:
            for foreground in foregrounds:
                assert _contrast(foreground, background) >= 4.5, (
                    theme,
                    foreground,
                    background,
                )


def test_history_rows_stay_compact(qtbot, tmp_path, isolated_settings) -> None:
    window, tasks = _window(qtbot, tmp_path, isolated_settings)
    output = tmp_path / "converted" / "clip_0_converted.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"out")
    window.history_records = [
        ConversionHistoryRecord(
            record_id="r1",
            timestamp="2026-10-13T13:09:00+08:00",
            source_key=tasks[0].content_signature,
            source_path=tasks[0].path,
            output_path=output,
            output_format="MP4",
            status="已完成",
            error=None,
            file_size=1024,
            elapsed_seconds=12.0,
        )
    ]

    window._refresh_history_list()

    item = window.history_list.item(0)
    lines = item.text().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("MP4")
    assert "耗时 00:12" in lines[1]
    assert str(output.parent) in item.toolTip()


def test_thumbnail_fades_in(qtbot, tmp_path, isolated_settings) -> None:
    window, _tasks = _window(qtbot, tmp_path, isolated_settings)
    pixmap = QPixmap(64, 36)
    pixmap.fill()

    window.thumbnail_label.set_source_pixmap(pixmap)

    effect = window.thumbnail_label._fade_effect
    assert window.thumbnail_label._fade.state() != window.thumbnail_label._fade.State.Stopped
    qtbot.waitUntil(lambda: effect.opacity() >= 1.0, timeout=3000)

    window.thumbnail_label.clear_source_pixmap()
    assert effect.opacity() == 1.0


def test_progress_updates_are_throttled(qtbot, tmp_path, isolated_settings) -> None:
    window, tasks = _window(qtbot, tmp_path, isolated_settings)
    task = tasks[0]
    task.status = TaskStatus.CONVERTING
    updates: list[int] = []
    original = window._update_task_item
    window._update_task_item = lambda changed: (updates.append(1), original(changed))[1]

    window._on_conversion_progress(
        ConversionProgress(
            task_key=task.key, percent=10.0, processed_seconds=9.0, speed="1x", eta_seconds=5.0
        )
    )
    for percent in (20.0, 30.0, 40.0, 50.0):
        window._on_conversion_progress(
            ConversionProgress(
                task_key=task.key,
                percent=percent,
                processed_seconds=percent,
                speed="1x",
                eta_seconds=1.0,
            )
        )

    assert task.conversion_progress == 50.0
    assert len(updates) == 1
    assert PROGRESS_UI_INTERVAL_MS > 0


def test_icon_buttons_expose_an_accessible_name(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    for button in (
        window.clear_button,
        window.theme_button,
        window.settings_button,
        window.browse_button,
        window.reset_output_button,
        window.regenerate_thumbnail_button,
        window.clear_state_button,
    ):
        assert button.accessibleName()
        assert button.accessibleName() == button.toolTip()


def test_first_run_guide_shows_once_without_ffmpeg(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    status = ToolchainStatus(
        ffmpeg=ToolInfo(name="ffmpeg", error="未找到 ffmpeg"),
        ffprobe=ToolInfo(name="ffprobe", error="未找到 ffprobe"),
    )

    window._maybe_show_toolchain_guide(status)

    dialogs = window.findChildren(QMessageBox)
    assert len(dialogs) == 1
    assert {"打开设置", "稍后再说"} <= {button.text() for button in dialogs[0].buttons()}
    assert bool(isolated_settings.value("ui/ffmpeg_guide_shown", False)) is True

    window._maybe_show_toolchain_guide(status)
    assert len(window.findChildren(QMessageBox)) == 1

    window._maybe_show_toolchain_guide(
        ToolchainStatus(
            ffmpeg=ToolInfo(name="ffmpeg", executable=Path("ffmpeg.exe"), version="6.0"),
            ffprobe=ToolInfo(name="ffprobe", executable=Path("ffprobe.exe"), version="6.0"),
        )
    )
    assert len(window.findChildren(QMessageBox)) == 1
