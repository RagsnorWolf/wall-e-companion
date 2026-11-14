"""Camera preview widget with detection overlays and a HUD frame."""

from __future__ import annotations

from typing import List, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ui.theme import AMBER, BG_DEEP, CYAN, GREEN, TEXT_DIM, TEXT_MUTED, YELLOW


class VideoFeed(QWidget):
    """Displays the latest BGR frame, letterboxed, with face overlays."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(360, 260)
        self._pixmap: Optional[QPixmap] = None
        self._faces: List = []
        self._fps = 0.0
        self._source = "SIN SEÑAL"
        self._recording = False
        self._show_overlay = True

    def set_frame(self, frame: Optional[np.ndarray], faces: Optional[List] = None, fps: float = 0.0):
        if frame is None:
            return
        try:
            rgb = frame[:, :, ::-1].copy()
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            self._pixmap = QPixmap.fromImage(img.copy())
            self._fps = fps
            self._source = "USB CAM"
            if faces is not None:
                self._faces = faces
            self.update()
        except Exception:
            pass

    def set_faces(self, faces: List):
        self._faces = faces or []
        self.update()

    def set_overlay_visible(self, visible: bool):
        self._show_overlay = visible
        self.update()

    def clear(self):
        self._pixmap = None
        self._faces = []
        self.update()

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(self.rect(), QColor(BG_DEEP))

        if self._pixmap is None:
            self._paint_no_signal(p, w, h)
            return

        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (w - scaled.width()) / 2
        y = (h - scaled.height()) / 2
        p.drawPixmap(int(x), int(y), scaled)

        if self._show_overlay:
            self._paint_faces(p, x, y, scaled.width(), scaled.height(), scaled.width(), scaled.height())

        # corner brackets
        p.setPen(QPen(QColor(AMBER), 2))
        m = 10
        ln = 22
        for (cx, cy, dx, dy) in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            p.drawLine(QPointF(cx, cy), QPointF(cx + dx * ln, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * ln))

        # status HUD
        p.setFont(QFont("Cascadia Mono", 8))
        p.setPen(QColor(AMBER))
        p.drawText(20, 28, "● REC  " + self._source)
        p.setPen(QColor(TEXT_MUTED))
        p.drawText(int(w - 140), 28, f"{self._fps:4.1f} FPS")
        p.drawText(int(w - 140), int(h - 20), "640x480 · MJPG")

    def _paint_faces(self, p: QPainter, ox: float, oy: float, sw: float, sh: float,
                     src_w: float, src_h: float):
        if not self._faces or self._pixmap is None:
            return
        sx = sw / max(1, self._pixmap.width())
        sy = sh / max(1, self._pixmap.height())
        for face in self._faces:
            bbox = getattr(face, "bbox", None)
            if not bbox:
                continue
            x, y, fw, fh = bbox
            rect = QRectF(ox + x * sx, oy + y * sy, fw * sx, fh * sy)
            confidence = float(getattr(face, "confidence", 0.0))
            emotion = getattr(face, "emotion", None) or "neutral"
            face_id = getattr(face, "face_id", None) or "FACE"
            p.setPen(QPen(QColor(GREEN), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, 4, 4)

            tag = f"{face_id}  {emotion.upper()}  {confidence * 100:.0f}%"
            p.setFont(QFont("Cascadia Mono", 7))
            tw = p.fontMetrics().horizontalAdvance(tag) + 10
            tag_rect = QRectF(rect.left(), max(oy + 2, rect.top() - 18), tw, 16)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(6, 14, 20, 220))
            p.drawRoundedRect(tag_rect, 3, 3)
            p.setPen(QColor(GREEN))
            p.drawText(tag_rect.adjusted(5, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, tag)

    def _paint_no_signal(self, p: QPainter, w: float, h: float):
        p.setPen(QPen(QColor(255, 255, 255, 12), 1))
        step = 32
        for x in range(0, int(w), step):
            p.drawLine(x, 0, x, int(h))
        for y in range(0, int(h), step):
            p.drawLine(0, y, int(w), y)

        p.setPen(QColor(TEXT_DIM))
        p.setFont(QFont("Bahnschrift", 14, QFont.DemiBold))
        p.drawText(self.rect().adjusted(0, -14, 0, -14), Qt.AlignCenter, "CÁMARA OFFLINE")
        p.setFont(QFont("Cascadia Mono", 8))
        p.drawText(self.rect().adjusted(0, 18, 0, 18), Qt.AlignCenter,
                   "Conectá el robot o verificá el índice de cámara")
