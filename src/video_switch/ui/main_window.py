"""Main desktop window and step-one interface shell."""

import json
import shutil
import time
from datetime import datetime
from math import ceil
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QPointF,
    QRect,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
    QShortcut,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyleOptionButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from video_switch.models.conversion_history import ConversionHistoryRecord
from video_switch.models.conversion_settings import (
    AUDIO_CODEC_OPTIONS,
    FORMAT_DEFAULTS,
    VIDEO_CODEC_OPTIONS,
    ConversionSettings,
)
from video_switch.models.media_task import MediaTask, TaskStatus
from video_switch.services.conversion_runner import (
    SEGMENT_DURATION_SECONDS,
    ConversionProgress,
    ConversionResult,
    ConversionRunner,
)
from video_switch.services.error_messages import SOURCE_MISSING, describe_probe_error
from video_switch.services.ffmpeg_command import (
    QUALITY_DEFAULTS,
    build_command_preview,
    estimate_conversion_seconds,
    unique_output_path,
)
from video_switch.services.history_store import (
    ConversionHistoryStore,
    default_history_path,
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
from video_switch.ui.advanced_help_dialog import AdvancedHelpDialog
from video_switch.ui.batch_dialogs import (
    BatchCandidate,
    BatchConfirmDialog,
    BatchSelectionDialog,
)
from video_switch.ui.fonts import register_cjk_fonts
from video_switch.ui.format_help_dialog import FormatHelpDialog
from video_switch.ui.settings_dialog import SettingsDialog
from video_switch.ui.task_item_delegate import (
    ACCENT_ROLE,
    META_ROLE,
    NAME_ROLE,
    STATUS_COLOR_ROLE,
    STATUS_ROLE,
    TaskItemDelegate,
    status_color,
)
from video_switch.ui.theme import ThemePalette, build_stylesheet, get_palette

APP_NAME = "Video Switch"
QUESTION_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "question.svg"
PLAY_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "play.svg"
FILE_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "file.svg"
VIDEO_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "video.svg"
TRASH_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "trash.svg"
THEME_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "theme.svg"
SETTINGS_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "settings.svg"
FOLDER_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "folder.svg"
REFRESH_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "refresh.svg"
APP_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "app.svg"
RUN_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "run.svg"
DELETE_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "delete.svg"
WARNING_ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "warning.svg"
VIDEO_FILE_FILTER = (
    "视频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.m4v *.wmv *.mpg *.mpeg *.ts *.3gp);;"
    "所有文件 (*)"
)
QUALITY_OPTIONS = ("平衡（推荐）", "高质量", "小体积")
RESOLUTION_OPTIONS = ("保持原始", "1080p", "720p", "480p")
FRAME_RATE_OPTIONS = ("保持原始", "30 FPS", "24 FPS", "60 FPS")
AUDIO_BITRATE_OPTIONS = ("128 kbps", "192 kbps", "256 kbps", "320 kbps")
NOT_APPLICABLE = "不适用"
MESSAGE_ICON_SIZE = 44
RESUME_DIRS_KEY = "conversion/resume_dirs"


def _progress_percent(value: float) -> int:
    """Clamp a progress value so a stray number can never break the progress bar."""
    if value != value:  # NaN
        return 0
    return round(min(100.0, max(0.0, value)))


def _center_message_text(dialog: QMessageBox, icon_size: int = MESSAGE_ICON_SIZE) -> None:
    """Vertically centre a message box text next to its icon."""
    label = dialog.findChild(QLabel, "qt_msgbox_label")
    if label is None:
        return
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    # The message label has no height of its own, so give it the icon's height;
    # otherwise Qt top-aligns it inside the row and the dialog looks unbalanced.
    label.setMinimumHeight(icon_size)


def _icon(widget: QWidget, pixmap: QStyle.StandardPixmap) -> QIcon:
    """Return a platform-standard icon matching the current Qt style."""
    return widget.style().standardIcon(pixmap)


def _question_icon() -> QIcon:
    """Return the bundled vector question icon."""
    return QIcon(str(QUESTION_ICON_PATH))


def _tinted_svg_pixmap(
    path: Path,
    color: str | None,
    size: int,
    widget: QWidget | None = None,
    device_pixel_ratio: float | None = None,
) -> QPixmap:
    """Render a DPR-aware SVG at a logical square size, tinting it when asked.

    Passing ``None`` keeps the colours authored in the SVG file.
    """
    if device_pixel_ratio is None:
        screen = widget.screen() if widget is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        device_pixel_ratio = screen.devicePixelRatio() if screen is not None else 1.0
    device_pixel_ratio = max(1.0, device_pixel_ratio)
    physical_size = max(1, ceil(size * device_pixel_ratio))

    renderer = QSvgRenderer(str(path))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    if color is not None:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(QRectF(0, 0, size, size), QColor(color))
    painter.end()
    return pixmap


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


class HelpIconButton(QToolButton):
    """Small SVG help button with a precisely positioned hover circle."""

    def __init__(self, tooltip: str, object_name: str) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setToolTip(tooltip)
        self.setFixedSize(22, 22)
        self.setIconSize(QSize(15, 15))
        self.setIcon(_question_icon())
        self._hover_color = QColor("#e2e8f0")
        self._hover_offset = QPointF(1.0, 1.0)
        self._hover_diameter = 20.0

    def set_hover_color(self, color: str) -> None:
        self._hover_color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:
        if self.underMouse():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._hover_color)
            left = (self.width() - self._hover_diameter) / 2 + self._hover_offset.x()
            top = (self.height() - self._hover_diameter) / 2 + self._hover_offset.y()
            painter.drawEllipse(QRectF(left, top, self._hover_diameter, self._hover_diameter))
            painter.end()
        super().paintEvent(event)


class AssetIconButton(QToolButton):
    """Toolbar button with a centered SVG icon and offset hover background."""

    def __init__(self, object_name: str, tooltip: str) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setToolTip(tooltip)
        self.setFixedSize(34, 34)
        self.setIconSize(QSize(18, 18))
        self._hover_color = QColor("#e2e8f0")
        self._icon_pixmap = QPixmap()

    def set_asset_icon(self, path: Path, color: str) -> None:
        self._icon_pixmap = _tinted_svg_pixmap(path, color, 18, widget=self)
        self.setIcon(QIcon(self._icon_pixmap))
        self.update()

    def set_hover_color(self, color: str) -> None:
        self._hover_color = QColor(color)
        self.update()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isEnabled() and self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._hover_color)
            painter.drawRoundedRect(QRectF(3, 3, 30, 30), 7, 7)

        if not self._icon_pixmap.isNull():
            icon_size = self._icon_pixmap.deviceIndependentSize().toSize()
            icon_x = (self.width() - icon_size.width()) // 2
            icon_y = (self.height() - icon_size.height()) // 2
            painter.setOpacity(1.0 if self.isEnabled() else 0.45)
            painter.drawPixmap(
                QRectF(
                    icon_x,
                    icon_y,
                    icon_size.width(),
                    icon_size.height(),
                ),
                self._icon_pixmap,
                QRectF(
                    0,
                    0,
                    self._icon_pixmap.width(),
                    self._icon_pixmap.height(),
                ),
            )
        painter.end()


class MarqueeLineEdit(QLineEdit):
    """Read-only line edit that continuously scrolls long text on hover."""

    SCROLL_SPEED_PX_PER_SECOND = 46.0

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full_text = ""
        self._offset = 0.0
        self._max_offset = 0.0
        self._last_tick = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance_marquee)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text
        super().setText("")
        self._update_scroll_range()
        self.update()

    def text(self) -> str:
        return self._full_text

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._last_tick = time.monotonic()
        if self._max_offset > 0:
            self._timer.start()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._timer.stop()
        self._offset = 0.0
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scroll_range()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._full_text:
            return

        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        rect = self.contentsRect().adjusted(4, 0, -4, 0)
        painter.setClipRect(rect)

        metrics = QFontMetrics(self.font())
        baseline = rect.y() + (rect.height() - metrics.height()) // 2 + metrics.ascent()
        painter.drawText(
            round(rect.x() - self._offset),
            baseline,
            self._full_text,
        )
        painter.end()

    def _update_scroll_range(self) -> None:
        text_width = QFontMetrics(self.font()).horizontalAdvance(self._full_text)
        viewport_width = max(0, self.contentsRect().width() - 8)
        self._max_offset = max(0.0, float(text_width - viewport_width))
        if self._max_offset <= 0:
            self._offset = 0.0
            self._timer.stop()
        elif self.underMouse():
            self._timer.start()

    def _advance_marquee(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self._last_tick)
        self._last_tick = now
        self._offset += self.SCROLL_SPEED_PX_PER_SECOND * elapsed
        if self._offset >= self._max_offset:
            self._offset = 0.0
        self.update()


class AddVideoButton(QPushButton):
    """Primary action button with precise SVG icon and text placement."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._label = text
        self._icon_pixmap = QPixmap()
        self.setMinimumHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(text)

    def text(self) -> str:
        return self._label

    def set_asset_icon(self, path: Path, color: str) -> None:
        icon_size = self.fontMetrics().height()
        self._icon_pixmap = _tinted_svg_pixmap(
            path,
            color,
            icon_size,
            widget=self,
        )
        self.update()

    def sizeHint(self) -> QSize:
        metrics = self.fontMetrics()
        icon_size = metrics.height()
        text_width = metrics.horizontalAdvance(self._label)
        first_character_width = metrics.horizontalAdvance(self._label[0])
        width = 8 + icon_size + 6 + text_width + first_character_width
        return QSize(max(88, width), 38)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event) -> None:
        del event
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.style().drawControl(
            QStyle.ControlElement.CE_PushButton,
            option,
            painter,
            self,
        )

        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self._label)
        first_character_width = metrics.horizontalAdvance(self._label[0])
        icon_size = (
            self._icon_pixmap.deviceIndependentSize().toSize()
            if not self._icon_pixmap.isNull()
            else QSize()
        )
        right_padding = first_character_width
        text_x = self.width() - right_padding - text_width
        gap = 6
        icon_x = max(8, text_x - gap - icon_size.width())

        icon_y = (self.height() - icon_size.height()) // 2
        if not self._icon_pixmap.isNull():
            painter.drawPixmap(
                QRectF(
                    icon_x,
                    icon_y,
                    icon_size.width(),
                    icon_size.height(),
                ),
                self._icon_pixmap,
                QRectF(
                    0,
                    0,
                    self._icon_pixmap.width(),
                    self._icon_pixmap.height(),
                ),
            )

        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            QRect(text_x, 0, text_width + 2, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._label,
        )
        painter.end()


class SvgActionButton(QPushButton):
    """Primary action button with a centered SVG icon and vertically aligned text."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._label = text
        self._icon_pixmap = QPixmap()
        self.setMinimumHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(text)

    def text(self) -> str:
        return self._label

    def setText(self, text: str) -> None:
        self._label = text
        self.setAccessibleName(text)
        self.update()

    def set_asset_icon(self, path: Path, color: str) -> None:
        icon_size = self.fontMetrics().height()
        self._icon_pixmap = _tinted_svg_pixmap(
            path,
            color,
            icon_size,
            widget=self,
        )
        self.update()

    def paintEvent(self, event) -> None:
        del event
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.style().drawControl(
            QStyle.ControlElement.CE_PushButton,
            option,
            painter,
            self,
        )

        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self._label)
        icon_size = (
            self._icon_pixmap.deviceIndependentSize().toSize()
            if not self._icon_pixmap.isNull()
            else QSize()
        )
        gap = 7
        group_width = icon_size.width() + gap + text_width
        group_left = (self.width() - group_width) // 2
        icon_y = (self.height() - icon_size.height()) // 2

        if not self._icon_pixmap.isNull():
            painter.drawPixmap(
                QRectF(
                    group_left,
                    icon_y,
                    icon_size.width(),
                    icon_size.height(),
                ),
                self._icon_pixmap,
                QRectF(
                    0,
                    0,
                    self._icon_pixmap.width(),
                    self._icon_pixmap.height(),
                ),
            )

        text_color = QColor("#ffffff") if self.isEnabled() else QColor("#94a3b8")
        painter.setPen(text_color)
        baseline = (self.height() - metrics.height()) // 2 + metrics.ascent()
        painter.drawText(
            group_left + icon_size.width() + gap,
            baseline,
            self._label,
        )
        painter.end()


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

    help_requested = Signal()

    def __init__(self, title: str, help_tooltip: str | None = None) -> None:
        super().__init__()
        self.toggle = QToolButton()
        self.toggle.setObjectName("SectionToggle")
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setFixedSize(18, 18)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("SectionTitle")

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        header_layout.addWidget(self.toggle)
        header_layout.addWidget(self.title_label)

        self.help_button: QToolButton | None = None
        if help_tooltip:
            self.help_button = HelpIconButton(
                help_tooltip,
                "InfoIconButton",
            )
            self.help_button.clicked.connect(self.help_requested.emit)
            header_layout.addWidget(self.help_button)
        header_layout.addStretch(1)

        self.content = QWidget()
        self.content_layout = QGridLayout(self.content)
        self.content_layout.setContentsMargins(0, 4, 0, 0)
        self.content_layout.setHorizontalSpacing(10)
        self.content_layout.setVerticalSpacing(10)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
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
        self.batch_running = False
        self.batch_cancelled = False
        self.batch_pending: list[str] = []
        self.batch_total = 0
        self.batch_index = 0
        self.batch_counts = {"success": 0, "failed": 0, "cancelled": 0, "skipped": 0}
        self._loading_conversion_settings = True
        self.format_help_dialog: FormatHelpDialog | None = None
        self.advanced_help_dialog: AdvancedHelpDialog | None = None
        self._footer_reset_timer = QTimer(self)
        self._footer_reset_timer.setSingleShot(True)
        self._footer_reset_timer.timeout.connect(self._restore_toolchain_status)
        self._batch_watchdog = QTimer(self)
        self._batch_watchdog.setInterval(400)
        self._batch_watchdog.timeout.connect(self._check_batch_progress)
        self.probe_service = MediaProbeService(self)
        self.probe_service.task_started.connect(self._on_task_probe_started)
        self.probe_service.task_finished.connect(self._on_task_probe_finished)
        self.thumbnail_service = ThumbnailService(
            default_thumbnail_cache_dir(),
            self,
        )
        self.thumbnail_service.task_started.connect(self._on_task_thumbnail_started)
        self.thumbnail_service.task_finished.connect(self._on_task_thumbnail_finished)
        self.conversion_runner = ConversionRunner(self)
        self.conversion_runner.started.connect(self._on_conversion_started)
        self.conversion_runner.progress.connect(self._on_conversion_progress)
        self.conversion_runner.log_line.connect(self._on_conversion_log)
        self.conversion_runner.finished.connect(self._on_conversion_finished)
        self.history_store = ConversionHistoryStore(default_history_path())
        self.history_records = self.history_store.load()
        self._history_source_key: str | None = None
        self.toolchain_detector = ToolchainDetector(self)
        self.toolchain_detector.started.connect(self._on_toolchain_detection_started)
        self.toolchain_detector.finished.connect(self._on_toolchain_detected)
        self.toolchain_status: ToolchainStatus | None = None

        self.setWindowTitle(f"{APP_NAME} - 视频转换器")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1280, 800)
        self.setMinimumSize(1080, 680)
        self.setAcceptDrops(True)
        self._restore_window_geometry()

        self._build_interface()
        self._refresh_history_list()
        self._install_wheel_guards()
        self._load_conversion_settings()
        self._apply_theme()
        self._install_shortcuts()
        QTimer.singleShot(0, self._restore_saved_tasks)
        QTimer.singleShot(0, self._detect_toolchain)

    def _restore_window_geometry(self) -> None:
        """Reuse the size, position and maximised state from the last session."""
        geometry = self.settings.value("ui/window_geometry")
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)

    def _save_window_geometry(self) -> None:
        self.settings.setValue("ui/window_geometry", self.saveGeometry())

    def _install_shortcuts(self) -> None:
        """Bind the everyday actions to keyboard shortcuts."""
        bindings = (
            ("Ctrl+O", self._choose_videos),
            ("Ctrl+Return", self._start_conversion),
            ("Ctrl+Enter", self._start_conversion),
            ("Ctrl+Shift+B", self._start_batch_conversion),
            ("Esc", self._cancel_conversion),
            ("Delete", self._delete_focused_task),
        )
        self.shortcuts: list[QShortcut] = []
        for sequence, handler in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)

    def _delete_focused_task(self) -> None:
        """Remove the selected task unless the user is typing in a field."""
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox, QComboBox)):
            return
        self._remove_selected_task()

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

        self.add_video_button = AddVideoButton("添加视频")
        self.add_video_button.setObjectName("PrimaryAction")
        self.add_video_button.setToolTip("添加视频文件（Ctrl+O）")
        self.add_video_button.clicked.connect(self._choose_videos)

        self.clear_button = AssetIconButton(
            "AssetIconButton",
            "清空全部任务",
        )
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self._clear_queue)

        self.theme_button = AssetIconButton(
            "AssetIconButton",
            "切换主题",
        )
        self.theme_button.clicked.connect(self._toggle_theme)

        self.settings_button = AssetIconButton(
            "AssetIconButton",
            "应用设置",
        )
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
        self.batch_progress_label = QLabel("")
        self.batch_progress_label.setProperty("muted", True)
        self.batch_progress_label.hide()
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.batch_progress_label)
        heading.addWidget(self.queue_count)

        self.task_list = QListWidget()
        self.task_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.task_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.task_list.currentItemChanged.connect(self._on_task_selected)
        self.task_delegate = TaskItemDelegate(get_palette(self.theme_name), self)
        self.task_list.setItemDelegate(self.task_delegate)
        self.task_stack = QStackedWidget()
        self.task_stack.addWidget(self._build_empty_queue())
        self.task_stack.addWidget(self.task_list)
        self.task_stack.setCurrentIndex(0)

        self.remove_button = QPushButton("移除选中")
        self.remove_button.setObjectName("SecondaryAction")
        self.remove_button.setToolTip("移除选中的任务（Delete）")
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
        self.empty_queue_icon.setFixedSize(56, 56)

        title = QLabel("队列为空")
        title.setObjectName("PanelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("导入视频后会显示在这里")
        hint.setProperty("muted", True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)

        layout.addWidget(
            self.empty_queue_icon,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
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
        self.regenerate_thumbnail_button = AssetIconButton(
            "AssetIconButton",
            "重新生成缩略图",
        )
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
        self.preview_stage.setMaximumHeight(420)
        self.preview_stage.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        preview_layout = QVBoxLayout(self.preview_stage)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.setSpacing(8)

        self.thumbnail_label = ThumbnailLabel()
        self.thumbnail_label.hide()

        self.preview_icon = QLabel()
        self.preview_icon.setObjectName("StageIcon")
        self.preview_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_icon.setFixedSize(72, 72)

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
        preview_message_layout.addWidget(
            self.preview_icon,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
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

        self.conversion_progress_frame = QFrame()
        self.conversion_progress_frame.setObjectName("ConversionProgress")
        progress_layout = QVBoxLayout(self.conversion_progress_frame)
        progress_layout.setContentsMargins(10, 9, 10, 9)
        progress_layout.setSpacing(6)

        progress_heading = QHBoxLayout()
        self.conversion_status_label = QLabel("转换进度")
        self.conversion_status_label.setObjectName("SectionLabel")
        self.conversion_detail_label = ElidedLabel("--")
        self.conversion_detail_label.setProperty("muted", True)
        self.conversion_detail_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        progress_heading.addWidget(self.conversion_status_label)
        progress_heading.addWidget(self.conversion_detail_label, 1)

        self.conversion_progress_bar = QProgressBar()
        self.conversion_progress_bar.setRange(0, 100)
        self.conversion_progress_bar.setValue(0)
        self.conversion_progress_bar.setTextVisible(True)

        result_actions = QHBoxLayout()
        result_actions.setSpacing(8)
        self.resume_conversion_button = QPushButton("恢复转换")
        self.resume_conversion_button.setObjectName("SecondaryAction")
        self.resume_conversion_button.setToolTip("从上次中断的位置继续转换")
        self.resume_conversion_button.clicked.connect(self._resume_conversion)
        self.resume_conversion_button.hide()
        self.clear_state_button = AssetIconButton(
            "AssetIconButton",
            "删除当前取消状态",
        )
        self.clear_state_button.clicked.connect(self._clear_conversion_state)
        self.clear_state_button.hide()
        self.open_file_button = QPushButton("打开文件")
        self.open_file_button.setObjectName("SecondaryAction")
        self.open_file_button.clicked.connect(self._open_output_file)
        self.open_folder_button = QPushButton("打开所在目录")
        self.open_folder_button.setObjectName("SecondaryAction")
        self.open_folder_button.clicked.connect(self._open_output_folder)
        result_actions.addWidget(self.resume_conversion_button)
        result_actions.addWidget(self.open_file_button)
        result_actions.addWidget(self.open_folder_button)
        result_actions.addStretch(1)
        result_actions.addWidget(self.clear_state_button)

        progress_layout.addLayout(progress_heading)
        progress_layout.addWidget(self.conversion_progress_bar)
        progress_layout.addLayout(result_actions)
        self.conversion_progress_frame.hide()

        self.conversion_log_section = CollapsibleSection("转换日志")
        self.conversion_log = QPlainTextEdit()
        self.conversion_log.setObjectName("CommandPreview")
        self.conversion_log.setReadOnly(True)
        self.conversion_log.setMaximumHeight(120)
        self.conversion_log_section.content_layout.addWidget(
            self.conversion_log,
            0,
            0,
            1,
            2,
        )
        self.conversion_log_section.hide()

        self.history_section = CollapsibleSection("转换历史")
        self.history_list = QListWidget()
        self.history_list.setObjectName("HistoryList")
        self.history_list.setMaximumHeight(210)
        self.history_list.setWordWrap(True)
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_list.itemDoubleClicked.connect(self._open_history_output_file)
        self.history_list.currentItemChanged.connect(lambda *_: self._update_history_buttons())

        self.history_open_button = QPushButton("打开记录文件")
        self.history_open_button.setObjectName("SecondaryAction")
        self.history_open_button.clicked.connect(self._open_history_output_file)
        self.history_folder_button = QPushButton("打开记录目录")
        self.history_folder_button.setObjectName("SecondaryAction")
        self.history_folder_button.clicked.connect(self._open_history_output_folder)
        self.history_delete_button = QPushButton("删除选中历史")
        self.history_delete_button.setObjectName("SecondaryAction")
        self.history_delete_button.clicked.connect(self._delete_selected_history)
        self.history_clear_button = QPushButton("清空该视频历史")
        self.history_clear_button.setObjectName("SecondaryAction")
        self.history_clear_button.clicked.connect(self._clear_history)

        history_actions = QHBoxLayout()
        history_actions.setSpacing(8)
        history_actions.addWidget(self.history_open_button)
        history_actions.addWidget(self.history_folder_button)
        history_actions.addWidget(self.history_delete_button)
        history_actions.addWidget(self.history_clear_button)
        history_actions.addStretch(1)

        self.history_section.content_layout.addWidget(
            self.history_list,
            0,
            0,
            1,
            2,
        )
        self.history_section.content_layout.addLayout(
            history_actions,
            1,
            0,
            1,
            2,
        )
        self.history_section.hide()

        layout.addLayout(heading)
        layout.addWidget(self.preview_stage, 1)
        layout.addWidget(metrics)
        layout.addWidget(source_row)
        layout.addWidget(self.conversion_progress_frame)
        layout.addWidget(self.conversion_log_section)
        layout.addWidget(self.history_section)

        scroll = QScrollArea()
        scroll.setObjectName("PreviewScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(panel)
        self.preview_scroll = scroll

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(scroll)
        return container

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
        self.settings_scroll = scroll

        content = QWidget()
        content.setMinimumWidth(0)
        self.settings_content = content
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(14)

        format_label = QLabel("目标格式")
        format_label.setObjectName("SectionLabel")
        self.format_help_button = HelpIconButton(
            "查看输出格式说明",
            "HelpIconButton",
        )
        self.format_help_button.clicked.connect(self._show_format_help)
        format_header = QHBoxLayout()
        format_header.setContentsMargins(0, 0, 0, 0)
        format_header.setSpacing(4)
        format_header.addWidget(format_label)
        format_header.addWidget(self.format_help_button)
        format_header.addStretch(1)
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
            button.setMinimumWidth(0)
            button.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            if name == "MP4":
                button.setChecked(True)
            self.format_group.addButton(button)
            self.format_buttons[name] = button
            format_grid.addWidget(button, index // 3, index % 3)
        for column in range(3):
            format_grid.setColumnStretch(column, 1)
        self.format_group.buttonToggled.connect(self._on_format_changed)

        basic_form = QGridLayout()
        basic_form.setContentsMargins(0, 0, 0, 0)
        basic_form.setHorizontalSpacing(10)
        basic_form.setVerticalSpacing(10)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(QUALITY_OPTIONS)
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(RESOLUTION_OPTIONS)
        self.resolution_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self.frame_rate_combo = QComboBox()
        self.frame_rate_combo.addItems(FRAME_RATE_OPTIONS)
        self.frame_rate_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self._add_form_row(basic_form, 0, "画质", self.quality_combo)
        self._add_form_row(basic_form, 1, "分辨率", self.resolution_combo)
        self._add_form_row(basic_form, 2, "帧率", self.frame_rate_combo)

        output_label = QLabel("输出目录")
        output_label.setObjectName("SectionLabel")
        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self.output_path = MarqueeLineEdit("默认：源文件旁的 converted")
        self.output_path.setReadOnly(True)
        self.browse_button = AssetIconButton(
            "AssetIconButton",
            "选择输出目录",
        )
        self.browse_button.clicked.connect(self._choose_output_directory)
        self.reset_output_button = AssetIconButton(
            "AssetIconButton",
            "恢复默认输出目录",
        )
        self.reset_output_button.clicked.connect(self._reset_output_directory)
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(self.browse_button)
        output_row.addWidget(self.reset_output_button)

        self.output_name_preview = ElidedLabel("输出：--")
        self.output_name_preview.setProperty("muted", True)
        self.duration_estimate_label = QLabel("预计转换时长：--")
        self.duration_estimate_label.setProperty("muted", True)

        advanced = CollapsibleSection(
            "高级设置",
            help_tooltip="查看高级参数说明",
        )
        self.advanced_section = advanced
        advanced.help_requested.connect(self._show_advanced_help)
        self.video_codec_combo = QComboBox()
        self.video_codec_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setSpecialValueText(NOT_APPLICABLE)
        self.crf_spin.setValue(23)
        self.crf_spin.valueChanged.connect(self._on_conversion_control_changed)
        self.audio_codec_combo = QComboBox()
        self.audio_codec_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self.audio_bitrate_combo = QComboBox()
        self.audio_bitrate_combo.addItems(AUDIO_BITRATE_OPTIONS)
        self.audio_bitrate_combo.currentTextChanged.connect(self._on_conversion_control_changed)
        self.keep_audio_checkbox = QCheckBox("保留音频")
        self.keep_audio_checkbox.setChecked(True)
        self.keep_audio_checkbox.toggled.connect(self._on_conversion_control_changed)
        for combo in (
            self.quality_combo,
            self.resolution_combo,
            self.frame_rate_combo,
            self.video_codec_combo,
            self.audio_codec_combo,
            self.audio_bitrate_combo,
        ):
            combo.setMinimumWidth(0)
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(5)
        self.crf_spin.setMinimumWidth(0)
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

        content_layout.addLayout(format_header)
        content_layout.addLayout(format_grid)
        content_layout.addLayout(basic_form)
        content_layout.addSpacing(2)
        content_layout.addWidget(output_label)
        content_layout.addLayout(output_row)
        content_layout.addWidget(self.output_name_preview)
        content_layout.addWidget(self.duration_estimate_label)
        content_layout.addWidget(advanced)
        content_layout.addWidget(command_section)
        content_layout.addStretch(1)
        scroll.setWidget(content)

        self.start_button = SvgActionButton("开始转换")
        self.start_button.setObjectName("PrimaryAction")
        self.start_button.setEnabled(False)
        self.start_button.setToolTip("请先导入视频")
        self.start_button.clicked.connect(self._start_conversion)

        self.cancel_button = QPushButton("取消转换")
        self.cancel_button.setObjectName("SecondaryAction")
        self.cancel_button.setToolTip("取消当前转换（Esc）")
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self._cancel_conversion)

        self.batch_button = QPushButton("批量转换")
        self.batch_button.setObjectName("SecondaryAction")
        self.batch_button.setToolTip("按当前设置依次转换队列中的全部视频（Ctrl+Shift+B）")
        self.batch_button.clicked.connect(self._start_batch_conversion)

        self.retry_button = QPushButton("重试失败项")
        self.retry_button.setObjectName("SecondaryAction")
        self.retry_button.setToolTip("只重新转换上一次失败的任务")
        self.retry_button.clicked.connect(self._retry_failed_tasks)
        self.retry_button.hide()

        bottom_actions = QHBoxLayout()
        bottom_actions.setSpacing(8)
        bottom_actions.addWidget(self.start_button, 3)
        bottom_actions.addWidget(self.batch_button, 1)
        bottom_actions.addWidget(self.retry_button, 1)
        bottom_actions.addWidget(self.cancel_button, 1)

        panel_layout.addLayout(heading)
        panel_layout.addWidget(scroll, 1)
        panel_layout.addLayout(bottom_actions)
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

    @staticmethod
    def _configure_combo(
        combo: QComboBox,
        options: tuple[str, ...],
        preferred: str | None = None,
        fallback: str | None = None,
    ) -> None:
        combo.clear()
        combo.addItems(options)
        if preferred in options:
            chosen = preferred
        elif fallback in options:
            chosen = fallback
        else:
            chosen = options[0]
        combo.setCurrentText(chosen)

    def _configure_quality_options(
        self,
        output_format: str,
        preferred: str | None = None,
    ) -> None:
        options = QUALITY_OPTIONS if output_format in {"MP4", "MKV", "WebM"} else (NOT_APPLICABLE,)
        self._configure_combo(
            self.quality_combo,
            options,
            preferred,
            "平衡（推荐）",
        )

    def _configure_resolution_options(
        self,
        output_format: str,
        preferred: str | None = None,
    ) -> None:
        options = (
            RESOLUTION_OPTIONS if output_format in {"MP4", "MKV", "WebM"} else (NOT_APPLICABLE,)
        )
        self._configure_combo(
            self.resolution_combo,
            options,
            preferred,
            "保持原始",
        )

    def _configure_frame_rate_options(
        self,
        output_format: str,
        preferred: str | None = None,
    ) -> None:
        options = (
            FRAME_RATE_OPTIONS if output_format in {"MP4", "MKV", "WebM"} else (NOT_APPLICABLE,)
        )
        self._configure_combo(
            self.frame_rate_combo,
            options,
            preferred,
            "保持原始",
        )

    def _configure_audio_bitrate_options(
        self,
        output_format: str,
        audio_codec: str,
        preferred: str | None = None,
    ) -> None:
        options = (
            (NOT_APPLICABLE,)
            if output_format in {"WAV", "GIF"} or audio_codec == "PCM"
            else AUDIO_BITRATE_OPTIONS
        )
        self._configure_combo(
            self.audio_bitrate_combo,
            options,
            preferred,
            "192 kbps",
        )

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
            self._configure_quality_options(output_format)
            self._configure_resolution_options(output_format)
            self._configure_frame_rate_options(output_format)
            self._configure_audio_bitrate_options(
                output_format,
                self.audio_codec_combo.currentText(),
            )
            if output_format in {"MP4", "MKV", "WebM"}:
                self.crf_spin.setValue(23)
            else:
                self.crf_spin.setValue(0)
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
            resolution=self._numeric_option(self.resolution_combo.currentText()),
            frame_rate=self._numeric_option(self.frame_rate_combo.currentText()),
            video_codec=self.video_codec_combo.currentText(),
            audio_codec=self.audio_codec_combo.currentText(),
            audio_bitrate=self.audio_bitrate_combo.currentText(),
            crf=self.crf_spin.value(),
            keep_audio=self.keep_audio_checkbox.isChecked(),
        )

    @staticmethod
    def _numeric_option(value: str) -> str:
        """Map disabled placeholder options back to the canonical "keep original" value."""
        return "保持原始" if value == NOT_APPLICABLE else value

    def _load_conversion_settings(self) -> None:
        self._loading_conversion_settings = True
        output_format = str(self.settings.value("conversion/format", "MP4"))
        if output_format not in self.format_buttons:
            output_format = "MP4"
        self.format_buttons[output_format].setChecked(True)

        saved_video = str(self.settings.value("conversion/video_codec", ""))
        saved_audio = str(self.settings.value("conversion/audio_codec", ""))
        self._configure_format_options(output_format, saved_video, saved_audio)
        self._configure_quality_options(
            output_format,
            str(self.settings.value("conversion/quality", "平衡（推荐）")),
        )
        self._configure_resolution_options(
            output_format,
            str(self.settings.value("conversion/resolution", "保持原始")),
        )
        self._configure_frame_rate_options(
            output_format,
            str(self.settings.value("conversion/frame_rate", "保持原始")),
        )
        self._configure_audio_bitrate_options(
            output_format,
            self.audio_codec_combo.currentText(),
            str(self.settings.value("conversion/audio_bitrate", "192 kbps")),
        )
        default_crf = 23 if output_format in {"MP4", "MKV", "WebM"} else 0
        self.crf_spin.setValue(self._settings_int("conversion/crf", default_crf))
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
        if task is not None and task.media_info is not None:
            estimated_seconds = estimate_conversion_seconds(
                settings,
                task.media_info.duration_seconds,
                task.media_info.width,
                task.media_info.height,
                task.media_info.frame_rate,
            )
            estimate_text = (
                f"约 {self._format_duration(estimated_seconds)}"
                if estimated_seconds is not None
                else "--"
            )
        else:
            estimate_text = "--"
        self.duration_estimate_label.setText(f"预计转换时长：{estimate_text}")
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

        self.batch_status_label = QLabel("")
        self.batch_status_label.setProperty("muted", True)
        self.batch_status_label.hide()

        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setObjectName("FooterProgress")
        self.batch_progress_bar.setRange(0, 100)
        self.batch_progress_bar.setValue(0)
        self.batch_progress_bar.setTextVisible(False)
        self.batch_progress_bar.setFixedSize(120, 6)
        self.batch_progress_bar.hide()

        stage_label = QLabel("开发阶段 · 步骤 10")
        stage_label.setProperty("muted", True)

        layout.addWidget(self.status_dot)
        layout.addWidget(self.footer_status_label)
        layout.addStretch(1)
        layout.addWidget(self.batch_status_label)
        layout.addWidget(self.batch_progress_bar)
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
        self._import_paths(paths, show_issue_dialog=True)

    def _import_paths(
        self,
        paths: list[str],
        show_feedback: bool = True,
        persist: bool = True,
        show_issue_dialog: bool = False,
    ) -> None:
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
        if persist:
            self._save_task_paths()

        if show_feedback:
            message, details, state = self._import_feedback(result)
            self._show_footer_message(
                message,
                details=details,
                state=state,
                timeout=6000,
            )
        if show_issue_dialog and result.issues:
            self._show_import_issues(result)

    def _restore_saved_tasks(self) -> None:
        saved_paths = self.settings.value("tasks/paths", [])
        if isinstance(saved_paths, str):
            paths = [saved_paths] if saved_paths else []
        elif isinstance(saved_paths, (list, tuple)):
            paths = [str(path) for path in saved_paths if path]
        else:
            paths = []
        if not paths:
            return
        self._import_paths(paths, show_feedback=False, persist=False)
        self._save_task_paths()
        restored = self._restore_resume_state()
        if restored:
            self._show_footer_message(
                f"检测到 {restored} 个上次中断的转换，可点击“继续转换”接着完成",
                timeout=10000,
            )

    def _save_task_paths(self) -> None:
        self.settings.setValue(
            "tasks/paths",
            [str(task.path) for task in self.tasks.values()],
        )

    def _warning_dialog(self, title: str, text: str) -> QMessageBox:
        """Build a themed warning dialog with the bundled warning icon."""
        palette = get_palette(self.theme_name)
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIconPixmap(
            _tinted_svg_pixmap(
                WARNING_ICON_PATH,
                # Light theme keeps the black icon from the SVG file;
                # a dark background needs a light tint to stay readable.
                None if palette.name == "light" else palette.text,
                MESSAGE_ICON_SIZE,
                widget=self,
            )
        )
        dialog.setText(text)
        _center_message_text(dialog)
        return dialog

    def _show_import_issues(self, result: ImportResult) -> None:
        if result.added:
            text = f"已导入 {len(result.added)} 个视频，但部分文件不支持或无法访问。"
        else:
            text = "拖入的文件中没有可导入的视频。"
        dialog = self._warning_dialog("文件未导入", text)
        dialog.setInformativeText("仅支持常见视频文件，例如 MP4、MKV、MOV、AVI、WebM。")
        dialog.setDetailedText(
            "\n".join(f"{issue.path.name or issue.path}：{issue.reason}" for issue in result.issues)
        )
        dialog.addButton("知道了", QMessageBox.ButtonRole.AcceptRole)
        dialog.exec()

    def _create_task_item(self, task: MediaTask) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, task.key)
        item.setToolTip(str(task.path))
        item.setSizeHint(QSize(0, 62))
        item.setIcon(self._task_icon(task.status))
        self.task_list.addItem(item)
        self.task_items[task.key] = item
        self._update_task_item(task)
        return item

    def _task_icon(self, status: TaskStatus) -> QIcon:
        palette = get_palette(self.theme_name)
        return QIcon(
            _tinted_svg_pixmap(
                FILE_ICON_PATH,
                status_color(status, palette),
                24,
                widget=self,
            )
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
        self._refresh_history_list()

    def _apply_task_to_preview(self, task: MediaTask) -> None:
        # Bind the history panel first: a later failure must not leave it showing
        # the records of the previously selected video.
        self._sync_history_panel()
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
            if task.probe_error:
                self.media_status.setText("读取失败")
                self.preview_hint.setText(task.probe_error)
            else:
                self.media_status.setText("转换失败")
                self.preview_hint.setText(task.conversion_error or "视频转换失败")
        elif task.status == TaskStatus.CONVERTING:
            self.media_status.setText("转换中")
            self.preview_hint.setText(f"转换进度 {task.conversion_progress:.0f}%")
        elif task.status == TaskStatus.COMPLETED:
            self.media_status.setText("已完成")
            self.preview_hint.setText("视频转换完成")
        elif task.status == TaskStatus.CANCELLED:
            self.media_status.setText("已取消")
            self.preview_hint.setText("转换已取消")
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
        self._apply_conversion_to_preview(task)
        self._update_output_preview()

    def _sync_history_panel(self) -> None:
        """Keep the history panel bound to the current task, whatever happened before."""
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        source_key = task.content_signature if task is not None else None
        if source_key != self._history_source_key:
            self._refresh_history_list()

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
        self.conversion_progress_frame.hide()
        self.conversion_log_section.hide()
        self.conversion_log.clear()
        self.history_section.hide()
        self.history_list.clear()
        self.resume_conversion_button.hide()
        self.clear_state_button.hide()
        self._update_conversion_controls()

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

    def _apply_conversion_to_preview(self, task: MediaTask) -> None:
        has_conversion_state = task.status in {
            TaskStatus.CONVERTING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
        if task.status == TaskStatus.FAILED and task.probe_error:
            has_conversion_state = False
        if has_conversion_state:
            self.conversion_progress_frame.show()
            self.conversion_progress_bar.setValue(_progress_percent(task.conversion_progress))
        else:
            self.conversion_progress_frame.hide()

        if task.status == TaskStatus.CONVERTING:
            details: list[str] = []
            if task.conversion_speed:
                details.append(task.conversion_speed)
            if task.conversion_eta_seconds is not None:
                details.append(f"剩余 {self._format_duration(task.conversion_eta_seconds)}")
            self.conversion_status_label.setText("正在转换")
            self.conversion_detail_label.setText(" · ".join(details) or "准备中")
        elif task.status == TaskStatus.COMPLETED:
            self.conversion_progress_bar.setValue(100)
            self.conversion_status_label.setText("转换完成")
            output_text = task.output_path.name if task.output_path else "--"
            if task.output_path and task.output_path.is_file():
                output_text += f" · {format_file_size(task.output_path.stat().st_size)}"
            self.conversion_detail_label.setText(output_text)
        elif task.status == TaskStatus.CANCELLED:
            self.conversion_status_label.setText("已取消")
            if self._has_kept_progress(task):
                self.conversion_detail_label.setText(
                    f"已保留 {task.conversion_progress:.0f}% 进度，可继续转换"
                )
            elif task.conversion_resumable:
                self.conversion_detail_label.setText("可继续转换")
            else:
                self.conversion_detail_label.setText("未生成输出文件")
        elif task.status == TaskStatus.FAILED:
            self.conversion_status_label.setText("转换失败")
            self.conversion_detail_label.setText(task.conversion_error or "未知错误")

        has_output = (
            task.status == TaskStatus.COMPLETED
            and task.output_path is not None
            and task.output_path.is_file()
        )
        cancelled = task.status == TaskStatus.CANCELLED
        self.resume_conversion_button.setVisible(cancelled)
        if task.conversion_resumable:
            self.resume_conversion_button.setText("继续转换")
            self.resume_conversion_button.setToolTip("从上次中断的位置继续转换")
        else:
            self.resume_conversion_button.setText("重新转换")
            self.resume_conversion_button.setToolTip("从开始重新执行转换")
        clearable = task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
        self.clear_state_button.setVisible(clearable)
        self.clear_state_button.setToolTip(
            "清除完成状态，输出文件会保留"
            if task.status == TaskStatus.COMPLETED
            else "删除当前取消状态"
        )
        self.open_file_button.setVisible(has_output)
        self.open_folder_button.setVisible(has_output)

        if task.conversion_log:
            self.conversion_log_section.show()
            self.conversion_log.setPlainText(task.conversion_log)
            if task.status == TaskStatus.FAILED:
                self.conversion_log_section.toggle.setChecked(True)
        else:
            self.conversion_log_section.hide()
            self.conversion_log.clear()
        self._update_conversion_controls()

    def _update_conversion_controls(self) -> None:
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        running = self.conversion_runner.is_running
        can_start = (
            task is not None
            and task.media_info is not None
            and self._available_ffmpeg_path() is not None
            and not running
            and not self.batch_running
        )
        self.start_button.setEnabled(can_start)
        if task is not None and task.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            self.start_button.setText("重新转换")
        else:
            self.start_button.setText("开始转换")

        if task is None:
            self.start_button.setToolTip("请先导入视频")
        elif task.media_info is None:
            self.start_button.setToolTip("请等待媒体信息读取完成")
        elif self._available_ffmpeg_path() is None:
            self.start_button.setToolTip("FFmpeg 环境未就绪")
        elif running:
            self.start_button.setToolTip("当前已有转换任务正在执行")
        else:
            self.start_button.setToolTip("使用当前设置转换所选视频（Ctrl+Enter）")

        self.cancel_button.setVisible(running)
        self.cancel_button.setEnabled(running)
        self.cancel_button.setText("取消全部" if self.batch_running else "取消转换")
        self.start_button.setVisible(True)
        if self.batch_running:
            self.start_button.setToolTip("批量转换进行中，请先取消或等待完成")
        self.batch_button.setVisible(True)
        self.batch_button.setEnabled(
            not running
            and not self.batch_running
            and self._available_ffmpeg_path() is not None
            and any(task.media_info is not None for task in self.tasks.values())
        )
        self.batch_button.setToolTip(
            "批量转换进行中" if self.batch_running else "按当前设置依次转换队列中的全部视频"
        )
        show_retry = not running and not self.batch_running and bool(self._failed_tasks())
        self.retry_button.setVisible(show_retry)
        self.retry_button.setEnabled(show_retry)

    def _start_conversion(self) -> None:
        if self.conversion_runner.is_running:
            return False
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        ffmpeg_path = self._available_ffmpeg_path()
        if task is None or task.media_info is None or ffmpeg_path is None:
            self._update_conversion_controls()
            return False
        if task.status == TaskStatus.CONVERTING:
            return False
        if not task.path.is_file():
            task.status = TaskStatus.FAILED
            task.conversion_error = SOURCE_MISSING
            self._discard_conversion_parts(task)
            self._update_task_item(task)
            if self._current_task_key() == task.key:
                self._apply_task_to_preview(task)
            self._show_footer_message(
                f"{task.display_name}：{SOURCE_MISSING}",
                state="error",
                timeout=8000,
            )
            return False

        settings = self._current_conversion_settings()
        task.conversion_format = settings.output_format
        task.conversion_summary = self._conversion_settings_summary(settings)
        try:
            self.conversion_runner.start(
                task,
                settings,
                self.output_directory,
                ffmpeg_path,
            )
        except (OSError, RuntimeError, ValueError) as error:
            task.status = TaskStatus.FAILED
            task.conversion_error = str(error)
            self._update_task_item(task)
            self._apply_task_to_preview(task)
            self._show_footer_message(
                f"无法开始转换：{error}",
                state="error",
                timeout=6000,
            )
            return False
        return True

    def _tasks_in_list_order(self) -> list[MediaTask]:
        """Return queued tasks in the order shown in the queue list."""
        ordered: list[MediaTask] = []
        for index in range(self.task_list.count()):
            item = self.task_list.item(index)
            task = self.tasks.get(str(item.data(Qt.ItemDataRole.UserRole)))
            if task is not None:
                ordered.append(task)
        return ordered

    def _start_batch_conversion(self) -> None:
        """Ask which videos to convert, confirm the settings, then run them in order."""
        if self.batch_running or self.conversion_runner.is_running:
            return
        if self._available_ffmpeg_path() is None:
            self._show_footer_message(
                "FFmpeg 环境未就绪，无法批量转换",
                state="error",
                timeout=6000,
            )
            return

        queued = self._tasks_in_list_order()
        if not queued:
            self._show_footer_message(
                "任务队列为空，请先导入视频",
                state="error",
                timeout=6000,
            )
            return
        if not any(task.media_info is not None for task in queued):
            self._show_footer_message(
                "队列中没有可转换的视频，请等待媒体信息读取完成",
                state="error",
                timeout=6000,
            )
            return

        selected: list[MediaTask] = []
        while True:
            chosen = self._ask_batch_selection(queued)
            if chosen is None:
                return
            selected = [task for task in queued if task.key in chosen]
            if self._ask_batch_confirmation(selected):
                break
        skipped = sum(1 for task in queued if task.media_info is None)
        self._begin_batch([task.key for task in selected], skipped)

    def _begin_batch(self, task_keys: list[str], skipped: int = 0) -> None:
        """Start a batch run over the given task keys, in queue order."""
        self.batch_pending = list(task_keys)
        self.batch_total = len(task_keys)
        self.batch_index = 0
        self.batch_cancelled = False
        self.batch_counts = {
            "success": 0,
            "failed": 0,
            "cancelled": 0,
            "skipped": skipped,
        }
        self.batch_running = True
        self._batch_watchdog.start()
        self._update_batch_progress()
        self._update_conversion_controls()
        self._start_next_batch_task()

    def _failed_tasks(self) -> list[MediaTask]:
        """Return queued tasks whose last conversion attempt failed."""
        return [
            task
            for task in self._tasks_in_list_order()
            if task.status == TaskStatus.FAILED and task.media_info is not None
        ]

    def _retry_failed_tasks(self) -> None:
        """Re-run only the tasks that failed, with the current settings."""
        if self.batch_running or self.conversion_runner.is_running:
            return
        failed = self._failed_tasks()
        if not failed:
            self._show_footer_message("队列中没有失败的转换任务", timeout=4000)
            return
        if self._available_ffmpeg_path() is None:
            self._show_footer_message(
                "FFmpeg 环境未就绪，无法重试",
                state="error",
                timeout=6000,
            )
            return
        if not self._ask_batch_confirmation(failed):
            return
        self._begin_batch([task.key for task in failed])

    def _ask_batch_selection(self, queued: list[MediaTask]) -> set[str] | None:
        """Show the checkbox dialog and return the chosen task keys."""
        candidates = []
        for task in queued:
            if task.media_info is None:
                reason = "媒体信息尚未读取完成，本次不参与批量转换"
                detail = f"{task.extension} · {format_file_size(task.size_bytes)}"
            else:
                reason = ""
                detail = (
                    f"{task.extension} · {format_file_size(task.size_bytes)} · {task.status_text}"
                )
            candidates.append(
                BatchCandidate(
                    task_key=task.key,
                    name=task.display_name,
                    detail=detail,
                    checked=task.status != TaskStatus.COMPLETED,
                    reason=reason,
                )
            )
        dialog = BatchSelectionDialog(candidates, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        chosen = dialog.selected_keys
        return set(chosen) if chosen else None

    def _ask_batch_confirmation(self, selected: list[MediaTask]) -> bool:
        """Show the settings summary; return True when the user confirms."""
        settings = self._current_conversion_settings()
        output_directory = str(
            self.output_directory
            if self.output_directory is not None
            else (selected[0].path.parent / "converted")
        )
        dialog = BatchConfirmDialog(
            len(selected),
            self._batch_settings_rows(settings),
            output_directory,
            self,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    @staticmethod
    def _batch_settings_rows(settings: ConversionSettings) -> list[tuple[str, str]]:
        """Describe every setting the batch run will apply."""
        rows = [
            ("输出格式", settings.output_format),
            ("画质", settings.quality),
            ("分辨率", settings.resolution),
            ("帧率", settings.frame_rate),
        ]
        if settings.video_codec:
            rows.append(("视频编码", settings.video_codec))
            rows.append(("CRF", str(settings.crf)))
        if settings.output_format in {"GIF"}:
            rows.append(("音频", "不适用"))
        elif settings.keep_audio:
            rows.append(("音频编码", settings.audio_codec))
            if settings.audio_codec != "PCM":
                rows.append(("音频码率", settings.audio_bitrate))
        else:
            rows.append(("音频", "不保留音频"))
        return rows

    def _check_batch_progress(self) -> None:
        """Keep a batch moving even if one of its handlers failed mid-flight."""
        if not self.batch_running:
            self._batch_watchdog.stop()
            return
        if self.conversion_runner.is_running:
            return
        self._start_next_batch_task()

    def _start_next_batch_task(self) -> None:
        if not self.batch_running:
            return
        while self.batch_pending:
            task_key = self.batch_pending.pop(0)
            task = self.tasks.get(task_key)
            item = self.task_items.get(task_key)
            if task is None or item is None:
                self.batch_counts["skipped"] += 1
                continue
            self.task_list.setCurrentItem(item)
            self.batch_index += 1
            self._update_batch_progress()
            if self._start_conversion():
                return
            self.batch_counts["skipped"] += 1
        self._finish_batch()

    def _advance_batch(self, result: ConversionResult) -> None:
        if result.success:
            self.batch_counts["success"] += 1
        elif result.cancelled:
            self.batch_counts["cancelled"] += 1
        else:
            self.batch_counts["failed"] += 1
        QTimer.singleShot(0, self._start_next_batch_task)

    def _finish_batch(self, aborted: bool = False) -> None:
        total = self.batch_total
        counts = dict(self.batch_counts)
        cancelled = self.batch_cancelled
        self.batch_running = False
        self.batch_cancelled = False
        self.batch_pending.clear()
        self.batch_total = 0
        self.batch_index = 0
        self._batch_watchdog.stop()
        self._update_batch_progress()
        self._update_conversion_controls()
        if aborted:
            return

        details = [f"成功 {counts['success']}"]
        if counts["failed"]:
            details.append(f"失败 {counts['failed']}")
        if counts["cancelled"]:
            details.append(f"已取消 {counts['cancelled']}")
        if counts["skipped"]:
            details.append(f"跳过 {counts['skipped']}")
        summary = " · ".join(details)
        self._show_footer_message(
            f"{'已取消批量转换' if cancelled else '批量转换完成'}（共 {total} 个）：{summary}",
            state="error" if counts["failed"] else "ready",
            timeout=10000,
        )

    def _update_batch_progress(self) -> None:
        if not self.batch_running:
            self.batch_progress_label.setText("")
            self.batch_progress_label.hide()
            self.batch_status_label.hide()
            self.batch_progress_bar.hide()
            return
        self.batch_progress_label.setText(f"批量 {self.batch_index}/{self.batch_total}")
        self.batch_progress_label.show()
        self._refresh_footer_batch_progress()
        self.batch_status_label.show()
        self.batch_progress_bar.show()

    def _refresh_footer_batch_progress(self, current_percent: float | None = None) -> None:
        """Show overall batch progress in the footer while a batch is running."""
        if not self.batch_running:
            return
        finished = max(0, self.batch_index - 1)
        if current_percent is None:
            task_key = self._current_task_key()
            task = self.tasks.get(task_key) if task_key else None
            current_percent = task.conversion_progress if task is not None else 0.0
        overall = (finished + min(100.0, max(0.0, current_percent)) / 100) / self.batch_total
        self.batch_status_label.setText(
            f"批量 {self.batch_index}/{self.batch_total} · 当前 {current_percent:.0f}%",
        )
        self.batch_progress_bar.setValue(round(overall * 100))

    def _abort_batch(self) -> None:
        """Drop batch bookkeeping, for example when the queue is cleared."""
        if not self.batch_running:
            return
        self._finish_batch(aborted=True)

    @staticmethod
    def _conversion_settings_summary(settings: ConversionSettings) -> str:
        parts = [settings.output_format]
        if settings.video_codec:
            parts.append(settings.video_codec)
        if settings.output_format in {"MP4", "MKV", "WebM"}:
            parts.append(f"CRF {settings.crf}")
        if settings.audio_codec:
            parts.append(settings.audio_codec)
        return " · ".join(parts)

    def _cancel_conversion(self) -> None:
        if not self.conversion_runner.is_running:
            return
        if self.batch_running:
            self.batch_cancelled = True
            self.batch_pending.clear()
            self._update_batch_progress()
        self.cancel_button.setEnabled(False)
        self.conversion_status_label.setText("正在取消")
        self.conversion_runner.cancel()

    def _resume_conversion(self) -> None:
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        if task is None or task.status != TaskStatus.CANCELLED:
            return
        task.status = TaskStatus.METADATA_READY
        task.conversion_error = None
        task.conversion_speed = None
        task.conversion_eta_seconds = None
        task.output_path = None
        if not task.conversion_resumable:
            self._discard_conversion_parts(task)
            task.conversion_progress = 0.0
        self._update_task_item(task)
        self._apply_task_to_preview(task)
        self._start_conversion()

    def _clear_conversion_state(self) -> None:
        """Drop a finished conversion so the task looks freshly imported."""
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        if task is None or task.status not in {
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        }:
            return
        was_completed = task.status == TaskStatus.COMPLETED
        had_parts = not was_completed and self._has_kept_progress(task)
        if had_parts and not self._confirm_discard_progress(task):
            return
        self._discard_conversion_parts(task)
        task.conversion_error = None
        task.conversion_summary = None
        task.conversion_format = None
        task.conversion_progress = 0.0
        task.conversion_speed = None
        task.conversion_eta_seconds = None
        task.conversion_log = ""
        task.output_path = None
        task.status = TaskStatus.METADATA_READY
        self._update_task_item(task)
        self._apply_task_to_preview(task)
        if was_completed:
            message = "已清除完成状态，输出文件仍然保留"
        elif had_parts:
            message = "已清除取消状态和保留进度"
        else:
            message = "已清除取消状态"
        self._show_footer_message(message, timeout=4000)

    def _confirm_discard_progress(self, task: MediaTask) -> bool:
        """Warn before dropping the segments kept by a cancelled conversion."""
        dialog = self._warning_dialog(
            "删除取消状态",
            f"该任务保留了约 {task.conversion_progress:.0f}% 的转换进度。",
        )
        dialog.setInformativeText("删除后已保留的进度会被清除，下次转换需要从头开始。")
        delete_button = dialog.addButton(
            "删除进度",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is delete_button

    @staticmethod
    def _has_kept_progress(task: MediaTask) -> bool:
        """True once a resumable cancellation has at least one finished segment."""
        return task.conversion_resumable and task.conversion_parts_completed > 0

    def _discard_conversion_parts(self, task: MediaTask) -> None:
        """Remove leftover segment files and their bookkeeping."""
        if task.conversion_part_dir is not None:
            shutil.rmtree(task.conversion_part_dir, ignore_errors=True)
        task.conversion_part_dir = None
        task.conversion_parts_completed = 0
        task.conversion_settings_key = ""
        task.conversion_resumable = False
        self._forget_resume_dir(task.content_signature)

    def _resume_map(self) -> dict[str, dict[str, object]]:
        """Read the persisted ``源视频 -> 分段目录`` table."""
        raw = self.settings.value(RESUME_DIRS_KEY, "")
        if isinstance(raw, str) and raw.strip():
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            if isinstance(payload, dict):
                return {
                    str(key): value for key, value in payload.items() if isinstance(value, dict)
                }
        return {}

    def _write_resume_map(self, mapping: dict[str, dict[str, object]]) -> None:
        self.settings.setValue(
            RESUME_DIRS_KEY,
            json.dumps(mapping, ensure_ascii=False) if mapping else "",
        )

    def _remember_resume_dir(self, task: MediaTask) -> None:
        """Persist the segment directory so a restart can offer to continue."""
        if task.conversion_part_dir is None:
            return
        mapping = self._resume_map()
        mapping[task.content_signature] = {
            "dir": str(task.conversion_part_dir),
            "settings": task.conversion_settings_key,
            "parts": task.conversion_parts_completed,
        }
        self._write_resume_map(mapping)

    def _forget_resume_dir(self, source_key: str) -> None:
        mapping = self._resume_map()
        if mapping.pop(source_key, None) is not None:
            self._write_resume_map(mapping)

    def _restore_resume_state(self) -> int:
        """Bring back the segments left behind by a conversion the app was closed on."""
        mapping = self._resume_map()
        if not mapping:
            return 0
        restored = 0
        for task in self.tasks.values():
            entry = mapping.get(task.content_signature)
            if not isinstance(entry, dict):
                continue
            part_dir = Path(str(entry.get("dir", "")))
            parts = [path for path in part_dir.glob("part_*") if path.is_file()]
            if not parts:
                self._forget_resume_dir(task.content_signature)
                continue
            if task.conversion_part_dir != part_dir:
                task.conversion_part_dir = part_dir
                task.conversion_settings_key = str(entry.get("settings", ""))
                task.conversion_parts_completed = len(parts)
                task.conversion_resumable = True
                restored += 1
            if task.media_info is None:
                # ffprobe has not run yet; keep the queue state so it still gets read.
                continue
            task.status = TaskStatus.CANCELLED
            task.conversion_error = "上次转换被中断，可点击“继续转换”接着完成"
            duration = task.media_info.duration_seconds
            if duration and duration > 0:
                task.conversion_progress = min(
                    99.9,
                    len(parts) * SEGMENT_DURATION_SECONDS / duration * 100,
                )
            self._update_task_item(task)
            if self._current_task_key() == task.key:
                self._apply_task_to_preview(task)
        return restored

    def _on_conversion_started(self, task_key: str, output_path: object) -> None:
        task = self.tasks.get(task_key)
        if task is None:
            return
        resuming = task.conversion_resumable
        task.status = TaskStatus.CONVERTING
        task.output_path = Path(output_path)
        if not resuming:
            task.conversion_progress = 0.0
        task.conversion_speed = None
        task.conversion_eta_seconds = None
        task.conversion_log = ""
        task.conversion_error = None
        self._update_task_item(task)
        if self._current_task_key() == task_key:
            self._apply_task_to_preview(task)
        if self.batch_running:
            self._show_footer_message(
                f"批量转换 {self.batch_index}/{self.batch_total}：{task.display_name}",
                timeout=0,
            )
            return
        self._show_footer_message(
            f"正在转换 {task.display_name}",
            timeout=0,
        )

    def _on_conversion_progress(self, progress: ConversionProgress) -> None:
        task = self.tasks.get(progress.task_key)
        if task is None:
            return
        task.conversion_progress = float(_progress_percent(progress.percent))
        task.conversion_speed = progress.speed
        task.conversion_eta_seconds = progress.eta_seconds
        self._update_task_item(task)
        self._refresh_footer_batch_progress(task.conversion_progress)
        if self._current_task_key() == progress.task_key:
            self._apply_conversion_to_preview(task)

    def _on_conversion_log(self, task_key: str, text: str) -> None:
        task = self.tasks.get(task_key)
        if task is None:
            return
        task.conversion_log += text
        if self._current_task_key() == task_key:
            self.conversion_log_section.show()
            self.conversion_log.setPlainText(task.conversion_log)
            scroll_bar = self.conversion_log.verticalScrollBar()
            scroll_bar.setValue(scroll_bar.maximum())

    def _on_conversion_finished(self, result: ConversionResult) -> None:
        self._record_conversion_history(result)
        task = self.tasks.get(result.task_key)
        if task is None:
            if self.batch_running:
                self._advance_batch(result)
            return
        task.conversion_resumable = result.can_resume
        task.output_path = result.output_path
        task.conversion_log = result.log
        task.conversion_speed = None
        task.conversion_eta_seconds = None
        if result.cancelled:
            task.status = TaskStatus.CANCELLED
            task.conversion_error = "转换已取消"
            task.conversion_progress = result.progress_percent
            if not result.can_resume:
                self._discard_conversion_parts(task)
            footer_message = f"已取消转换 {task.display_name}"
        elif result.success:
            task.status = TaskStatus.COMPLETED
            task.conversion_progress = 100.0
            task.conversion_error = None
            footer_message = f"转换完成：{result.output_path.name}"
        else:
            task.status = TaskStatus.FAILED
            task.conversion_error = result.error or "转换失败"
            footer_message = f"转换失败：{task.display_name}"

        if task.conversion_resumable and task.conversion_part_dir is not None:
            self._remember_resume_dir(task)
        else:
            self._forget_resume_dir(task.content_signature)

        self._update_task_item(task)
        if self._current_task_key() == task.key:
            self._apply_task_to_preview(task)
        else:
            self._update_conversion_controls()
        if self.batch_running:
            self._advance_batch(result)
            return
        self._show_footer_message(
            footer_message,
            details=task.conversion_error or "",
            state="error" if task.status == TaskStatus.FAILED else "ready",
            timeout=6000,
        )

    def _open_output_file(self) -> None:
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        if task is None or task.output_path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(task.output_path)))

    def _open_output_folder(self) -> None:
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        if task is None or task.output_path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(task.output_path.parent)))

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total_seconds = max(0, round(seconds))
        minutes, remaining_seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{remaining_seconds:02d}"

    def _record_conversion_history(self, result: ConversionResult) -> None:
        if result.cancelled:
            status = "已取消"
        elif result.success:
            status = "已完成"
        else:
            status = "失败"
        file_size = None
        if result.success and result.output_path.is_file():
            try:
                file_size = result.output_path.stat().st_size
            except OSError:
                file_size = None

        record = ConversionHistoryRecord(
            record_id=uuid4().hex,
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            source_key=result.source_key,
            source_path=result.source_path,
            output_path=result.output_path,
            output_format=result.output_format or result.output_path.suffix.lstrip(".").upper(),
            status=status,
            error=result.error,
            file_size=file_size,
            elapsed_seconds=result.elapsed_seconds,
        )
        try:
            self.history_records = self.history_store.add(record)
        except OSError:
            self._show_footer_message(
                "转换已完成，但历史记录保存失败",
                state="error",
                timeout=6000,
            )
            return
        self._refresh_history_list(expand=True)

    def _refresh_history_list(self, expand: bool = False) -> None:
        self.history_list.clear()
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        self._history_source_key = task.content_signature if task is not None else None
        records = (
            self._history_records_for_source(task.content_signature) if task is not None else []
        )
        if task is not None:
            self.history_section.title_label.setText(f"转换历史 · {task.display_name}")
        else:
            self.history_section.title_label.setText("转换历史")

        for record in records:
            try:
                timestamp = datetime.fromisoformat(record.timestamp).strftime("%m-%d %H:%M")
            except ValueError:
                timestamp = record.timestamp
            size_text = (
                f" · {format_file_size(record.file_size)}" if record.file_size is not None else ""
            )
            elapsed_text = self._format_duration(record.elapsed_seconds)
            item = QListWidgetItem(
                f"{record.output_format}  →  {record.output_path.name}\n"
                f"{record.output_directory}\n"
                f"{timestamp} · {record.status}{size_text}\n"
                f"转换耗时 {elapsed_text}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record.record_id)
            item.setToolTip(
                f"源文件：{record.source_path}\n"
                f"输出文件：{record.output_path}\n"
                f"转换类型：{record.output_format}\n"
                f"状态：{record.status}\n"
                f"转换耗时：{elapsed_text}" + (f"\n原因：{record.error}" if record.error else "")
            )
            self.history_list.addItem(item)

        self.history_section.setVisible(bool(records))
        if records and self.history_list.currentItem() is None:
            self.history_list.setCurrentRow(0)
        if expand and records:
            self.history_section.toggle.setChecked(True)
            QTimer.singleShot(0, self._scroll_to_history)
        self._update_history_buttons()

    def _scroll_to_history(self) -> None:
        self.preview_scroll.ensureWidgetVisible(self.history_section)

    def _selected_history_record(self) -> ConversionHistoryRecord | None:
        item = self.history_list.currentItem()
        if item is None:
            return None
        record_id = str(item.data(Qt.ItemDataRole.UserRole))
        return next(
            (record for record in self.history_records if record.record_id == record_id),
            None,
        )

    def _update_history_buttons(self) -> None:
        record = self._selected_history_record()
        self.history_open_button.setEnabled(record is not None and record.output_path.is_file())
        self.history_folder_button.setEnabled(
            record is not None and record.output_directory.is_dir()
        )
        self.history_delete_button.setEnabled(record is not None)
        self.history_clear_button.setEnabled(bool(self.history_records))

    def _open_history_output_file(
        self,
        item: QListWidgetItem | None = None,
        *args,
    ) -> None:
        del args
        if item is not None:
            self.history_list.setCurrentItem(item)
        record = self._selected_history_record()
        if record is None or not record.output_path.is_file():
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(record.output_path)))

    def _open_history_output_folder(self) -> None:
        record = self._selected_history_record()
        if record is None or not record.output_directory.is_dir():
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(record.output_directory)))

    def _delete_selected_history(self) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        dialog = self._warning_dialog(
            "删除历史记录",
            f"确定删除这条 {record.output_format} 转换历史吗？",
        )
        delete_button = dialog.addButton(
            "删除",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is not delete_button:
            return
        try:
            self.history_records = self.history_store.delete_record(record.record_id)
        except OSError as error:
            self._show_footer_message(
                f"删除历史失败：{error}",
                state="error",
                timeout=6000,
            )
            return
        self._refresh_history_list()

    def _clear_history(self) -> None:
        task_key = self._current_task_key()
        task = self.tasks.get(task_key) if task_key else None
        if task is None:
            return
        records = self._history_records_for_source(task.content_signature)
        if not records:
            return
        dialog = self._warning_dialog(
            "清空转换历史",
            f"确定清空“{task.display_name}”的 {len(records)} 条转换历史吗？",
        )
        clear_button = dialog.addButton(
            "清空该视频历史",
            QMessageBox.ButtonRole.AcceptRole,
        )
        cancel_button = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is not clear_button:
            return
        try:
            self.history_records = self.history_store.delete_by_source_key(task.content_signature)
        except OSError as error:
            self._show_footer_message(
                f"清空历史失败：{error}",
                state="error",
                timeout=6000,
            )
            return
        self._refresh_history_list()

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
            task.probe_error = describe_probe_error(
                f"{result.raw_output or ''}\n{result.error or ''}",
            )
            task.status = TaskStatus.FAILED

        if task.conversion_resumable:
            # The duration is known now, so the kept progress can be shown properly.
            self._restore_resume_state()
        self._update_task_item(task)
        if self._current_task_key() == task.key:
            self._apply_task_to_preview(task)

    def _update_task_item(self, task: MediaTask) -> None:
        item = self.task_items.get(task.key)
        if item is None:
            return
        status_text = task.status_text
        if task.status == TaskStatus.CONVERTING:
            status_text = f"转换中 {task.conversion_progress:.0f}%"
        palette = get_palette(self.theme_name)
        item.setText(f"{task.display_name}\n{status_text}")
        item.setData(NAME_ROLE, task.display_name)
        item.setData(
            META_ROLE,
            f"{task.extension}  ·  {format_file_size(task.size_bytes)}",
        )
        item.setData(STATUS_ROLE, status_text)
        item.setData(STATUS_COLOR_ROLE, status_color(task.status, palette))
        item.setData(
            ACCENT_ROLE,
            palette.danger if task.status == TaskStatus.FAILED else "",
        )
        item.setIcon(self._task_icon(task.status))
        tooltip = str(task.path)
        if task.probe_error:
            tooltip = f"{tooltip}\n{task.probe_error}"
        if task.conversion_error:
            tooltip = f"{tooltip}\n{task.conversion_error}"
        if task.output_path:
            tooltip = f"{tooltip}\n输出：{task.output_path}"
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
        task = self.tasks.get(task_key)
        if task is None:
            return
        if task.status == TaskStatus.CONVERTING:
            self._show_footer_message(
                "请先取消当前转换任务",
                state="error",
                timeout=4000,
            )
            return

        history_records = self._history_records_for_source(task.content_signature)
        history_action = "keep"
        if history_records:
            history_action = self._ask_history_delete(
                len(history_records),
                "该视频",
            )
            if history_action == "cancel":
                return

        self.tasks.pop(task_key, None)
        self.task_items.pop(task_key, None)
        if task_key in self.batch_pending:
            self.batch_pending.remove(task_key)
            self.batch_total -= 1
            self.batch_counts["skipped"] += 1
            self._update_batch_progress()
        self.probe_service.cancel_task(task_key)
        self.thumbnail_service.cancel_task(task_key)
        self.thumbnail_service.delete_cached(task.content_signature)
        self._discard_conversion_parts(task)
        if history_action == "delete":
            self.history_records = self.history_store.delete_by_source_key(task.content_signature)
            self._refresh_history_list()
        self.task_list.takeItem(self.task_list.row(item))
        self._save_task_paths()
        self._update_task_actions()
        self._show_footer_message("已移除所选任务", timeout=4000)

    def _clear_queue(self, checked: bool = False) -> None:
        del checked
        if not self.tasks:
            return
        source_keys = {task.content_signature for task in self.tasks.values()}
        history_count = sum(
            1 for record in self.history_records if record.source_key in source_keys
        )
        history_action = "keep"
        if history_count:
            history_action = self._ask_history_delete(
                history_count,
                "队列中的视频",
            )
            if history_action == "cancel":
                return
        else:
            dialog = self._warning_dialog(
                "清空任务",
                f"确定要移除队列中的 {len(self.tasks)} 个任务吗？",
            )
            clear_button = dialog.addButton(
                "清空",
                QMessageBox.ButtonRole.AcceptRole,
            )
            cancel_button = dialog.addButton(
                "取消",
                QMessageBox.ButtonRole.RejectRole,
            )
            dialog.setDefaultButton(cancel_button)
            dialog.exec()
            if dialog.clickedButton() is not clear_button:
                return

        if history_action == "delete" and source_keys:
            self.history_records = self.history_store.delete_by_source_keys(source_keys)
            self._refresh_history_list()
        if self.conversion_runner.is_running:
            self.conversion_runner.cancel()
        self._abort_batch()
        self.probe_service.cancel_all()
        self.thumbnail_service.cancel_all()
        for task in self.tasks.values():
            self.thumbnail_service.delete_cached(task.content_signature)
            self._discard_conversion_parts(task)
        self.tasks.clear()
        self.task_items.clear()
        self.task_list.clear()
        self._save_task_paths()
        self._update_task_actions()
        self._show_footer_message("任务队列已清空", timeout=4000)

    def _history_records_for_source(
        self,
        source_key: str,
    ) -> list[ConversionHistoryRecord]:
        return [record for record in self.history_records if record.source_key == source_key]

    def _ask_history_delete(self, count: int, subject: str) -> str:
        dialog = self._warning_dialog(
            "删除转换历史",
            f"{subject}有 {count} 条转换历史记录。删除任务时是否同时删除这些历史记录？",
        )
        history_button = dialog.addButton(
            "删除任务和历史",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        task_button = dialog.addButton(
            "仅删除任务",
            QMessageBox.ButtonRole.AcceptRole,
        )
        cancel_button = dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is history_button:
            return "delete"
        if clicked is task_button:
            return "keep"
        return "cancel"

    def _update_task_actions(self) -> None:
        has_tasks = bool(self.tasks)
        has_selection = self.task_list.currentItem() is not None
        self.queue_count.setText(str(len(self.tasks)))
        self.task_stack.setCurrentIndex(1 if has_tasks else 0)
        self.clear_button.setEnabled(has_tasks)
        self.remove_button.setEnabled(has_selection)
        self.clear_queue_button.setEnabled(has_tasks)
        self._update_output_preview()
        self._update_conversion_controls()

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
        self._import_paths(paths, show_issue_dialog=True)

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
        self._update_conversion_controls()

    def _set_status_state(self, state: str) -> None:
        self.status_dot.setProperty("state", state)
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

    def _install_wheel_guards(self) -> None:
        controls = self.findChildren(QComboBox) + self.findChildren(QAbstractSpinBox)
        for control in controls:
            control.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Wheel and isinstance(
            watched,
            (QComboBox, QAbstractSpinBox),
        ):
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.conversion_runner.is_running:
            dialog = self._warning_dialog(
                "转换正在进行",
                "当前仍有视频正在转换，是否取消并退出？",
            )
            exit_button = dialog.addButton(
                "取消并退出",
                QMessageBox.ButtonRole.DestructiveRole,
            )
            dialog.addButton("继续转换", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            if dialog.clickedButton() is not exit_button:
                event.ignore()
                return
            self.conversion_runner.shutdown()
        self._save_window_geometry()
        event.accept()
        super().closeEvent(event)

    def _show_format_help(self) -> None:
        if self.format_help_dialog is None:
            self.format_help_dialog = FormatHelpDialog(self)
        self.format_help_dialog.show()
        self.format_help_dialog.raise_()
        self.format_help_dialog.activateWindow()

    def _show_advanced_help(self) -> None:
        if self.advanced_help_dialog is None:
            self.advanced_help_dialog = AdvancedHelpDialog(self)
        self.advanced_help_dialog.show()
        self.advanced_help_dialog.raise_()
        self.advanced_help_dialog.activateWindow()

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

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange:
            self._apply_icon_theme(get_palette(self.theme_name))

    def _apply_theme(self) -> None:
        palette = get_palette(self.theme_name)
        self.setStyleSheet(build_stylesheet(palette))
        self._apply_icon_theme(palette)
        self.preview_title.refresh_elide()
        target = "浅色" if palette.name == "dark" else "深色"
        self.theme_button.setToolTip(f"切换为{target}主题")

    def _apply_icon_theme(self, palette: ThemePalette) -> None:
        self.add_video_button.set_asset_icon(VIDEO_ICON_PATH, "#ffffff")
        self.clear_button.set_asset_icon(TRASH_ICON_PATH, palette.text)
        self.theme_button.set_asset_icon(THEME_ICON_PATH, palette.text)
        self.settings_button.set_asset_icon(SETTINGS_ICON_PATH, palette.text)
        self.clear_button.set_hover_color(palette.help_hover)
        self.theme_button.set_hover_color(palette.help_hover)
        self.settings_button.set_hover_color(palette.help_hover)
        self.empty_queue_icon.setPixmap(
            _tinted_svg_pixmap(
                FILE_ICON_PATH,
                palette.muted,
                48,
                widget=self,
            )
        )
        self.preview_icon.setPixmap(
            _tinted_svg_pixmap(
                PLAY_ICON_PATH,
                palette.preview_muted,
                64,
                widget=self,
            )
        )
        self.browse_button.set_asset_icon(FOLDER_ICON_PATH, palette.text)
        self.reset_output_button.set_asset_icon(REFRESH_ICON_PATH, palette.text)
        self.browse_button.set_hover_color(palette.help_hover)
        self.reset_output_button.set_hover_color(palette.help_hover)
        self.format_help_button.set_hover_color(palette.help_hover)
        if self.advanced_section.help_button is not None:
            self.advanced_section.help_button.set_hover_color(palette.help_hover)
        self.start_button.set_asset_icon(RUN_ICON_PATH, "#ffffff")
        self.clear_state_button.set_asset_icon(DELETE_ICON_PATH, palette.danger)
        self.clear_state_button.set_hover_color(palette.help_hover)
        self.regenerate_thumbnail_button.set_asset_icon(
            REFRESH_ICON_PATH,
            palette.text,
        )
        self.regenerate_thumbnail_button.set_hover_color(palette.help_hover)
        self.task_delegate.set_theme(palette)
        for index in range(self.task_list.count()):
            item = self.task_list.item(index)
            task = self.tasks.get(str(item.data(Qt.ItemDataRole.UserRole)))
            if task is not None:
                self._update_task_item(task)
