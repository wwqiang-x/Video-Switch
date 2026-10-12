"""Output format guide shown from the conversion settings panel."""

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
class FormatGuide:
    """User-facing description of one output format."""

    code: str
    title: str
    summary: str
    use_case: str
    note: str


FORMAT_GUIDES = (
    FormatGuide(
        code="MP4",
        title="通用视频",
        summary="兼容性最好，适合在手机、平板、网页和常见播放器中播放。",
        use_case="发送视频、上传平台、日常保存。",
        note="默认使用 H.264 + AAC，兼顾画质、体积和兼容性。",
    ),
    FormatGuide(
        code="MKV",
        title="多轨视频容器",
        summary="可以封装多条音频、字幕和不同编码的视频流。",
        use_case="本地收藏、影视资源、需要字幕或多音轨的视频。",
        note="兼容性不如 MP4，部分手机和网页播放器支持有限。",
    ),
    FormatGuide(
        code="WebM",
        title="网页视频",
        summary="面向网页播放，通常使用 VP9 或 AV1 视频编码。",
        use_case="网页项目、在线演示、浏览器内播放。",
        note="编码速度可能较慢，部分旧软件不能直接打开。",
    ),
    FormatGuide(
        code="MP3",
        title="通用音频",
        summary="只保留音频，兼容性很高，文件体积较小。",
        use_case="音乐、播客、语音和只需要声音的场景。",
        note="会丢失视频画面，并且属于有损压缩。",
    ),
    FormatGuide(
        code="WAV",
        title="无损音频",
        summary="使用 PCM 音频，音质损失最少，但文件体积明显更大。",
        use_case="音频编辑、后期制作和需要保留原始音质的场景。",
        note="不支持视频画面，不适合直接用于网络传输。",
    ),
    FormatGuide(
        code="GIF",
        title="循环动画",
        summary="生成自动循环播放的动画图片，不包含声音。",
        use_case="聊天表情、简短演示和无声循环动画。",
        note="颜色数量有限，文件可能较大，不适合长视频。",
    ),
)


class FormatHelpDialog(QDialog):
    """Modal card list that explains all supported output formats."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        register_cjk_fonts()
        self.setObjectName("FormatHelpDialog")
        self.setWindowTitle("输出格式说明")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(680, 640)
        self.setMinimumSize(580, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("选择适合的输出格式")
        title.setObjectName("DialogTitle")
        description = QLabel(
            "不同格式适用于不同场景。兼容性、文件大小、编码速度和音视频能力各有取舍。"
        )
        description.setProperty("muted", True)
        description.setWordWrap(True)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(10)
        for guide in FORMAT_GUIDES:
            content_layout.addWidget(self._build_card(guide))
        content_layout.addStretch(1)
        scroll.setWidget(content)

        close_button = QPushButton("知道了")
        close_button.setObjectName("PrimaryAction")
        close_button.clicked.connect(self.accept)
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(close_button)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(scroll, 1)
        layout.addLayout(action_row)

    def _build_card(self, guide: FormatGuide) -> QFrame:
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
        use_case = QLabel(f"适合：{guide.use_case}")
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
