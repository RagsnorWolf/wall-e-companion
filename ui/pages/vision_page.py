"""Vision page — live camera, detection overlay and pipeline diagnostics."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from core.hardware import get_hardware_config
from ui.theme import AMBER, CYAN, GREEN, PURPLE, RED, TEXT, TEXT_DIM, TEXT_MUTED, YELLOW
from ui.widgets.common import Card, MetricTile, StatusPill
from ui.widgets.video_feed import VideoFeed


class VisionPage(QWidget):
    def __init__(self, backend, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.backend = backend
        self.hw = get_hardware_config()
        self._last_face_update = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        content = QHBoxLayout()
        content.setSpacing(12)

        feed_card = Card("Cámara principal", "stream USB · 640 × 480")
        self.pill_cam = StatusPill("OFFLINE", RED)
        self.overlay_check = QCheckBox("Overlay")
        self.overlay_check.setChecked(True)
        self.overlay_check.toggled.connect(self._toggle_overlay)
        snap = QPushButton("Captura")
        snap.setObjectName("Ghost")
        snap.clicked.connect(self._snapshot)
        feed_card.add_header_widget(self.overlay_check)
        feed_card.add_header_widget(snap)
        feed_card.add_header_widget(self.pill_cam)

        self.feed = VideoFeed()
        feed_card.body.addWidget(self.feed, 1)

        legend = QHBoxLayout()
        for label, color in (("ROSTRO", GREEN), ("EMOCIÓN", YELLOW), ("SIN SEÑAL", RED)):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color};")
            text = QLabel(label)
            text.setStyleSheet(f"color: {TEXT_DIM}; font-family: 'Cascadia Mono'; font-size: 9px;")
            legend.addWidget(dot)
            legend.addWidget(text)
            legend.addSpacing(12)
        legend.addStretch()
        self.fps_label = QLabel("0.0 FPS")
        self.fps_label.setStyleSheet(f"color: {TEXT_MUTED}; font-family: 'Cascadia Mono'; font-size: 10px;")
        legend.addWidget(self.fps_label)
        feed_card.body.addLayout(legend)
        content.addWidget(feed_card, 3)

        side = QVBoxLayout()
        side.setSpacing(12)

        tiles = QGridLayout()
        tiles.setSpacing(10)
        self.tile_faces = MetricTile("Rostros", "", GREEN)
        self.tile_fps = MetricTile("FPS", "", CYAN)
        self.tile_conf = MetricTile("Confianza", "%", PURPLE)
        self.tile_emotion = MetricTile("Emoción", "", AMBER)
        for i, tile in enumerate((self.tile_faces, self.tile_fps, self.tile_conf, self.tile_emotion)):
            tile.setMinimumHeight(96)
            tiles.addWidget(tile, i // 2, i % 2)
        side.addLayout(tiles)

        detect_card = Card("Detecciones", "seguimiento en vivo")
        self.face_list = QVBoxLayout()
        self.face_list.setSpacing(6)
        self.empty_label = QLabel("Sin rostros detectados")
        self.empty_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        self.face_list.addWidget(self.empty_label)
        detect_card.body.addLayout(self.face_list)
        detect_card.body.addStretch()
        side.addWidget(detect_card, 1)

        pipe_card = Card("Pipeline", "modelos de percepción")
        for name, state, color in (
            ("Detección de rostros", "Haar cascade", YELLOW),
            ("Reconocimiento facial", "pendiente", TEXT_DIM),
            ("Emociones", "heurística", CYAN),
            ("Objetos (YOLOv8)", "no cargado", TEXT_DIM),
        ):
            row = QHBoxLayout()
            label = QLabel(name)
            label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            value = QLabel(state)
            value.setStyleSheet(
                f"color: {color}; font-family: 'Cascadia Mono'; font-size: 10px;"
            )
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            pipe_card.body.addLayout(row)
        side.addWidget(pipe_card)

        content.addLayout(side, 2)
        root.addLayout(content, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pull_frame)
        self._timer.start(45)

    # -------------------------------------------------------------- internals
    def _toggle_overlay(self, enabled: bool):
        self.feed.set_overlay_visible(enabled)

    def _pull_frame(self):
        if not self.isVisible():
            return
        frame = self.backend.latest_frame() if self.backend else None
        if frame is not None:
            self.feed.set_frame(frame, self.backend.faces, self.backend.vision_fps)
            self.fps_label.setText(f"{self.backend.vision_fps:.1f} FPS")
            if self.backend.connected:
                self.pill_cam.set_status("EN VIVO", GREEN)
        else:
            self.pill_cam.set_status("SIN SEÑAL", RED)

    def _snapshot(self):
        frame = self.backend.latest_frame() if self.backend else None
        if frame is None:
            return
        out = Path(__file__).resolve().parents[2] / "capturas"
        out.mkdir(exist_ok=True)
        name = datetime.now().strftime("walle_%Y%m%d_%H%M%S.png")
        cv2.imwrite(str(out / name), frame)

    # -------------------------------------------------------------- handlers
    def set_connected(self, connected: bool, mock: bool = False):
        self.pill_cam.set_status("EN VIVO" if connected else "OFFLINE", GREEN if connected else RED)

    def set_faces(self, faces):
        faces = faces or []
        self.tile_faces.set_value(str(len(faces)), "en campo de visión")
        self.feed.set_faces(faces)

        while self.face_list.count():
            item = self.face_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not faces:
            self.empty_label = QLabel("Sin rostros detectados")
            self.empty_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
            self.face_list.addWidget(self.empty_label)
            self.tile_conf.set_value("--", "sin datos")
            self.tile_emotion.set_value("--", "sin datos")
            return

        best = max(faces, key=lambda f: getattr(f, "confidence", 0.0))
        self.tile_conf.set_value(f"{getattr(best, 'confidence', 0) * 100:.0f}", "mejor coincidencia")
        self.tile_emotion.set_value(
            (getattr(best, "emotion", None) or "neutral").capitalize(), "estimada"
        )

        for face in faces[:5]:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {GREEN}; font-size: 8px;")
            label = QLabel(getattr(face, "face_id", None) or "FACE")
            label.setStyleSheet(f"color: {TEXT}; font-family: 'Cascadia Mono'; font-size: 10px;")
            meta = QLabel(
                f"{(getattr(face, 'emotion', None) or 'neutral').upper()} · "
                f"{getattr(face, 'confidence', 0) * 100:.0f}%"
            )
            meta.setStyleSheet(f"color: {TEXT_MUTED}; font-family: 'Cascadia Mono'; font-size: 9px;")
            layout.addWidget(dot)
            layout.addWidget(label)
            layout.addStretch()
            layout.addWidget(meta)
            self.face_list.addWidget(row)

    def refresh_state(self, state):
        if self.backend and self.backend.vision_fps:
            self.tile_fps.set_value(f"{self.backend.vision_fps:.0f}", "procesados por segundo")
