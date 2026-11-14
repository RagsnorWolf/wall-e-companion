"""Animated Wall-E head rendered with QPainter.

Reacts live to mood, servo positions and audio level. No external assets.
"""

from __future__ import annotations

import math
import random
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from ui.theme import (
    AMBER, BG_DEEP, CYAN, GREEN, PURPLE, RED, SURFACE, SURFACE_3, TEXT_DIM, YELLOW,
    mood_color,
)


class RobotFace(QWidget):
    """Stylised Wall-E head with live eyes, tilting and ambient HUD."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(280, 240)
        self.setSizePolicy(self.sizePolicy().Expanding, self.sizePolicy().Expanding)

        self._mood = "idle"
        self._pan = 0.0          # -90..90
        self._tilt = 0.0         # -45..45
        self._eye_open = 1.0     # 0..1
        self._target_eye = 1.0
        self._blink = 0.0
        self._pupil_x = 0.0
        self._pupil_y = 0.0
        self._target_pupil_x = 0.0
        self._target_pupil_y = 0.0
        self._level = 0.0
        self._t = 0.0
        self._connected = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        self._blink_timer = QTimer(self)
        self._blink_timer.setSingleShot(True)
        self._blink_timer.timeout.connect(self._start_blink)
        self._schedule_blink()

        self._wander_timer = QTimer(self)
        self._wander_timer.timeout.connect(self._wander)
        self._wander_timer.start(2600)

    # ------------------------------------------------------------------ API
    def set_mood(self, mood: str):
        self._mood = str(mood).lower()
        self._target_eye = {
            "happy": 0.72,
            "curious": 1.0,
            "alert": 1.14,
            "sad": 0.58,
            "thinking": 0.82,
            "sleeping": 0.05,
            "idle": 0.94,
        }.get(self._mood, 0.94)
        self.update()

    def set_servo(self, servo_id: str, angle: float):
        if servo_id == "head_pan":
            self._pan = angle
        elif servo_id == "head_tilt":
            self._tilt = angle
        elif servo_id in ("eye_L", "eye_R"):
            # eye servo scales aperture
            self._target_eye = max(0.18, min(1.2, angle / 100.0))
        self.update()

    def set_connected(self, connected: bool):
        self._connected = connected
        self.update()

    def set_audio_level(self, level: float):
        self._level = max(0.0, min(1.0, float(level)))

    # --------------------------------------------------------------- motion
    def _tick(self):
        self._t += 0.033
        self._eye_open += (self._target_eye - self._eye_open) * 0.18
        if self._blink > 0:
            self._blink = max(0.0, self._blink - 0.09)
        self._pupil_x += (self._target_pupil_x - self._pupil_x) * 0.12
        self._pupil_y += (self._target_pupil_y - self._pupil_y) * 0.12
        self.update()

    def _schedule_blink(self):
        base = 3200 if self._mood != "sleeping" else 7000
        self._blink_timer.start(random.randint(base, base + 2600))

    def _start_blink(self):
        self._blink = 1.0
        self._schedule_blink()

    def _wander(self):
        if self._mood == "sleeping":
            self._target_pupil_x, self._target_pupil_y = 0.0, 0.12
            return
        self._target_pupil_x = random.uniform(-0.55, 0.55)
        self._target_pupil_y = random.uniform(-0.28, 0.28)

    # -------------------------------------------------------------- painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        self._paint_backdrop(p, w, h)

        scale = min(w / 360.0, h / 300.0)
        head_w, head_h = 232 * scale, 156 * scale
        pan_shift = (self._pan / 90.0) * 16 * scale
        tilt_shift = -(self._tilt / 45.0) * 10 * scale

        p.save()
        p.translate(cx + pan_shift, cy - 6 * scale + tilt_shift)
        p.rotate((self._pan / 90.0) * 3.0)

        self._paint_neck(p, head_w, head_h, scale)
        self._paint_head(p, head_w, head_h, scale)
        self._paint_eyes(p, head_w, head_h, scale)
        p.restore()

        self._paint_hud(p, w, h, cx, cy, scale)

    # ---------------------------------------------------------------- pieces
    def _paint_backdrop(self, p: QPainter, w: float, h: float):
        grad = QRadialGradient(w / 2, h * 0.46, max(w, h) * 0.75)
        accent = QColor(mood_color(self._mood))
        accent.setAlpha(26 if self._connected else 10)
        grad.setColorAt(0.0, accent)
        grad.setColorAt(0.55, QColor(SURFACE))
        grad.setColorAt(1.0, QColor(BG_DEEP))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(0, 0, w, h, 12, 12)

        # grid
        p.setPen(QPen(QColor(255, 255, 255, 10), 1))
        step = 28
        for x in range(0, int(w), step):
            p.drawLine(x, 0, x, int(h))
        for y in range(0, int(h), step):
            p.drawLine(0, y, int(w), y)

        # scan line
        y = (self._t * 34) % (h + 40) - 20
        scan = QLinearGradient(0, y - 16, 0, y + 16)
        scan.setColorAt(0.0, QColor(255, 255, 255, 0))
        scan.setColorAt(0.5, QColor(56, 214, 255, 16))
        scan.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(scan)
        p.drawRect(0, int(y - 16), int(w), 32)

    def _paint_neck(self, p: QPainter, hw: float, hh: float, s: float):
        p.setPen(Qt.NoPen)
        neck = QLinearGradient(0, hh * 0.35, 0, hh * 0.85)
        neck.setColorAt(0, QColor("#2a3540"))
        neck.setColorAt(1, QColor("#111a22"))
        p.setBrush(neck)
        p.drawRoundedRect(-hw * 0.26, hh * 0.38, hw * 0.52, hh * 0.55, 6 * s, 6 * s)
        p.setBrush(QColor("#0c141b"))
        p.drawRoundedRect(-hw * 0.20, hh * 0.42, hw * 0.40, hh * 0.10, 4 * s, 4 * s)

    def _paint_head(self, p: QPainter, hw: float, hh: float, s: float):
        rect = QRectF(-hw / 2, -hh / 2, hw, hh)

        # shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(rect.adjusted(-6 * s, 8 * s, 6 * s, 14 * s), 20 * s, 20 * s)

        # body metal
        metal = QLinearGradient(rect.topLeft(), rect.bottomRight())
        metal.setColorAt(0.0, QColor("#e3b23c"))
        metal.setColorAt(0.28, QColor("#d69a26"))
        metal.setColorAt(0.62, QColor("#b87c16"))
        metal.setColorAt(1.0, QColor("#8a5b0d"))
        p.setBrush(metal)
        p.setPen(QPen(QColor("#f5cb6a"), 1.4))
        p.drawRoundedRect(rect, 22 * s, 22 * s)

        # top highlight
        hi = QLinearGradient(0, rect.top(), 0, rect.top() + hh * 0.4)
        hi.setColorAt(0, QColor(255, 255, 255, 70))
        hi.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hi)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect.adjusted(4 * s, 3 * s, -4 * s, -hh * 0.55), 18 * s, 18 * s)

        # center divider
        p.setPen(QPen(QColor(90, 58, 8, 200), 2 * s))
        p.drawLine(QPointF(0, -hh * 0.40), QPointF(0, hh * 0.42))

        # rivets
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#6d4708"))
        for sign in (-1, 1):
            for dy in (-hh * 0.36, hh * 0.36):
                p.drawEllipse(QPointF(sign * hw * 0.44, dy), 2.2 * s, 2.2 * s)

        # brow bar
        p.setBrush(QColor("#8a5b0d"))
        p.drawRoundedRect(-hw * 0.47, -hh * 0.50, hw * 0.94, hh * 0.10, 6 * s, 6 * s)

        # antenna / status LED
        p.setPen(QPen(QColor("#5c6f7d"), 2 * s))
        p.drawLine(QPointF(-hw * 0.34, -hh * 0.52), QPointF(-hw * 0.38, -hh * 0.74))
        led = QColor(mood_color(self._mood))
        glow = QRadialGradient(-hw * 0.38, -hh * 0.76, 14 * s)
        glow.setColorAt(0, QColor(led.red(), led.green(), led.blue(), 200))
        glow.setColorAt(1, QColor(led.red(), led.green(), led.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(-hw * 0.38, -hh * 0.76), 13 * s, 13 * s)
        p.setBrush(led)
        p.drawEllipse(QPointF(-hw * 0.38, -hh * 0.76), 3.2 * s, 3.2 * s)

    def _paint_eyes(self, p: QPainter, hw: float, hh: float, s: float):
        blink = self._blink
        openness = max(0.04, self._eye_open * (1.0 - 0.92 * blink))
        accent = QColor(mood_color(self._mood))
        if not self._connected:
            accent = QColor(TEXT_DIM)

        eye_w = hw * 0.33
        eye_h = hh * 0.40
        for side, cx in ((-1, -hw * 0.21), (1, hw * 0.21)):
            outer = QRectF(cx - eye_w / 2, -eye_h * 0.62, eye_w, eye_h)

            # bezel
            bez = QLinearGradient(outer.topLeft(), outer.bottomRight())
            bez.setColorAt(0, QColor("#3b4753"))
            bez.setColorAt(1, QColor("#161f28"))
            p.setBrush(bez)
            p.setPen(QPen(QColor("#0a0f14"), 1.4 * s))
            p.drawRoundedRect(outer.adjusted(-5 * s, -5 * s, 5 * s, 5 * s), 9 * s, 9 * s)

            # glass
            p.setBrush(QColor("#060b10"))
            p.setPen(QPen(QColor("#000000"), 1 * s))
            p.drawRoundedRect(outer, 6 * s, 6 * s)

            # iris
            iw = eye_w * 0.62
            ih = max(2.0, eye_h * 0.78 * openness)
            ix = cx + self._pupil_x * eye_w * 0.20
            iy = -eye_h * 0.12 + self._pupil_y * eye_h * 0.22
            iris = QRectF(ix - iw / 2, iy - ih / 2, iw, ih)

            glow = QRadialGradient(ix, iy, iw * 0.9)
            glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 235))
            glow.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(), 150))
            glow.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(iris.adjusted(-10 * s, -10 * s, 10 * s, 10 * s))

            core = QLinearGradient(iris.topLeft(), iris.bottomRight())
            core.setColorAt(0, accent.lighter(135))
            core.setColorAt(1, accent.darker(120))
            p.setBrush(core)
            p.drawRoundedRect(iris, 3.2 * s, 3.2 * s)

            # specular
            p.setBrush(QColor(255, 255, 255, 110))
            p.drawRoundedRect(iris.adjusted(iw * 0.08, ih * 0.06, -iw * 0.55, -ih * 0.55), 2 * s, 2 * s)

            # mood eyebrow tint
            if self._mood == "sad":
                p.setPen(QPen(QColor(0, 0, 0, 120), 2 * s))
                slope = 4 * s * side
                p.drawLine(QPointF(outer.left(), outer.top() + slope),
                           QPointF(outer.right(), outer.top() - slope))

    def _paint_hud(self, p: QPainter, w: float, h: float, cx: float, cy: float, s: float):
        color = QColor(mood_color(self._mood))
        color.setAlpha(120 if self._connected else 45)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, 1.2))
        r = min(w, h) * 0.40
        p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), 30 * 16, 44 * 16)
        p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), 214 * 16, 26 * 16)

        font = QFont("Cascadia Mono", max(7, int(7 * s)))
        p.setFont(font)
        p.setPen(QColor(TEXT_DIM))
        p.drawText(12, int(h - 12), f"MOOD::{self._mood.upper()}")
        p.drawText(12, 18, "WALL·E // UNIT-07")
        p.drawText(int(w - 96), int(h - 12), f"PAN {self._pan:+05.1f}°")

        # audio bars bottom-right
        if self._level > 0.01:
            bar_w = 3
            for i in range(12):
                bh = 3 + (self._level * 20) * (0.35 + 0.65 * abs(math.sin(self._t * 6 + i * 0.7)))
                x = w - 26 - i * (bar_w + 2)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(AMBER if self._level > 0.65 else CYAN))
                p.drawRoundedRect(QRectF(x, h - 24 - bh, bar_w, bh), 1.5, 1.5)
