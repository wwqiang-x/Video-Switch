"""Smoke tests for the desktop entry point and main interface shell."""

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from video_switch import main
from video_switch.ui.main_window import MainWindow


def test_main_is_callable() -> None:
    assert callable(main)


def test_main_window_can_be_created(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert "Video Switch" in window.windowTitle()
    assert window.minimumWidth() == 1080
    assert window.minimumHeight() == 680


def test_initial_shell_state(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.add_video_button.text() == "添加视频"
    assert window.format_buttons["MP4"].isChecked()
    assert window.task_stack.currentIndex() == 0
    assert window.start_button.isEnabled() is False
    assert window.media_status.text() == "未选择"


def test_importing_video_updates_queue_and_preview(qtbot, tmp_path) -> None:
    video = tmp_path / "sample video.mp4"
    video.write_bytes(b"video")
    window = MainWindow()
    qtbot.addWidget(window)

    window._import_paths([str(video)])

    assert len(window.tasks) == 1
    assert window.queue_count.text() == "1"
    assert window.task_stack.currentIndex() == 1
    assert window.media_status.text() == "已导入"
    assert window.metric_file_size.value_label.text() == "5 B"
    assert window.source_path.text() == str(video.resolve())


def test_remove_selected_task(qtbot, tmp_path) -> None:
    video = tmp_path / "remove-me.mov"
    video.write_bytes(b"video")
    window = MainWindow()
    qtbot.addWidget(window)
    window._import_paths([str(video)])

    window._remove_selected_task()

    assert window.tasks == {}
    assert window.task_stack.currentIndex() == 0
    assert window.media_status.text() == "未选择"


def test_drop_event_imports_local_video(qtbot, tmp_path) -> None:
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
    window = MainWindow()
    qtbot.addWidget(window)

    window.dropEvent(event)

    assert len(window.tasks) == 1
    assert window.source_path.text() == str(video.resolve())
