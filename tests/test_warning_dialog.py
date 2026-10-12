"""Tests for the themed warning dialogs used by destructive actions."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox

from video_switch.ui.main_window import (
    MESSAGE_ICON_SIZE,
    WARNING_ICON_PATH,
    MainWindow,
)


def test_warning_icon_resource_exists() -> None:
    assert WARNING_ICON_PATH.is_file()


def test_warning_dialog_uses_bundled_icon_and_centered_text(
    qtbot,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    dialog = window._warning_dialog("清空任务", "确定要移除队列中的 2 个任务吗？")
    qtbot.addWidget(dialog)

    label = dialog.findChild(QLabel, "qt_msgbox_label")
    assert label is not None
    assert label.text() == "确定要移除队列中的 2 个任务吗？"
    assert label.minimumHeight() == MESSAGE_ICON_SIZE
    assert label.alignment() & Qt.AlignmentFlag.AlignVCenter
    assert dialog.iconPixmap().isNull() is False


def test_warning_dialog_keeps_buttons_and_informative_text(
    qtbot,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    dialog = window._warning_dialog("删除取消状态", "该任务保留了约 43% 的转换进度。")
    qtbot.addWidget(dialog)
    dialog.setInformativeText("删除后已保留的进度会被清除。")
    delete_button = dialog.addButton("删除进度", QMessageBox.ButtonRole.DestructiveRole)
    cancel_button = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(cancel_button)

    assert dialog.informativeText() == "删除后已保留的进度会被清除。"
    # Qt reorders buttons per platform layout, so only the set is stable.
    assert {button.text() for button in dialog.buttons()} == {"删除进度", "取消"}
    assert dialog.defaultButton() is cancel_button
    assert delete_button is not cancel_button
