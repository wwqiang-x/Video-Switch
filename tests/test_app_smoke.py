"""Step-zero smoke tests for the desktop entry point."""

from video_switch import main
from video_switch.app import MainWindow


def test_main_is_callable() -> None:
    assert callable(main)


def test_main_window_can_be_created(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert "Video Switch" in window.windowTitle()
    assert window.minimumWidth() == 860
    assert window.minimumHeight() == 560
