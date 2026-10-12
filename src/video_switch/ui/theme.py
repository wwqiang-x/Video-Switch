"""Application themes and Qt stylesheet generation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePalette:
    """Colors used by the application stylesheet."""

    name: str
    app_bg: str
    surface: str
    surface_alt: str
    surface_hover: str
    help_hover: str
    border: str
    border_strong: str
    text: str
    muted: str
    primary: str
    primary_hover: str
    primary_soft: str
    success: str
    success_soft: str
    warning: str
    danger: str
    danger_soft: str
    preview_bg: str
    preview_text: str
    preview_muted: str
    shadow: str


LIGHT_PALETTE = ThemePalette(
    name="light",
    app_bg="#edf1f5",
    surface="#ffffff",
    surface_alt="#f7f9fc",
    surface_hover="#eef3f9",
    help_hover="#e2e8f0",
    border="#dce3eb",
    border_strong="#c7d2df",
    text="#172033",
    muted="#66758a",
    primary="#2563eb",
    primary_hover="#1d4ed8",
    primary_soft="#e7efff",
    success="#15803d",
    success_soft="#eaf7ef",
    warning="#b45309",
    danger="#dc2626",
    danger_soft="#fff0f0",
    preview_bg="#111827",
    preview_text="#f8fafc",
    preview_muted="#a8b3c2",
    shadow="rgba(15, 23, 42, 24)",
)

DARK_PALETTE = ThemePalette(
    name="dark",
    app_bg="#0f1419",
    surface="#171d24",
    surface_alt="#1d252e",
    surface_hover="#252f3a",
    help_hover="#394858",
    border="#2d3946",
    border_strong="#3b4a5b",
    text="#edf2f7",
    muted="#9aa8b8",
    primary="#4f8ef7",
    primary_hover="#6aa0fa",
    primary_soft="#1d355e",
    success="#4ade80",
    success_soft="#163324",
    warning="#fbbf24",
    danger="#f87171",
    danger_soft="#3a2024",
    preview_bg="#080c10",
    preview_text="#f8fafc",
    preview_muted="#94a3b8",
    shadow="rgba(0, 0, 0, 90)",
)


def get_palette(name: str) -> ThemePalette:
    """Return a palette by name, falling back to the light theme."""
    return DARK_PALETTE if name == DARK_PALETTE.name else LIGHT_PALETTE


def build_stylesheet(palette: ThemePalette) -> str:
    """Build the Qt stylesheet for the selected palette."""
    return f"""
QWidget {{
    color: {palette.text};
    font-family: "Microsoft YaHei UI";
    font-size: 13px;
}}

QMainWindow,
QWidget#AppRoot,
QDialog {{
    background: {palette.app_bg};
}}

QDialog#FormatHelpDialog,
QDialog#HelpCardDialog {{
    background: {palette.app_bg};
}}

QMessageBox {{
    background: {palette.surface};
}}

QMessageBox QLabel {{
    color: {palette.text};
}}

QMessageBox QPushButton {{
    background: {palette.surface_alt};
    border: 1px solid {palette.border_strong};
    border-radius: 6px;
    color: {palette.text};
    min-height: 30px;
    min-width: 78px;
    padding: 0 14px;
}}

QMessageBox QPushButton:hover {{
    background: {palette.surface_hover};
}}

QMessageBox QPushButton:default {{
    background: {palette.primary};
    border-color: {palette.primary};
    color: #ffffff;
}}

QFrame#Header,
QFrame#Footer {{
    background: {palette.surface};
    border: none;
}}

QFrame#Header {{
    border-bottom: 1px solid {palette.border};
}}

QFrame#Footer {{
    border-top: 1px solid {palette.border};
}}

QFrame[panel="true"] {{
    background: {palette.surface};
    border: 1px solid {palette.border};
    border-radius: 8px;
}}

QLabel#BrandMark {{
    background: {palette.primary};
    border-radius: 8px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 800;
}}

QLabel#BrandTitle {{
    color: {palette.text};
    font-size: 18px;
    font-weight: 700;
}}

QLabel#PanelTitle {{
    color: {palette.text};
    font-size: 15px;
    font-weight: 700;
}}

QLabel#DialogTitle {{
    color: {palette.text};
    font-size: 18px;
    font-weight: 700;
}}

QLabel#PanelSubtitle,
QLabel[muted="true"] {{
    color: {palette.muted};
}}

QLabel#SectionLabel {{
    color: {palette.text};
    font-size: 13px;
    font-weight: 600;
}}

QLabel#MetricValue {{
    color: {palette.text};
    font-size: 15px;
    font-weight: 650;
}}

QLabel#StatusChip,
QLabel#CountBadge {{
    background: {palette.primary_soft};
    border-radius: 10px;
    color: {palette.primary};
    font-size: 12px;
    font-weight: 650;
    padding: 3px 9px;
}}

QLabel#ToolStatus {{
    background: {palette.surface_alt};
    border: 1px solid {palette.border};
    border-radius: 6px;
    color: {palette.muted};
    padding: 10px 12px;
}}

QLabel#ToolStatus[state="ready"] {{
    background: {palette.success_soft};
    border-color: {palette.success};
    color: {palette.success};
}}

QLabel#ToolStatus[state="error"] {{
    background: {palette.danger_soft};
    border-color: {palette.danger};
    color: {palette.danger};
}}

QLabel#QueueCount {{
    background: {palette.surface_hover};
    border-radius: 10px;
    color: {palette.muted};
    font-size: 12px;
    font-weight: 650;
    padding: 2px 8px;
}}

QToolButton#HelpIconButton,
QToolButton#InfoIconButton {{
    background: transparent;
    border: none;
    border-radius: 10px;
    margin: 0;
    padding: 0;
}}

QToolButton#HelpIconButton:hover,
QToolButton#InfoIconButton:hover {{
    background: transparent;
}}

QFrame#FormatCard {{
    background: {palette.surface};
    border: 1px solid {palette.border};
    border-radius: 8px;
}}

QLabel#FormatBadge {{
    background: {palette.primary};
    border-radius: 6px;
    color: #ffffff;
    font-weight: 700;
}}

QLabel#FormatCardTitle {{
    color: {palette.text};
    font-size: 14px;
    font-weight: 700;
}}

QLabel#FormatUseCase {{
    color: {palette.text};
    font-weight: 600;
}}

QLabel#FormatNote {{
    color: {palette.warning};
}}

QLabel#StageIcon {{
    color: {palette.preview_muted};
    font-size: 34px;
    font-weight: 300;
}}

QLabel#PreviewTitle {{
    color: {palette.preview_text};
    font-size: 17px;
    font-weight: 650;
}}

QLabel#PreviewHint {{
    color: {palette.preview_muted};
}}

QLabel#ThumbnailPreview {{
    background: transparent;
    border: none;
}}

QFrame#PreviewStage {{
    background: {palette.preview_bg};
    border: 1px solid {palette.border_strong};
    border-radius: 8px;
}}

QFrame#PreviewStage[dragActive="true"] {{
    border: 2px solid {palette.primary};
}}

QFrame#SourcePathRow {{
    background: {palette.surface_alt};
    border: 1px solid {palette.border};
    border-radius: 6px;
}}

QPushButton#PrimaryAction {{
    background: {palette.primary};
    border: 1px solid {palette.primary};
    border-radius: 7px;
    color: #ffffff;
    font-weight: 650;
    min-height: 38px;
    padding: 0 16px;
}}

QPushButton#PrimaryAction:hover {{
    background: {palette.primary_hover};
    border-color: {palette.primary_hover};
}}

QPushButton#PrimaryAction:disabled {{
    background: {palette.surface_hover};
    border-color: {palette.border};
    color: {palette.muted};
}}

QPushButton#SecondaryAction {{
    background: {palette.surface};
    border: 1px solid {palette.border_strong};
    border-radius: 7px;
    color: {palette.text};
    min-height: 36px;
    padding: 0 12px;
}}

QPushButton#SecondaryAction:hover {{
    background: {palette.surface_hover};
}}

QPushButton#SecondaryAction:disabled {{
    background: {palette.surface_alt};
    border-color: {palette.border};
    color: {palette.muted};
}}

QToolButton#IconButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    min-height: 34px;
    min-width: 34px;
    padding: 0;
}}

QToolButton#AssetIconButton {{
    background: transparent;
    border: none;
    margin: 0;
    padding: 0;
}}

QToolButton#IconButton:hover {{
    background: {palette.surface_hover};
    border-color: {palette.border};
}}

QToolButton#IconButton:disabled {{
    color: {palette.muted};
}}

QToolButton#SectionToggle {{
    background: transparent;
    border: none;
    padding: 0;
}}

QLabel#SectionTitle {{
    color: {palette.text};
    font-size: 13px;
    font-weight: 650;
}}

QToolButton[formatPreset="true"] {{
    background: {palette.surface_alt};
    border: 1px solid {palette.border};
    border-radius: 6px;
    color: {palette.text};
    min-height: 38px;
    font-weight: 600;
}}

QToolButton[formatPreset="true"]:hover {{
    background: {palette.surface_hover};
}}

QToolButton[formatPreset="true"]:checked {{
    background: {palette.primary_soft};
    border-color: {palette.primary};
    color: {palette.primary};
}}

QLineEdit,
QComboBox,
QSpinBox,
QPlainTextEdit {{
    background: {palette.surface_alt};
    border: 1px solid {palette.border_strong};
    border-radius: 6px;
    color: {palette.text};
    min-height: 24px;
    padding: 5px 8px;
}}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QPlainTextEdit:focus {{
    border-color: {palette.primary};
}}

QPlainTextEdit#CommandPreview {{
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
    padding: 8px;
}}

QLineEdit:read-only {{
    color: {palette.muted};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QCheckBox {{
    color: {palette.text};
    spacing: 8px;
}}

QListWidget {{
    background: {palette.surface_alt};
    border: 1px solid {palette.border};
    border-radius: 7px;
    outline: none;
    padding: 5px;
}}

QListWidget::item {{
    border-radius: 6px;
    padding: 8px;
}}

QListWidget::item:selected {{
    background: {palette.primary_soft};
    color: {palette.primary};
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {palette.border_strong};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QFrame#StatusDot {{
    background: {palette.warning};
    border-radius: 4px;
}}

QFrame#StatusDot[state="ready"] {{
    background: {palette.success};
}}

QFrame#StatusDot[state="error"] {{
    background: {palette.danger};
}}

QSplitter::handle {{
    background: transparent;
    width: 10px;
}}
"""
