"""AI Engine — Wall-E Companion Software.

Central coordination: vision + audio + personality + decision making.
Orchestrates all services into coherent robot behavior.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable
from loguru import logger
from core.hardware import get_hardware_config
from core.serial_comm import SerialComm
from core.state_machine import StateMachine, RobotMode, Mood
from core.personality import PersonalityEngine
from services.vision import VisionService, FaceDetection
from services.audio import AudioService


@dataclass
class AIEngineConfig:
    """AI Engine configuration."""
    enable_vision: bool = True
    enable_audio: bool = True
    enable_personality: bool = True
    wake_words: list[str] = None
    face_tracking: bool = True
    auto_greet: bool = True
    conversation_timeout: float = 30.0

    def __post_init__(self):
        if self.wake_words is None:
            self.wake_words = ["wall-e", "wall e", "eva", "robot", "hola"]


class AIEngine:
    """Central AI coordination engine."""

    def __init__(
        self,
        serial_comm: SerialComm,
        state_machine: StateMachine,
        personality: PersonalityEngine,
        vision: VisionService,
        audio: AudioService,
        config: Optional[AIEngineConfig] = None,
        config_path: Optional[str] = None,
    ):
        self.serial = serial_comm
        self.state_machine = state_machine
        self.personality = personality
        self.vision = vision
        self.audio = audio
        self.config = config or AIEngineConfig()
        self.hw = get_hardware_config(config_path)

        self.running = False
        self.main_loop_task: Optional[asyncio.Task] = None
        self.conversation_task: Optional[asyncio.Task] = None

        # State
        self.last_face_time = 0.0
        self.last_face_id: Optional[str] = None
        self.conversation_active = False
        self.conversation_start = 0.0

        # Callbacks
        self.status_callbacks: list[Callable[[dict], Awaitable[None]]] = []

        # Wire up service callbacks
        self._wire_callbacks()

    def _wire_callbacks(self):
        """Connect service events to AI engine handlers."""
        if self.config.enable_vision:
            self.vision.on_faces(self._on_faces_detected)

        if self.config.enable_audio:
            self.audio.on_vad(self._on_voice_activity)
            self.audio.on_transcription(self._on_transcription)

        self.state_machine.on_mode_change(self._on_mode_change)
        self.personality.on_expression(self._on_expression)

    async def start(self):
        """Start AI engine."""
        self.running = True
        self.main_loop_task = asyncio.create_task(self._main_loop())
        logger.info("AI Engine started")

    async def stop(self):
        """Stop AI engine."""
        self.running = False
        if self.main_loop_task:
            self.main_loop_task.cancel()
            try:
                await self.main_loop_task
            except asyncio.CancelledError:
                pass
        if self.conversation_task:
            self.conversation_task.cancel()
            try:
                await self.conversation_task
            except asyncio.CancelledError:
                pass
        logger.info("AI Engine stopped")

    async def _main_loop(self):
        """Main coordination loop."""
        while self.running:
            try:
                await self._tick()
                await asyncio.sleep(0.1)  # 10Hz
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"AI engine tick error: {e}")
                await asyncio.sleep(1.0)

    async def _tick(self):
        """Single coordination tick."""
        now = time.time()

        # Face tracking timeout
        if self.config.face_tracking and self.last_face_id:
            if now - self.last_face_time > 5.0:
                await self.state_machine.on_face_lost()
                self.last_face_id = None

        # Conversation timeout
        if self.conversation_active:
            if now - self.conversation_start > self.config.conversation_timeout:
                await self._end_conversation()

        # Battery check (handled by state machine via serial)

        # Emit status
        await self._emit_status()

    async def _on_faces_detected(self, faces: list[FaceDetection]):
        """Handle face detections from vision service."""
        if not faces:
            return

        # Get closest face (largest)
        main_face = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
        face_id = main_face.face_id or "unknown"
        distance = self._estimate_distance(main_face.bbox)

        self.last_face_time = time.time()
        self.last_face_id = face_id

        # Notify state machine
        await self.state_machine.on_face_detected(distance)

        # Auto-greet new faces
        if self.config.auto_greet and face_id != self.last_face_id:
            await self.personality.greet(face_id)

        # Track face with head (if in curious/interacting mode)
        if self.state_machine.ctx.mode in (RobotMode.CURIOUS, RobotMode.INTERACTING):
            await self._track_face(main_face)

    def _estimate_distance(self, bbox: tuple) -> float:
        """Estimate face distance from bounding box size."""
        _, _, w, h = bbox
        face_size = w * h
        # Rough calibration: larger face = closer
        # Assuming 640x480 frame, face at 1m ~ 80x80px
        if face_size > 0:
            return max(0.3, min(5.0, 6400 / face_size))
        return 2.0

    async def _track_face(self, face: FaceDetection):
        """Move head to track face."""
        x, y, w, h = face.bbox
        frame_center_x = self.hw.camera.width / 2
        frame_center_y = self.hw.camera.height / 2
        face_center_x = x + w / 2
        face_center_y = y + h / 2

        # Calculate offset from center (-1 to 1)
        offset_x = (face_center_x - frame_center_x) / frame_center_x
        offset_y = (face_center_y - frame_center_y) / frame_center_y

        # Map to servo angles (head_pan: -90 to 90, head_tilt: -45 to 45)
        target_pan = -offset_x * 45  # Negative because camera is mirrored
        target_tilt = -offset_y * 22.5

        # Smooth movement
        current_pan = self.state_machine.ctx.mood  # This would come from servo state
        await self.serial.move_servo("head_pan", target_pan, speed=80)
        await self.serial.move_servo("head_tilt", target_tilt, speed=80)

    async def _on_voice_activity(self, is_speech: bool):
        """Handle voice activity detection."""
        if is_speech:
            await self.state_machine.on_voice_detected()
        else:
            await self.state_machine.on_voice_end()

    async def _on_transcription(self, transcription):
        """Handle speech recognition results."""
        text = transcription.text.strip()
        if not text:
            return

        logger.info(f"Heard: {text}")

        # Check for wake word
        if not self.conversation_active:
            for word in self.config.wake_words:
                if word in text.lower():
                    await self._start_conversation(text)
                    return

        # If in conversation, process as command/query
        if self.conversation_active:
            await self._process_conversation(text)

    async def _start_conversation(self, text: str):
        """Start a conversation interaction."""
        self.conversation_active = True
        self.conversation_start = time.time()
        await self.state_machine.on_wake_word()
        await self.personality.on_wake_word()

        # Remove wake word from text and process remainder
        for word in self.config.wake_words:
            text = text.lower().replace(word, "").strip()

        if text:
            await self._process_conversation(text)
        else:
            # Just woke up, acknowledge
            await self.audio.speak("¿Sí?")
            await self.state_machine.on_speech_start()
            await self.state_machine.on_speech_end()

    async def _process_conversation(self, text: str):
        """Process user input during conversation."""
        self.conversation_start = time.time()  # Reset timeout

        await self.state_machine.on_thinking_start()
        await self.personality.on_thinking_start()

        # Simple intent recognition (replace with LLM in future)
        response = await self._generate_response(text)

        await self.state_machine.on_thinking_end()

        if response:
            await self.state_machine.on_speech_start()
            await self.audio.speak(response)
            await self.state_machine.on_speech_end()

    async def _generate_response(self, text: str) -> str:
        """Generate response to user input (placeholder for LLM)."""
        text_lower = text.lower()

        # Simple pattern matching - replace with actual LLM
        if any(w in text_lower for w in ["hola", "buenos", "buenas", "hey"]):
            return "¡Hola! ¿En qué te puedo ayudar?"

        elif any(w in text_lower for w in ["cómo estás", "que tal", "bien"]):
            return "¡Muy bien, gracias por preguntar! ¿Y tú qué tal?"

        elif any(w in text_lower for w in ["nombre", "quién eres", "quien eres"]):
            return "Soy Wall-E, tu compañero robot. ¡Encantado de conocerte!"

        elif any(w in text_lower for w in ["baila", "baile", "dance"]):
            await self.personality.celebrate()
            return "¡Me encanta bailar!"

        elif any(w in text_lower for w in ["gracias", "gracias"]):
            await self.personality.react_to_praise()
            return "¡De nada! Me hace feliz poder ayudar."

        elif any(w in text_lower for w in ["adiós", "adios", "hasta luego", "chao"]):
            await self._end_conversation()
            return "¡Hasta luego! Fue un placer charlar contigo."

        elif any(w in text_lower for w in ["triste", "mal", "mal"]):
            await self.personality.react_to_scolding()
            return "Oh, lo siento. ¿Hay algo en lo que pueda ayudar?"

        elif "te quiero" in text_lower or "te quiero" in text_lower:
            await self.personality.show_affection(self.last_face_id or "unknown")
            return "¡Yo también te aprecio mucho!"

        else:
            # Default curious response
            responses = [
                "Interesante... cuéntame más.",
                "Hmm, no entendí bien. ¿Puedes repetirlo?",
                "Mi procesador está pensando... ¿qué más?",
                "Beep boop... ¡ah! Entendido.",
            ]
            import random
            return random.choice(responses)

    async def _end_conversation(self):
        """End current conversation."""
        if self.conversation_active:
            self.conversation_active = False
            logger.info("Conversation ended")

    async def _on_mode_change(self, mode: RobotMode):
        """Handle mode changes."""
        logger.debug(f"AI Engine: mode changed to {mode.value}")

    async def _on_expression(self, expression: str, data: dict):
        """Handle personality expressions."""
        logger.debug(f"Expression: {expression} - {data}")

    async def _emit_status(self):
        """Emit combined status for UI."""
        status = {
            "ai_engine": {
                "running": self.running,
                "conversation_active": self.conversation_active,
                "last_face_id": self.last_face_id,
                "last_face_time": self.last_face_time,
            },
            "state_machine": self.state_machine.get_status(),
            "personality": self.personality.get_status(),
        }

        for cb in self.status_callbacks:
            try:
                await cb(status)
            except Exception as e:
                logger.error(f"Status callback error: {e}")

    def on_status(self, callback: Callable[[dict], Awaitable[None]]):
        self.status_callbacks.append(callback)

    # Manual triggers for testing/external control
    async def trigger_greeting(self, face_id: Optional[str] = None):
        await self.personality.greet(face_id)

    async def trigger_celebration(self):
        await self.personality.celebrate()

    async def trigger_surprise(self):
        await self.personality.react_to_surprise()

    async def set_personality_trait(self, trait: str, value: float):
        from core.personality import PersonalityTrait
        try:
            trait_enum = PersonalityTrait(trait)
            self.personality.set_trait(trait_enum, value)
        except ValueError:
            logger.warning(f"Unknown personality trait: {trait}")