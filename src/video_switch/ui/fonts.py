"""Font registration helpers for consistent Chinese rendering."""

import os
from pathlib import Path

from PySide6.QtGui import QFontDatabase

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
