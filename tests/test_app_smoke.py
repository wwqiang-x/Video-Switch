"""Smoke tests for the desktop entry point and main interface shell."""

import time

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QFont, QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from video_switch import main
from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import TaskStatus
from video_switch.services.conversion_runner import ConversionResult
from video_switch.services.history_store import ConversionHistoryStore
from video_switch.services.media_probe import ProbeResult
from video_switch.services.thumbnail import ThumbnailResult
from video_switch.ui.fonts import create_application_font
from video_switch.ui.main_window import (
    APP_ICON_PATH,
    FILE_ICON_PATH,
    FOLDER_ICON_PATH,
    PLAY_ICON_PATH,
    REFRESH_ICON_PATH,
    RUN_ICON_PATH,
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
    assert APP_ICON_PATH.is_file()
    assert RUN_ICON_PATH.is_file()

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
    assert window.windowIcon().isNull() is False
    assert window.format_buttons["MP4"].isChecked()
    assert window.task_stack.currentIndex() == 0
    assert window.start_button.isEnabled() is False
    assert window.start_button._icon_pixmap.isNull() is False
    start_icon_size = window.start_button._icon_pixmap.deviceIndependentSize()
    assert round(start_icon_size.height()) == window.start_button.fontMetrics().height()
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


def test_mouse_wheel_does_not_change_settings(
    qtbot,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    original_index = window.quality_combo.currentIndex()
    wheel_event = QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )

    handled = window.eventFilter(window.quality_combo, wheel_event)

    assert handled is True
    assert window.quality_combo.currentIndex() == original_index


def test_settings_panel_does_not_clip_horizontally(
    qtbot,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    window.resize(1080, 680)
    window.output_name_preview.setText("输出：8ccf8ecc40068d1c758c624387187ba4_converted.mp4")
    window.output_path.setText("D:/very/long/output/directory/8ccf8ecc40068d1c758c624387187ba4")
    window.show()
    qtbot.addWidget(window)
    qtbot.wait(20)

    assert (
        window.settings_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert window.settings_scroll.horizontalScrollBar().maximum() == 0
    assert all(button.width() > 0 for button in window.format_buttons.values())


def test_unsupported_import_shows_warning_dialog(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("not a video", encoding="utf-8")
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    captured: dict[str, str] = {}

    def fake_exec(dialog: QMessageBox) -> int:
        captured["title"] = dialog.windowTitle()
        captured["text"] = dialog.text()
        captured["details"] = dialog.detailedText()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    window._import_paths([str(unsupported)], show_issue_dialog=True)

    assert captured["title"] == "文件未导入"
    assert "没有可导入的视频" in captured["text"]
    assert "notes.txt" in captured["details"]
    assert "不支持该文件格式" in captured["details"]


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


def test_conversion_history_record_is_added(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    source = tmp_path / "history-source.mp4"
    output = tmp_path / "converted" / "history-source_converted.mkv"
    output.parent.mkdir()
    source.write_bytes(b"video")
    output.write_bytes(b"converted")
    window = MainWindow(settings=isolated_settings)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    qtbot.addWidget(window)
    window._import_paths([str(source)])
    task = next(iter(window.tasks.values()))

    window._record_conversion_history(
        ConversionResult(
            task_key="task",
            source_key=task.content_signature,
            source_path=source,
            output_format="MKV",
            output_path=output,
            success=True,
            cancelled=False,
            error=None,
            log="",
            elapsed_seconds=1.5,
        )
    )

    assert len(window.history_records) == 1
    assert window.history_list.count() == 1
    item = window.history_list.item(0)
    assert "MKV" in item.text()
    assert str(output.parent) in item.text()
    assert "转换耗时" in item.text()


def test_removing_task_can_delete_associated_history(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    source = tmp_path / "remove-with-history.mp4"
    output = tmp_path / "converted" / "remove-with-history.mp4"
    output.parent.mkdir()
    source.write_bytes(b"video")
    output.write_bytes(b"converted")
    window = MainWindow(settings=isolated_settings)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    qtbot.addWidget(window)
    window._import_paths([str(source)])
    task = next(iter(window.tasks.values()))
    window._record_conversion_history(
        ConversionResult(
            task_key=task.key,
            source_key=task.content_signature,
            source_path=source,
            output_format="MP4",
            output_path=output,
            success=True,
            cancelled=False,
            error=None,
            log="",
            elapsed_seconds=1.0,
        )
    )
    monkeypatch.setattr(
        window,
        "_ask_history_delete",
        lambda count, subject: "delete",
    )

    window._remove_selected_task()

    assert window.tasks == {}
    assert window.history_records == []
    assert window.history_list.count() == 0


def test_history_list_only_shows_selected_source(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    source_a = tmp_path / "source-a.mp4"
    source_b = tmp_path / "source-b.mp4"
    source_a.write_bytes(b"video-a")
    source_b.write_bytes(b"video-b")
    output_a = tmp_path / "source-a_converted.mp4"
    output_b = tmp_path / "source-b_converted.mp4"
    output_a.write_bytes(b"a")
    output_b.write_bytes(b"b")
    window = MainWindow(settings=isolated_settings)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    qtbot.addWidget(window)
    window._import_paths([str(source_a), str(source_b)])
    tasks = list(window.tasks.values())
    window.task_list.setCurrentRow(0)
    window._record_conversion_history(
        ConversionResult(
            task_key=tasks[0].key,
            source_key=tasks[0].content_signature,
            source_path=tasks[0].path,
            output_format="MP4",
            output_path=output_a,
            success=True,
            cancelled=False,
            error=None,
            log="",
            elapsed_seconds=1.0,
        )
    )
    window._record_conversion_history(
        ConversionResult(
            task_key=tasks[1].key,
            source_key=tasks[1].content_signature,
            source_path=tasks[1].path,
            output_format="WebM",
            output_path=output_b,
            success=True,
            cancelled=False,
            error=None,
            log="",
            elapsed_seconds=1.0,
        )
    )

    assert window.history_list.count() == 1
    assert "MP4" in window.history_list.item(0).text()

    window.task_list.setCurrentRow(1)

    assert window.history_list.count() == 1
    assert "WebM" in window.history_list.item(0).text()


def test_cancelled_conversion_shows_resume_button(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    source = tmp_path / "resume.mp4"
    output = tmp_path / "resume_converted.mp4"
    source.write_bytes(b"video")
    window = MainWindow(settings=isolated_settings)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    qtbot.addWidget(window)
    window._import_paths([str(source)])
    task = next(iter(window.tasks.values()))
    window._on_conversion_started(task.key, output)
    window._on_conversion_finished(
        ConversionResult(
            task_key=task.key,
            source_key=task.content_signature,
            source_path=source,
            output_format="MP4",
            output_path=output,
            success=False,
            cancelled=True,
            error="转换已取消",
            log="",
            elapsed_seconds=1.0,
        )
    )
    resumed: list[bool] = []
    monkeypatch.setattr(
        window,
        "_start_conversion",
        lambda: resumed.append(True),
    )

    assert window.resume_conversion_button.isHidden() is False

    window.resume_conversion_button.click()

    assert resumed == [True]
    assert task.status == TaskStatus.METADATA_READY
