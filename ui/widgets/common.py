"""Reusable UI primitives: cards, metric tiles, status pills, event feed."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget,
)

from ui.theme import (
    AMBER, BORDER_SOFT, CYAN, FONT_DISPLAY, FONT_MONO, GREEN, RED, SURFACE_2,
    TEXT, TEXT_DIM, TEXT_MUTED, YELLOW,
)


class Card(QFrame):
    """Panel with optional title and right-hand accessory row."""

    def __init__(self, title: str = "", subtitle: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(18, 16, 18, 16)
        self._outer.setSpacing(12)

        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Hint")
        self.header.addWidget(self.title_label)
        self.header.addWidget(self.subtitle_label)
        self.header.addStretch()
        if title:
            self._outer.addLayout(self.header)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        self._outer.addLayout(self.body)

    def add_header_widget(self, widget: QWidget):
        self.header.addWidget(widget)

    def set_title(self, text: str):
        self.title_label.setText(text)


class SectionLabel(QLabel):
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text.upper(), parent)
        self.setObjectName("SectionLabel")


class Divider(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)


class StatusPill(QWidget):
    """Rounded pill with a colored dot and label — used for mode/connection."""

    def __init__(self, text: str = "OFFLINE", color: str = RED, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._text = text
        self._color = QColor(color)
        self._dot = QColor(color)
        self.setFixedHeight(28)
        self.setMinimumWidth(96)
        self._font = QFont("Segoe UI", 8)
        self._font.setBold(True)
        self._font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)

    def set_status(self, text: str, color: str):
        self._text = text.upper()
        self._color = QColor(color)
        self._dot = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        bg = QColor(self._color)
        bg.setAlpha(28)
        border = QColor(self._color)
        border.setAlpha(90)
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 14, 14)
        p.drawPath(path)

        p.setPen(Qt.NoPen)
        p.setBrush(self._dot)
        p.drawEllipse(12, self.height() // 2 - 3, 6, 6)

        p.setFont(self._font)
        p.setPen(self._color)
        p.drawText(rect.adjusted(26, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, self._text)


class MetricTile(QFrame):
    """KPI card: label, big value, unit, optional trend/subtitle and accent bar."""

    def __init__(self, label: str, unit: str = "", color: str = CYAN, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Tile")
        self.setMinimumHeight(104)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._color = QColor(color)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self.label = QLabel(label.upper())
        self.label.setObjectName("SectionLabel")
        self.icon = QLabel("●")
        self.icon.setStyleSheet(f"color: {color}; font-size: 9px;")
        top.addWidget(self.label)
        top.addStretch()
        top.addWidget(self.icon)
        layout.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.value = QLabel("--")
        self.value.setObjectName("MetricValue")
        self.unit = QLabel(unit)
        self.unit.setObjectName("HeroUnit")
        row.addWidget(self.value)
        row.addWidget(self.unit, 0, Qt.AlignBottom)
        row.addStretch()
        layout.addLayout(row)

        self.sub = QLabel("Sin datos")
        self.sub.setObjectName("Hint")
        layout.addWidget(self.sub)

    def set_value(self, value: str, sub: Optional[str] = None):
        self.value.setText(value)
        if sub is not None:
            self.sub.setText(sub)


class EventFeed(QListWidget):
    """Compact, colored chronological event list."""

    MAX_ROWS = 200

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setSelectionMode(QListWidget.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; }}"
            f"QListWidget::item {{ padding: 3px 0px; }}"
        )

    def push(self, kind: str, message: str):
        colors = {
            "system": TEXT_MUTED,
            "robot": AMBER,
            "user": CYAN,
            "vision": "#b18cff",
            "voice": YELLOW,
            "ai": GREEN,
            "error": RED,
            "warning": YELLOW,
            "success": GREEN,
        }
        color = colors.get(kind, TEXT)
        stamp = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem()
        html = (
            f'<span style="color:{TEXT_DIM}; font-family:{FONT_MONO}; font-size:10px;">{stamp}</span> '
            f'<span style="color:{color}; font-family:{FONT_MONO}; font-size:11px;">{message}</span>'
        )
        label = QLabel(html)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setContentsMargins(2, 2, 2, 2)
        item.setSizeHint(QSize(100, max(20, label.sizeHint().height())))
        self.addItem(item)
        self.setItemWidget(item, label)
        while self.count() > self.MAX_ROWS:
            self.takeItem(0)
        QTimer.singleShot(0, lambda: self.scrollToBottom())


class GhostButtonStyles:
    """Small helper constants for consistent buttons inside pages."""


def mono_label(text: str, color: str = TEXT_MUTED, size: int = 11) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {color}; font-family: '{FONT_MONO}'; font-size: {size}px;")
    return label


def display_label(text: str, color: str = TEXT, size: int = 14, bold: bool = False) -> QLabel:
    label = QLabel(text)
    weight = "700" if bold else "500"
    label.setStyleSheet(
        f"color: {color}; font-family: '{FONT_DISPLAY}'; font-size: {size}px; font-weight: {weight};"
    )
    return label


class FadeIn:
    """Utility: fade a widget in by animating its opacity effect."""

    @staticmethod
    def apply(widget: QWidget, duration: int = 220):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        from PySide6.QtCore import QPropertyAnimation
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        widget._fade_anim = anim
