"""Main desktop window and step-one interface shell."""

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from video_switch.ui.fonts import register_cjk_fonts
from video_switch.ui.theme import ThemePalette, build_stylesheet, get_palette

APP_NAME = "Video Switch"


def _icon(widget: QWidget, pixmap: QStyle.StandardPixmap) -> QIcon:
    """Return a platform-standard icon matching the current Qt style."""
    return widget.style().standardIcon(pixmap)


def _colored_icon(
    widget: QWidget,
    pixmap: QStyle.StandardPixmap,
    color: str,
    size: int = 18,
) -> QIcon:
    """Tint a standard Qt icon so it remains visible in both themes."""
    source = _icon(widget, pixmap).pixmap(size, size)
    tinted = QPixmap(source.size())
    tinted.fill(Qt.GlobalColor.transparent)

    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    return QIcon(tinted)


def _panel() -> tuple[QFrame, QVBoxLayout]:
    """Create a top-level panel with consistent spacing."""
    panel = QFrame()
    panel.setProperty("panel", True)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    return panel, layout


class MetricItem(QWidget):
    """A compact label and value pair used by the media information area."""

    def __init__(self, label: str, value: str = "--") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        caption = QLabel(label)
        caption.setProperty("muted", True)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")

        layout.addWidget(caption)
        layout.addWidget(self.value_label)


class CollapsibleSection(QWidget):
    """A lightweight expandable settings section."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.toggle = QToolButton()
        self.toggle.setObjectName("SectionToggle")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)

        self.content = QWidget()
        self.content_layout = QGridLayout(self.content)
        self.content_layout.setContentsMargins(0, 4, 0, 0)
        self.content_layout.setHorizontalSpacing(10)
        self.content_layout.setVerticalSpacing(10)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)

        self.toggle.toggled.connect(self._set_expanded)
        self._set_expanded(False)

    def _set_expanded(self, expanded: bool) -> None:
        arrow = Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        self.toggle.setArrowType(arrow)
        self.content.setVisible(expanded)


class MainWindow(QMainWindow):
    """Primary window for the video conversion workflow."""

    def __init__(self) -> None:
        super().__init__()
        register_cjk_fonts()
        self.settings = QSettings("VideoSwitch", "Video Switch")
        self.theme_name = str(self.settings.value("ui/theme", "light"))

        self.setWindowTitle(f"{APP_NAME} - 视频转换器")
        self.resize(1280, 800)
        self.setMinimumSize(1080, 680)

        self._build_interface()
        self._apply_theme()

    def _build_interface(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header())

        splitter = QWidget()
        splitter_layout = QHBoxLayout(splitter)
        splitter_layout.setContentsMargins(16, 16, 16, 16)
        splitter_layout.setSpacing(12)

        queue_panel, queue_layout = _panel()
        queue_layout.addWidget(self._build_queue_panel())
        queue_panel.setMinimumWidth(250)
        queue_panel.setMaximumWidth(330)

        preview_panel, preview_layout = _panel()
        preview_layout.addWidget(self._build_preview_panel())
        preview_panel.setMinimumWidth(430)

        settings_panel, settings_layout = _panel()
        settings_layout.addWidget(self._build_settings_panel())
        settings_panel.setMinimumWidth(310)
        settings_panel.setMaximumWidth(390)

        splitter_layout.addWidget(queue_panel, 0)
        splitter_layout.addWidget(preview_panel, 1)
        splitter_layout.addWidget(settings_panel, 0)
        root_layout.addWidget(splitter, 1)
        root_layout.addWidget(self._build_footer())

        self.setCentralWidget(root)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(72)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(12)

        brand_mark = QLabel("VS")
        brand_mark.setObjectName("BrandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(40, 40)

        brand_copy = QWidget()
        brand_copy_layout = QVBoxLayout(brand_copy)
        brand_copy_layout.setContentsMargins(0, 0, 0, 0)
        brand_copy_layout.setSpacing(1)

        brand_title = QLabel(APP_NAME)
        brand_title.setObjectName("BrandTitle")
        brand_subtitle = QLabel("本地视频格式转换器")
        brand_subtitle.setProperty("muted", True)
        brand_copy_layout.addWidget(brand_title)
        brand_copy_layout.addWidget(brand_subtitle)

        local_chip = QLabel("本地处理 · 无需联网")
        local_chip.setObjectName("StatusChip")

        self.add_video_button = QPushButton("添加视频")
        self.add_video_button.setObjectName("PrimaryAction")
        self.add_video_button.setIcon(_icon(self, QStyle.StandardPixmap.SP_DialogOpenButton))
        self.add_video_button.clicked.connect(
            lambda: self._show_footer_message("视频导入将在步骤 3 接入")
        )

        self.clear_button = QToolButton()
        self.clear_button.setObjectName("IconButton")
        self.clear_button.setToolTip("清空任务")
        self.clear_button.setEnabled(False)

        self.theme_button = QToolButton()
        self.theme_button.setObjectName("IconButton")
        self.theme_button.setIcon(_icon(self, QStyle.StandardPixmap.SP_ComputerIcon))
        self.theme_button.clicked.connect(self._toggle_theme)

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setToolTip("应用设置")
        self.settings_button.clicked.connect(
            lambda: self._show_footer_message("应用设置将在后续步骤接入")
        )

        layout.addWidget(brand_mark)
        layout.addWidget(brand_copy)
        layout.addSpacing(8)
        layout.addWidget(local_chip)
        layout.addStretch(1)
        layout.addWidget(self.add_video_button)
        layout.addWidget(self.clear_button)
        layout.addWidget(self.theme_button)
        layout.addWidget(self.settings_button)
        return header

    def _build_queue_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        heading = QHBoxLayout()
        title = QLabel("任务队列")
        title.setObjectName("PanelTitle")
        self.queue_count = QLabel("0")
        self.queue_count.setObjectName("QueueCount")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.queue_count)

        self.task_list = QListWidget()
        self.task_stack = QStackedWidget()
        self.task_stack.addWidget(self._build_empty_queue())
        self.task_stack.addWidget(self.task_list)
        self.task_stack.setCurrentIndex(0)

        clear_finished = QPushButton("清空已完成")
        clear_finished.setObjectName("SecondaryAction")
        clear_finished.setEnabled(False)

        layout.addLayout(heading)
        layout.addWidget(self.task_stack, 1)
        layout.addWidget(clear_finished)
        return panel

    def _build_empty_queue(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        self.empty_queue_icon = QLabel()
        self.empty_queue_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("队列为空")
        title.setObjectName("PanelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("导入视频后会显示在这里")
        hint.setProperty("muted", True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)

        layout.addWidget(self.empty_queue_icon)
        layout.addWidget(title)
        layout.addWidget(hint)
        return widget

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        heading = QHBoxLayout()
        title = QLabel("视频信息")
        title.setObjectName("PanelTitle")
        self.media_status = QLabel("未选择")
        self.media_status.setObjectName("StatusChip")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.media_status)

        self.preview_stage = QFrame()
        self.preview_stage.setObjectName("PreviewStage")
        self.preview_stage.setMinimumHeight(310)
        preview_layout = QVBoxLayout(self.preview_stage)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.setSpacing(8)

        self.preview_icon = QLabel()
        self.preview_icon.setObjectName("StageIcon")
        self.preview_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        preview_title = QLabel("拖入视频文件")
        preview_title.setObjectName("PreviewTitle")
        preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        preview_hint = QLabel("或点击右上角“添加视频”")
        preview_hint.setObjectName("PreviewHint")
        preview_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        preview_layout.addWidget(self.preview_icon)
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(preview_hint)

        metrics = QWidget()
        metrics_layout = QHBoxLayout(metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(24)
        self.metric_duration = MetricItem("时长")
        self.metric_resolution = MetricItem("分辨率")
        self.metric_video_codec = MetricItem("视频编码")
        self.metric_file_size = MetricItem("文件大小")
        metrics_layout.addWidget(self.metric_duration)
        metrics_layout.addWidget(self.metric_resolution)
        metrics_layout.addWidget(self.metric_video_codec)
        metrics_layout.addWidget(self.metric_file_size)
        metrics_layout.addStretch(1)

        source_row = QFrame()
        source_row.setObjectName("SourcePathRow")
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(10, 8, 10, 8)
        source_layout.setSpacing(8)
        source_label = QLabel("源文件")
        source_label.setProperty("muted", True)
        self.source_path = QLabel("尚未导入视频")
        self.source_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        source_layout.addWidget(source_label)
        source_layout.addWidget(self.source_path, 1)

        layout.addLayout(heading)
        layout.addWidget(self.preview_stage, 1)
        layout.addWidget(metrics)
        layout.addWidget(source_row)
        return panel

    def _build_settings_panel(self) -> QWidget:
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(12)

        heading = QHBoxLayout()
        title = QLabel("转换设置")
        title.setObjectName("PanelTitle")
        mode = QLabel("基础模式")
        mode.setObjectName("StatusChip")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(mode)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(14)

        format_label = QLabel("目标格式")
        format_label.setObjectName("SectionLabel")
        format_grid = QGridLayout()
        format_grid.setContentsMargins(0, 0, 0, 0)
        format_grid.setHorizontalSpacing(8)
        format_grid.setVerticalSpacing(8)
        self.format_group = QButtonGroup(self)
        self.format_group.setExclusive(True)
        self.format_buttons: dict[str, QToolButton] = {}

        for index, name in enumerate(("MP4", "MKV", "WebM", "MP3", "WAV", "GIF")):
            button = QToolButton()
            button.setText(name)
            button.setCheckable(True)
            button.setProperty("formatPreset", True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if name == "MP4":
                button.setChecked(True)
            self.format_group.addButton(button)
            self.format_buttons[name] = button
            format_grid.addWidget(button, index // 3, index % 3)

        basic_form = QGridLayout()
        basic_form.setContentsMargins(0, 0, 0, 0)
        basic_form.setHorizontalSpacing(10)
        basic_form.setVerticalSpacing(10)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(("平衡（推荐）", "高质量", "小体积"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(("保持原始", "1080p", "720p", "480p"))
        self.frame_rate_combo = QComboBox()
        self.frame_rate_combo.addItems(("保持原始", "30 FPS", "24 FPS", "60 FPS"))
        self._add_form_row(basic_form, 0, "画质", self.quality_combo)
        self._add_form_row(basic_form, 1, "分辨率", self.resolution_combo)
        self._add_form_row(basic_form, 2, "帧率", self.frame_rate_combo)

        output_label = QLabel("输出目录")
        output_label.setObjectName("SectionLabel")
        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self.output_path = QLineEdit("输出到源文件旁的 converted 目录")
        self.output_path.setReadOnly(True)
        self.browse_button = QToolButton()
        self.browse_button.setObjectName("IconButton")
        self.browse_button.setToolTip("选择输出目录")
        self.browse_button.clicked.connect(
            lambda: self._show_footer_message("输出目录选择将在步骤 6 接入")
        )
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(self.browse_button)

        advanced = CollapsibleSection("高级设置")
        self.video_codec_combo = QComboBox()
        self.video_codec_combo.addItems(("H.264", "H.265", "AV1", "VP9"))
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(23)
        self.audio_codec_combo = QComboBox()
        self.audio_codec_combo.addItems(("AAC", "Opus", "MP3"))
        self.audio_bitrate_combo = QComboBox()
        self.audio_bitrate_combo.addItems(("128 kbps", "192 kbps", "256 kbps", "320 kbps"))
        keep_audio = QCheckBox("保留音频")
        keep_audio.setChecked(True)
        self._add_form_row(advanced.content_layout, 0, "视频编码", self.video_codec_combo)
        self._add_form_row(advanced.content_layout, 1, "CRF", self.crf_spin)
        self._add_form_row(advanced.content_layout, 2, "音频编码", self.audio_codec_combo)
        self._add_form_row(advanced.content_layout, 3, "音频码率", self.audio_bitrate_combo)
        advanced.content_layout.addWidget(keep_audio, 4, 0, 1, 2)

        content_layout.addWidget(format_label)
        content_layout.addLayout(format_grid)
        content_layout.addLayout(basic_form)
        content_layout.addSpacing(2)
        content_layout.addWidget(output_label)
        content_layout.addLayout(output_row)
        content_layout.addWidget(advanced)
        content_layout.addStretch(1)
        scroll.setWidget(content)

        self.start_button = QPushButton("开始转换")
        self.start_button.setObjectName("PrimaryAction")
        self.start_button.setIcon(_icon(self, QStyle.StandardPixmap.SP_MediaPlay))
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("请先导入视频")

        panel_layout.addLayout(heading)
        panel_layout.addWidget(scroll, 1)
        panel_layout.addWidget(self.start_button)
        return panel

    @staticmethod
    def _add_form_row(layout: QGridLayout, row: int, label: str, widget: QWidget) -> None:
        caption = QLabel(label)
        caption.setProperty("muted", True)
        layout.addWidget(caption, row, 0)
        layout.addWidget(widget, row, 1)
        layout.setColumnStretch(1, 1)

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("Footer")
        footer.setFixedHeight(38)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 7, 16, 7)
        layout.setSpacing(8)

        status_dot = QFrame()
        status_dot.setObjectName("StatusDot")
        status_dot.setFixedSize(8, 8)

        self.footer_status_label = QLabel("FFmpeg 环境将在下一步检测")
        self.footer_status_label.setProperty("muted", True)

        stage_label = QLabel("开发阶段 · 步骤 1")
        stage_label.setProperty("muted", True)

        layout.addWidget(status_dot)
        layout.addWidget(self.footer_status_label)
        layout.addStretch(1)
        layout.addWidget(stage_label)
        return footer

    def _show_footer_message(self, message: str) -> None:
        self.footer_status_label.setText(message)

    def _toggle_theme(self) -> None:
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.settings.setValue("ui/theme", self.theme_name)
        self._apply_theme()

    def _apply_theme(self) -> None:
        palette = get_palette(self.theme_name)
        self.setStyleSheet(build_stylesheet(palette))
        self._apply_icon_theme(palette)
        target = "浅色" if palette.name == "dark" else "深色"
        self.theme_button.setToolTip(f"切换为{target}主题")

    def _apply_icon_theme(self, palette: ThemePalette) -> None:
        self.add_video_button.setIcon(
            _colored_icon(
                self,
                QStyle.StandardPixmap.SP_DialogOpenButton,
                "#ffffff",
            )
        )
        self.clear_button.setIcon(
            _colored_icon(self, QStyle.StandardPixmap.SP_TrashIcon, palette.muted)
        )
        self.theme_button.setIcon(
            _colored_icon(self, QStyle.StandardPixmap.SP_ComputerIcon, palette.text)
        )
        self.settings_button.setIcon(
            _colored_icon(
                self,
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
                palette.text,
            )
        )
        self.empty_queue_icon.setPixmap(
            _colored_icon(
                self,
                QStyle.StandardPixmap.SP_FileIcon,
                palette.muted,
                42,
            ).pixmap(42, 42)
        )
        self.preview_icon.setPixmap(
            _colored_icon(
                self,
                QStyle.StandardPixmap.SP_MediaPlay,
                palette.preview_muted,
                54,
            ).pixmap(54, 54)
        )
        self.browse_button.setIcon(
            _colored_icon(self, QStyle.StandardPixmap.SP_DirOpenIcon, palette.text)
        )
        self.start_button.setIcon(
            _colored_icon(self, QStyle.StandardPixmap.SP_MediaPlay, palette.text)
        )
