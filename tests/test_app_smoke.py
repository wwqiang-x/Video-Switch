"""Smoke tests for the desktop entry point and main interface shell."""

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
