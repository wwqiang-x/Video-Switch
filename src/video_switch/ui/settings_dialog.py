"""FFmpeg environment configuration dialog."""

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from video_switch.services.toolchain import ToolchainDetector, ToolchainStatus
from video_switch.ui.fonts import register_cjk_fonts


class SettingsDialog(QDialog):
    """Configure and validate the local ffmpeg and ffprobe executables."""

    def __init__(
        self,
        ffmpeg_path: str = "",
        ffprobe_path: str = "",
        parent: QWidget | None = None,
        auto_detect: bool = True,
    ) -> None:
        super().__init__(parent)
        register_cjk_fonts()
        self.setWindowTitle("FFmpeg 环境设置")
        self.setModal(True)
        self.resize(620, 350)
        self.setMinimumSize(560, 330)

        self.result_status: ToolchainStatus | None = None
        self.detector = ToolchainDetector(self)
        self.detector.started.connect(self._on_detection_started)
        self.detector.finished.connect(self._on_detection_finished)

        self._build_interface(ffmpeg_path, ffprobe_path)
        if auto_detect:
            QTimer.singleShot(0, self._auto_detect)

    def _build_interface(self, ffmpeg_path: str, ffprobe_path: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title = QLabel("FFmpeg 环境设置")
        title.setObjectName("PanelTitle")
        description = QLabel("应用需要 ffmpeg 和 ffprobe。可以自动检测，也可以手动选择两个程序。")
        description.setProperty("muted", True)
        description.setWordWrap(True)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self.ffmpeg_path = QLineEdit(ffmpeg_path)
        self.ffmpeg_path.setPlaceholderText("未选择 ffmpeg.exe")
        self.ffprobe_path = QLineEdit(ffprobe_path)
        self.ffprobe_path.setPlaceholderText("未选择 ffprobe.exe")

        form.addRow("ffmpeg", self._path_row(self.ffmpeg_path, "ffmpeg"))
        form.addRow("ffprobe", self._path_row(self.ffprobe_path, "ffprobe"))

        self.status_label = QLabel("等待检测")
        self.status_label.setObjectName("ToolStatus")
        self.status_label.setProperty("state", "pending")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(56)

        self.auto_button = QPushButton("自动检测")
        self.auto_button.setObjectName("SecondaryAction")
        self.auto_button.clicked.connect(self._auto_detect)

        self.detect_button = QPushButton("检测当前路径")
        self.detect_button.setObjectName("SecondaryAction")
        self.detect_button.clicked.connect(self._detect_current_paths)

        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("SecondaryAction")
        cancel_button.clicked.connect(self.reject)

        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("PrimaryAction")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.auto_button)
        actions.addWidget(self.detect_button)
        actions.addStretch(1)
        actions.addWidget(cancel_button)
        actions.addWidget(self.save_button)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addLayout(actions)

    def _path_row(self, line_edit: QLineEdit, tool_name: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        choose_button = QToolButton()
        choose_button.setObjectName("IconButton")
        choose_button.setText("…")
        choose_button.setToolTip(f"选择 {tool_name}.exe")
        choose_button.clicked.connect(lambda: self._choose_executable(line_edit, tool_name))

        layout.addWidget(line_edit, 1)
        layout.addWidget(choose_button)
        return row

    def _choose_executable(self, line_edit: QLineEdit, tool_name: str) -> None:
        current = Path(line_edit.text()).parent if line_edit.text() else Path.home()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            f"选择 {tool_name}.exe",
            str(current),
            "可执行程序 (*.exe);;所有文件 (*)",
        )
        if not selected:
            return

        line_edit.setText(selected)
        if tool_name == "ffmpeg" and not self.ffprobe_path.text():
            sibling = Path(selected).with_name("ffprobe.exe")
            if sibling.is_file():
                self.ffprobe_path.setText(str(sibling))
        self._invalidate_status()

    def _auto_detect(self) -> None:
        self.ffmpeg_path.clear()
        self.ffprobe_path.clear()
        self._start_detection()

    def _detect_current_paths(self) -> None:
        self._start_detection()

    def _start_detection(self) -> None:
        self.detector.detect(
            self.ffmpeg_path.text() or None,
            self.ffprobe_path.text() or None,
        )

    def _on_detection_started(self) -> None:
        self._set_controls_enabled(False)
        self.save_button.setEnabled(False)
        self._set_status("正在检测 FFmpeg 环境…", "pending")

    def _on_detection_finished(self, status: ToolchainStatus) -> None:
        self.result_status = status
        self._set_controls_enabled(True)
        self.save_button.setEnabled(status.ready)

        if status.ready:
            self.ffmpeg_path.setText(str(status.ffmpeg.executable))
            self.ffprobe_path.setText(str(status.ffprobe.executable))
            self._set_status(
                "检测成功："
                f"ffmpeg {status.ffmpeg.display_version}，"
                f"ffprobe {status.ffprobe.display_version}",
                "ready",
            )
            return

        errors = [
            tool.error or f"{tool.name} 未就绪"
            for tool in (status.ffmpeg, status.ffprobe)
            if not tool.ready
        ]
        self._set_status("；".join(errors), "error")

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.auto_button.setEnabled(enabled)
        self.detect_button.setEnabled(enabled)
        self.ffmpeg_path.setEnabled(enabled)
        self.ffprobe_path.setEnabled(enabled)

    def _set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _invalidate_status(self) -> None:
        self.result_status = None
        self.save_button.setEnabled(False)
        self._set_status("路径已改变，请重新检测。", "pending")

    def _save(self) -> None:
        if self.result_status is not None and self.result_status.ready:
            self.accept()
