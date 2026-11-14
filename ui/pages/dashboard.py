"""Dashboard — live overview of the robot."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from core.hardware import get_hardware_config
from ui.theme import AMBER, CYAN, GREEN, RED, TEXT_DIM, TEXT_MUTED, YELLOW, mood_color
from ui.widgets.charts import LevelBar, RadialGauge, TelemetryChart
from ui.widgets.common import Card, EventFeed, MetricTile, SectionLabel, StatusPill
from ui.widgets.robot_face import RobotFace


class DashboardPage(QWidget):
    moodRequested = Signal(str)
    actionRequested = Signal(str)

    def __init__(self, backend, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.backend = backend
        self.hw = get_hardware_config()
        self._battery_history = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # ---------------------------------------------------------- KPI row
        kpi = QGridLayout()
        kpi.setSpacing(12)
        self.tile_battery = MetricTile("Batería", "%", GREEN)
        self.tile_temp = MetricTile("Temperatura", "°C", AMBER)
        self.tile_uptime = MetricTile("Uptime", "", CYAN)
        self.tile_faces = MetricTile("Rostros", "", "#b18cff")
        for i, tile in enumerate((self.tile_battery, self.tile_temp, self.tile_uptime, self.tile_faces)):
            kpi.addWidget(tile, 0, i)
        root.addLayout(kpi)

        # ------------------------------------------------------- main grid
        grid = QGridLayout()
        grid.setSpacing(12)

        # Robot card
        robot_card = Card("Unidad Wall-E", "visualización en vivo")
        self.face = RobotFace()
        self.face.setMinimumHeight(300)
        robot_card.body.addWidget(self.face)

        mood_row = QHBoxLayout()
        mood_row.setSpacing(6)
        self.mood_buttons = {}
        for mood in self.hw.moods.keys():
            btn = QPushButton(mood.capitalize())
            btn.setObjectName("Chip")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=mood: self.moodRequested.emit(m))
            mood_row.addWidget(btn)
            self.mood_buttons[mood] = btn
        mood_row.addStretch()
        robot_card.body.addLayout(mood_row)

        grid.addWidget(robot_card, 0, 0, 2, 1)

        # Telemetry card
        telemetry_card = Card("Telemetría", "últimos 45 s")
        chart_row = QHBoxLayout()
        chart_row.setSpacing(16)
        self.gauge = RadialGauge("Batería", GREEN)
        self.gauge.setFixedSize(168, 168)
        chart_row.addWidget(self.gauge)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.chart = TelemetryChart(
            {"Batería %": GREEN, "Temp °C": AMBER}, capacity=180, y_min=0, y_max=100
        )
        self.chart.setMinimumHeight(150)
        right.addWidget(self.chart)

        self.bar_temp = LevelBar("Temperatura", AMBER, 0, 100, "°C")
        self.bar_heap = LevelBar("Heap libre", CYAN, 0, 320, "K")
        right.addWidget(self.bar_temp)
        right.addWidget(self.bar_heap)
        chart_row.addLayout(right, 1)
        telemetry_card.body.addLayout(chart_row)
        grid.addWidget(telemetry_card, 0, 1, 1, 2)

        # Quick actions card
        actions_card = Card("Comandos rápidos")
        actions_grid = QGridLayout()
        actions_grid.setSpacing(8)
        actions = [
            ("Despertar", "wake", "Primary"),
            ("Saludar", "greet", ""),
            ("Celebrar", "celebrate", ""),
            ("Sorprender", "surprise", ""),
            ("Home", "home", "Ghost"),
            ("Dormir", "sleep", "Ghost"),
        ]
        for i, (label, key, style) in enumerate(actions):
            btn = QPushButton(label)
            if style:
                btn.setObjectName(style)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(36)
            btn.clicked.connect(lambda _=False, k=key: self.actionRequested.emit(k))
            actions_grid.addWidget(btn, i // 3, i % 3)
        actions_card.body.addLayout(actions_grid)

        stop = QPushButton("EMERGENCY STOP")
        stop.setObjectName("Danger")
        stop.setMinimumHeight(40)
        stop.setCursor(Qt.PointingHandCursor)
        stop.clicked.connect(lambda: self.actionRequested.emit("stop"))
        actions_card.body.addWidget(stop)
        grid.addWidget(actions_card, 1, 1, 1, 1)

        # Resources card
        resources_card = Card("Recursos")
        self.bar_battery = LevelBar("Batería", GREEN, 0, 100, "%")
        self.bar_servo = LevelBar("Servo máx", "#b18cff", 0, 180, "°")
        self.bar_signal = LevelBar("Señal", CYAN, 0, 100, "%")
        resources_card.body.addWidget(self.bar_battery)
        resources_card.body.addWidget(self.bar_servo)
        resources_card.body.addWidget(self.bar_signal)
        self.pill_serial = StatusPill("SERIAL", RED)
        self.pill_vision = StatusPill("VISIÓN", RED)
        self.pill_audio = StatusPill("AUDIO", RED)
        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        for pill in (self.pill_serial, self.pill_vision, self.pill_audio):
            pill_row.addWidget(pill)
        resources_card.body.addLayout(pill_row)
        grid.addWidget(resources_card, 1, 2, 1, 1)

        grid.setColumnStretch(0, 4)
        grid.setColumnStretch(1, 5)
        grid.setColumnStretch(2, 3)
        root.addLayout(grid, 1)

        # -------------------------------------------------------- event feed
        feed_card = Card("Actividad reciente")
        clear = QPushButton("Limpiar")
        clear.setObjectName("Ghost")
        clear.clicked.connect(lambda: self.feed.clear())
        feed_card.add_header_widget(clear)
        self.feed = EventFeed()
        self.feed.setMinimumHeight(150)
        self.feed.push("system", "Interfaz lista. Esperando conexión con la unidad.")
        feed_card.body.addWidget(self.feed)
        root.addWidget(feed_card)

    # ------------------------------------------------------------- handlers
    def refresh_state(self, state):
        if state is None:
            return
        battery = int(getattr(state, "battery_percent", 0))
        voltage = float(getattr(state, "battery_voltage", 0.0))
        temp = float(getattr(state, "temperature_c", 0.0))
        uptime_ms = int(getattr(state, "uptime_ms", 0))
        heap = int(getattr(state, "free_heap", 0))

        self.tile_battery.set_value(f"{battery}", f"{voltage:.2f} V · nominal")
        self.tile_temp.set_value(f"{temp:.1f}", "sensor interno")
        secs = uptime_ms // 1000
        self.tile_uptime.set_value(
            f"{secs // 3600:02d}:{(secs // 60) % 60:02d}:{secs % 60:02d}", "desde el arranque"
        )
        faces = len(self.backend.faces) if self.backend else 0
        self.tile_faces.set_value(str(faces), "en campo de visión")

        color = GREEN if battery > 40 else (YELLOW if battery > 20 else RED)
        self.gauge.set_value(battery, f"{voltage:.2f} V")
        self.gauge.set_color(color)
        self.bar_battery.set_value(battery)
        self.bar_temp.set_value(temp)
        self.bar_heap.set_value(heap / 1000.0)
        self.bar_signal.set_value(max(0, min(100, 100 - abs(temp - 35) * 4)))

        self.chart.push("Batería %", battery)
        self.chart.push("Temp °C", temp)

        max_servo = 0.0
        for servo in getattr(state, "servos", {}).values():
            try:
                max_servo = max(max_servo, abs(float(servo.get("current_angle", 0))))
            except Exception:
                pass
        self.bar_servo.set_value(min(180.0, max_servo))

        for sid, angle in getattr(state, "servos", {}).items():
            try:
                self.face.set_servo(sid, float(angle.get("current_angle", 0)))
            except Exception:
                pass

    def set_mode(self, mode: str):
        pass

    def set_mood(self, mood: str):
        self.face.set_mood(mood)
        for name, btn in self.mood_buttons.items():
            btn.setChecked(name == mood)

    def set_connected(self, connected: bool, mock: bool = False):
        self.face.set_connected(connected)
        good = GREEN if connected else RED
        self.pill_serial.set_status("SERIAL OK" if connected else "SERIAL", good)
        self.pill_vision.set_status("VISIÓN OK" if (connected and not mock) else "VISIÓN", good)
        self.pill_audio.set_status("AUDIO OK" if connected else "AUDIO", good)

    def set_faces(self, faces):
        self.tile_faces.set_value(str(len(faces or [])), "en campo de visión")

    def set_level(self, level: float):
        self.face.set_audio_level(level)

    def append_event(self, kind: str, message: str):
        self.feed.push(kind, message)
