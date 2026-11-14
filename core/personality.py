"""Wall-E Personality Engine — Core behavior, expressions, and character.

Defines Wall-E's personality traits, autonomous behaviors, emotional responses,
and the logic that makes him feel alive and curious.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Awaitable
from loguru import logger
from core.hardware import get_hardware_config
from core.serial_comm import SerialComm
from core.state_machine import StateMachine, RobotMode, Mood


class PersonalityTrait(Enum):
    """Core personality dimensions (inspired by Big Five + Wall-E character)."""
    CURIOSITY = "curiosity"          # Exploration drive
    EMPATHY = "empathy"              # Emotional responsiveness
    PLAYFULNESS = "playfulness"      # Joy in interaction
    CAUTIOUSNESS = "cautiousness"    # Risk avoidance
    PERSISTENCE = "persistence"      # Task completion drive
    EXPRESSIVENESS = "expressiveness" # Emotional display intensity


@dataclass
class PersonalityProfile:
    """Wall-E's personality configuration."""
    curiosity: float = 0.8
    empathy: float = 0.9
    playfulness: float = 0.7
    cautiousness: float = 0.6
    persistence: float = 0.7
    expressiveness: float = 0.85

    def get_trait(self, trait: PersonalityTrait) -> float:
        return getattr(self, trait.value)


@dataclass
class Memory:
    """Simple episodic memory for continuity."""
    interactions: list[dict] = field(default_factory=list)
    known_faces: dict = field(default_factory=dict)  # face_id -> {name, last_seen, affinity}
    learned_objects: dict = field(default_factory=dict)
    preferences: dict = field(default_factory=dict)

    def add_interaction(self, interaction_type: str, data: dict):
        self.interactions.append({
            "type": interaction_type,
            "data": data,
            "timestamp": time.time(),
        })
        # Keep last 100 interactions
        if len(self.interactions) > 100:
            self.interactions = self.interactions[-100:]

    def get_affinity(self, face_id: str) -> float:
        face = self.known_faces.get(face_id, {})
        return face.get("affinity", 0.5)

    def update_affinity(self, face_id: str, delta: float):
        if face_id not in self.known_faces:
            self.known_faces[face_id] = {"name": "Unknown", "affinity": 0.5, "last_seen": time.time()}
        face = self.known_faces[face_id]
        face["affinity"] = max(0.0, min(1.0, face["affinity"] + delta))
        face["last_seen"] = time.time()


class PersonalityEngine:
    """Wall-E's personality - autonomous behavior, expressions, decision making."""

    def __init__(
        self,
        serial_comm: SerialComm,
        state_machine: StateMachine,
        config_path: Optional[str] = None,
    ):
        self.serial = serial_comm
        self.state_machine = state_machine
        self.hw = get_hardware_config(config_path)
        self.profile = PersonalityProfile()
        self.memory = Memory()
        self.running = False
        self.behavior_task: Optional[asyncio.Task] = None
        self.expression_task: Optional[asyncio.Task] = None

        # Behavior weights (sum = 1.0)
        self.behavior_weights = {
            "look_around": 0.3,
            "fidget": 0.2,
            "idle_sound": 0.1,
            "check_sensors": 0.2,
            "micro_expression": 0.2,
        }

        # Register for state changes
        self.state_machine.on_mood_change(self._on_mood_change)
        self.state_machine.on_mode_change(self._on_mode_change)

        # Expression callbacks
        self.expression_callbacks: list[Callable[[str, dict], Awaitable[None]]] = []

    async def start(self):
        """Start personality engine."""
        self.running = True
        self.behavior_task = asyncio.create_task(self._behavior_loop())
        self.expression_task = asyncio.create_task(self._expression_loop())
        logger.info("Personality engine started")

    async def stop(self):
        """Stop personality engine."""
        self.running = False
        for task in (self.behavior_task, self.expression_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("Personality engine stopped")

    async def _behavior_loop(self):
        """Autonomous behavior loop - runs when idle/curious."""
        while self.running:
            try:
                if self.state_machine.ctx.mode in (RobotMode.IDLE, RobotMode.CURIOUS):
                    await self._run_autonomous_behavior()
                await asyncio.sleep(random.uniform(2.0, 5.0))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Behavior loop error: {e}")
                await asyncio.sleep(1.0)

    async def _expression_loop(self):
        """Micro-expression loop - subtle life-like movements."""
        while self.running:
            try:
                if self.state_machine.ctx.mode not in (RobotMode.SLEEPING, RobotMode.EMERGENCY_STOP):
                    await self._micro_expression()
                await asyncio.sleep(random.uniform(3.0, 8.0))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Expression loop error: {e}")
                await asyncio.sleep(1.0)

    async def _run_autonomous_behavior(self):
        """Pick and execute an autonomous behavior based on personality."""
        behavior = random.choices(
            list(self.behavior_weights.keys()),
            weights=list(self.behavior_weights.values()),
        )[0]

        if behavior == "look_around":
            await self._look_around()
        elif behavior == "fidget":
            await self._fidget()
        elif behavior == "idle_sound":
            await self._idle_sound()
        elif behavior == "check_sensors":
            await self._check_sensors()
        elif behavior == "micro_expression":
            await self._micro_expression()

    async def _look_around(self):
        """Curious head movement - scan environment."""
        if self.profile.get_trait(PersonalityTrait.CURIOSITY) < 0.3:
            return

        # Scan pattern: center -> left -> right -> center
        positions = [
            (0, 0),
            (-40, 10),
            (40, -5),
            (-20, 15),
            (20, -10),
            (0, 0),
        ]

        for pan, tilt in positions:
            if not self.running or self.state_machine.ctx.mode not in (RobotMode.IDLE, RobotMode.CURIOUS):
                break
            await self.serial.move_servo("head_pan", pan, speed=60)
            await self.serial.move_servo("head_tilt", tilt, speed=60)
            await asyncio.sleep(random.uniform(0.8, 1.5))

    async def _fidget(self):
        """Small body movements - weight shift, arm twitch."""
        if self.profile.get_trait(PersonalityTrait.PLAYFULNESS) < 0.3:
            return

        actions = [
            lambda: self.serial.move_servo("body_lean", random.uniform(-10, 10), speed=40),
            lambda: self.serial.move_servo("arm_L", random.uniform(-20, 20), speed=30),
            lambda: self.serial.move_servo("arm_R", random.uniform(-20, 20), speed=30),
            lambda: self.serial.move_servos([
                {"id": "body_lean", "angle": random.uniform(-5, 5)},
                {"id": "arm_L", "angle": random.uniform(-15, 15)},
            ]),
        ]

        action = random.choice(actions)
        await action()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        # Return to neutral
        await self.serial.move_servo("body_lean", 0, speed=30)
        await self.serial.move_servo("arm_L", 0, speed=30)
        await self.serial.move_servo("arm_R", 0, speed=30)

    async def _idle_sound(self):
        """Make a small Wall-E sound."""
        if self.profile.get_trait(PersonalityTrait.EXPRESSIVENESS) < 0.4:
            return

        sounds = ["beep", "boop", "whirr", "click", "hum"]
        sound = random.choice(sounds)
        logger.debug(f"Idle sound: {sound}")
        # Trigger sound via callback (audio service handles playback)
        for cb in self.expression_callbacks:
            try:
                await cb("sound", {"sound": sound, "volume": 0.3})
            except Exception:
                pass

    async def _check_sensors(self):
        """Check sensors, react to environment."""
        await self.serial.get_state()
        # State machine handles sensor reactions via callbacks

    async def _micro_expression(self):
        """Subtle facial expression - eye squint, brow raise equivalent."""
        if self.profile.get_trait(PersonalityTrait.EXPRESSIVENESS) < 0.5:
            return

        expressions = [
            # Blink
            ({"eye_L": 0, "eye_R": 0}, 0.1, {"eye_L": 50, "eye_R": 50}),
            # Slow blink (sleepy)
            ({"eye_L": 20, "eye_R": 20}, 0.5, {"eye_L": 50, "eye_R": 50}),
            # Wink left
            ({"eye_L": 0, "eye_R": 50}, 0.2, {"eye_L": 50, "eye_R": 50}),
            # Wink right
            ({"eye_L": 50, "eye_R": 0}, 0.2, {"eye_L": 50, "eye_R": 50}),
            # Wide eyes (surprise)
            ({"eye_L": 90, "eye_R": 90}, 0.3, {"eye_L": 50, "eye_R": 50}),
            # Squint (thinking/suspicious)
            ({"eye_L": 30, "eye_R": 30}, 0.4, {"eye_L": 50, "eye_R": 50}),
        ]

        expr = random.choice(expressions)
        pose, hold, reset = expr
        await self.serial.move_servos([{"id": k, "angle": v} for k, v in pose.items()])
        await asyncio.sleep(hold)
        await self.serial.move_servos([{"id": k, "angle": v} for k, v in reset.items()])

    async def _on_mood_change(self, mood: Mood):
        """React to mood changes with characteristic expressions."""
        reactions = {
            Mood.HAPPY: self._express_happy,
            Mood.SAD: self._express_sad,
            Mood.CURIOUS: self._express_curious,
            Mood.ALERT: self._express_alert,
            Mood.THINKING: self._express_thinking,
            Mood.SLEEPING: self._express_sleeping,
        }

        if mood in reactions:
            await reactions[mood]()

    async def _on_mode_change(self, mode: RobotMode):
        """React to mode changes."""
        if mode == RobotMode.LISTENING:
            await self._express_listening()
        elif mode == RobotMode.SPEAKING:
            await self._express_speaking()

    async def _express_happy(self):
        """Happy expression: bouncy, wide eyes, tilted head."""
        await self.serial.move_servos([
            {"id": "head_tilt", "angle": 15},
            {"id": "eye_L", "angle": 80},
            {"id": "eye_R", "angle": 80},
            {"id": "arm_L", "angle": 30},
            {"id": "arm_R", "angle": -30},
        ], speed=100)
        await self._emit_expression("happy", {"intensity": 0.8})

    async def _express_sad(self):
        """Sad expression: droopy, head down, slow."""
        await self.serial.move_servos([
            {"id": "head_tilt", "angle": -30},
            {"id": "eye_L", "angle": 20},
            {"id": "eye_R", "angle": 20},
            {"id": "body_lean", "angle": 10},
            {"id": "arm_L", "angle": -20},
            {"id": "arm_R", "angle": -20},
        ], speed=40)
        await self._emit_expression("sad", {"intensity": 0.7})

    async def _express_curious(self):
        """Curious expression: head cocked, one eye wider."""
        await self.serial.move_servos([
            {"id": "head_pan", "angle": 15},
            {"id": "head_tilt", "angle": -10},
            {"id": "eye_L", "angle": 70},
            {"id": "eye_R", "angle": 85},
            {"id": "body_lean", "angle": 5},
        ], speed=80)
        await self._emit_expression("curious", {"intensity": 0.6})

    async def _express_alert(self):
        """Alert expression: wide eyes, straight posture."""
        await self.serial.move_servos([
            {"id": "head_pan", "angle": 0},
            {"id": "head_tilt", "angle": 20},
            {"id": "eye_L", "angle": 90},
            {"id": "eye_R", "angle": 90},
            {"id": "body_lean", "angle": 0},
        ], speed=150)
        await self._emit_expression("alert", {"intensity": 0.9})

    async def _express_thinking(self):
        """Thinking expression: asymmetrical, looking up."""
        await self.serial.move_servos([
            {"id": "head_pan", "angle": -20},
            {"id": "head_tilt", "angle": -15},
            {"id": "eye_L", "angle": 40},
            {"id": "eye_R", "angle": 60},
            {"id": "body_lean", "angle": 5},
        ], speed=50)
        await self._emit_expression("thinking", {"intensity": 0.5})

    async def _express_sleeping(self):
        """Sleeping expression: eyes closed, head down."""
        await self.serial.move_servos([
            {"id": "head_tilt", "angle": -45},
            {"id": "eye_L", "angle": 0},
            {"id": "eye_R", "angle": 0},
            {"id": "body_lean", "angle": 15},
            {"id": "arm_L", "angle": -45},
            {"id": "arm_R", "angle": -45},
        ], speed=30)
        await self._emit_expression("sleeping", {"intensity": 1.0})

    async def _express_listening(self):
        """Listening: head forward, eyes attentive."""
        await self.serial.move_servos([
            {"id": "head_pan", "angle": 0},
            {"id": "head_tilt", "angle": 10},
            {"id": "eye_L", "angle": 70},
            {"id": "eye_R", "angle": 70},
        ], speed=80)

    async def _express_speaking(self):
        """Speaking: slight jaw/eye movement sync would go here."""
        pass

    async def _emit_expression(self, expression: str, data: dict):
        """Emit expression event for UI/audio."""
        for cb in self.expression_callbacks:
            try:
                await cb(expression, data)
            except Exception as e:
                logger.error(f"Expression callback error: {e}")

    def on_expression(self, callback: Callable[[str, dict], Awaitable[None]]):
        self.expression_callbacks.append(callback)

    # High-level behavior triggers
    async def greet(self, face_id: Optional[str] = None):
        """Greeting behavior."""
        affinity = self.memory.get_affinity(face_id) if face_id else 0.5

        if affinity > 0.7:
            # Excited greeting for known friend
            await self._set_mood_with_expr(Mood.HAPPY, "excited_greeting")
            await self._emit_expression("greeting", {"type": "excited", "face_id": face_id})
        elif affinity > 0.3:
            # Friendly greeting
            await self._set_mood_with_expr(Mood.HAPPY, "friendly_greeting")
            await self._emit_expression("greeting", {"type": "friendly", "face_id": face_id})
        else:
            # Cautious greeting for stranger
            await self._set_mood_with_expr(Mood.CURIOUS, "cautious_greeting")
            await self._emit_expression("greeting", {"type": "cautious", "face_id": face_id})

        if face_id:
            self.memory.add_interaction("greeting", {"face_id": face_id, "affinity": affinity})
            self.memory.update_affinity(face_id, 0.05)

    async def react_to_praise(self):
        """React to positive feedback."""
        await self._set_mood_with_expr(Mood.HAPPY, "praise_reaction")
        await self._emit_expression("praise_reaction", {"intensity": 0.8})

    async def react_to_scolding(self):
        """React to negative feedback."""
        await self._set_mood_with_expr(Mood.SAD, "scolding_reaction")
        await self._emit_expression("scolding_reaction", {"intensity": 0.7})

    async def react_to_surprise(self):
        """React to unexpected event."""
        await self._set_mood_with_expr(Mood.ALERT, "surprise")
        await self._express_surprise()
        await self._emit_expression("surprise", {"intensity": 0.9})

    async def on_wake_word(self):
        """Called when wake word detected - curious attentive pose."""
        await self._express_curious()

    async def on_thinking_start(self):
        """Called when robot starts thinking - thinking pose."""
        await self._express_thinking()

    async def _express_surprise(self):
        """Surprise: jump back, wide eyes."""
        await self.serial.move_servos([
            {"id": "head_pan", "angle": 0},
            {"id": "head_tilt", "angle": 25},
            {"id": "eye_L", "angle": 100},
            {"id": "eye_R", "angle": 100},
            {"id": "body_lean", "angle": -15},
            {"id": "arm_L", "angle": 20},
            {"id": "arm_R", "angle": -20},
        ], speed=200)
        await asyncio.sleep(0.5)
        await self.serial.move_servos([
            {"id": "body_lean", "angle": 0},
            {"id": "arm_L", "angle": 0},
            {"id": "arm_R", "angle": 0},
        ], speed=100)

    async def celebrate(self):
        """Celebration dance."""
        await self._set_mood_with_expr(Mood.HAPPY, "celebration")
        for _ in range(3):
            await self.serial.move_servos([
                {"id": "head_pan", "angle": -30},
                {"id": "arm_L", "angle": 45},
                {"id": "arm_R", "angle": -45},
            ], speed=150)
            await asyncio.sleep(0.3)
            await self.serial.move_servos([
                {"id": "head_pan", "angle": 30},
                {"id": "arm_L", "angle": -45},
                {"id": "arm_R", "angle": 45},
            ], speed=150)
            await asyncio.sleep(0.3)
        await self.serial.move_servos([
            {"id": "head_pan", "angle": 0},
            {"id": "arm_L", "angle": 0},
            {"id": "arm_R", "angle": 0},
        ], speed=100)

    async def show_affection(self, face_id: str):
        """Show affection to known person."""
        self.memory.update_affinity(face_id, 0.1)
        await self._set_mood_with_expr(Mood.HAPPY, "affection")
        await self.serial.move_servos([
            {"id": "head_tilt", "angle": 20},
            {"id": "eye_L", "angle": 75},
            {"id": "eye_R", "angle": 75},
            {"id": "body_lean", "angle": -10},
        ], speed=60)
        await self._emit_expression("affection", {"face_id": face_id, "intensity": 0.8})

    async def _set_mood_with_expr(self, mood: Mood, context: str):
        """Set mood with personality-appropriate expression."""
        await self.state_machine._set_mood(mood)

    def set_trait(self, trait: PersonalityTrait, value: float):
        """Adjust personality trait (0.0 - 1.0)."""
        value = max(0.0, min(1.0, value))
        setattr(self.profile, trait.value, value)
        logger.info(f"Personality trait {trait.value} set to {value}")

    def get_status(self) -> dict:
        return {
            "personality": {
                "curiosity": self.profile.curiosity,
                "empathy": self.profile.empathy,
                "playfulness": self.profile.playfulness,
                "cautiousness": self.profile.cautiousness,
                "persistence": self.profile.persistence,
                "expressiveness": self.profile.expressiveness,
            },
            "memory": {
                "interactions_count": len(self.memory.interactions),
                "known_faces": len(self.memory.known_faces),
                "learned_objects": len(self.memory.learned_objects),
            },
        }