"""Smoke tests for the desktop entry point and main interface shell."""

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QPixmap

from video_switch import main
from video_switch.models.media_info import MediaInfo
from video_switch.services.media_probe import ProbeResult
from video_switch.services.thumbnail import ThumbnailResult
from video_switch.ui.main_window import PLAY_ICON_PATH, MainWindow


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

    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    assert window.add_video_button.text() == "添加视频"
    assert window.format_buttons["MP4"].isChecked()
    assert window.task_stack.currentIndex() == 0
    assert window.start_button.isEnabled() is False
    assert window.regenerate_thumbnail_button.isHidden() is True
    assert window.preview_icon.pixmap().isNull() is False
    assert window.preview_icon.pixmap().width() == 64
    preview_layout = window.preview_icon.parentWidget().layout()
    icon_item = preview_layout.itemAt(preview_layout.indexOf(window.preview_icon))
    assert icon_item.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert window.media_status.text() == "未选择"


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
