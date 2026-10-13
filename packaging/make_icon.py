"""Render the application SVG into a multi-size Windows ICO file.

The ICO container is written by hand (PNG-compressed entries, supported since
Windows Vista) so packaging needs no extra image library beyond Qt.
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt  # noqa: E402  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ICON_SVG = ROOT / "src" / "video_switch" / "resources" / "icons" / "app.svg"
TARGET = ROOT / "packaging" / "VideoSwitch.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(size: int) -> bytes:
    """Render the application SVG at a square size and return PNG bytes."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(str(ICON_SVG)).render(painter, QRectF(0, 0, size, size))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def build_ico(payloads: list[tuple[int, bytes]]) -> bytes:
    """Assemble an ICO container from (size, png bytes) pairs."""
    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = len(header) + 16 * len(payloads)
    entries = bytearray()
    body = bytearray()
    for size, payload in payloads:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            dimension,
            dimension,
            0,
            0,
            1,
            32,
            len(payload),
            offset,
        )
        body += payload
        offset += len(payload)
    return bytes(header + entries + body)


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    del app
    payloads = [(size, render_png(size)) for size in SIZES]
    TARGET.write_bytes(build_ico(payloads))
    print(f"icon written: {TARGET} ({TARGET.stat().st_size} bytes, sizes {list(SIZES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
