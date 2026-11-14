"""Telemetry page — charts, servo activity and system diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
)

from core.hardware import get_hardware_config
from ui.theme import AMBER, CYAN, GREEN, PURPLE, TEXT, TEXT_DIM, TEXT_MUTED, YELLOW
from ui.widgets.charts import LevelBar, TelemetryChart
from ui.widgets.common import Card, MetricTile, SectionLabel, mono_label


class TelemetryPage(QWidget):
    def __init__(self, backend, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.backend = backend
        self.hw = get_hardware_config()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        tiles = QGridLayout()
        tiles.setSpacing(12)
        self.tile_voltage = MetricTile("Voltaje", "V", YELLOW)
        self.tile_current = MetricTile("Consumo", "A", AMBER)
        self.tile_heap = MetricTile("Heap libre", "KB", CYAN)
        self.tile_tof = MetricTile("Distancia ToF", "mm", PURPLE)
        for i, tile in enumerate((self.tile_voltage, self.tile_current, self.tile_heap, self.tile_tof)):
            tile.setMinimumHeight(98)
            tiles.addWidget(tile, 0, i)
        root.addLayout(tiles)

        charts = QHBoxLayout()
        charts.setSpacing(12)

        battery_card = Card("Energía", "batería y temperatura")
        self.chart = TelemetryChart(
            {"Batería %": GREEN, "Temp °C": AMBER}, capacity=240, y_min=0, y_max=100
        )
        self.chart.setMinimumHeight(190)
        battery_card.body.addWidget(self.chart)
        charts.addWidget(battery_card, 3)

        servos_card = Card("Actividad de servos", "posición actual")
        self.servo_bars = {}
        for sid in self.hw.servos:
            bar = LevelBar(sid, "#38d6ff" if sid.startswith("head") else "#b18cff",
                           -180, 180, "°")
            servos_card.body.addWidget(bar)
            self.servo_bars[sid] = bar
        charts.addWidget(servos_card, 2)
        root.addLayout(charts, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        console_card = Card("Bus de datos", "JSON Lines · 115200 baud")
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(400)
        self.console.setStyleSheet(
            "background: #050a0f; border: 1px solid #122030; border-radius: 8px;"
            "font-family: 'Cascadia Mono'; font-size: 10px; color: #7e93a6;"
        )
        console_card.body.addWidget(self.console, 1)
        bottom.addWidget(console_card, 3)

        info_card = Card("Especificaciones")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(7)
        specs = [
            ("MCU", self.hw.mcu.type),
            ("Puerto", self.hw.mcu.port),
            ("Baudrate", f"{self.hw.mcu.baudrate}"),
            ("Protocolo", self.hw.mcu.protocol),
            ("Servos", f"{len(self.hw.servos)} × PCA9685"),
            ("Cámara", f"{self.hw.camera.width}×{self.hw.camera.height} @ {self.hw.camera.fps}fps"),
            ("Batería", self.hw.power.battery_type),
            ("Watchdog", f"{self.hw.behavior.watchdog_timeout:.0f} s"),
            ("Rango bat.", f"{self.hw.power.min_voltage}–{self.hw.power.max_voltage} V"),
        ]
        for i, (key, value) in enumerate(specs):
            k = QLabel(key.upper())
            k.setStyleSheet(
                f"color: {TEXT_DIM}; font-family: 'Cascadia Mono'; font-size: 9px; letter-spacing: 1px;"
            )
            v = QLabel(str(value))
            v.setStyleSheet(f"color: {TEXT_MUTED}; font-family: 'Cascadia Mono'; font-size: 10px;")
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1)
        info_card.body.addLayout(grid)
        info_card.body.addStretch()
        bottom.addWidget(info_card, 2)
        root.addLayout(bottom, 1)

    # -------------------------------------------------------------- handlers
    def refresh_state(self, state):
        if state is None:
            return
        voltage = float(getattr(state, "battery_voltage", 0.0))
        battery = int(getattr(state, "battery_percent", 0))
        temp = float(getattr(state, "temperature_c", 0.0))
        heap = int(getattr(state, "free_heap", 0))
        tof = int(getattr(state, "tof_distance_mm", 0))

        self.tile_voltage.set_value(f"{voltage:.2f}", "rieles principales")
        self.tile_current.set_value(f"{voltage / 2.6:.2f}" if voltage else "--", "estimado")
        self.tile_heap.set_value(f"{heap / 1024:.0f}", "memoria disponible")
        self.tile_tof.set_value(f"{tof}" if tof else "--", "sensor frontal")

        self.chart.push("Batería %", battery)
        self.chart.push("Temp °C", temp)

        for sid, data in getattr(state, "servos", {}).items():
            if sid in self.servo_bars:
                try:
                    self.servo_bars[sid].set_value(float(data.get("current_angle", 0)))
                except Exception:
                    pass

    def append_event(self, kind: str, message: str):
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if kind in ("robot", "error", "warning", "system"):
            self.console.appendPlainText(f"[{stamp}] {kind.upper():7s} {message}")
        elif kind == "vision":
            self.console.appendPlainText(f"[{stamp}] VISION  {message}")
        elif kind == "success":
            self.console.appendPlainText(f"[{stamp}] OK      {message}")
