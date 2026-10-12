"""Dialogs for picking the videos and confirming the settings of a batch run."""

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from video_switch.ui.fonts import register_cjk_fonts


@dataclass(frozen=True, slots=True)
class BatchCandidate:
    """One queued video offered for batch conversion."""

    task_key: str
    name: str
    detail: str
    checked: bool = True
    reason: str = ""

    @property
    def selectable(self) -> bool:
        return not self.reason


class BatchSelectionDialog(QDialog):
    """Modal list that lets the user tick which videos a batch run converts."""

    def __init__(
        self,
        candidates: Sequence[BatchCandidate],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        register_cjk_fonts()
        self.setObjectName("HelpCardDialog")
        self.setWindowTitle("批量转换")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(560, 520)
        self.setMinimumSize(480, 400)
        self._checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("选择要批量转换的视频")
        title.setObjectName("DialogTitle")
        description = QLabel(
            "勾选需要转换的视频后点击“下一步”。已完成的视频默认不勾选，可以手动选上重新转换。"
        )
        description.setProperty("muted", True)
        description.setWordWrap(True)

        self.select_all_box = QCheckBox("全选")
        self.select_all_box.stateChanged.connect(self._on_select_all)
        self.selection_label = QLabel()
        self.selection_label.setProperty("muted", True)
        heading = QHBoxLayout()
        heading.addWidget(self.select_all_box)
        heading.addStretch(1)
        heading.addWidget(self.selection_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(8)
        for candidate in candidates:
            content_layout.addWidget(self._build_row(candidate))
        content_layout.addStretch(1)
        scroll.setWidget(content)

        self.next_button = QPushButton("下一步")
        self.next_button.setObjectName("PrimaryAction")
        self.next_button.clicked.connect(self.accept)
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("SecondaryAction")
        cancel_button.clicked.connect(self.reject)
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(cancel_button)
        action_row.addWidget(self.next_button)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addLayout(heading)
        layout.addWidget(scroll, 1)
        layout.addLayout(action_row)
        self._refresh_summary()

    def _build_row(self, candidate: BatchCandidate) -> QFrame:
        row = QFrame()
        row.setObjectName("FormatCard")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 10, 12, 10)
        row_layout.setSpacing(10)

        check = QCheckBox(candidate.name)
        check.setChecked(candidate.checked and candidate.selectable)
        check.setEnabled(candidate.selectable)
        check.stateChanged.connect(self._refresh_summary)
        self._checkboxes[candidate.task_key] = check

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        if candidate.reason:
            hint = QLabel(candidate.reason)
            hint.setProperty("muted", True)
            hint.setWordWrap(True)
            text_layout.addWidget(hint)
        detail = QLabel(candidate.detail)
        detail.setProperty("muted", True)
        detail.setWordWrap(True)
        text_layout.addWidget(detail)

        row_layout.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)
        row_layout.addLayout(text_layout, 1)
        return row

    def _on_select_all(self, state: int) -> None:
        target = state == Qt.CheckState.Checked.value
        for check in self._checkboxes.values():
            if check.isEnabled():
                check.setChecked(target)

    def _refresh_summary(self) -> None:
        selectable = [check for check in self._checkboxes.values() if check.isEnabled()]
        chosen = [check for check in selectable if check.isChecked()]
        self.selection_label.setText(f"已选择 {len(chosen)}/{len(selectable)}")
        self.next_button.setEnabled(bool(chosen))
        self.select_all_box.blockSignals(True)
        self.select_all_box.setChecked(bool(selectable) and len(chosen) == len(selectable))
        self.select_all_box.blockSignals(False)

    @property
    def selected_keys(self) -> list[str]:
        return [
            task_key
            for task_key, check in self._checkboxes.items()
            if check.isEnabled() and check.isChecked()
        ]


class BatchConfirmDialog(QDialog):
    """Modal summary of the settings a batch run is about to apply."""

    def __init__(
        self,
        count: int,
        settings_rows: Sequence[tuple[str, str]],
        output_directory: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        register_cjk_fonts()
        self.setObjectName("HelpCardDialog")
        self.setWindowTitle("确认批量转换")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(520, 520)
        self.setMinimumSize(440, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel(f"确认转换 {count} 个视频")
        title.setObjectName("DialogTitle")
        description = QLabel("以下设置会应用到本次批量转换的全部视频。")
        description.setProperty("muted", True)
        description.setWordWrap(True)

        card = QFrame()
        card.setObjectName("FormatCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        rows = [*settings_rows, ("输出目录", output_directory)]
        for row, (caption_text, value_text) in enumerate(rows):
            caption = QLabel(caption_text)
            caption.setProperty("muted", True)
            value = QLabel(value_text)
            value.setWordWrap(True)
            grid.addWidget(caption, row, 0)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)

        self.start_button = QPushButton("开始转换")
        self.start_button.setObjectName("PrimaryAction")
        self.start_button.clicked.connect(self.accept)
        back_button = QPushButton("返回重选")
        back_button.setObjectName("SecondaryAction")
        back_button.clicked.connect(self.reject)
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(back_button)
        action_row.addWidget(self.start_button)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(card)
        layout.addStretch(1)
        layout.addLayout(action_row)
