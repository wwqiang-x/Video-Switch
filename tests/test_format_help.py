"""Tests for the output format explanation dialog."""

from PySide6.QtWidgets import QFrame

from video_switch.ui.format_help_dialog import FORMAT_GUIDES, FormatHelpDialog
from video_switch.ui.main_window import QUESTION_ICON_PATH, MainWindow


def test_format_help_dialog_contains_all_formats(qtbot) -> None:
    assert QUESTION_ICON_PATH.is_file()

    dialog = FormatHelpDialog()
    qtbot.addWidget(dialog)

    cards = dialog.findChildren(QFrame, "FormatCard")

    assert len(FORMAT_GUIDES) == 6
    assert len(cards) == 6
    assert dialog.windowTitle() == "输出格式说明"


def test_format_help_button_opens_dialog(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    assert window.format_help_button.text() == ""
    assert window.format_help_button.width() == 22
    assert window.format_help_button.icon().isNull() is False

    window.format_help_button.click()

    assert window.format_help_dialog is not None
    assert window.format_help_dialog.windowTitle() == "输出格式说明"
