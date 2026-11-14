"""Custom-painted charts: rolling telemetry lines, radial gauge, level bars, waveform."""

from __future__ import annotations

import math
import random
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QWidget

from ui.theme import AMBER, BORDER_SOFT, CYAN, GREEN, RED, SURFACE_2, TEXT, TEXT_DIM, TEXT_MUTED, YELLOW


class TelemetryChart(QWidget):
    """Smooth multi-series rolling chart with grid and gradient fill."""

    def __init__(self, series: Optional[Dict[str, str]] = None, capacity: int = 120,
                 y_min: float = 0.0, y_max: float = 100.0, unit: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self._capacity = capacity
        self._data: Dict[str, Deque[float]] = {}
        self._colors: Dict[str, QColor] = {}
        self._y_min = y_min
        self._y_max = y_max
        self._unit = unit
        self._autoscale = y_min is None or y_max is None
        for name, color in (series or {}).items():
            self.add_series(name, color)

    def add_series(self, name: str, color: str):
        self._data[name] = deque(maxlen=self._capacity)
        self._colors[name] = QColor(color)
        self.update()

    def push(self, name: str, value: float):
        if name not in self._data:
            self.add_series(name, CYAN)
        self._data[name].append(float(value))
        self.update()

    def clear(self):
        for d in self._data.values():
            d.clear()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 44, 14, 12, 22
        plot = QRectF(pad_l, pad_t, max(10, w - pad_l - pad_r), max(10, h - pad_t - pad_b))

        p.fillRect(self.rect(), Qt.NoBrush)

        y0, y1 = self._y_min, self._y_max
        values = [v for d in self._data.values() for v in d]
        if auto := (self._autoscale or not values):
            pass
        if values:
            vmin, vmax = min(values), max(values)
            if vmax - vmin < 1e-6:
                vmax = vmin + 1
            margin = (vmax - vmin) * 0.15
            y0, y1 = vmin - margin, vmax + margin

        # grid
        p.setPen(QPen(QColor(BORDER_SOFT), 1, Qt.DotLine))
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        for i in range(7):
            x = plot.left() + plot.width() * i / 6
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        # labels
        font = QFont("Cascadia Mono", 7)
        p.setFont(font)
        p.setPen(QColor(TEXT_DIM))
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            val = y1 - (y1 - y0) * i / 4
            p.drawText(QRectF(0, y - 8, pad_l - 8, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"{val:.0f}")

        if not any(self._data.values()):
            p.setPen(QColor(TEXT_DIM))
            p.drawText(plot, Qt.AlignCenter, "ESPERANDO TELEMETRÍA")
            return

        # series
        for name, data in self._data.items():
            if len(data) < 2:
                continue
            color = self._colors[name]
            n = len(data)
            step = plot.width() / max(1, self._capacity - 1)
            offset = plot.right() - (n - 1) * step
            path = QPainterPath()
            pts: List[QPointF] = []
            for i, v in enumerate(data):
                x = offset + i * step
                y = plot.bottom() - (v - y0) / max(1e-6, (y1 - y0)) * plot.height()
                pts.append(QPointF(x, y))
            path.moveTo(pts[0])
            for i in range(1, len(pts) - 1):
                mid = QPointF((pts[i].x() + pts[i + 1].x()) / 2,
                              (pts[i].y() + pts[i + 1].y()) / 2)
                path.quadTo(pts[i], mid)
            path.lineTo(pts[-1])

            # fill under primary series
            if name == next(iter(self._data)):
                fill = QPainterPath(path)
                fill.lineTo(pts[-1].x(), plot.bottom())
                fill.lineTo(pts[0].x(), plot.bottom())
                fill.closeSubpath()
                grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
                c = QColor(color)
                c.setAlpha(70)
                grad.setColorAt(0, c)
                c2 = QColor(color)
                c2.setAlpha(0)
                grad.setColorAt(1, c2)
                p.setPen(Qt.NoPen)
                p.setBrush(grad)
                p.drawPath(fill)

            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color, 2.0))
            p.drawPath(path)

            # last point
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(pts[-1], 3.2, 3.2)
            halo = QColor(color)
            halo.setAlpha(60)
            p.setBrush(halo)
            p.drawEllipse(pts[-1], 7.0, 7.0)

        # legend
        p.setFont(QFont("Segoe UI", 8))
        x = plot.left()
        for name, color in self._colors.items():
            if not self._data.get(name):
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(x + 4, plot.top() + 4), 3, 3)
            p.setPen(QColor(TEXT_MUTED))
            p.drawText(QPointF(x + 12, plot.top() + 8), name.upper())
            x += p.fontMetrics().horizontalAdvance(name.upper()) + 32


class RadialGauge(QWidget):
    """270-degree arc gauge with animated needle-less fill."""

    def __init__(self, label: str = "BATTERY", color: str = GREEN,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(150, 150)
        self._label = label
        self._color = QColor(color)
        self._value = 0.0
        self._display = 0.0
        self._suffix = "%"
        self._sub = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(16)

    def set_value(self, value: float, sub: str = ""):
        self._value = max(0.0, min(100.0, float(value)))
        self._sub = sub

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def set_suffix(self, suffix: str):
        self._suffix = suffix

    def _animate(self):
        delta = self._value - self._display
        if abs(delta) > 0.2:
            self._display += delta * 0.15
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = min(self.width(), self.height())
        cx, cy = self.width() / 2, self.height() / 2
        r = w * 0.38
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(SURFACE_2), 10, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 225 * 16, -270 * 16)

        span = -270 * (self._display / 100.0)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        c = self._color
        grad.setColorAt(0, c.lighter(125))
        grad.setColorAt(1, c.darker(115))
        p.setPen(QPen(grad, 10, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 225 * 16, int(span * 16))

        # ticks
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        for i in range(0, 28):
            angle = math.radians(225 - i * 10)
            x1 = cx + math.cos(angle) * (r - 12)
            y1 = cy - math.sin(angle) * (r - 12)
            x2 = cx + math.cos(angle) * (r - 7)
            y2 = cy - math.sin(angle) * (r - 7)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        p.setPen(QColor(TEXT))
        p.setFont(QFont("Bahnschrift", 26, QFont.DemiBold))
        p.drawText(QRectF(cx - r, cy - r * 0.45, r * 2, r * 0.9), Qt.AlignCenter,
                   f"{self._display:.0f}{self._suffix}")

        p.setPen(QColor(TEXT_DIM))
        p.setFont(QFont("Cascadia Mono", 8))
        p.drawText(QRectF(cx - r, cy + r * 0.38, r * 2, 18), Qt.AlignCenter, self._label.upper())

        if self._sub:
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(QRectF(cx - r, cy + r * 0.38 + 16, r * 2, 16), Qt.AlignCenter, self._sub)


class LevelBar(QWidget):
    """Horizontal labelled bar for servo / resource values."""

    def __init__(self, label: str, color: str = CYAN, minimum: float = 0.0,
                 maximum: float = 100.0, suffix: str = "°", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(34)
        self._label = label
        self._color = QColor(color)
        self._minimum = minimum
        self._maximum = maximum
        self._value = minimum
        self._suffix = suffix
        self._show_value = True

    def set_value(self, value: float):
        self._value = max(self._minimum, min(self._maximum, float(value)))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        label_w = 92
        p.setPen(QColor(TEXT_MUTED))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(0, 0, label_w, h), Qt.AlignLeft | Qt.AlignVCenter,
                   self._label.replace("_", " ").title())

        track = QRectF(label_w, h / 2 - 4, w - label_w - 52, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(SURFACE_2))
        p.drawRoundedRect(track, 4, 4)

        ratio = (self._value - self._minimum) / max(1e-6, self._maximum - self._minimum)
        fill = QRectF(track)
        fill.setWidth(max(2.0, track.width() * ratio))
        grad = QLinearGradient(fill.topLeft(), fill.topRight())
        grad.setColorAt(0, self._color.darker(140))
        grad.setColorAt(1, self._color)
        p.setBrush(grad)
        p.drawRoundedRect(fill, 4, 4)

        if self._show_value:
            p.setPen(QColor(TEXT))
            p.setFont(QFont("Cascadia Mono", 8))
            p.drawText(QRectF(w - 50, 0, 50, h), Qt.AlignRight | Qt.AlignVCenter,
                       f"{self._value:.0f}{self._suffix}")


class Waveform(QWidget):
    """Live audio-level visualiser drawn as a mirrored bar waveform."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(70)
        self._bars = deque(maxlen=64)
        self._level = 0.0
        self._active = False
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, float(level)))
        self._active = self._level > 0.02

    def _tick(self):
        if self._active:
            base = self._level
            self._bars.append(min(1.0, base * (0.55 + random.random() * 0.9)))
        else:
            self._bars.append(0.02 + 0.02 * random.random())
        self._t += 0.05
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        n = len(self._bars) or 1
        gap = 2
        bar_w = max(2.0, (w - gap * (n - 1)) / n)
        cy = h / 2
        for i, v in enumerate(self._bars):
            bh = max(2.0, v * (h - 8))
            x = i * (bar_w + gap)
            color = QColor(CYAN if v < 0.75 else AMBER)
            color.setAlpha(90 + int(165 * v))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, cy - bh / 2, bar_w, bh), 1.5, 1.5)

        if not self._active:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(QFont("Cascadia Mono", 8))
            p.drawText(self.rect(), Qt.AlignCenter, "MIC · STANDBY")
