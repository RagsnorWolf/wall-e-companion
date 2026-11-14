"""Voice & AI page — speech synthesis, conversation, personality tuning."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from core.personality import PersonalityTrait
from ui.backend import spawn
from ui.theme import AMBER, CYAN, GREEN, PURPLE, TEXT, TEXT_DIM, TEXT_MUTED, YELLOW
from ui.widgets.charts import Waveform
from ui.widgets.common import Card, EventFeed, SectionLabel, StatusPill


TRAIT_LABELS = {
    "curiosity": "Curiosidad",
    "empathy": "Empatía",
    "playfulness": "Juguetonería",
    "cautiousness": "Precaución",
    "persistence": "Persistencia",
    "expressiveness": "Expresividad",
}


class VoicePage(QWidget):
    def __init__(self, backend, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.backend = backend

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        columns = QHBoxLayout()
        columns.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(12)

        # ------------------------------------------------------------ mic card
        mic_card = Card("Entrada de voz", "Whisper · VAD integrado")
        self.pill_mic = StatusPill("STANDBY", TEXT_DIM)
        mic_card.add_header_widget(self.pill_mic)
        self.wave = Waveform()
        self.wave.setMinimumHeight(84)
        mic_card.body.addWidget(self.wave)

        row = QHBoxLayout()
        self.mic_input = QLineEdit()
        self.mic_input.setPlaceholderText("Escribí una frase para simular el micrófono…")
        self.mic_input.returnPressed.connect(self._send_text)
        send = QPushButton("Enviar")
        send.setObjectName("Primary")
        send.clicked.connect(self._send_text)
        row.addWidget(self.mic_input, 1)
        row.addWidget(send)
        mic_card.body.addLayout(row)
        left.addWidget(mic_card)

        # --------------------------------------------------------- speech card
        speech_card = Card("Síntesis de voz", "Piper TTS")
        self.speech_input = QLineEdit()
        self.speech_input.setPlaceholderText("Lo que Wall-E debe decir…")
        self.speech_input.returnPressed.connect(self._speak)
        speak = QPushButton("Hablar")
        speak.setObjectName("Primary")
        speak.clicked.connect(self._speak)
        speech_row = QHBoxLayout()
        speech_row.addWidget(self.speech_input, 1)
        speech_row.addWidget(speak)
        speech_card.body.addLayout(speech_row)

        quick = QHBoxLayout()
        quick.setSpacing(6)
        for phrase in ("Hola", "¿Qué tal?", "Wall-E listo", "Adiós", "¡Sí!"):
            btn = QPushButton(phrase)
            btn.setObjectName("Chip")
            btn.clicked.connect(lambda _=False, p=phrase: self._speak(p))
            quick.addWidget(btn)
        quick.addStretch()
        speech_card.body.addLayout(quick)
        left.addWidget(speech_card)

        # ------------------------------------------------------------ AI card
        ai_card = Card("Acciones de inteligencia", "comportamiento autónomo")
        ai_row = QHBoxLayout()
        for label, key in (("Saludar", "greet"), ("Celebrar", "celebrate"), ("Sorprender", "surprise")):
            btn = QPushButton(label)
            btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _=False, k=key: spawn(self.backend.trigger(k)))
            ai_row.addWidget(btn)
        ai_card.body.addLayout(ai_row)
        left.addWidget(ai_card)
        left.addStretch()

        columns.addLayout(left, 3)

        # ----------------------------------------------------- transcript card
        transcript_card = Card("Conversación", "registro en vivo")
        clear = QPushButton("Limpiar")
        clear.setObjectName("Ghost")
        clear.clicked.connect(lambda: self.transcript.clear())
        transcript_card.add_header_widget(clear)
        self.transcript = EventFeed()
        self.transcript.push("system", "Canal de voz en espera.")
        transcript_card.body.addWidget(self.transcript, 1)
        columns.addWidget(transcript_card, 2)

        root.addLayout(columns, 3)

        # ------------------------------------------------------ personality
        personality_card = Card("Perfil de personalidad", "rasgos persistentes · 0.0 – 1.0")
        traits = QGridLayout()
        traits.setHorizontalSpacing(28)
        traits.setVerticalSpacing(8)
        self.trait_sliders = {}
        defaults = {
            "curiosity": 0.8, "empathy": 0.9, "playfulness": 0.7,
            "cautiousness": 0.6, "persistence": 0.7, "expressiveness": 0.85,
        }
        for i, trait in enumerate(PersonalityTrait):
            name = QLabel(TRAIT_LABELS.get(trait.value, trait.value))
            name.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(defaults.get(trait.value, 0.7) * 100))
            value = QLabel(f"{slider.value() / 100:.2f}")
            value.setStyleSheet(
                f"color: {CYAN}; font-family: 'Cascadia Mono'; font-size: 10px;"
            )
            slider.valueChanged.connect(
                lambda v, t=trait.value, lbl=value: self._trait_changed(t, v, lbl)
            )
            col = (i % 3) * 3
            traits.addWidget(name, i // 3, col)
            traits.addWidget(slider, i // 3, col + 1)
            traits.addWidget(value, i // 3, col + 2)
            self.trait_sliders[trait.value] = slider
        personality_card.body.addLayout(traits)
        root.addWidget(personality_card)

    # ---------------------------------------------------------------- actions
    def _trait_changed(self, trait: str, value: int, label: QLabel):
        label.setText(f"{value / 100:.2f}")
        if self.backend:
            spawn(self.backend.set_trait(trait, value / 100.0))

    def _speak(self, text: Optional[str] = None):
        text = text if isinstance(text, str) and text else self.speech_input.text().strip()
        if not text:
            return
        self.speech_input.clear()
        self.transcript.push("robot", f"WALL·E: {text}")
        if self.backend:
            spawn(self.backend.speak(text))

    def _send_text(self):
        text = self.mic_input.text().strip()
        if not text:
            return
        self.mic_input.clear()
        self.transcript.push("user", f"VOS: {text}")
        if self.backend:
            spawn(self.backend.inject_transcription(text))

    # -------------------------------------------------------------- handlers
    def set_level(self, level: float):
        self.wave.set_level(level)
        self.pill_mic.set_status("ESCUCHANDO" if level > 0.05 else "STANDBY",
                                 GREEN if level > 0.05 else TEXT_DIM)

    def set_transcription(self, text: str):
        self.transcript.push("user", f"VOS: {text}")

    def append_event(self, kind: str, message: str):
        if kind in ("robot", "ai", "user", "voice", "error"):
            self.transcript.push(kind, message)
