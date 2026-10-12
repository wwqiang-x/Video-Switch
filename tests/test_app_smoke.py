"""Smoke tests for the desktop entry point and main interface shell."""

import time

from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QFont, QPixmap
from PySide6.QtWidgets import QApplication

from video_switch import main
from video_switch.models.media_info import MediaInfo
from video_switch.services.media_probe import ProbeResult
from video_switch.services.thumbnail import ThumbnailResult
from video_switch.ui.fonts import create_application_font
from video_switch.ui.main_window import (
    FILE_ICON_PATH,
    FOLDER_ICON_PATH,
    PLAY_ICON_PATH,
    REFRESH_ICON_PATH,
    SETTINGS_ICON_PATH,
    THEME_ICON_PATH,
    TRASH_ICON_PATH,
    VIDEO_ICON_PATH,
    MainWindow,
    MarqueeLineEdit,
    _tinted_svg_pixmap,
)


def test_main_is_callable() -> None:
    assert callable(main)


def test_main_window_can_be_created(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    assert "Video Switch" in window.windowTitle()
    assert window.minimumWidth() == 1080
    assert window.minimumHeight() == 680


def test_initial_shell_state(qtbot, isolated_settings) -> None:
    assert PLAY_ICON_PATH.is_file()
    assert FILE_ICON_PATH.is_file()
    assert VIDEO_ICON_PATH.is_file()
    assert TRASH_ICON_PATH.is_file()
    assert THEME_ICON_PATH.is_file()
    assert SETTINGS_ICON_PATH.is_file()
    assert FOLDER_ICON_PATH.is_file()
    assert REFRESH_ICON_PATH.is_file()

    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    assert window.add_video_button.text() == "添加视频"
    assert window.add_video_button._icon_pixmap.isNull() is False
    add_icon_size = window.add_video_button._icon_pixmap.deviceIndependentSize()
    assert round(add_icon_size.height()) == window.add_video_button.fontMetrics().height()
    metrics = window.add_video_button.fontMetrics()
    expected_width = max(
        88,
        8
        + metrics.height()
        + 6
        + metrics.horizontalAdvance("添加视频")
        + metrics.horizontalAdvance("添"),
    )
    assert window.add_video_button.sizeHint().width() == expected_width
    assert window.clear_button.width() == 34
    assert window.clear_button.icon().isNull() is False
    assert window.theme_button.icon().isNull() is False
    assert window.settings_button.icon().isNull() is False
    assert window.browse_button.icon().isNull() is False
    assert window.reset_output_button.icon().isNull() is False
    assert window._task_icon().isNull() is False
    assert window.format_buttons["MP4"].isChecked()
    assert window.task_stack.currentIndex() == 0
    assert window.start_button.isEnabled() is False
    assert window.regenerate_thumbnail_button.isHidden() is True
    assert window.regenerate_thumbnail_button.width() == 34
    assert window.regenerate_thumbnail_button.icon().isNull() is False
    assert window.preview_icon.pixmap().isNull() is False
    preview_size = window.preview_icon.pixmap().deviceIndependentSize()
    assert round(preview_size.width()) == 64
    assert window.empty_queue_icon.pixmap().isNull() is False
    queue_size = window.empty_queue_icon.pixmap().deviceIndependentSize()
    assert round(queue_size.width()) == 48
    preview_layout = window.preview_icon.parentWidget().layout()
    icon_item = preview_layout.itemAt(preview_layout.indexOf(window.preview_icon))
    assert icon_item.alignment() & Qt.AlignmentFlag.AlignHCenter
    queue_layout = window.empty_queue_icon.parentWidget().layout()
    queue_icon_item = queue_layout.itemAt(queue_layout.indexOf(window.empty_queue_icon))
    assert queue_icon_item.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert window.media_status.text() == "未选择"


def test_svg_rendering_uses_device_pixel_ratio() -> None:
    pixmap = _tinted_svg_pixmap(
        FILE_ICON_PATH,
        "#000000",
        24,
        device_pixel_ratio=2.0,
    )

    assert pixmap.width() == 48
    assert pixmap.height() == 48
    assert pixmap.devicePixelRatio() == 2.0


def test_application_font_uses_full_hinting() -> None:
    font = create_application_font()

    assert font.family() == "Microsoft YaHei UI"
    assert font.pixelSize() == 13
    assert font.hintingPreference() == QFont.HintingPreference.PreferFullHinting


def test_marquee_line_edit_scrolls_and_resets(qtbot) -> None:
    line = MarqueeLineEdit("很长的输出路径" * 20)
    line.resize(100, 30)
    line.show()
    qtbot.addWidget(line)
    qtbot.wait(10)

    assert line.text().startswith("很长的输出路径")
    assert line._max_offset > 0

    line._offset = 0.0
    line._last_tick = time.monotonic() - 0.1
    line._advance_marquee()

    assert line._offset > 0

    QApplication.sendEvent(line, QEvent(QEvent.Type.Leave))

    assert line._offset == 0.0


def test_importing_video_updates_queue_and_preview(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    video = tmp_path / "sample video.mp4"
    video.write_bytes(b"video")
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    window._import_paths([str(video)])

    assert len(window.tasks) == 1
    assert window.queue_count.text() == "1"
    assert window.task_stack.currentIndex() == 1
    assert window.media_status.text() == "已导入"
    assert window.metric_file_size.value_label.text() == "5 B"
    assert window.source_path.text() == str(video.resolve())


def test_remove_selected_task(qtbot, tmp_path, isolated_settings) -> None:
    video = tmp_path / "remove-me.mov"
    video.write_bytes(b"video")
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window._import_paths([str(video)])

    window._remove_selected_task()

    assert window.tasks == {}
    assert window.task_stack.currentIndex() == 0
    assert window.media_status.text() == "未选择"


def test_drop_event_imports_local_video(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    video = tmp_path / "dropped.webm"
    video.write_bytes(b"video")
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(video))])
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    window.dropEvent(event)

    assert len(window.tasks) == 1
    assert window.source_path.text() == str(video.resolve())


def test_probe_result_updates_selected_task(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    video = tmp_path / "metadata.mp4"
    video.write_bytes(b"video")
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window._import_paths([str(video)])
    task_key = next(iter(window.tasks))
    info = MediaInfo(
        duration_seconds=65,
        width=1920,
        height=1080,
        frame_rate=30,
        video_codec="h264",
        audio_codec="aac",
        audio_channels=2,
        container="MP4",
        bit_rate=3_000_000,
    )

    window._on_task_probe_started(task_key)
    window._on_task_probe_finished(ProbeResult(task_key=task_key, path=video.resolve(), info=info))

    assert window.tasks[task_key].status.value == "已读取"
    assert window.media_status.text() == "信息已读取"
    assert window.metric_duration.value_label.text() == "01:05"
    assert window.metric_resolution.value_label.text() == "1920 × 1080"
    assert window.metric_frame_rate.value_label.text() == "30 FPS"
    assert window.metric_audio_codec.value_label.text() == "AAC · 2 声道"
    assert window.metric_container.value_label.text() == "MP4"


def test_thumbnail_result_updates_preview(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    video = tmp_path / "thumbnail.mp4"
    video.write_bytes(b"video")
    thumbnail = tmp_path / "thumbnail.png"
    pixmap = QPixmap(64, 36)
    pixmap.fill(Qt.GlobalColor.blue)
    assert pixmap.save(str(thumbnail))

    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window._import_paths([str(video)])
    task_key = next(iter(window.tasks))
    window._on_task_thumbnail_started(task_key)
    window._on_task_thumbnail_finished(ThumbnailResult(task_key=task_key, thumbnail_path=thumbnail))

    assert window.thumbnail_label.isHidden() is False
    assert window.thumbnail_label.pixmap().isNull() is False
    assert window.preview_hint.text() == "缩略图已生成"
