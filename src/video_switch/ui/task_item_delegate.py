"""Queue row painting: file name, metadata and a colour-coded status."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from video_switch.models.media_task import TaskStatus
from video_switch.ui.theme import ThemePalette

NAME_ROLE = Qt.ItemDataRole.UserRole + 1
META_ROLE = Qt.ItemDataRole.UserRole + 2
STATUS_ROLE = Qt.ItemDataRole.UserRole + 3
STATUS_COLOR_ROLE = Qt.ItemDataRole.UserRole + 4
ACCENT_ROLE = Qt.ItemDataRole.UserRole + 5

ROW_HEIGHT = 62
ICON_SIZE = 24
ACCENT_WIDTH = 3
PENDING_STATES = (TaskStatus.WAITING_FOR_METADATA, TaskStatus.PROBING_METADATA)


def status_color(status: TaskStatus, palette: ThemePalette) -> str:
    """Return the colour that represents one task state."""
    if status in PENDING_STATES:
        return palette.muted
    if status == TaskStatus.CONVERTING:
        return palette.primary
    if status == TaskStatus.COMPLETED:
        return palette.success
    if status == TaskStatus.FAILED:
        return palette.danger
    if status == TaskStatus.CANCELLED:
        return palette.warning
    return palette.text


class TaskItemDelegate(QStyledItemDelegate):
    """Draw a queue row with a coloured status and an accent for failures."""

    def __init__(self, theme: ThemePalette, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._theme = theme

    def set_theme(self, theme: ThemePalette) -> None:
        """Switch the colours used for the next repaint."""
        self._theme = theme

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(ROW_HEIGHT, size.height()))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        view_option = self._background_option(option, index)
        style = view_option.widget.style() if view_option.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            view_option,
            painter,
            view_option.widget,
        )

        rect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        accent = index.data(ACCENT_ROLE)
        if accent:
            bar = QRect(rect.left() + 3, rect.top() + 9, ACCENT_WIDTH, rect.height() - 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(accent))
            painter.drawRoundedRect(bar, 1.5, 1.5)

        text_left = rect.left() + 12
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, QRect(text_left, rect.top() + 13, ICON_SIZE, ICON_SIZE))
            text_left += ICON_SIZE + 10

        width = max(0, rect.right() - text_left - 8)
        metrics = painter.fontMetrics()
        line_height = metrics.height()
        name_rect = QRect(text_left, rect.top() + 8, width, line_height)
        meta_rect = QRect(text_left, name_rect.bottom() + 2, width, line_height)

        name = str(index.data(NAME_ROLE) or "")
        meta = str(index.data(META_ROLE) or "")
        status = str(index.data(STATUS_ROLE) or "")
        color = index.data(STATUS_COLOR_ROLE) or self._theme.text

        painter.setPen(QPen(QColor(self._theme.text)))
        painter.drawText(
            name_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, width),
        )

        meta_prefix = f"{meta}  ·  " if meta else ""
        prefix_width = metrics.horizontalAdvance(meta_prefix)
        painter.setPen(QPen(QColor(self._theme.muted)))
        painter.drawText(
            meta_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(meta_prefix, Qt.TextElideMode.ElideRight, width),
        )
        if status:
            status_rect = QRect(
                text_left + prefix_width,
                meta_rect.top(),
                max(0, width - prefix_width),
                line_height,
            )
            painter.setPen(QPen(QColor(color)))
            painter.drawText(
                status_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(status, Qt.TextElideMode.ElideRight, status_rect.width()),
            )
        painter.restore()

    def _background_option(
        self,
        option: QStyleOptionViewItem,
        index,
    ) -> QStyleOptionViewItem:
        """Return an option that only carries the row background for the style.

        Text and icon must be cleared, otherwise the style paints its own copy
        and the glyph is drawn twice, which looks like a doubled icon.
        """
        view_option = QStyleOptionViewItem(option)
        self.initStyleOption(view_option, index)
        view_option.text = ""
        view_option.icon = QIcon()
        return view_option
