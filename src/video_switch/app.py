"""Application entry point."""

from PySide6.QtWidgets import QApplication

from video_switch.ui.main_window import APP_NAME, MainWindow


def main() -> None:
    """Create the application and show the initial window."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("VideoSwitch")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    app.exec()
