"""Settings page — connection, behavior tuning, persistence and about."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core.hardware import get_hardware_config
from core.serial_comm import SerialComm
from ui.theme import AMBER, CYAN, GREEN, RED, TEXT, TEXT_DIM, TEXT_MUTED, YELLOW
from ui.widgets.common import Card, SectionLabel, StatusPill

PREFS_PATH = Path(__file__).resolve().parents[2] / "config" / "preferences.json"


class SettingsPage(QWidget):
    connectRequested = Signal(str, bool)   # port, mock
    disconnectRequested = Signal()
    preferencesSaved = Signal()

    def __init__(self, backend, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.backend = backend
        self.hw = get_hardware_config()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(12)

        # ------------------------------------------------------ connection
        conn = Card("Conexión", "enlace serial con la unidad")
        self.pill = StatusPill("DESCONECTADO", RED)
        conn.add_header_widget(self.pill)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        grid.addWidget(self._label("Puerto"), 0, 0)
        port_row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self._reload_ports()
        self.port_combo.setCurrentText(self.hw.mcu.port)
        refresh = QPushButton("↻")
        refresh.setObjectName("Ghost")
        refresh.setFixedWidth(34)
        refresh.clicked.connect(self._reload_ports)
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(refresh)
        grid.addLayout(port_row, 0, 1)

        grid.addWidget(self._label("Baudrate"), 1, 0)
        self.baud = QComboBox()
        for rate in (115200, 230400, 460800, 921600):
            self.baud.addItem(str(rate), rate)
        self.baud.setCurrentText(str(self.hw.mcu.baudrate))
        grid.addWidget(self.baud, 1, 1)

        self.mock_check = QCheckBox("Modo simulación (sin hardware)")
        grid.addWidget(self.mock_check, 2, 0, 1, 2)
        self.autoconnect_check = QCheckBox("Conectar automáticamente al iniciar")
        grid.addWidget(self.autoconnect_check, 3, 0, 1, 2)

        conn.body.addLayout(grid)
        self.connect_btn = QPushButton("Conectar unidad")
        self.connect_btn.setObjectName("Primary")
        self.connect_btn.setMinimumHeight(40)
        self.connect_btn.clicked.connect(self._toggle)
        conn.body.addWidget(self.connect_btn)
        left.addWidget(conn)

        # -------------------------------------------------------- behavior
        behav = Card("Comportamiento", "parámetros de movimiento")
        bg = QGridLayout()
        bg.setHorizontalSpacing(14)
        bg.setVerticalSpacing(10)

        bg.addWidget(self._label("Idle timeout"), 0, 0)
        self.idle_spin = QDoubleSpinBox()
        self.idle_spin.setRange(5, 300)
        self.idle_spin.setSuffix(" s")
        self.idle_spin.setValue(self.hw.behavior.idle_timeout)
        bg.addWidget(self.idle_spin, 0, 1)

        bg.addWidget(self._label("Smoothing"), 1, 0)
        self.smoothing_spin = QDoubleSpinBox()
        self.smoothing_spin.setRange(0.01, 1.0)
        self.smoothing_spin.setSingleStep(0.05)
        self.smoothing_spin.setValue(self.hw.behavior.smoothing_factor)
        bg.addWidget(self.smoothing_spin, 1, 1)

        bg.addWidget(self._label("Velocidad máx"), 2, 0)
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(10, 255)
        self.speed_spin.setValue(self.hw.behavior.max_servo_speed)
        bg.addWidget(self.speed_spin, 2, 1)

        bg.addWidget(self._label("Umbral ToF"), 3, 0)
        self.tof_spin = QSpinBox()
        self.tof_spin.setRange(50, 2000)
        self.tof_spin.setSuffix(" mm")
        self.tof_spin.setValue(self.hw.behavior.tof_threshold_mm)
        bg.addWidget(self.tof_spin, 3, 1)

        behav.body.addLayout(bg)
        hint = QLabel("Los cambios de comportamiento se aplican al firmware mediante comandos de configuración.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        behav.body.addWidget(hint)
        left.addWidget(behav)
        left.addStretch()
        columns.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(12)

        # ---------------------------------------------------------- about
        about = Card("Acerca de", "Wall-E Companion")
        title = QLabel("WALL·E // COMPANION")
        title.setStyleSheet(
            f"color: {AMBER}; font-family: 'Bahnschrift'; font-size: 20px; font-weight: 700; letter-spacing: 2px;"
        )
        version = QLabel("v2.0.0 · Mission Control Edition")
        version.setStyleSheet(f"color: {TEXT_MUTED}; font-family: 'Cascadia Mono'; font-size: 10px;")
        about.body.addWidget(title)
        about.body.addWidget(version)
        about.body.addSpacing(8)
        desc = QLabel(
            "Estación de control para el robot companion Wall-E. "
            "Telemetría en vivo, control de servos, visión artificial, "
            "voz y personalidad autónoma sobre ESP32-S3."
        )
        desc.setWordWrap(True)
        desc.setObjectName("Hint")
        about.body.addWidget(desc)
        about.body.addSpacing(6)
        for key, value in (
            ("Interfaz", "PySide6 / Qt 6"),
            ("Runtime", "Python 3.12 · asyncio"),
            ("Servicios", "Visión · Audio · IA · Serial"),
            ("Protocolo", "JSON Lines @ 115200"),
            ("Licencia", "MIT"),
        ):
            row = QHBoxLayout()
            k = QLabel(key.upper())
            k.setStyleSheet(f"color: {TEXT_DIM}; font-family: 'Cascadia Mono'; font-size: 9px;")
            v = QLabel(value)
            v.setStyleSheet(f"color: {TEXT_MUTED}; font-family: 'Cascadia Mono'; font-size: 10px;")
            row.addWidget(k)
            row.addStretch()
            row.addWidget(v)
            about.body.addLayout(row)
        right.addWidget(about)

        # ------------------------------------------------------ quick actions
        tools = Card("Mantenimiento")
        save = QPushButton("Guardar preferencias")
        save.setObjectName("Primary")
        save.clicked.connect(self.save_preferences)
        tools.body.addWidget(save)
        reload_cfg = QPushButton("Recargar hardware.yaml")
        reload_cfg.setObjectName("Ghost")
        reload_cfg.clicked.connect(self._reload_config)
        tools.body.addWidget(reload_cfg)
        open_logs = QPushButton("Abrir carpeta de logs")
        open_logs.setObjectName("Ghost")
        open_logs.clicked.connect(self._open_logs)
        tools.body.addWidget(open_logs)
        right.addWidget(tools)
        right.addStretch()
        columns.addLayout(right, 1)

        root.addLayout(columns, 1)
        self.load_preferences()

    # ---------------------------------------------------------------- helpers
    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        return label

    def _reload_ports(self):
        current = self.port_combo.currentText() if hasattr(self, "port_combo") else self.hw.mcu.port
        self.port_combo.clear()
        ports = SerialComm.list_ports()
        if not ports:
            ports = ["COM3", "COM4", "COM5"]
        self.port_combo.addItems(ports)
        self.port_combo.setCurrentText(current or self.hw.mcu.port)

    def _toggle(self):
        if self.backend and self.backend.connected:
            self.disconnectRequested.emit()
        else:
            self.connectRequested.emit(self.port_combo.currentText(), self.mock_check.isChecked())

    def _reload_config(self):
        try:
            self.hw.reload()
            self.idle_spin.setValue(self.hw.behavior.idle_timeout)
            self.smoothing_spin.setValue(self.hw.behavior.smoothing_factor)
            self.speed_spin.setValue(self.hw.behavior.max_servo_speed)
            self.tof_spin.setValue(self.hw.behavior.tof_threshold_mm)
            self.preferencesSaved.emit()
        except Exception:
            pass

    def _open_logs(self):
        import os
        logs = Path(__file__).resolve().parents[2] / "logs"
        logs.mkdir(exist_ok=True)
        os.startfile(str(logs))  # noqa: S606 — Windows-only desktop app

    # ----------------------------------------------------------- persistence
    def load_preferences(self):
        if not PREFS_PATH.exists():
            return
        try:
            data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
            self.port_combo.setCurrentText(data.get("port", self.hw.mcu.port))
            self.mock_check.setChecked(bool(data.get("mock", False)))
            self.autoconnect_check.setChecked(bool(data.get("auto_connect", False)))
            self.baud.setCurrentText(str(data.get("baudrate", self.hw.mcu.baudrate)))
        except Exception:
            pass

    def save_preferences(self):
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "port": self.port_combo.currentText(),
            "mock": self.mock_check.isChecked(),
            "auto_connect": self.autoconnect_check.isChecked(),
            "baudrate": int(self.baud.currentText()),
            "idle_timeout": self.idle_spin.value(),
            "smoothing_factor": self.smoothing_spin.value(),
            "max_servo_speed": self.speed_spin.value(),
            "tof_threshold_mm": self.tof_spin.value(),
        }
        PREFS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

        self.hw.mcu.port = data["port"]
        self.hw.mcu.baudrate = data["baudrate"]
        self.hw.behavior.idle_timeout = data["idle_timeout"]
        self.hw.behavior.smoothing_factor = data["smoothing_factor"]
        self.hw.behavior.max_servo_speed = data["max_servo_speed"]
        self.hw.behavior.tof_threshold_mm = data["tof_threshold_mm"]
        self.preferencesSaved.emit()

    # -------------------------------------------------------------- handlers
    def set_connected(self, connected: bool, mock: bool = False):
        self.pill.set_status("EN LÍNEA" if connected else "DESCONECTADO",
                             GREEN if connected else RED)
        self.connect_btn.setText("Desconectar unidad" if connected else "Conectar unidad")
        self.connect_btn.setObjectName("Danger" if connected else "Primary")
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
        self.port_combo.setEnabled(not connected)
        self.mock_check.setEnabled(not connected)
