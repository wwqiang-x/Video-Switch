"""Reusable help-card dialog used by settings explanations."""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from video_switch.ui.fonts import register_cjk_fonts


@dataclass(frozen=True, slots=True)
class HelpCard:
    """One explanation card shown in a help dialog."""

    code: str
    title: str
    summary: str
    use_case: str
    note: str
    action_label: str = "适合"


class HelpCardDialog(QDialog):
    """Scrollable modal containing a list of explanation cards."""

    def __init__(
        self,
        window_title: str,
        heading: str,
        description: str,
        cards: tuple[HelpCard, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        register_cjk_fonts()
        self.setObjectName("HelpCardDialog")
        self.setWindowTitle(window_title)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(680, 640)
        self.setMinimumSize(580, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel(heading)
        title.setObjectName("DialogTitle")
        description_label = QLabel(description)
        description_label.setProperty("muted", True)
        description_label.setWordWrap(True)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(10)
        for card in cards:
            content_layout.addWidget(self._build_card(card))
        content_layout.addStretch(1)
        scroll.setWidget(content)

        close_button = QPushButton("关闭")
        close_button.setObjectName("PrimaryAction")
        close_button.clicked.connect(self.accept)
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(close_button)

        layout.addWidget(title)
        layout.addWidget(description_label)
        layout.addWidget(scroll, 1)
        layout.addLayout(action_row)

    def _build_card(self, guide: HelpCard) -> QFrame:
        card = QFrame()
        card.setObjectName("FormatCard")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(14)

        badge = QLabel(guide.code)
        badge.setObjectName("FormatBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(70, 34)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        card_title = QLabel(guide.title)
        card_title.setObjectName("FormatCardTitle")
        summary = QLabel(guide.summary)
        summary.setProperty("muted", True)
        summary.setWordWrap(True)
        use_case = QLabel(f"{guide.action_label}：{guide.use_case}")
        use_case.setObjectName("FormatUseCase")
        use_case.setWordWrap(True)
        note = QLabel(f"注意：{guide.note}")
        note.setObjectName("FormatNote")
        note.setWordWrap(True)

        text_layout.addWidget(card_title)
        text_layout.addWidget(summary)
        text_layout.addWidget(use_case)
        text_layout.addWidget(note)

        card_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(text_layout, 1)
        return card
