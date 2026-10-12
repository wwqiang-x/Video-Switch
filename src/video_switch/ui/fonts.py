"""Font registration helpers for consistent Chinese rendering."""

import os
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

_registered_font_families: tuple[str, ...] | None = None


def register_cjk_fonts() -> tuple[str, ...]:
    """Register common Windows CJK fonts when Qt cannot discover them."""
    global _registered_font_families
    if _registered_font_families is not None:
        return _registered_font_families

    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    font_paths = (
        windows_dir / "Fonts" / "msyh.ttc",
        windows_dir / "Fonts" / "msyhbd.ttc",
    )

    registered: list[str] = []
    for font_path in font_paths:
        if not font_path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            registered.extend(QFontDatabase.applicationFontFamilies(font_id))

    _registered_font_families = tuple(dict.fromkeys(registered))
    return _registered_font_families


def create_application_font() -> QFont:
    """Create a crisp UI font using the registered CJK family."""
    register_cjk_fonts()
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(13)
    font.setWeight(QFont.Weight.Normal)
    font.setKerning(True)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font
