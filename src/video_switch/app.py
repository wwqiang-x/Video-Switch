"""Application entry point."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from video_switch.ui.main_window import APP_NAME, MainWindow


def main() -> None:
    """Create the application and show the initial window."""
    app = QApplication.instance()
    if app is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("VideoSwitch")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    app.exec()
