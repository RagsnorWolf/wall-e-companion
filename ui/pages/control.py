"""Control page — servo manipulation, poses, mood presets and safety."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from core.hardware import get_hardware_config
from ui.backend import spawn
from ui.theme import (
    AMBER, CYAN, GREEN, PURPLE, RED, SERVO_COLORS, TEXT, TEXT_DIM, TEXT_MUTED, YELLOW,
)
from ui.widgets.common import Card, SectionLabel, StatusPill


class ServoRow(QWidget):
    valueChanged = Signal(str, float)

    def __init__(self, servo_id: str, servo, color: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.servo_id = servo_id
        self.servo = servo
        self._dragging = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(servo_id.replace("_", " ").upper())
        name.setStyleSheet(
            f"color: {TEXT}; font-family: 'Cascadia Mono'; font-size: 10px; letter-spacing: 1px;"
        )
        self.channel = QLabel(f"CH {servo.channel:02d}")
        self.channel.setStyleSheet(
            f"color: {TEXT_DIM}; font-family: 'Cascadia Mono'; font-size: 9px;"
        )
        self.angle_label = QLabel(f"{servo.default_angle:.0f}°")
        self.angle_label.setStyleSheet(
            f"color: {color}; font-family: 'Bahnschrift'; font-size: 12px; font-weight: 600;"
        )
        top.addWidget(name)
        top.addStretch()
        top.addWidget(self.channel)
        top.addSpacing(8)
        top.addWidget(self.angle_label)
        layout.addLayout(top)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(servo.angle_range[0]), int(servo.angle_range[1]))
        self.slider.setValue(int(servo.default_angle))
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(self._on_change)
        self.slider.sliderPressed.connect(self._on_press)
        self.slider.sliderReleased.connect(self._on_release)
        layout.addWidget(self.slider)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(90)
        self._debounce.timeout.connect(self._emit)

    def _on_press(self):
        self._dragging = True

    def _on_change(self, value: int):
        self.angle_label.setText(f"{value}°")
        if self._dragging:
            self._debounce.start()

    def _on_release(self):
        self._dragging = False
        self._debounce.stop()
        self._emit()

    def _emit(self):
        self.valueChanged.emit(self.servo_id, float(self.slider.value()))

    def set_current(self, angle: float):
        if self._dragging:
            return
        self.angle_label.setText(f"{self.slider.value()}°")
        self.slider.blockSignals(True)
        self.slider.setValue(int(max(self.slider.minimum(), min(self.slider.maximum(), angle))))
        self.slider.blockSignals(False)

    def set_angle(self, angle: float):
        self.slider.blockSignals(True)
        self.slider.setValue(int(max(self.slider.minimum(), min(self.slider.maximum(), angle))))
        self.slider.blockSignals(False)
        self.angle_label.setText(f"{angle:.0f}°")


class ControlPage(QWidget):
    moodRequested = Signal(str)

    def __init__(self, backend, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.backend = backend
        self.hw = get_hardware_config()
        self.rows: Dict[str, ServoRow] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        content = QHBoxLayout()
        content.setSpacing(12)

        # ------------------------------------------------------ servos card
        servo_card = Card("Articulaciones", "7 canales PCA9685 · rango calibrado")
        self.pill_link = StatusPill("DESCONECTADO", RED)
        servo_card.add_header_widget(self.pill_link)

        grid = QGridLayout()
        grid.setHorizontalSpacing(26)
        grid.setVerticalSpacing(14)
        for i, (sid, servo) in enumerate(self.hw.servos.items()):
            row = ServoRow(sid, servo, SERVO_COLORS.get(sid, CYAN))
            row.valueChanged.connect(self._send_servo)
            grid.addWidget(row, i // 2, i % 2)
            self.rows[sid] = row
        servo_card.body.addLayout(grid)

        servo_card.body.addSpacing(6)
        buttons = QHBoxLayout()
        home = QPushButton("Pose Home")
        home.setObjectName("Ghost")
        home.clicked.connect(self._home)
        test = QPushButton("Barrido de prueba")
        test.setObjectName("Ghost")
        test.clicked.connect(self._sweep)
        apply_all = QPushButton("Aplicar todo")
        apply_all.setObjectName("Primary")
        apply_all.clicked.connect(self._apply_all)
        buttons.addWidget(home)
        buttons.addWidget(test)
        buttons.addStretch()
        buttons.addWidget(apply_all)
        servo_card.body.addLayout(buttons)
        content.addWidget(servo_card, 3)

        right = QVBoxLayout()
        right.setSpacing(12)

        # ------------------------------------------------------- mood card
        mood_card = Card("Estados de ánimo", "presets expresivos")
        mood_grid = QGridLayout()
        mood_grid.setSpacing(8)
        self.mood_buttons = {}
        descriptions = {
            "idle": "Neutro · mirada al frente",
            "curious": "Cabeza inclinada · atento",
            "happy": "Ojos abiertos · alegre",
            "sad": "Cabeza baja · apagado",
            "alert": "Alerta máxima · tenso",
            "thinking": "Procesando · ojos finos",
            "sleeping": "Reposo · ojos cerrados",
        }
        for i, mood in enumerate(self.hw.moods.keys()):
            btn = QPushButton()
            btn.setObjectName("Ghost")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(52)
            box = QVBoxLayout(btn)
            box.setContentsMargins(10, 6, 10, 6)
            title = QLabel(mood.capitalize())
            title.setStyleSheet(f"color: {TEXT}; font-weight: 600; font-size: 12px; background: transparent;")
            sub = QLabel(descriptions.get(mood, "Preset"))
            sub.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px; background: transparent;")
            box.addWidget(title)
            box.addWidget(sub)
            btn.clicked.connect(lambda _=False, m=mood: self.moodRequested.emit(m))
            mood_grid.addWidget(btn, i // 2, i % 2)
            self.mood_buttons[mood] = btn
        mood_card.body.addLayout(mood_grid)
        right.addWidget(mood_card)

        # ---------------------------------------------------- safety card
        safety_card = Card("Seguridad", "control de parada")
        info = QLabel(
            "El watchdog del ESP32 detiene los servos si se pierde el enlace "
            f"durante más de {self.hw.behavior.watchdog_timeout:.0f} s."
        )
        info.setWordWrap(True)
        info.setObjectName("Hint")
        safety_card.body.addWidget(info)

        row = QHBoxLayout()
        self.reset_btn = QPushButton("Reset controlado")
        self.reset_btn.setObjectName("Ghost")
        self.reset_btn.clicked.connect(lambda: spawn(self.backend.reset()))
        self.stop_btn = QPushButton("EMERGENCY STOP")
        self.stop_btn.setObjectName("DangerSolid")
        self.stop_btn.setMinimumHeight(44)
        self.stop_btn.clicked.connect(lambda: spawn(self.backend.emergency_stop()))
        row.addWidget(self.reset_btn)
        row.addWidget(self.stop_btn, 1)
        safety_card.body.addLayout(row)
        right.addWidget(safety_card)
        right.addStretch()

        content.addLayout(right, 2)
        root.addLayout(content, 1)

    # --------------------------------------------------------------- actions
    def _send_servo(self, servo_id: str, angle: float):
        if self.backend and self.backend.connected:
            spawn(self.backend.move_servo(servo_id, angle))

    def _apply_all(self):
        if self.backend and self.backend.connected:
            spawn(self.backend.move_all({sid: r.slider.value() for sid, r in self.rows.items()}))

    def _home(self):
        for sid, servo in self.hw.servos.items():
            if sid in self.rows:
                self.rows[sid].set_angle(servo.default_angle)
        self._apply_all()

    def _sweep(self):
        """Animated demo sweep across every joint using timers."""
        sequence = []
        for sid, servo in self.hw.servos.items():
            lo, hi = servo.angle_range
            sequence.append((sid, float(lo)))
            sequence.append((sid, float(hi)))
            sequence.append((sid, float(servo.default_angle)))

        def step(index: int = 0):
            if index >= len(sequence):
                self._home()
                return
            sid, angle = sequence[index]
            if sid in self.rows:
                self.rows[sid].set_angle(angle)
            self._send_servo(sid, angle)
            QTimer.singleShot(420, lambda: step(index + 1))

        step()

    # -------------------------------------------------------------- handlers
    def refresh_state(self, state):
        for sid, data in getattr(state, "servos", {}).items():
            if sid in self.rows:
                try:
                    self.rows[sid].set_current(float(data.get("current_angle", 0)))
                except Exception:
                    pass

    def set_connected(self, connected: bool, mock: bool = False):
        self.pill_link.set_status("EN LÍNEA" if connected else "DESCONECTADO",
                                  GREEN if connected else RED)
        for btn in (self.reset_btn, self.stop_btn):
            btn.setEnabled(connected)

    def set_mood(self, mood: str):
        for name, btn in self.mood_buttons.items():
            active = name == mood
            btn.setStyleSheet(
                f"QPushButton {{ border-color: {AMBER if active else '#1a2a3a'}; "
                f"background: {'rgba(255,178,63,0.10)' if active else 'transparent'}; }}"
            )
