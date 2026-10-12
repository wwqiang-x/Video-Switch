"""Application entry point."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from video_switch.services.crash_handler import install_exception_hook
from video_switch.ui.fonts import create_application_font
from video_switch.ui.main_window import APP_ICON_PATH, APP_NAME, MainWindow


def _show_log_dialog(log_path: str) -> None:
    """Tell the user where an unexpected error was written."""
    dialog = QMessageBox()
    dialog.setWindowTitle("程序遇到未预期的错误")
    dialog.setIcon(QMessageBox.Icon.Critical)
    dialog.setText("Video Switch 刚刚遇到一个未预期的错误，部分功能可能受影响。")
    dialog.setInformativeText(f"详细信息已经记录到日志文件：\n{log_path}")
    open_button = dialog.addButton("打开日志所在目录", QMessageBox.ButtonRole.AcceptRole)
    dialog.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
    dialog.exec()
    if dialog.clickedButton() is open_button:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(log_path).parent)))


def _notify_unexpected_error(log_path: str) -> None:
    """Defer the notice so it never runs inside the failing call stack."""
    QTimer.singleShot(0, lambda: _show_log_dialog(log_path))


def main() -> None:
    """Create the application and show the initial window."""
    app = QApplication.instance()
    if app is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication([])
    app.setFont(create_application_font())
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("VideoSwitch")
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    app.setStyle("Fusion")
    install_exception_hook(_notify_unexpected_error)

    window = MainWindow()
    window.show()
    app.exec()
