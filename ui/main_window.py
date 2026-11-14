"""Main application window — sidebar navigation, top bar, page stack, status bar."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from core.hardware import get_hardware_config
from ui.backend import RobotBackend, spawn
from ui.pages.control import ControlPage
from ui.pages.dashboard import DashboardPage
from ui.pages.settings_page import SettingsPage
from ui.pages.telemetry import TelemetryPage
from ui.pages.vision_page import VisionPage
from ui.pages.voice import VoicePage
from ui.theme import (
    AMBER, APP_QSS, BG, BORDER_SOFT, CYAN, GREEN, RED, SURFACE, TEXT, TEXT_DIM,
    TEXT_MUTED, YELLOW, mode_color, mood_color,
)
from ui.widgets.common import StatusPill


APP_VERSION = "2.0.0"


class LogoMark(QWidget):
    """Small painted Wall-E eye pair used as the app mark."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(38, 30)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(AMBER))
        p.drawRoundedRect(0, 0, 38, 30, 7, 7)
        p.setBrush(QColor("#0a1119"))
        p.drawRoundedRect(4, 9, 12, 12, 3, 3)
        p.drawRoundedRect(22, 9, 12, 12, 3, 3)
        p.setBrush(QColor(CYAN))
        p.drawRoundedRect(7, 12, 6, 6, 2, 2)
        p.drawRoundedRect(25, 12, 6, 6, 2, 2)


class Toast(QFrame):
    """Transient notification sliding in below the top bar."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(48)
        self.setMinimumWidth(280)
        self._label = QLabel("", self)
        self._label.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; background: transparent; padding: 0 16px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 16, 0)
        layout.addWidget(self._label)
        self.hide()

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)

    def show_message(self, message: str, kind: str = "info"):
        colors = {"info": CYAN, "success": GREEN, "warning": YELLOW, "error": RED}
        color = colors.get(kind, CYAN)
        self.setStyleSheet(
            f"QFrame#Toast {{ background: #0d1824; border: 1px solid {color};"
            f" border-left: 4px solid {color}; border-radius: 8px; }}"
        )
        self._label.setText(message)
        self.adjustSize()
        self.move(self.parentWidget().width() - self.width() - 26, 86)
        self._effect.setOpacity(0.0)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        QTimer.singleShot(3400, self.hide)


class MainWindow(QMainWindow):
    def __init__(self, mock_default: bool = False):
        super().__init__()
        self.hw = get_hardware_config()
        self.backend = RobotBackend(self)
        self.mock_default = mock_default
        self._close_armed = False
        self._connecting = False

        self.setWindowTitle("Wall·E Companion — Mission Control")
        self.setMinimumSize(1240, 780)
        self.resize(1460, 900)
        self.setStyleSheet(APP_QSS)

        self._build_ui()
        self._build_shortcuts()
        self._wire_backend()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)
        self.clock_timer.start(1000)
        self._tick_clock()

        self.toast = Toast(self)
        self._maybe_autoconnect()

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._build_topbar())

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {BG};")
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(22, 18, 22, 14)
        wrap_layout.setSpacing(0)
        wrap_layout.addWidget(self.stack)
        main_layout.addWidget(wrap, 1)

        main_layout.addWidget(self._build_statusbar())
        layout.addWidget(main, 1)

        # pages
        self.dashboard = DashboardPage(self.backend)
        self.control = ControlPage(self.backend)
        self.vision = VisionPage(self.backend)
        self.voice = VoicePage(self.backend)
        self.telemetry = TelemetryPage(self.backend)
        self.settings = SettingsPage(self.backend)

        self.pages = {
            "dashboard": ("Panel", "Estado en vivo de la unidad", self.dashboard),
            "control": ("Control", "Articulaciones y presets de movimiento", self.control),
            "vision": ("Visión", "Cámara y percepción artificial", self.vision),
            "voice": ("Voz & IA", "Diálogo, síntesis y personalidad", self.voice),
            "telemetry": ("Telemetría", "Bus de datos y diagnóstico", self.telemetry),
            "settings": ("Ajustes", "Conexión, comportamiento y sistema", self.settings),
        }
        for _, (_, _, page) in self.pages.items():
            self.stack.addWidget(page)

        self._wire_pages()
        self.nav_buttons["dashboard"].setChecked(True)
        self._switch_page("dashboard")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(224)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(LogoMark())
        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel("WALL·E")
        name.setObjectName("BrandMark")
        sub = QLabel("COMPANION OS")
        sub.setObjectName("BrandSub")
        text.addWidget(name)
        text.addWidget(sub)
        brand.addLayout(text)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(20)

        section = QLabel("NAVEGACIÓN")
        section.setObjectName("SectionLabel")
        layout.addWidget(section)
        layout.addSpacing(4)

        self.nav_buttons: Dict[str, QPushButton] = {}
        icons = {
            "dashboard": "◉", "control": "☰", "vision": "◫",
            "voice": "♪", "telemetry": "◔", "settings": "⚙",
        }
        for key, (title, _, _) in getattr(self, "pages", {}).items() if hasattr(self, "pages") else []:
            pass

        for key in ("dashboard", "control", "vision", "voice", "telemetry", "settings"):
            titles = {
                "dashboard": "Panel", "control": "Control", "vision": "Visión",
                "voice": "Voz & IA", "telemetry": "Telemetría", "settings": "Ajustes",
            }
            btn = QPushButton(f"  {icons.get(key, '•')}   {titles[key]}")
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(42)
            btn.clicked.connect(lambda _=False, k=key: self._switch_page(k))
            layout.addWidget(btn)
            self.nav_buttons[key] = btn

        layout.addStretch()

        conn_card = QFrame()
        conn_card.setStyleSheet(
            f"background: {SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 10px;"
        )
        card_layout = QVBoxLayout(conn_card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)
        self.sidebar_pill = StatusPill("OFFLINE", RED)
        card_layout.addWidget(self.sidebar_pill)
        self.sidebar_port = QLabel(self.hw.mcu.port)
        self.sidebar_port.setStyleSheet(
            f"color: {TEXT_DIM}; font-family: 'Cascadia Mono'; font-size: 9px;"
        )
        card_layout.addWidget(self.sidebar_port)
        layout.addWidget(conn_card)

        layout.addSpacing(8)
        version = QLabel(f"v{APP_VERSION} · BUILD 2026.10")
        version.setStyleSheet(
            f"color: #3c4d5c; font-family: 'Cascadia Mono'; font-size: 8px;"
        )
        layout.addWidget(version)
        return sidebar

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(70)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(22, 0, 22, 0)
        layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = QLabel("Panel")
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel("Estado en vivo de la unidad")
        self.page_subtitle.setObjectName("PageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        layout.addLayout(titles)
        layout.addStretch()

        self.mode_pill = StatusPill("BOOTING", CYAN)
        self.mood_pill = StatusPill("IDLE", CYAN)
        self.battery_pill = StatusPill("BAT --%", YELLOW)
        for pill in (self.mode_pill, self.mood_pill, self.battery_pill):
            layout.addWidget(pill)

        self.clock_label = QLabel("--:--:--")
        self.clock_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: 'Cascadia Mono'; font-size: 12px;"
        )
        layout.addWidget(self.clock_label)

        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.setObjectName("Primary")
        self.connect_btn.setMinimumWidth(120)
        self.connect_btn.setMinimumHeight(34)
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self._toggle_connection)
        layout.addWidget(self.connect_btn)
        return bar

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(30)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(22, 0, 22, 0)
        layout.setSpacing(18)
        self.status_msg = QLabel("Listo")
        self.status_msg.setStyleSheet(f"color: {TEXT_DIM}; font-family: 'Cascadia Mono'; font-size: 9px;")
        layout.addWidget(self.status_msg)
        layout.addStretch()
        self.status_port = QLabel(f"PORT {self.hw.mcu.port}")
        self.status_fps = QLabel("FPS --")
        self.status_heap = QLabel("HEAP --")
        for label in (self.status_port, self.status_fps, self.status_heap):
            label.setStyleSheet(f"color: {TEXT_DIM}; font-family: 'Cascadia Mono'; font-size: 9px;")
            layout.addWidget(label)
        return bar

    def _wire_pages(self):
        self.dashboard.moodRequested.connect(self._request_mood)
        self.dashboard.actionRequested.connect(self._run_action)
        self.control.moodRequested.connect(self._request_mood)
        self.settings.connectRequested.connect(self._connect)
        self.settings.disconnectRequested.connect(self._disconnect)
        self.settings.preferencesSaved.connect(
            lambda: self._notify("Preferencias guardadas", "success")
        )

    def _build_shortcuts(self):
        for i, key in enumerate(self.pages.keys()):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda k=key: self._switch_page(k))
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        full = QShortcut(QKeySequence("F11"), self)
        full.activated.connect(self._toggle_fullscreen)
        esc = QShortcut(QKeySequence("Escape"), self)
        esc.activated.connect(lambda: self.showNormal() if self.isFullScreen() else None)

    def _toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    # ------------------------------------------------------------------ pages
    def _switch_page(self, key: str):
        if key not in self.pages:
            return
        title, subtitle, page = self.pages[key]
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        self.stack.setCurrentWidget(page)
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)
        self.status_msg.setText(f"SECCIÓN · {title.upper()}")

    # -------------------------------------------------------------- backend
    def _wire_backend(self):
        self.backend.stateUpdated.connect(self._on_state)
        self.backend.modeChanged.connect(self._on_mode)
        self.backend.moodChanged.connect(self._on_mood)
        self.backend.connectionChanged.connect(self._on_connection)
        self.backend.event.connect(self._on_event)
        self.backend.facesUpdated.connect(self._on_faces)
        self.backend.transcriptionReceived.connect(self._on_transcription)
        self.backend.audioLevelChanged.connect(self._on_level)
        self.backend.visionFpsChanged.connect(self._on_fps)
        self.backend.errorOccurred.connect(lambda msg: self._notify(msg, "error"))

    def _on_state(self, state):
        for page in self.pages.values():
            fn = getattr(page[2], "refresh_state", None)
            if fn:
                fn(state)
        try:
            self.battery_pill.set_status(
                f"BAT {int(state.battery_percent)}%",
                GREEN if state.battery_percent > 40 else (YELLOW if state.battery_percent > 20 else RED),
            )
            heap = int(getattr(state, "free_heap", 0))
            self.status_heap.setText(f"HEAP {heap / 1024:.0f}K")
            servos = getattr(state, "servos", {})
            self.sidebar_port.setText(f"{self.backend.port} · {len(servos)} CH")
        except Exception:
            pass

    def _on_mode(self, mode: str):
        self.mode_pill.set_status(mode.replace("_", " "), mode_color(mode))
        for page in self.pages.values():
            fn = getattr(page[2], "set_mode", None)
            if fn:
                fn(mode)

    def _on_mood(self, mood: str):
        self.mood_pill.set_status(mood, mood_color(mood))
        for page in self.pages.values():
            fn = getattr(page[2], "set_mood", None)
            if fn:
                fn(mood)

    def _on_connection(self, connected: bool, port: str):
        self.connect_btn.setText("Desconectar" if connected else "Conectar")
        self.connect_btn.setObjectName("Danger" if connected else "Primary")
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
        self.sidebar_pill.set_status("EN LÍNEA" if connected else "OFFLINE",
                                     GREEN if connected else RED)
        self.status_port.setText(f"PORT {port}")
        self.sidebar_port.setText(port)
        for page in self.pages.values():
            fn = getattr(page[2], "set_connected", None)
            if fn:
                fn(connected, self.backend.mock)
        if connected:
            self._notify(f"Unidad conectada en {port}", "success")
        else:
            self._notify("Unidad desconectada", "warning")

    def _on_faces(self, faces):
        for page in self.pages.values():
            fn = getattr(page[2], "set_faces", None)
            if fn:
                fn(faces)

    def _on_transcription(self, text: str):
        self.voice.set_transcription(text)

    def _on_level(self, level: float):
        self.dashboard.set_level(level)
        self.voice.set_level(level)

    def _on_fps(self, fps: float):
        self.status_fps.setText(f"FPS {fps:4.1f}")

    def _on_event(self, kind: str, message: str):
        for page in self.pages.values():
            fn = getattr(page[2], "append_event", None)
            if fn:
                fn(kind, message)
        if kind in ("error", "warning", "success"):
            self.status_msg.setText(message[:90])

    # -------------------------------------------------------------- commands
    def _toggle_connection(self):
        if self.backend.connected:
            self._disconnect()
        else:
            self._connect(
                self.settings.port_combo.currentText(),
                self.settings.mock_check.isChecked() or self.mock_default,
            )

    def _connect(self, port: str, mock: bool):
        if self._connecting:
            return
        self._connecting = True
        self.connect_btn.setText("Conectando…")
        self.connect_btn.setEnabled(False)
        self._notify("Iniciando servicios del robot…", "info")
        spawn(self._connect_async(port, mock))

    async def _connect_async(self, port: str, mock: bool):
        try:
            await self.backend.connect(port, mock)
        finally:
            self._connecting = False
            self.connect_btn.setEnabled(True)
            if not self.backend.connected:
                self.connect_btn.setText("Conectar")

    def _disconnect(self):
        spawn(self.backend.disconnect())

    def _maybe_autoconnect(self):
        if self.mock_default:
            QTimer.singleShot(700, lambda: self._connect("MOCK", True))
            return
        prefs = self.settings
        if prefs.autoconnect_check.isChecked():
            QTimer.singleShot(
                900,
                lambda: self._connect(prefs.port_combo.currentText(), prefs.mock_check.isChecked()),
            )

    def _request_mood(self, mood: str):
        if self.backend.connected:
            spawn(self.backend.set_mood(mood))
            self._notify(f"Estado de ánimo · {mood}", "info")
        else:
            self._on_mood(mood)

    def _run_action(self, action: str):
        if action == "stop":
            reply = QMessageBox.question(
                self, "Emergency Stop",
                "¿Detener todos los servos inmediatamente?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                spawn(self.backend.emergency_stop())
                self._notify("PARADA DE EMERGENCIA EJECUTADA", "error")
            return
        if not self.backend.connected:
            self._notify("Conectá la unidad primero", "warning")
            return
        if action == "wake":
            spawn(self.backend.set_mood("curious"))
            spawn(self.backend.speak("Hola. Wall-E en línea y listo."))
        elif action == "sleep":
            spawn(self.backend.set_mood("sleeping"))
            self._notify("Unidad en reposo", "info")
        elif action == "home":
            spawn(self.backend.reset())
        else:
            spawn(self.backend.trigger(action))

    # ----------------------------------------------------------------- extras
    def _notify(self, message: str, kind: str = "info"):
        if hasattr(self, "toast"):
            self.toast.show_message(message, kind)

    def _tick_clock(self):
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast.move(self.width() - self.toast.width() - 26, 86)

    def closeEvent(self, event):
        if self.backend.connected and not self._close_armed:
            self._close_armed = True
            spawn(self.backend.disconnect())
            self._notify("Cerrando servicios…", "info")
            event.ignore()
            QTimer.singleShot(700, self.close)
            return
        event.accept()
