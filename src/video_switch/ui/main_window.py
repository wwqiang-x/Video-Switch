"""Main desktop window and step-one interface shell."""

from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFontMetrics,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
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

from video_switch.models.conversion_settings import (
    AUDIO_CODEC_OPTIONS,
    FORMAT_DEFAULTS,
    VIDEO_CODEC_OPTIONS,
    ConversionSettings,
)
from video_switch.models.media_task import MediaTask, TaskStatus
from video_switch.services.ffmpeg_command import (
    QUALITY_DEFAULTS,
    build_command_preview,
    unique_output_path,
)
from video_switch.services.media_probe import MediaProbeService, ProbeResult
from video_switch.services.thumbnail import (
    ThumbnailResult,
    ThumbnailService,
    default_thumbnail_cache_dir,
)
from video_switch.services.toolchain import ToolchainDetector, ToolchainStatus
from video_switch.services.video_importer import (
    ImportResult,
    VideoImporter,
    format_file_size,
)
from video_switch.ui.fonts import register_cjk_fonts
from video_switch.ui.settings_dialog import SettingsDialog
from video_switch.ui.theme import ThemePalette, build_stylesheet, get_palette

APP_NAME = "Video Switch"
VIDEO_FILE_FILTER = (
    "视频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.m4v *.wmv *.mpg *.mpeg *.ts *.3gp);;"
    "所有文件 (*)"
)


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


class ElidedLabel(QLabel):
    """A single-line label that elides long text in the middle."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self.refresh_elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh_elide()

    def refresh_elide(self) -> None:
        width = max(0, self.contentsRect().width())
        displayed = QFontMetrics(self.font()).elidedText(
            self._full_text,
            Qt.TextElideMode.ElideMiddle,
            width,
        )
        super().setText(displayed)


class ThumbnailLabel(QLabel):
    """A label that keeps an image centered and scales it on resize."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ThumbnailPreview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._source_pixmap = QPixmap()

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._refresh_pixmap()

    def clear_source_pixmap(self) -> None:
        self._source_pixmap = QPixmap()
        self.clear()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._source_pixmap.isNull():
            return
        self.setPixmap(
            self._source_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


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

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        register_cjk_fonts()
        self.settings = settings or QSettings("VideoSwitch", "Video Switch")
        self.theme_name = str(self.settings.value("ui/theme", "light"))
        self.importer = VideoImporter()
        self.tasks: dict[str, MediaTask] = {}
        self.task_items: dict[str, QListWidgetItem] = {}
        self.output_directory: Path | None = None
        self._loading_conversion_settings = True
        self._footer_reset_timer = QTimer(self)
        self._footer_reset_timer.setSingleShot(True)
        self._footer_reset_timer.timeout.connect(self._restore_toolchain_status)
        self.probe_service = MediaProbeService(self)
        self.probe_service.task_started.connect(self._on_task_probe_started)
        self.probe_service.task_finished.connect(self._on_task_probe_finished)
        self.thumbnail_service = ThumbnailService(
            default_thumbnail_cache_dir(),
            self,
        )
        self.thumbnail_service.task_started.connect(self._on_task_thumbnail_started)
        self.thumbnail_service.task_finished.connect(self._on_task_thumbnail_finished)
        self.toolchain_detector = ToolchainDetector(self)
        self.toolchain_detector.started.connect(self._on_toolchain_detection_started)
        self.toolchain_detector.finished.connect(self._on_toolchain_detected)
        self.toolchain_status: ToolchainStatus | None = None

        self.setWindowTitle(f"{APP_NAME} - 视频转换器")
        self.resize(1280, 800)
        self.setMinimumSize(1080, 680)
        self.setAcceptDrops(True)

        self._build_interface()
        self._load_conversion_settings()
        self._apply_theme()
        QTimer.singleShot(0, self._detect_toolchain)

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
        self.add_video_button.clicked.connect(self._choose_videos)

        self.clear_button = QToolButton()
        self.clear_button.setObjectName("IconButton")
        self.clear_button.setToolTip("清空全部任务")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self._clear_queue)

        self.theme_button = QToolButton()
        self.theme_button.setObjectName("IconButton")
        self.theme_button.setIcon(_icon(self, QStyle.StandardPixmap.SP_ComputerIcon))
        self.theme_button.clicked.connect(self._toggle_theme)

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setToolTip("应用设置")
        self.settings_button.clicked.connect(self._open_settings)

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
        self.task_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.task_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.task_list.currentItemChanged.connect(self._on_task_selected)
        self.task_stack = QStackedWidget()
        self.task_stack.addWidget(self._build_empty_queue())
        self.task_stack.addWidget(self.task_list)
        self.task_stack.setCurrentIndex(0)

        self.remove_button = QPushButton("移除选中")
        self.remove_button.setObjectName("SecondaryAction")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self._remove_selected_task)

        self.clear_queue_button = QPushButton("清空全部")
        self.clear_queue_button.setObjectName("SecondaryAction")
        self.clear_queue_button.setEnabled(False)
        self.clear_queue_button.clicked.connect(self._clear_queue)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_queue_button)

        layout.addLayout(heading)
        layout.addWidget(self.task_stack, 1)
        layout.addLayout(actions)
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
        self.regenerate_thumbnail_button = QToolButton()
        self.regenerate_thumbnail_button.setObjectName("IconButton")
        self.regenerate_thumbnail_button.setToolTip("重新生成缩略图")
        self.regenerate_thumbnail_button.setEnabled(False)
        self.regenerate_thumbnail_button.hide()
        self.regenerate_thumbnail_button.clicked.connect(self._regenerate_thumbnail)
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.regenerate_thumbnail_button)
        heading.addWidget(self.media_status)

        self.preview_stage = QFrame()
        self.preview_stage.setObjectName("PreviewStage")
        self.preview_stage.setMinimumHeight(310)
        preview_layout = QVBoxLayout(self.preview_stage)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.setSpacing(8)

        self.thumbnail_label = ThumbnailLabel()
        self.thumbnail_label.hide()

        self.preview_icon = QLabel()
        self.preview_icon.setObjectName("StageIcon")
        self.preview_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_title = ElidedLabel("拖入视频文件")
        self.preview_title.setObjectName("PreviewTitle")
        self.preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_title.setWordWrap(True)

        self.preview_hint = QLabel("或点击右上角“添加视频”")
        self.preview_hint.setObjectName("PreviewHint")
        self.preview_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_hint.setWordWrap(True)
        self.preview_hint.setMinimumWidth(320)

        preview_message = QWidget()
        preview_message.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        preview_message_layout = QVBoxLayout(preview_message)
        preview_message_layout.setContentsMargins(0, 0, 0, 0)
        preview_message_layout.setSpacing(7)
        preview_message_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_message_layout.addWidget(self.preview_icon)
        preview_message_layout.addWidget(self.preview_title)
        preview_message_layout.addWidget(self.preview_hint)

        preview_layout.addWidget(self.thumbnail_label, 1)
        preview_layout.addWidget(preview_message)

        metrics = QWidget()
        metrics_layout = QGridLayout(metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setHorizontalSpacing(24)
        metrics_layout.setVerticalSpacing(10)
        self.metric_duration = MetricItem("时长")
        self.metric_resolution = MetricItem("分辨率")
        self.metric_frame_rate = MetricItem("帧率")
        self.metric_file_size = MetricItem("文件大小")
        self.metric_video_codec = MetricItem("视频编码")
        self.metric_audio_codec = MetricItem("音频编码")
        self.metric_bit_rate = MetricItem("总码率")
        self.metric_container = MetricItem("容器")

        metrics_layout.addWidget(self.metric_duration, 0, 0)
        metrics_layout.addWidget(self.metric_resolution, 0, 1)
        metrics_layout.addWidget(self.metric_frame_rate, 0, 2)
        metrics_layout.addWidget(self.metric_file_size, 0, 3)
        metrics_layout.addWidget(self.metric_video_codec, 1, 0)
        metrics_layout.addWidget(self.metric_audio_codec, 1, 1)
        metrics_layout.addWidget(self.metric_bit_rate, 1, 2)
        metrics_layout.addWidget(self.metric_container, 1, 3)
        for column in range(4):
            metrics_layout.setColumnStretch(column, 1)

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
        self.format_group.buttonToggled.connect(self._on_format_changed)

        basic_form = QGridLayout()
        basic_form.setContentsMargins(0, 0, 0, 0)
        basic_form.setHorizontalSpacing(10)
        basic_form.setVerticalSpacing(10)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(("平衡（推荐）", "高质量", "小体积"))
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(("保持原始", "1080p", "720p", "480p"))
        self.resolution_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self.frame_rate_combo = QComboBox()
        self.frame_rate_combo.addItems(("保持原始", "30 FPS", "24 FPS", "60 FPS"))
        self.frame_rate_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self._add_form_row(basic_form, 0, "画质", self.quality_combo)
        self._add_form_row(basic_form, 1, "分辨率", self.resolution_combo)
        self._add_form_row(basic_form, 2, "帧率", self.frame_rate_combo)

        output_label = QLabel("输出目录")
        output_label.setObjectName("SectionLabel")
        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self.output_path = QLineEdit("默认：源文件旁的 converted")
        self.output_path.setReadOnly(True)
        self.browse_button = QToolButton()
        self.browse_button.setObjectName("IconButton")
        self.browse_button.setToolTip("选择输出目录")
        self.browse_button.clicked.connect(self._choose_output_directory)
        self.reset_output_button = QToolButton()
        self.reset_output_button.setObjectName("IconButton")
        self.reset_output_button.setToolTip("恢复默认输出目录")
        self.reset_output_button.clicked.connect(self._reset_output_directory)
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(self.browse_button)
        output_row.addWidget(self.reset_output_button)

        self.output_name_preview = QLabel("输出文件：--")
        self.output_name_preview.setProperty("muted", True)
        self.output_name_preview.setWordWrap(True)

        advanced = CollapsibleSection("高级设置")
        self.advanced_section = advanced
        self.video_codec_combo = QComboBox()
        self.video_codec_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(23)
        self.crf_spin.valueChanged.connect(self._on_conversion_control_changed)
        self.audio_codec_combo = QComboBox()
        self.audio_codec_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self.audio_bitrate_combo = QComboBox()
        self.audio_bitrate_combo.addItems(("128 kbps", "192 kbps", "256 kbps", "320 kbps"))
        self.audio_bitrate_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self.keep_audio_checkbox = QCheckBox("保留音频")
        self.keep_audio_checkbox.setChecked(True)
        self.keep_audio_checkbox.toggled.connect(self._on_conversion_control_changed)
        self._add_form_row(advanced.content_layout, 0, "视频编码", self.video_codec_combo)
        self._add_form_row(advanced.content_layout, 1, "CRF", self.crf_spin)
        self._add_form_row(advanced.content_layout, 2, "音频编码", self.audio_codec_combo)
        self._add_form_row(advanced.content_layout, 3, "音频码率", self.audio_bitrate_combo)
        advanced.content_layout.addWidget(self.keep_audio_checkbox, 4, 0, 1, 2)

        command_section = CollapsibleSection("FFmpeg 命令预览")
        self.command_section = command_section
        self.command_preview = QPlainTextEdit()
        self.command_preview.setObjectName("CommandPreview")
        self.command_preview.setReadOnly(True)
        self.command_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.command_preview.setMaximumHeight(110)
        command_section.content_layout.addWidget(self.command_preview, 0, 0, 1, 2)

        content_layout.addWidget(format_label)
        content_layout.addLayout(format_grid)
        content_layout.addLayout(basic_form)
        content_layout.addSpacing(2)
        content_layout.addWidget(output_label)
        content_layout.addLayout(output_row)
        content_layout.addWidget(self.output_name_preview)
        content_layout.addWidget(advanced)
        content_layout.addWidget(command_section)
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

    def _on_format_changed(self, button: QToolButton, checked: bool) -> None:
        if not checked or self._loading_conversion_settings:
            return
        self._apply_format_defaults(button.text())
        self._on_conversion_control_changed()

    def _on_quality_changed(self, quality: str) -> None:
        if self._loading_conversion_settings:
            return
        self.crf_spin.setValue(QUALITY_DEFAULTS[quality][0])
        self._on_conversion_control_changed()

    def _on_conversion_control_changed(self, *args) -> None:
        del args
        if self._loading_conversion_settings:
            return
        self._set_conversion_controls_enabled(self._selected_output_format())
        self._save_conversion_settings()
        self._update_output_preview()

    def _selected_output_format(self) -> str:
        for name, button in self.format_buttons.items():
            if button.isChecked():
                return name
        return "MP4"

    def _configure_format_options(
        self,
        output_format: str,
        video_codec: str | None = None,
        audio_codec: str | None = None,
    ) -> None:
        video_options = VIDEO_CODEC_OPTIONS[output_format]
        default_video, default_audio = FORMAT_DEFAULTS[output_format]

        self.video_codec_combo.clear()
        self.video_codec_combo.addItems(video_options)
        chosen_video = video_codec if video_codec in video_options else default_video
        if chosen_video:
            self.video_codec_combo.setCurrentText(chosen_video)

        audio_options = AUDIO_CODEC_OPTIONS[output_format]
        self.audio_codec_combo.clear()
        self.audio_codec_combo.addItems(audio_options)
        chosen_audio = audio_codec if audio_codec in audio_options else default_audio
        if chosen_audio:
            self.audio_codec_combo.setCurrentText(chosen_audio)

    def _apply_format_defaults(self, output_format: str) -> None:
        previous_loading = self._loading_conversion_settings
        self._loading_conversion_settings = True
        try:
            self._configure_format_options(output_format)
            if output_format in {"MP4", "MKV", "WebM"}:
                self.quality_combo.setCurrentText("平衡（推荐）")
                self.crf_spin.setValue(23)
            if output_format == "GIF":
                self.keep_audio_checkbox.setChecked(False)
            elif output_format in {"MP3", "WAV"}:
                self.keep_audio_checkbox.setChecked(True)
            self._set_conversion_controls_enabled(output_format)
        finally:
            self._loading_conversion_settings = previous_loading

    def _set_conversion_controls_enabled(self, output_format: str) -> None:
        video_capable = output_format in {"MP4", "MKV", "WebM"}
        audio_capable = output_format not in {"GIF"}
        basic_video = output_format in {"MP4", "MKV", "WebM"}

        self.quality_combo.setEnabled(basic_video)
        self.resolution_combo.setEnabled(video_capable and output_format != "GIF")
        self.frame_rate_combo.setEnabled(video_capable and output_format != "GIF")
        self.video_codec_combo.setEnabled(video_capable)
        self.crf_spin.setEnabled(video_capable)

        if output_format in {"MP3", "WAV"}:
            self.keep_audio_checkbox.setChecked(True)
            self.keep_audio_checkbox.setEnabled(False)
        elif output_format == "GIF":
            self.keep_audio_checkbox.setChecked(False)
            self.keep_audio_checkbox.setEnabled(False)
        else:
            self.keep_audio_checkbox.setEnabled(True)

        audio_enabled = audio_capable and self.keep_audio_checkbox.isChecked()
        self.audio_codec_combo.setEnabled(audio_enabled)
        self.audio_bitrate_combo.setEnabled(
            audio_enabled
            and output_format != "WAV"
            and self.audio_codec_combo.currentText() != "PCM"
        )

    def _current_conversion_settings(self) -> ConversionSettings:
        return ConversionSettings(
            output_format=self._selected_output_format(),
            quality=self.quality_combo.currentText(),
            resolution=self.resolution_combo.currentText(),
            frame_rate=self.frame_rate_combo.currentText(),
            video_codec=self.video_codec_combo.currentText(),
            audio_codec=self.audio_codec_combo.currentText(),
            audio_bitrate=self.audio_bitrate_combo.currentText(),
            crf=self.crf_spin.value(),
            keep_audio=self.keep_audio_checkbox.isChecked(),
        )

    def _load_conversion_settings(self) -> None:
        self._loading_conversion_settings = True
        output_format = str(self.settings.value("conversion/format", "MP4"))
        if output_format not in self.format_buttons:
            output_format = "MP4"
        self.format_buttons[output_format].setChecked(True)

        saved_video = str(self.settings.value("conversion/video_codec", ""))
        saved_audio = str(self.settings.value("conversion/audio_codec", ""))
        self._configure_format_options(output_format, saved_video, saved_audio)

        self._set_combo_value(
            self.quality_combo,
            str(self.settings.value("conversion/quality", "平衡（推荐）")),
        )
        self._set_combo_value(
            self.resolution_combo,
            str(self.settings.value("conversion/resolution", "保持原始")),
        )
        self._set_combo_value(
            self.frame_rate_combo,
            str(self.settings.value("conversion/frame_rate", "保持原始")),
        )
        self._set_combo_value(
            self.audio_bitrate_combo,
            str(self.settings.value("conversion/audio_bitrate", "192 kbps")),
        )
        self.crf_spin.setValue(self._settings_int("conversion/crf", 23))
        self.keep_audio_checkbox.setChecked(self._settings_bool("conversion/keep_audio", True))

        output_directory = str(self.settings.value("conversion/output_directory", ""))
        if output_directory:
            candidate = Path(output_directory)
            if candidate.is_dir():
                self.output_directory = candidate

        self._loading_conversion_settings = False
        self._set_conversion_controls_enabled(output_format)
        self._update_output_preview()

    def _save_conversion_settings(self) -> None:
        settings = self._current_conversion_settings()
        self.settings.setValue("conversion/format", settings.output_format)
        self.settings.setValue("conversion/quality", settings.quality)
        self.settings.setValue("conversion/resolution", settings.resolution)
        self.settings.setValue("conversion/frame_rate", settings.frame_rate)
        self.settings.setValue("conversion/video_codec", settings.video_codec)
        self.settings.setValue("conversion/audio_codec", settings.audio_codec)
        self.settings.setValue("conversion/audio_bitrate", settings.audio_bitrate)
        self.settings.setValue("conversion/crf", settings.crf)
        self.settings.setValue("conversion/keep_audio", settings.keep_audio)
        self.settings.setValue(
            "conversion/output_directory",
            str(self.output_directory) if self.output_directory else "",
        )

    def _settings_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() not in {"0", "false", "no", ""}

    def _settings_int(self, key: str, default: int) -> int:
        try:
            return int(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _choose_output_directory(self) -> None:
        initial = self.output_directory or Path(
            str(self.settings.value("files/last_import_directory", "")) or Path.home()
        )
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            str(initial),
        )
        if not selected:
            return
        self.output_directory = Path(selected)
        self._save_conversion_settings()
        self._update_output_preview()

    def _reset_output_directory(self) -> None:
        self.output_directory = None
        self._save_conversion_settings()
        self._update_output_preview()

    def _update_output_preview(self) -> None:
        settings = self._current_conversion_settings()
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None

        if task is not None:
            output_path = unique_output_path(
                task.path,
                settings,
                self.output_directory,
            )
        else:
            output_directory = self.output_directory or Path("converted")
            output_path = output_directory / f"输入文件_converted{settings.output_extension}"

        if self.output_directory is None:
            self.output_path.setText("默认：源文件旁的 converted")
            self.output_path.setToolTip("")
        else:
            self.output_path.setText(str(self.output_directory))
            self.output_path.setToolTip(str(self.output_directory))
        self.output_path.setCursorPosition(0)

        self.output_name_preview.setText(f"输出：{output_path.name}")
        command = build_command_preview(
            settings,
            task.path if task else None,
            output_path,
            self._available_ffmpeg_path(),
        )
        self.command_preview.setPlainText(command)

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("Footer")
        footer.setFixedHeight(38)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 7, 16, 7)
        layout.setSpacing(8)

        self.status_dot = QFrame()
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setProperty("state", "pending")
        self.status_dot.setFixedSize(8, 8)

        self.footer_status_label = QLabel("正在检测 FFmpeg 环境...")
        self.footer_status_label.setProperty("muted", True)

        stage_label = QLabel("开发阶段 · 步骤 6")
        stage_label.setProperty("muted", True)

        layout.addWidget(self.status_dot)
        layout.addWidget(self.footer_status_label)
        layout.addStretch(1)
        layout.addWidget(stage_label)
        return footer

    def _choose_videos(self) -> None:
        last_directory = str(self.settings.value("files/last_import_directory", ""))
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择视频文件",
            last_directory,
            VIDEO_FILE_FILTER,
        )
        if not paths:
            return
        self.settings.setValue("files/last_import_directory", str(Path(paths[0]).parent))
        self._import_paths(paths)

    def _import_paths(self, paths: list[str]) -> None:
        result = self.importer.import_paths(
            paths,
            set(self.tasks),
            {task.content_signature for task in self.tasks.values()},
        )
        first_item: QListWidgetItem | None = None
        for task in result.added:
            item = self._create_task_item(task)
            self.tasks[task.key] = task
            if first_item is None:
                first_item = item

        self._update_task_actions()
        if first_item is not None:
            self.task_list.setCurrentItem(first_item)
        self._probe_pending_tasks()

        message, details, state = self._import_feedback(result)
        self._show_footer_message(
            message,
            details=details,
            state=state,
            timeout=6000,
        )

    def _create_task_item(self, task: MediaTask) -> QListWidgetItem:
        item = QListWidgetItem(
            f"{task.display_name}\n"
            f"{task.extension}  ·  {format_file_size(task.size_bytes)}  ·  {task.status_text}"
        )
        item.setData(Qt.ItemDataRole.UserRole, task.key)
        item.setToolTip(str(task.path))
        item.setSizeHint(QSize(0, 62))
        item.setIcon(self._task_icon())
        self.task_list.addItem(item)
        self.task_items[task.key] = item
        return item

    def _task_icon(self) -> QIcon:
        palette = get_palette(self.theme_name)
        return _colored_icon(
            self,
            QStyle.StandardPixmap.SP_FileIcon,
            palette.primary,
            24,
        )

    def _import_feedback(self, result: ImportResult) -> tuple[str, str, str]:
        parts: list[str] = []
        if result.added:
            parts.append(f"已导入 {len(result.added)} 个视频")
        if result.duplicates:
            parts.append(f"忽略 {len(result.duplicates)} 个重复文件")
        if result.issues:
            parts.append(f"{len(result.issues)} 个文件未导入")

        if not parts:
            return "没有可导入的文件", "", "error"

        detail_lines = [f"重复文件：{path}" for path in result.duplicates]
        detail_lines.extend(f"{issue.path}：{issue.reason}" for issue in result.issues)

        if result.added and result.skipped_count == 0:
            state = "ready"
        elif result.added:
            state = "pending"
        else:
            state = "error"
        return "；".join(parts), "\n".join(detail_lines), state

    def _on_task_selected(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self._clear_preview()
            self._update_task_actions()
            return

        task_key = str(current.data(Qt.ItemDataRole.UserRole))
        task = self.tasks.get(task_key)
        if task is None:
            self._clear_preview()
            self._update_task_actions()
            return

        self._apply_task_to_preview(task)
        self._update_task_actions()

    def _apply_task_to_preview(self, task: MediaTask) -> None:
        info = task.media_info
        self.source_path.setText(str(task.path))
        self.preview_title.setText(task.display_name)
        self.preview_title.setToolTip(task.display_name)
        self.metric_file_size.value_label.setText(format_file_size(task.size_bytes))
        self.metric_duration.value_label.setText(info.duration_text if info else "--")
        self.metric_resolution.value_label.setText(info.resolution_text if info else "--")
        self.metric_frame_rate.value_label.setText(info.frame_rate_text if info else "--")
        self.metric_video_codec.value_label.setText(info.video_codec_text if info else "--")
        self.metric_audio_codec.value_label.setText(info.audio_codec_text if info else "--")
        self.metric_bit_rate.value_label.setText(info.bit_rate_text if info else "--")
        self.metric_container.value_label.setText(info.container_text if info else "--")
        self.metric_video_codec.value_label.setToolTip(
            f"像素格式：{info.pixel_format}" if info and info.pixel_format else ""
        )
        self.metric_audio_codec.value_label.setToolTip(
            f"采样率：{info.audio_sample_rate} Hz" if info and info.audio_sample_rate else ""
        )

        if task.status == TaskStatus.PROBING_METADATA:
            self.media_status.setText("读取中")
            self.preview_hint.setText("正在读取视频信息...")
        elif task.status == TaskStatus.METADATA_READY:
            self.media_status.setText("信息已读取")
            self.preview_hint.setText("等待生成缩略图")
        elif task.status == TaskStatus.FAILED:
            self.media_status.setText("读取失败")
            self.preview_hint.setText(task.probe_error or "无法读取视频信息")
        else:
            self.media_status.setText("已导入")
            if self._available_ffprobe_path():
                self.preview_hint.setText("正在等待读取视频信息")
            else:
                self.preview_hint.setText("请先在设置中配置 ffprobe 环境")

        self._apply_thumbnail_to_preview(task)
        self.preview_hint.setToolTip(task.probe_error or task.thumbnail_error or "")
        self.regenerate_thumbnail_button.setVisible(info is not None)
        self.regenerate_thumbnail_button.setEnabled(info is not None)
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("视频转换将在步骤 7 接入")

    def _apply_thumbnail_to_preview(self, task: MediaTask) -> None:
        thumbnail_path = task.thumbnail_path
        if thumbnail_path is not None and thumbnail_path.is_file():
            pixmap = QPixmap(str(thumbnail_path))
            if not pixmap.isNull():
                self.thumbnail_label.set_source_pixmap(pixmap)
                self.thumbnail_label.show()
                self.preview_icon.hide()
                self.preview_hint.setText("缩略图已生成")
                return

        self.thumbnail_label.clear_source_pixmap()
        self.thumbnail_label.hide()
        self.preview_icon.show()
        if task.thumbnail_generating:
            self.preview_hint.setText("正在生成缩略图...")
        elif task.thumbnail_error:
            self.preview_hint.setText(f"缩略图生成失败：{task.thumbnail_error}")

    def _clear_preview(self) -> None:
        self.media_status.setText("未选择")
        self.metric_duration.value_label.setText("--")
        self.metric_resolution.value_label.setText("--")
        self.metric_frame_rate.value_label.setText("--")
        self.metric_video_codec.value_label.setText("--")
        self.metric_audio_codec.value_label.setText("--")
        self.metric_bit_rate.value_label.setText("--")
        self.metric_container.value_label.setText("--")
        self.metric_file_size.value_label.setText("--")
        self.metric_video_codec.value_label.setToolTip("")
        self.metric_audio_codec.value_label.setToolTip("")
        self.source_path.setText("尚未导入视频")
        self.preview_title.setText("拖入视频文件")
        self.preview_title.setToolTip("")
        self.preview_hint.setText("或点击右上角“添加视频”")
        self.preview_hint.setToolTip("")
        self.thumbnail_label.clear_source_pixmap()
        self.thumbnail_label.hide()
        self.preview_icon.show()
        self.regenerate_thumbnail_button.hide()
        self.regenerate_thumbnail_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("请先导入视频")

    def _probe_pending_tasks(self) -> None:
        ffprobe_path = self._available_ffprobe_path()
        if ffprobe_path is None:
            return
        for task in self.tasks.values():
            if task.status == TaskStatus.WAITING_FOR_METADATA:
                self.probe_service.enqueue(task, ffprobe_path)

    def _available_ffprobe_path(self) -> Path | None:
        if self.toolchain_status is None or not self.toolchain_status.ffprobe.ready:
            return None
        return self.toolchain_status.ffprobe.executable

    def _available_ffmpeg_path(self) -> Path | None:
        if self.toolchain_status is None or not self.toolchain_status.ffmpeg.ready:
            return None
        return self.toolchain_status.ffmpeg.executable

    def _queue_thumbnails_for_ready_tasks(self) -> None:
        for task in self.tasks.values():
            if task.status == TaskStatus.METADATA_READY:
                self._queue_thumbnail_for_task(task)

    def _queue_thumbnail_for_task(
        self,
        task: MediaTask,
        force: bool = False,
    ) -> None:
        ffmpeg_path = self._available_ffmpeg_path()
        if ffmpeg_path is None or task.media_info is None:
            return
        if task.thumbnail_generating:
            return
        if task.thumbnail_path is not None and task.thumbnail_path.is_file() and not force:
            if self._current_task_key() == task.key:
                self._apply_task_to_preview(task)
            return
        if task.thumbnail_error and not force:
            return

        if force:
            self.thumbnail_service.delete_cached(task.content_signature)
            task.thumbnail_path = None
            task.thumbnail_error = None

        self.thumbnail_service.enqueue(task, ffmpeg_path)

    def _on_task_thumbnail_started(self, task_key: str) -> None:
        task = self.tasks.get(task_key)
        if task is None:
            return
        task.thumbnail_generating = True
        task.thumbnail_error = None
        if self._current_task_key() == task_key:
            self._apply_task_to_preview(task)

    def _on_task_thumbnail_finished(self, result: ThumbnailResult) -> None:
        task = self.tasks.get(result.task_key)
        if task is None:
            return
        task.thumbnail_generating = False
        if result.thumbnail_path is not None:
            task.thumbnail_path = result.thumbnail_path
            task.thumbnail_error = None
        else:
            task.thumbnail_path = None
            task.thumbnail_error = result.error or "无法生成缩略图"
        if self._current_task_key() == task.key:
            self._apply_task_to_preview(task)

    def _regenerate_thumbnail(self) -> None:
        task_key = self._current_task_key()
        if task_key is None:
            return
        task = self.tasks.get(task_key)
        if task is None or task.media_info is None:
            return
        self._queue_thumbnail_for_task(task, force=True)

    def _on_task_probe_started(self, task_key: str) -> None:
        task = self.tasks.get(task_key)
        if task is None:
            return
        task.status = TaskStatus.PROBING_METADATA
        task.probe_error = None
        self._update_task_item(task)
        if self._current_task_key() == task_key:
            self._apply_task_to_preview(task)

    def _on_task_probe_finished(self, result: ProbeResult) -> None:
        task = self.tasks.get(result.task_key)
        if task is None:
            return

        task.raw_probe_output = result.raw_output or None
        if result.info is not None:
            task.media_info = result.info
            task.probe_error = None
            task.status = TaskStatus.METADATA_READY
            self._queue_thumbnail_for_task(task)
        else:
            task.media_info = None
            task.probe_error = result.error or "无法读取视频信息"
            task.status = TaskStatus.FAILED

        self._update_task_item(task)
        if self._current_task_key() == task.key:
            self._apply_task_to_preview(task)

    def _update_task_item(self, task: MediaTask) -> None:
        item = self.task_items.get(task.key)
        if item is None:
            return
        item.setText(
            f"{task.display_name}\n"
            f"{task.extension}  ·  {format_file_size(task.size_bytes)}  ·  {task.status_text}"
        )
        tooltip = str(task.path)
        if task.probe_error:
            tooltip = f"{tooltip}\n{task.probe_error}"
        item.setToolTip(tooltip)

    def _current_task_key(self) -> str | None:
        item = self.task_list.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))

    def _remove_selected_task(self) -> None:
        item = self.task_list.currentItem()
        if item is None:
            return
        task_key = str(item.data(Qt.ItemDataRole.UserRole))
        task = self.tasks.pop(task_key, None)
        self.task_items.pop(task_key, None)
        self.probe_service.cancel_task(task_key)
        self.thumbnail_service.cancel_task(task_key)
        if task is not None:
            self.thumbnail_service.delete_cached(task.content_signature)
        self.task_list.takeItem(self.task_list.row(item))
        self._update_task_actions()
        self._show_footer_message("已移除所选任务", timeout=4000)

    def _clear_queue(self, checked: bool = False) -> None:
        del checked
        if not self.tasks:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("清空任务")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(f"确定要移除队列中的 {len(self.tasks)} 个任务吗？")
        clear_button = dialog.addButton("清空", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is not clear_button:
            return
        self.probe_service.cancel_all()
        self.thumbnail_service.cancel_all()
        for task in self.tasks.values():
            self.thumbnail_service.delete_cached(task.content_signature)
        self.tasks.clear()
        self.task_items.clear()
        self.task_list.clear()
        self._update_task_actions()
        self._show_footer_message("任务队列已清空", timeout=4000)

    def _update_task_actions(self) -> None:
        has_tasks = bool(self.tasks)
        has_selection = self.task_list.currentItem() is not None
        self.queue_count.setText(str(len(self.tasks)))
        self.task_stack.setCurrentIndex(1 if has_tasks else 0)
        self.clear_button.setEnabled(has_tasks)
        self.remove_button.setEnabled(has_selection)
        self.clear_queue_button.setEnabled(has_tasks)
        self._update_output_preview()

    def _show_footer_message(
        self,
        message: str,
        details: str = "",
        state: str | None = None,
        timeout: int = 0,
    ) -> None:
        self.footer_status_label.setText(message)
        self.footer_status_label.setToolTip(details)
        if state is not None:
            self._set_status_state(state)
        if timeout:
            self._footer_reset_timer.start(timeout)

    def _restore_toolchain_status(self) -> None:
        if self.toolchain_status is not None:
            self._on_toolchain_detected(self.toolchain_status)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._drop_paths(event.mimeData()):
            event.acceptProposedAction()
            self._set_drag_active(True)
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        del event
        self._set_drag_active(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        paths = self._drop_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self._import_paths(paths)

    @staticmethod
    def _drop_paths(mime_data) -> list[str]:
        if not mime_data.hasUrls():
            return []
        return [
            url.toLocalFile() for url in mime_data.urls() if url.isLocalFile() and url.toLocalFile()
        ]

    def _set_drag_active(self, active: bool) -> None:
        self.preview_stage.setProperty("dragActive", active)
        self.preview_stage.style().unpolish(self.preview_stage)
        self.preview_stage.style().polish(self.preview_stage)

    def _detect_toolchain(self) -> None:
        configured_ffmpeg = str(self.settings.value("toolchain/ffmpeg_path", ""))
        configured_ffprobe = str(self.settings.value("toolchain/ffprobe_path", ""))
        self.toolchain_detector.detect(
            configured_ffmpeg or None,
            configured_ffprobe or None,
        )

    def _on_toolchain_detection_started(self) -> None:
        self._set_status_state("pending")
        self.footer_status_label.setText("正在检测 FFmpeg 环境...")
        self.footer_status_label.setToolTip("")

    def _on_toolchain_detected(self, status: ToolchainStatus) -> None:
        self.toolchain_status = status
        self.footer_status_label.setText(status.summary)

        if status.ready:
            self._set_status_state("ready")
        else:
            self._set_status_state("error")

        details = [
            f"ffmpeg：{status.ffmpeg.executable or '未找到'}"
            if status.ffmpeg.ready
            else f"ffmpeg：{status.ffmpeg.error or '未就绪'}",
            f"ffprobe：{status.ffprobe.executable or '未找到'}"
            if status.ffprobe.ready
            else f"ffprobe：{status.ffprobe.error or '未就绪'}",
        ]
        self.footer_status_label.setToolTip("\n".join(details))
        self._probe_pending_tasks()
        self._queue_thumbnails_for_ready_tasks()

    def _set_status_state(self, state: str) -> None:
        self.status_dot.setProperty("state", state)
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            ffmpeg_path=str(self.settings.value("toolchain/ffmpeg_path", "")),
            ffprobe_path=str(self.settings.value("toolchain/ffprobe_path", "")),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        status = dialog.result_status
        if status is None or not status.ready:
            return

        self.settings.setValue("toolchain/ffmpeg_path", str(status.ffmpeg.executable))
        self.settings.setValue("toolchain/ffprobe_path", str(status.ffprobe.executable))
        self._on_toolchain_detected(status)

    def _toggle_theme(self) -> None:
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.settings.setValue("ui/theme", self.theme_name)
        self._apply_theme()

    def _apply_theme(self) -> None:
        palette = get_palette(self.theme_name)
        self.setStyleSheet(build_stylesheet(palette))
        self._apply_icon_theme(palette)
        self.preview_title.refresh_elide()
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
        self.reset_output_button.setIcon(
            _colored_icon(
                self,
                QStyle.StandardPixmap.SP_BrowserReload,
                palette.text,
            )
        )
        self.start_button.setIcon(
            _colored_icon(self, QStyle.StandardPixmap.SP_MediaPlay, palette.text)
        )
        self.regenerate_thumbnail_button.setIcon(
            _colored_icon(
                self,
                QStyle.StandardPixmap.SP_BrowserReload,
                palette.text,
            )
        )
        task_icon = self._task_icon()
        for index in range(self.task_list.count()):
            self.task_list.item(index).setIcon(task_icon)
