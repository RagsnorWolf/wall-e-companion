"""Async backend bridge between the Qt UI and the robot services.

Owns the full service lifecycle (serial → state machine → personality → vision →
audio → AI) and converts service callbacks into Qt signals consumed by the UI.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger
from PySide6.QtCore import QObject, Signal

from core.hardware import get_hardware_config
from core.personality import PersonalityEngine, PersonalityTrait
from core.serial_comm import MockSerialComm, SerialComm
from core.state_machine import Mood, RobotMode, StateMachine
from services.ai_engine import AIEngine, AIEngineConfig
from services.audio import AudioService, MockAudioService
from services.vision import VisionService


class RobotBackend(QObject):
    """Service orchestrator with Qt signalling."""

    stateUpdated = Signal(object)
    modeChanged = Signal(str)
    moodChanged = Signal(str)
    connectionChanged = Signal(bool, str)
    event = Signal(str, str)
    facesUpdated = Signal(list)
    transcriptionReceived = Signal(str)
    audioLevelChanged = Signal(float)
    aiStatusUpdated = Signal(dict)
    errorOccurred = Signal(str)
    visionFpsChanged = Signal(float)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.hw = get_hardware_config()

        self.serial: Optional[SerialComm] = None
        self.state_machine: Optional[StateMachine] = None
        self.personality: Optional[PersonalityEngine] = None
        self.vision: Optional[VisionService] = None
        self.audio: Optional[AudioService] = None
        self.ai: Optional[AIEngine] = None

        self.mock = False
        self.port = self.hw.mcu.port
        self.connected = False
        self.state: Any = None
        self.mode = "booting"
        self.mood = "idle"
        self.faces: List = []
        self.vision_fps = 0.0
        self.audio_level = 0.0
        self._busy = False

    # ------------------------------------------------------------- lifecycle
    async def connect(self, port: Optional[str] = None, mock: bool = False) -> bool:
        if self.connected or self._busy:
            return self.connected
        self._busy = True
        self.mock = mock
        self.port = port or self.port
        try:
            self.event.emit("system", f"Conectando a {'MOCK' if mock else self.port}…")

            if mock:
                self.serial = MockSerialComm()
            else:
                self.serial = SerialComm()
                self.hw.mcu.port = self.port

            ok = await self.serial.connect()
            if not ok:
                raise RuntimeError(f"No se pudo abrir {self.port}")

            self.state = self.serial.state
            self.serial.on_state(self._on_state)
            self.serial.on_log(self._on_robot_log)
            self.serial.on_error(self._on_serial_error)

            self.state_machine = StateMachine(self.serial)
            await self.state_machine.start()
            self.state_machine.on_mode_change(self._on_mode)
            self.state_machine.on_mood_change(self._on_mood)

            self.personality = PersonalityEngine(self.serial, self.state_machine)
            await self.personality.start()
            self.personality.on_expression(self._on_expression)

            self.vision = VisionService()
            try:
                await self.vision.start()
                self.vision.on_faces(self._on_faces)
                self.vision.on_frame(self._on_frame)
                self.event.emit("vision", "Servicio de visión iniciado")
            except Exception as exc:  # camera may be missing
                logger.warning(f"Vision unavailable: {exc}")
                self.event.emit("warning", f"Visión no disponible: {exc}")
                self.vision = None

            if mock:
                self.audio = MockAudioService()
            else:
                self.audio = AudioService()
            try:
                await self.audio.start()
                self.audio.on_transcription(self._on_transcription)
                self.audio.on_audio_level(self._on_audio_level)
                self.event.emit("system", "Servicio de audio iniciado")
            except Exception as exc:
                logger.warning(f"Audio unavailable: {exc}")
                self.event.emit("warning", f"Audio no disponible: {exc}")
                if not mock:
                    try:
                        self.audio = MockAudioService()
                        await self.audio.start()
                        self.audio.on_transcription(self._on_transcription)
                        self.audio.on_audio_level(self._on_audio_level)
                    except Exception:
                        self.audio = None

            self.ai = AIEngine(
                self.serial, self.state_machine, self.personality,
                self.vision, self.audio,
                AIEngineConfig(
                    enable_vision=self.vision is not None,
                    enable_audio=self.audio is not None,
                    enable_personality=True,
                ),
            )
            self.ai.on_status(self._on_ai_status)
            await self.ai.start()

            self.connected = True
            self.connectionChanged.emit(True, self.port)
            self.event.emit("success", "Robot en línea · todos los servicios activos")
            return True

        except Exception as exc:
            logger.exception("Connection failed")
            self.event.emit("error", f"Error de conexión: {exc}")
            self.errorOccurred.emit(str(exc))
            await self._teardown()
            return False
        finally:
            self._busy = False

    async def disconnect(self):
        if self._busy:
            return
        self._busy = True
        try:
            await self._teardown()
        finally:
            self._busy = False
            self.connected = False
            self.connectionChanged.emit(False, self.port)
            self.event.emit("system", "Robot desconectado")

    async def _teardown(self):
        for name, service in (
            ("ai", self.ai), ("personality", self.personality),
            ("state", self.state_machine), ("vision", self.vision),
            ("audio", self.audio), ("serial", self.serial),
        ):
            if service is None:
                continue
            try:
                await service.stop() if name != "serial" else await service.disconnect()
            except Exception as exc:
                logger.debug(f"Teardown {name}: {exc}")
        self.ai = None
        self.personality = None
        self.state_machine = None
        self.vision = None
        self.audio = None
        self.serial = None
        self.connected = False

    # ------------------------------------------------------- service callbacks
    async def _on_state(self, state):
        self.state = state
        self.stateUpdated.emit(state)

    async def _on_mode(self, mode: RobotMode):
        self.mode = mode.value
        self.modeChanged.emit(mode.value)

    async def _on_mood(self, mood: Mood):
        self.mood = mood.value
        self.moodChanged.emit(mood.value)

    async def _on_faces(self, faces):
        self.faces = faces or []
        self.facesUpdated.emit(self.faces)

    async def _on_frame(self, frame):
        self.vision_fps = getattr(frame, "fps", 0.0) or self.vision_fps
        self.visionFpsChanged.emit(self.vision_fps)

    async def _on_transcription(self, transcription):
        text = getattr(transcription, "text", str(transcription))
        self.transcriptionReceived.emit(text)
        self.event.emit("voice", f"“{text}”")

    async def _on_audio_level(self, level: float):
        self.audio_level = float(level)
        self.audioLevelChanged.emit(self.audio_level)

    async def _on_expression(self, expression: str, data: dict):
        self.event.emit("robot", f"Expresión · {expression}")

    async def _on_ai_status(self, status: dict):
        self.aiStatusUpdated.emit(status)

    async def _on_robot_log(self, level: str, message: str):
        self.event.emit("robot", f"[{level}] {message}")

    async def _on_serial_error(self, message: str):
        self.event.emit("error", message)
        self.errorOccurred.emit(message)

    # ---------------------------------------------------------------- actions
    async def move_servo(self, servo_id: str, angle: float):
        if self.serial and self.serial.connected:
            await self.serial.move_servo(servo_id, float(angle))

    async def move_all(self, positions: Dict[str, float]):
        if self.serial and self.serial.connected:
            payload = [{"id": k, "angle": float(v)} for k, v in positions.items()]
            await self.serial.move_servos(payload)

    async def set_mood(self, mood: str):
        if self.state_machine:
            try:
                await self.state_machine._set_mood(Mood(mood))
            except Exception:
                pass
        if self.serial and self.serial.connected:
            await self.serial.set_mood(mood)
        self.mood = mood
        self.moodChanged.emit(mood)

    async def speak(self, text: str):
        if self.audio:
            await self.audio.speak(text)
        self.event.emit("robot", text)

    async def reset(self):
        if self.serial and self.serial.connected:
            await self.serial.reset()
        self.event.emit("system", "Pose home aplicada")

    async def emergency_stop(self):
        if self.serial and self.serial.connected:
            await self.serial.emergency_stop()
        if self.state_machine:
            await self.state_machine.on_emergency_stop()
        self.event.emit("error", "EMERGENCY STOP ejecutado")

    async def trigger(self, action: str):
        if not self.ai:
            return
        mapping = {
            "greet": self.ai.trigger_greeting,
            "celebrate": self.ai.trigger_celebration,
            "surprise": self.ai.trigger_surprise,
        }
        fn = mapping.get(action)
        if fn:
            await fn()
            self.event.emit("ai", f"Acción IA · {action}")

    async def set_trait(self, trait: str, value: float):
        try:
            if self.personality:
                self.personality.set_trait(PersonalityTrait(trait), value)
            elif self.ai:
                await self.ai.set_personality_trait(trait, value)
        except Exception as exc:
            logger.debug(f"Trait set failed: {exc}")

    async def inject_transcription(self, text: str):
        if isinstance(self.audio, MockAudioService):
            self.audio.inject_transcription(text)
        if self.ai:
            await self.ai._process_conversation(text)

    def trait_values(self) -> Dict[str, float]:
        if not self.personality:
            return {}
        return {
            t.value: self.personality.profile.get_trait(t)
            for t in PersonalityTrait
        }

    def latest_frame(self):
        if self.vision:
            try:
                return self.vision.get_latest_frame()
            except Exception:
                return None
        return None


def spawn(coro) -> Optional[asyncio.Task]:
    """Schedule a coroutine on the running qasync loop, logging failures."""
    try:
        task = asyncio.ensure_future(coro)
    except RuntimeError:
        logger.debug("No running loop for coroutine")
        return None

    def _done(t: asyncio.Task):
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        except Exception:
            return
        if exc:
            logger.error(f"Async task failed: {exc}")

    task.add_done_callback(_done)
    return task
