"""Wall-E Companion - Desktop App (PySide6/Qt)"""

import sys
import asyncio
import qasync
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QSlider, QPushButton, QComboBox,
    QProgressBar, QTextEdit, QTabWidget, QCheckBox, QSpinBox,
    QDoubleSpinBox, QMessageBox, QStatusBar, QSplitter, QFrame
)
from PySide6.QtGui import QFont, QIcon, QColor, QPalette
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis

from core.hardware import get_hardware_config
from core.serial_comm import SerialComm, MockSerialComm
from core.state_machine import StateMachine, RobotMode, Mood
from core.personality import PersonalityEngine
from services.vision import VisionService
from services.audio import AudioService, MockAudioService
from services.ai_engine import AIEngine, AIEngineConfig


class WorkerSignals(QObject):
    status_update = Signal(dict)
    log_message = Signal(str, str)  # type, message
    servo_update = Signal(str, float)  # servo_id, angle
    connection_changed = Signal(bool)


class WallEDesktopApp(QMainWindow):
    def __init__(self, mock: bool = False):
        super().__init__()
        self.mock = mock
        self.hw = get_hardware_config()
        self.signals = WorkerSignals()
        
        # Components
        self.serial: Optional[SerialComm] = None
        self.state_machine: Optional[StateMachine] = None
        self.personality: Optional[PersonalityEngine] = None
        self.vision: Optional[VisionService] = None
        self.audio: Optional[AudioService] = None
        self.ai_engine: Optional[AIEngine] = None
        
        # Async loop
        self.loop = qasync.QEventLoop(self)
        asyncio.set_event_loop(self.loop)
        
        self.init_ui()
        self.connect_signals()
        
    def init_ui(self):
        self.setWindowTitle("Wall-E Companion - Control Panel")
        self.resize(1200, 800)
        
        # Dark theme
        self.setStyleSheet("""
            QMainWindow { background: #0d1117; color: #e6edf3; }
            QGroupBox { 
                border: 1px solid #30363d; 
                border-radius: 6px; 
                margin-top: 12px; 
                padding-top: 10px;
                font-weight: bold;
                color: #58a6ff;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLabel { color: #e6edf3; }
            QPushButton { 
                background: #21262d; 
                border: 1px solid #30363d; 
                border-radius: 4px; 
                padding: 8px 16px; 
                color: #e6edf3;
                font-weight: 500;
            }
            QPushButton:hover { background: #30363d; border-color: #58a6ff; }
            QPushButton:pressed { background: #161b22; }
            QPushButton:disabled { background: #161b22; color: #484f58; border-color: #21262d; }
            QPushButton#danger { background: #da3633; border-color: #da3633; }
            QPushButton#danger:hover { background: #f85149; }
            QPushButton#warning { background: #d29922; border-color: #d29922; color: #0d1117; }
            QPushButton#success { background: #238636; border-color: #238636; }
            QSlider::groove:horizontal { height: 6px; background: #161b22; border-radius: 3px; }
            QSlider::handle:horizontal { width: 16px; height: 16px; border-radius: 8px; background: #58a6ff; margin: -5px 0; }
            QProgressBar { border: 1px solid #30363d; border-radius: 4px; background: #161b22; text-align: center; color: #e6edf3; }
            QProgressBar::chunk { background: #238636; border-radius: 3px; }
            QTextEdit { background: #161b22; border: 1px solid #30363d; border-radius: 4px; color: #e6edf3; font-family: 'Consolas', monospace; }
            QComboBox { background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 4px 8px; color: #e6edf3; }
            QComboBox::drop-down { border: none; }
            QSpinBox, QDoubleSpinBox { background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 4px; color: #e6edf3; }
            QTabWidget::pane { border: 1px solid #30363d; border-radius: 4px; }
            QTabBar::tab { background: #161b22; border: 1px solid #30363d; padding: 8px 16px; color: #8b949e; }
            QTabBar::tab:selected { background: #21262d; color: #58a6ff; border-bottom-color: #58a6ff; }
            QStatusBar { background: #161b22; color: #8b949e; border-top: 1px solid #30363d; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #30363d; border-radius: 3px; background: #161b22; }
            QCheckBox::indicator:checked { background: #58a6ff; border-color: #58a6ff; }
        """)
        
        # Central widget with splitter
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)
        
        # Left panel - Controls
        left_widget = self.create_control_panel()
        splitter.addWidget(left_widget)
        
        # Right panel - Status & Logs
        right_widget = self.create_status_panel()
        splitter.addWidget(right_widget)
        
        splitter.setSizes([500, 700])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.connection_label = QLabel("Desconectado")
        self.connection_label.setStyleSheet("color: #f85149; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.connection_label)
        self.status_bar.showMessage("Listo - Haz clic en Conectar")
        
    def create_control_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        
        # Connection group
        conn_group = QGroupBox("Conexión")
        conn_layout = QGridLayout(conn_group)
        
        self.port_combo = QComboBox()
        self.port_combo.addItems([p for p in SerialComm.list_ports()])
        if not self.port_combo.count():
            self.port_combo.addItems(["COM3", "COM4", "COM5", "/dev/ttyUSB0"])
        self.port_combo.setCurrentText(self.hw.mcu.port)
        
        self.mock_check = QCheckBox("Modo Simulación (Mock)")
        self.mock_check.setChecked(self.mock)
        
        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        conn_layout.addWidget(QLabel("Puerto:"), 0, 0)
        conn_layout.addWidget(self.port_combo, 0, 1)
        conn_layout.addWidget(self.mock_check, 1, 0, 1, 2)
        conn_layout.addWidget(self.connect_btn, 2, 0, 1, 2)
        
        layout.addWidget(conn_group)
        
        # Servo Control group
        servo_group = QGroupBox("Control de Servos")
        servo_layout = QVBoxLayout(servo_group)
        
        self.servo_sliders = {}
        self.servo_labels = {}
        servo_grid = QGridLayout()
        
        for i, (sid, config) in enumerate(self.hw.servos.items()):
            row = i // 2
            col = (i % 2) * 3
            
            label = QLabel(f"{sid.replace('_', ' ').title()}: {config.default_angle}°")
            label.setMinimumWidth(120)
            
            slider = QSlider(Qt.Horizontal)
            slider.setRange(int(config.angle_range[0]), int(config.angle_range[1]))
            slider.setValue(int(config.default_angle))
            slider.setTickPosition(QSlider.TicksBelow)
            slider.setTickInterval(max(1, int((config.angle_range[1] - config.angle_range[0]) / 10)))
            slider.valueChanged.connect(lambda v, s=sid, l=label: self.on_servo_slider(s, v, l))
            slider.sliderReleased.connect(lambda s=sid: self.send_servo(s))
            
            self.servo_sliders[sid] = slider
            self.servo_labels[sid] = label
            
            servo_grid.addWidget(label, row, col)
            servo_grid.addWidget(slider, row, col + 1, 1, 2)
            
        servo_layout.addLayout(servo_grid)
        
        # Mood buttons
        mood_group = QGroupBox("Estados de Ánimo (Moods)")
        mood_layout = QHBoxLayout(mood_group)
        
        self.mood_buttons = {}
        for mood_name in self.hw.moods.keys():
            btn = QPushButton(mood_name.capitalize())
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, m=mood_name: self.set_mood(m))
            mood_layout.addWidget(btn)
            self.mood_buttons[mood_name] = btn
            
        servo_layout.addWidget(mood_group)
        layout.addWidget(servo_group)
        
        # Robot Actions
        action_group = QGroupBox("Acciones")
        action_layout = QHBoxLayout(action_group)
        
        self.reset_btn = QPushButton("Reset (Home)")
        self.reset_btn.setObjectName("warning")
        self.reset_btn.clicked.connect(self.reset_robot)
        
        self.emergency_btn = QPushButton("EMERGENCY STOP")
        self.emergency_btn.setObjectName("danger")
        self.emergency_btn.clicked.connect(self.emergency_stop)
        
        action_layout.addWidget(self.reset_btn)
        action_layout.addWidget(self.emergency_btn)
        layout.addWidget(action_group)
        
        # Speech
        speech_group = QGroupBox("Síntesis de Voz")
        speech_layout = QVBoxLayout(speech_group)
        
        speech_input_layout = QHBoxLayout()
        self.speech_input = QTextEdit()
        self.speech_input.setMaximumHeight(60)
        self.speech_input.setPlaceholderText("Escribe lo que debe decir Wall-E...")
        self.speak_btn = QPushButton("Hablar")
        self.speak_btn.setObjectName("success")
        self.speak_btn.clicked.connect(self.speak_text)
        speech_input_layout.addWidget(self.speech_input)
        speech_input_layout.addWidget(self.speak_btn)
        
        speech_layout.addLayout(speech_input_layout)
        
        # Quick phrases
        quick_layout = QHBoxLayout()
        phrases = ["Hola", "¿Qué tal?", "Adiós", "¡Sí!", "No entiendo"]
        for phrase in phrases:
            btn = QPushButton(phrase)
            btn.clicked.connect(lambda _, p=phrase: self.speak_text(p))
            quick_layout.addWidget(btn)
        speech_layout.addLayout(quick_layout)
        
        layout.addWidget(speech_group)
        
        # AI Actions
        ai_group = QGroupBox("Acciones IA")
        ai_layout = QHBoxLayout(ai_group)
        
        self.greet_btn = QPushButton("Saludar")
        self.greet_btn.clicked.connect(lambda: self.trigger_ai_action("greet"))
        
        self.celebrate_btn = QPushButton("Celebrar")
        self.celebrate_btn.clicked.connect(lambda: self.trigger_ai_action("celebrate"))
        
        self.surprise_btn = QPushButton("Sorprender")
        self.surprise_btn.clicked.connect(lambda: self.trigger_ai_action("surprise"))
        
        ai_layout.addWidget(self.greet_btn)
        ai_layout.addWidget(self.celebrate_btn)
        ai_layout.addWidget(self.surprise_btn)
        layout.addWidget(ai_group)
        
        # Personality traits
        trait_group = QGroupBox("Personalidad")
        trait_layout = QGridLayout(trait_group)
        
        self.trait_spins = {}
        traits = [
            ("curiosity", "Curiosidad"),
            ("empathy", "Empatía"),
            ("playfulness", "Juguetonería"),
            ("cautiousness", "Precaución"),
            ("persistence", "Persistencia"),
            ("expressiveness", "Expresividad"),
        ]
        
        for i, (trait_key, trait_label) in enumerate(traits):
            label = QLabel(trait_label)
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setValue(getattr(self.hw, 'personality_default', 0.5))
            spin.setDecimals(2)
            spin.valueChanged.connect(lambda v, t=trait_key: self.set_personality_trait(t, v))
            trait_layout.addWidget(label, i, 0)
            trait_layout.addWidget(spin, i, 1)
            self.trait_spins[trait_key] = spin
            
        layout.addWidget(trait_group)
        
        layout.addStretch()
        return widget
    
    def create_status_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Tabs
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Status Tab
        status_tab = QWidget()
        status_layout = QVBoxLayout(status_tab)
        
        # Mode & Mood
        mode_group = QGroupBox("Estado Actual")
        mode_layout = QGridLayout(mode_group)
        
        self.mode_label = QLabel("Modo: -")
        self.mood_label = QLabel("Mood: -")
        self.battery_label = QLabel("Batería: --% (--V)")
        self.temp_label = QLabel("Temp: --°C")
        self.uptime_label = QLabel("Uptime: --")
        
        for label in [self.mode_label, self.mood_label, self.battery_label, self.temp_label, self.uptime_label]:
            label.setFont(QFont("Consolas", 10))
            
        mode_layout.addWidget(self.mode_label, 0, 0)
        mode_layout.addWidget(self.mood_label, 0, 1)
        mode_layout.addWidget(self.battery_label, 1, 0)
        mode_layout.addWidget(self.temp_label, 1, 1)
        mode_layout.addWidget(self.uptime_label, 2, 0, 1, 2)
        
        status_layout.addWidget(mode_group)
        
        # Battery visual
        battery_group = QGroupBox("Batería")
        battery_layout = QVBoxLayout(battery_group)
        
        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setValue(0)
        self.battery_bar.setFormat("%p%")
        battery_layout.addWidget(self.battery_bar)
        
        status_layout.addWidget(battery_group)
        
        # Servo positions
        servo_pos_group = QGroupBox("Posiciones Servos (Actual)")
        servo_pos_layout = QGridLayout(servo_pos_group)
        
        self.servo_pos_labels = {}
        for i, sid in enumerate(self.hw.servos.keys()):
            label = QLabel(f"{sid}: --°")
            label.setFont(QFont("Consolas", 9))
            servo_pos_layout.addWidget(label, i // 4, i % 4)
            self.servo_pos_labels[sid] = label
            
        status_layout.addWidget(servo_pos_group)
        
        # Vision info
        vision_group = QGroupBox("Visión")
        vision_layout = QVBoxLayout(vision_group)
        self.vision_label = QLabel("Cámara: Esperando...")
        self.vision_label.setFont(QFont("Consolas", 9))
        vision_layout.addWidget(self.vision_label)
        status_layout.addWidget(vision_group)
        
        status_layout.addStretch()
        tabs.addTab(status_tab, "Estado")
        
        # Log Tab
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        
        log_btn_layout = QHBoxLayout()
        clear_log_btn = QPushButton("Limpiar Log")
        clear_log_btn.clicked.connect(self.log_text.clear)
        log_btn_layout.addStretch()
        log_btn_layout.addWidget(clear_log_btn)
        log_layout.addLayout(log_btn_layout)
        
        tabs.addTab(log_tab, "Log")
        
        # Config Tab
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)
        
        config_group = QGroupBox("Configuración")
        config_form = QGridLayout(config_group)
        
        config_form.addWidget(QLabel("Puerto Serial:"), 0, 0)
        config_form.addWidget(self.port_combo, 0, 1)
        
        config_form.addWidget(QLabel("Baudrate:"), 1, 0)
        self.baudrate_spin = QSpinBox()
        self.baudrate_spin.setRange(9600, 921600)
        self.baudrate_spin.setValue(self.hw.mcu.baudrate)
        config_form.addWidget(self.baudrate_spin, 1, 1)
        
        config_form.addWidget(QLabel("Idle Timeout (s):"), 2, 0)
        self.idle_timeout_spin = QDoubleSpinBox()
        self.idle_timeout_spin.setRange(5, 300)
        self.idle_timeout_spin.setValue(self.hw.behavior.idle_timeout)
        config_form.addWidget(self.idle_timeout_spin, 2, 1)
        
        config_form.addWidget(QLabel("Watchdog Timeout (s):"), 3, 0)
        self.watchdog_spin = QDoubleSpinBox()
        self.watchdog_spin.setRange(1, 30)
        self.watchdog_spin.setValue(self.hw.behavior.watchdog_timeout)
        config_form.addWidget(self.watchdog_spin, 3, 1)
        
        config_form.addWidget(QLabel("Smoothing Factor:"), 4, 0)
        self.smoothing_spin = QDoubleSpinBox()
        self.smoothing_spin.setRange(0.01, 1.0)
        self.smoothing_spin.setSingleStep(0.01)
        self.smoothing_spin.setValue(self.hw.behavior.smoothing_factor)
        config_form.addWidget(self.smoothing_spin, 4, 1)
        
        config_form.addWidget(QLabel("Max Servo Speed:"), 5, 0)
        self.max_speed_spin = QSpinBox()
        self.max_speed_spin.setRange(1, 255)
        self.max_speed_spin.setValue(self.hw.behavior.max_servo_speed)
        config_form.addWidget(self.max_speed_spin, 5, 1)
        
        config_layout.addWidget(config_group)
        config_layout.addStretch()
        tabs.addTab(config_tab, "Config")
        
        return widget
    
    def connect_signals(self):
        self.signals.status_update.connect(self.on_status_update)
        self.signals.log_message.connect(self.on_log_message)
        self.signals.servo_update.connect(self.on_servo_update)
        self.signals.connection_changed.connect(self.on_connection_changed)
    
    @Slot()
    def toggle_connection(self):
        if self.serial and self.serial.connected:
            self.disconnect_robot()
        else:
            self.connect_robot()
    
    async def connect_robot(self):
        try:
            self.connect_btn.setEnabled(False)
            self.connect_btn.setText("Conectando...")
            
            port = self.port_combo.currentText()
            self.hw.mcu.port = port
            self.mock = self.mock_check.isChecked()
            
            if self.mock:
                self.serial = MockSerialComm()
            else:
                self.serial = SerialComm()
                self.serial.mcu.port = port
            
            connected = await self.serial.connect()
            if not connected:
                raise RuntimeError(f"No se pudo conectar a {port}")
            
            # Initialize components
            self.state_machine = StateMachine(self.serial)
            await self.state_machine.start()
            
            self.personality = PersonalityEngine(self.serial, self.state_machine)
            await self.personality.start()
            
            self.vision = VisionService()
            try:
                await self.vision.start()
            except Exception as e:
                self.log_message("warning", f"Visión: {e}")
                self.vision = None
            
            if self.mock:
                self.audio = MockAudioService()
            else:
                self.audio = AudioService()
            
            try:
                await self.audio.start()
            except Exception as e:
                self.log_message("warning", f"Audio: {e}")
                if not self.mock:
                    self.audio = MockAudioService()
                    await self.audio.start()
            
            ai_config = AIEngineConfig(
                enable_vision=self.vision is not None,
                enable_audio=self.audio is not None,
                enable_personality=True,
            )
            self.ai_engine = AIEngine(
                self.serial, self.state_machine, self.personality,
                self.vision, self.audio, ai_config
            )
            await self.ai_engine.start()
            
            # Wire callbacks
            self.serial.on_state(self.on_robot_state)
            self.state_machine.on_mode_change(self.on_mode_change)
            self.state_machine.on_mood_change(self.on_mood_change)
            self.personality.on_expression(self.on_expression)
            
            if self.vision:
                self.vision.on_faces(self.on_faces_detected)
            if self.audio:
                self.audio.on_transcription(self.on_transcription)
            
            self.signals.connection_changed.emit(True)
            self.log_message("system", f"Conectado a {port}")
            
        except Exception as e:
            self.log_message("error", f"Error conectando: {e}")
            QMessageBox.critical(self, "Error", f"No se pudo conectar:\n{e}")
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("Conectar")
    
    def disconnect_robot(self):
        asyncio.run_coroutine_threadsafe(self._disconnect_async(), self.loop)
    
    async def _disconnect_async(self):
        if self.ai_engine:
            await self.ai_engine.stop()
        if self.personality:
            await self.personality.stop()
        if self.state_machine:
            await self.state_machine.stop()
        if self.vision:
            await self.vision.stop()
        if self.audio:
            await self.audio.stop()
        if self.serial:
            await self.serial.disconnect()
        
        self.signals.connection_changed.emit(False)
        self.log_message("system", "Desconectado")
    
    @Slot(bool)
    def on_connection_changed(self, connected: bool):
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Desconectar" if connected else "Conectar")
        self.port_combo.setEnabled(not connected)
        self.mock_check.setEnabled(not connected)
        
        if connected:
            self.connection_label.setText("Conectado")
            self.connection_label.setStyleSheet("color: #3fb950; font-weight: bold;")
            self.status_bar.showMessage("Conectado - Robot operativo")
        else:
            self.connection_label.setText("Desconectado")
            self.connection_label.setStyleSheet("color: #f85149; font-weight: bold;")
            self.status_bar.showMessage("Desconectado")
    
    def on_servo_slider(self, servo_id: str, value: int, label: QLabel):
        label.setText(f"{servo_id.replace('_', ' ').title()}: {value}°")
    
    def send_servo(self, servo_id: str):
        if self.serial and self.serial.connected:
            angle = self.servo_sliders[servo_id].value()
            asyncio.run_coroutine_threadsafe(
                self.serial.move_servo(servo_id, float(angle)), self.loop
            )
    
    def set_mood(self, mood: str):
        # Uncheck other mood buttons
        for m, btn in self.mood_buttons.items():
            btn.setChecked(m == mood)
        
        if self.serial and self.serial.connected:
            asyncio.run_coroutine_threadsafe(
                self.serial.set_mood(mood), self.loop
            )
    
    def reset_robot(self):
        if self.serial and self.serial.connected:
            asyncio.run_coroutine_threadsafe(
                self.serial.reset(), self.loop
            )
            # Reset sliders to defaults
            for sid, slider in self.servo_sliders.items():
                default = self.hw.servos[sid].default_angle
                slider.setValue(int(default))
                self.servo_labels[sid].setText(f"{sid.replace('_', ' ').title()}: {default}°")
    
    def emergency_stop(self):
        reply = QMessageBox.question(
            self, "Emergency Stop",
            "¿Ejecutar EMERGENCY STOP? Esto detiene TODOS los servos inmediatamente.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes and self.serial and self.serial.connected:
            asyncio.run_coroutine_threadsafe(
                self.serial.emergency_stop(), self.loop
            )
            if self.state_machine:
                asyncio.run_coroutine_threadsafe(
                    self.state_machine.on_emergency_stop(), self.loop
                )
    
    def speak_text(self, text: str = None):
        if text is None:
            text = self.speech_input.toPlainText().strip()
        if not text:
            return
        
        if self.audio:
            asyncio.run_coroutine_threadsafe(
                self.audio.speak(text), self.loop
            )
        self.log_message("robot", text)
        self.speech_input.clear()
    
    def trigger_ai_action(self, action: str):
        if not self.ai_engine:
            return
        
        actions = {
            "greet": self.ai_engine.trigger_greeting,
            "celebrate": self.ai_engine.trigger_celebration,
            "surprise": self.ai_engine.trigger_surprise,
        }
        if action in actions:
            asyncio.run_coroutine_threadsafe(actions[action](), self.loop)
            self.log_message("system", f"AI Action: {action}")
    
    def set_personality_trait(self, trait: str, value: float):
        if self.ai_engine:
            asyncio.run_coroutine_threadsafe(
                self.ai_engine.set_personality_trait(trait, value), self.loop
            )
    
    # Callbacks from robot
    def on_robot_state(self, state):
        data = {
            "battery_voltage": state.battery_voltage,
            "battery_percent": state.battery_percent,
            "temperature_c": state.temperature_c,
            "uptime_ms": state.uptime_ms,
            "servos": state.servos,
        }
        self.signals.status_update.emit(data)
    
    def on_mode_change(self, mode: RobotMode):
        self.signals.log_message.emit("system", f"Modo: {mode.value}")
    
    def on_mood_change(self, mood: Mood):
        self.signals.log_message.emit("system", f"Mood: {mood.value}")
        # Update mood button
        for m, btn in self.mood_buttons.items():
            btn.setChecked(m == mood.value)
    
    def on_expression(self, expression: str, data: dict):
        self.signals.log_message.emit("expression", f"{expression}: {data}")
    
    def on_faces_detected(self, faces):
        if faces:
            face = faces[0]
            self.signals.log_message.emit("vision", f"Cara detectada: {face.face_id} ({face.emotion})")
    
    def on_transcription(self, transcription):
        self.signals.log_message.emit("voice", f"Escuchado: {transcription.text}")
    
    # UI Updates from signals
    @Slot(dict)
    def on_status_update(self, data: dict):
        # Battery
        volt = data.get("battery_voltage", 0)
        pct = data.get("battery_percent", 0)
        self.battery_label.setText(f"Batería: {pct}% ({volt:.2f}V)")
        self.battery_bar.setValue(pct)
        if pct <= 20:
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background: #da3633; }")
        elif pct <= 40:
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background: #d29922; }")
        else:
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background: #238636; }")
        
        # Temperature
        self.temp_label.setText(f"Temp: {data.get('temperature_c', 0):.1f}°C")
        
        # Uptime
        ms = data.get("uptime_ms", 0)
        secs = ms // 1000
        mins = secs // 60
        hrs = mins // 60
        self.uptime_label.setText(f"Uptime: {hrs}h {mins%60}m {secs%60}s")
        
        # Servo positions
        for sid, servo_data in data.get("servos", {}).items():
            if sid in self.servo_pos_labels:
                angle = servo_data.get("current_angle", 0)
                self.servo_pos_labels[sid].setText(f"{sid}: {angle:.1f}°")
                # Update slider position (without triggering signal)
                if sid in self.servo_sliders:
                    self.servo_sliders[sid].blockSignals(True)
                    self.servo_sliders[sid].setValue(int(angle))
                    self.servo_sliders[sid].blockSignals(False)
                    self.servo_labels[sid].setText(f"{sid.replace('_', ' ').title()}: {angle:.1f}°")
    
    @Slot(str, str)
    def on_log_message(self, msg_type: str, message: str):
        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M:%S")
        
        color_map = {
            "system": "#8b949e",
            "robot": "#3fb950",
            "user": "#58a6ff",
            "vision": "#a371f7",
            "voice": "#d29922",
            "expression": "#f85149",
            "error": "#f85149",
            "warning": "#d29922",
        }
        color = color_map.get(msg_type, "#e6edf3")
        
        self.log_text.append(
            f'<span style="color:#8b949e">[{time_str}]</span> '
            f'<span style="color:{color}">{message}</span>'
        )
        # Auto scroll
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    @Slot(str, float)
    def on_servo_update(self, servo_id: str, angle: float):
        if servo_id in self.servo_pos_labels:
            self.servo_pos_labels[servo_id].setText(f"{servo_id}: {angle:.1f}°")
    
    def closeEvent(self, event):
        if self.serial and self.serial.connected:
            self.disconnect_robot()
        event.accept()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Wall-E Companion Desktop App")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    app.setApplicationName("Wall-E Companion")
    
    # Apply dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(0x0d1117))
    palette.setColor(QPalette.WindowText, QColor(0xe6edf3))
    palette.setColor(QPalette.Base, QColor(0x161b22))
    palette.setColor(QPalette.AlternateBase, QColor(0x21262d))
    palette.setColor(QPalette.ToolTipBase, QColor(0x161b22))
    palette.setColor(QPalette.ToolTipText, QColor(0xe6edf3))
    palette.setColor(QPalette.Text, QColor(0xe6edf3))
    palette.setColor(QPalette.Button, QColor(0x21262d))
    palette.setColor(QPalette.ButtonText, QColor(0xe6edf3))
    palette.setColor(QPalette.BrightText, QColor(0xf85149))
    palette.setColor(QPalette.Highlight, QColor(0x58a6ff))
    palette.setColor(QPalette.HighlightedText, QColor(0x0d1117))
    app.setPalette(palette)
    
    window = WallEDesktopApp(mock=args.mock)
    window.show()
    
    with qasync.QEventLoop(app) as loop:
        loop.run_forever()


if __name__ == "__main__":
    main()