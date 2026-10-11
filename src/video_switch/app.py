"""Application entry point and the initial desktop window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

APP_NAME = "Video Switch"


class MainWindow(QMainWindow):
    """Temporary step-zero window used to verify the desktop runtime."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} - 视频转换器")
        self.resize(1080, 680)
        self.setMinimumSize(860, 560)

        placeholder = QLabel("Video Switch\n项目环境已就绪", self)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet(
            "font-size: 24px; font-weight: 600; color: #334155; background: #f8fafc;"
        )
        self.setCentralWidget(placeholder)


def main() -> None:
    """Create the application and show the initial window."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("VideoSwitch")

    window = MainWindow()
    window.show()
    app.exec()
