"""Application entry point."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from video_switch.ui.fonts import create_application_font
from video_switch.ui.main_window import APP_ICON_PATH, APP_NAME, MainWindow


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

    window = MainWindow()
    window.show()
    app.exec()
