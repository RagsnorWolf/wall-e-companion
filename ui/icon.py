"""Programmatically painted application icon (no binary assets required)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def render_pixmap(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    scale = size / 256.0
    p.setPen(Qt.NoPen)

    # rounded amber head
    p.setBrush(QColor("#ffb23f"))
    p.drawRoundedRect(QRectF(8 * scale, 30 * scale, 240 * scale, 196 * scale),
                      46 * scale, 46 * scale)

    # brow shadow
    p.setBrush(QColor("#c98d1e"))
    p.drawRoundedRect(QRectF(20 * scale, 44 * scale, 216 * scale, 42 * scale),
                      18 * scale, 18 * scale)

    # eye sockets
    p.setBrush(QColor("#08111a"))
    p.drawRoundedRect(QRectF(34 * scale, 96 * scale, 78 * scale, 92 * scale),
                      20 * scale, 20 * scale)
    p.drawRoundedRect(QRectF(144 * scale, 96 * scale, 78 * scale, 92 * scale),
                      20 * scale, 20 * scale)

    # irises
    p.setBrush(QColor("#38d6ff"))
    p.drawRoundedRect(QRectF(50 * scale, 116 * scale, 46 * scale, 48 * scale),
                      12 * scale, 12 * scale)
    p.drawRoundedRect(QRectF(160 * scale, 116 * scale, 46 * scale, 48 * scale),
                      12 * scale, 12 * scale)

    # highlights
    p.setBrush(QColor(255, 255, 255, 160))
    p.drawRoundedRect(QRectF(58 * scale, 122 * scale, 16 * scale, 14 * scale),
                      5 * scale, 5 * scale)
    p.drawRoundedRect(QRectF(168 * scale, 122 * scale, 16 * scale, 14 * scale),
                      5 * scale, 5 * scale)

    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(render_pixmap(size))
    return icon


def save_ico(path: str) -> bool:
    """Save a multi-resolution .ico using Pillow when available."""
    try:
        from PIL import Image
    except Exception:
        return False
    pm = render_pixmap(256)
    image = pm.toImage().convertToFormat(pm.toImage().Format_RGBA8888)
    ptr = image.bits()
    data = bytes(ptr)
    img = Image.frombytes("RGBA", (image.width(), image.height()), data)
    img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return True
