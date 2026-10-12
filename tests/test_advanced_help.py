"""Tests for advanced conversion parameter explanations."""

from PySide6.QtWidgets import QFrame

from video_switch.ui.advanced_help_dialog import (
    ADVANCED_GUIDES,
    AdvancedHelpDialog,
)
from video_switch.ui.main_window import MainWindow


def test_advanced_help_dialog_contains_parameters(qtbot) -> None:
    dialog = AdvancedHelpDialog()
    qtbot.addWidget(dialog)

    cards = dialog.findChildren(QFrame, "FormatCard")

    assert len(ADVANCED_GUIDES) == 5
    assert len(cards) == 5
    assert dialog.windowTitle() == "高级参数说明"


def test_advanced_help_button_opens_dialog(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    help_button = window.advanced_section.help_button

    assert help_button is not None
    assert help_button.text() == ""
    assert help_button.width() == 22
    assert help_button.icon().isNull() is False

    help_button.click()

    assert window.advanced_help_dialog is not None
    assert window.advanced_help_dialog.windowTitle() == "高级参数说明"
