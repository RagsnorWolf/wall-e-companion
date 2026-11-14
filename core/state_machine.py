"""Robot State Machine — Wall-E Companion Software.

Manages high-level robot states, mood transitions, autonomous behaviors.
"""

from __future__ import annotations

import asyncio
import random
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable
from loguru import logger
from core.hardware import get_hardware_config
from core.serial_comm import SerialComm, RobotState


class RobotMode(Enum):
    """High-level robot operational modes."""
    BOOTING = "booting"
    IDLE = "idle"
    CURIOUS = "curious"
    INTERACTING = "interacting"
    SPEAKING = "speaking"
    LISTENING = "listening"
    THINKING = "thinking"
    SLEEPING = "sleeping"
    LOW_BATTERY = "low_battery"
    EMERGENCY_STOP = "emergency_stop"
    ERROR = "error"


class Mood(Enum):
    """Robot emotional states."""
    IDLE = "idle"
    CURIOUS = "curious"
    HAPPY = "happy"
    SAD = "sad"
    ALERT = "alert"
    THINKING = "thinking"
    SLEEPING = "sleeping"


@dataclass
class StateContext:
    """Current robot context for decision making."""
    mode: RobotMode = RobotMode.BOOTING
    mood: Mood = Mood.IDLE
    last_interaction: float = 0.0
    last_mood_change: float = 0.0
    battery_percent: int = 100
    is_charging: bool = False
    face_detected: bool = False
    face_distance: float = 0.0
    voice_detected: bool = False
    obstacle_detected: bool = False
    obstacle_distance: int = 0
    current_task: Optional[str] = None
    task_progress: float = 0.0


class StateMachine:
    """Robot behavior state machine."""

    def __init__(self, serial_comm: SerialComm, config_path: Optional[str] = None):
        self.serial = serial_comm
        self.hw = get_hardware_config(config_path)
        self.ctx = StateContext()
        self.running = False
        self.main_loop_task: Optional[asyncio.Task] = None
        self.idle_timer: Optional[asyncio.Task] = None
        self.mode_callbacks: list[Callable[[RobotMode], Awaitable[None]]] = []
        self.mood_callbacks: list[Callable[[Mood], Awaitable[None]]] = []

        # Register for serial state updates
        self.serial.on_state(self._on_robot_state)

    async def start(self):
        """Start the state machine."""
        self.running = True
        self.main_loop_task = asyncio.create_task(self._main_loop())
        await self._set_mode(RobotMode.IDLE)
        logger.info("State machine started")

    async def stop(self):
        """Stop the state machine."""
        self.running = False
        if self.main_loop_task:
            self.main_loop_task.cancel()
            try:
                await self.main_loop_task
            except asyncio.CancelledError:
                pass
        if self.idle_timer:
            self.idle_timer.cancel()
        logger.info("State machine stopped")

    async def _on_robot_state(self, state: RobotState):
        """Handle robot state updates from serial."""
        self.ctx.battery_percent = state.battery_percent

        # Check battery
        if state.battery_voltage > 0:
            if self.hw.power.is_critical(state.battery_voltage) and self.ctx.mode != RobotMode.EMERGENCY_STOP:
                await self._set_mode(RobotMode.LOW_BATTERY)
            elif self.hw.power.is_low(state.battery_voltage) and self.ctx.mode == RobotMode.IDLE:
                # Just a warning, don't change mode
                pass

        # Check obstacle (ToF sensor)
        if state.tof_distance_mm > 0:
            self.ctx.obstacle_distance = state.tof_distance_mm
            self.ctx.obstacle_detected = state.tof_distance_mm < self.hw.behavior.tof_threshold_mm

    async def _main_loop(self):
        """Main behavior loop."""
        while self.running:
            try:
                await self._tick()
                await asyncio.sleep(0.1)  # 10Hz
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"State machine tick error: {e}")
                await asyncio.sleep(1.0)

    async def _tick(self):
        """Single behavior tick."""
        now = time.time()

        # Handle mode-specific behavior
        if self.ctx.mode == RobotMode.IDLE:
            await self._tick_idle(now)
        elif self.ctx.mode == RobotMode.CURIOUS:
            await self._tick_curious(now)
        elif self.ctx.mode == RobotMode.INTERACTING:
            await self._tick_interacting(now)
        elif self.ctx.mode == RobotMode.LOW_BATTERY:
            await self._tick_low_battery(now)
        elif self.ctx.mode == RobotMode.SLEEPING:
            await self._tick_sleeping(now)

        # Check idle timeout
        if self.ctx.mode in (RobotMode.IDLE, RobotMode.CURIOUS):
            if now - self.ctx.last_interaction > self.hw.behavior.idle_timeout:
                await self._set_mood(Mood.SLEEPING)
                await self._set_mode(RobotMode.SLEEPING)

    async def _tick_idle(self, now: float):
        """Idle behavior: random micro-movements, look around."""
        # Randomly look around
        if random.random() < 0.02:  # 2% chance per tick
            pan = random.uniform(-30, 30)
            tilt = random.uniform(-15, 15)
            await self.serial.move_servo("head_pan", pan)
            await self.serial.move_servo("head_tilt", tilt)

        # Random blink
        if random.random() < 0.05:
            await self.serial.move_servo("eye_L", 0)
            await self.serial.move_servo("eye_R", 0)
            await asyncio.sleep(0.1)
            await self.serial.move_servo("eye_L", 50)
            await self.serial.move_servo("eye_R", 50)

    async def _tick_curious(self, now: float):
        """Curious behavior: track face/object, investigate."""
        if self.ctx.face_detected and self.ctx.face_distance > 0:
            # Track face (simplified - real implementation would use vision service)
            pass

        # Return to idle if nothing interesting
        if not self.ctx.face_detected and not self.ctx.voice_detected:
            if now - self.ctx.last_interaction > 10.0:
                await self._set_mode(RobotMode.IDLE)
                await self._set_mood(Mood.IDLE)

    async def _tick_interacting(self, now: float):
        """Interacting behavior: maintain engagement."""
        if not self.ctx.face_detected and not self.ctx.voice_detected:
            if now - self.ctx.last_interaction > 5.0:
                await self._set_mode(RobotMode.CURIOUS)
                await self._set_mood(Mood.CURIOUS)

    async def _tick_low_battery(self, now: float):
        """Low battery behavior: find charger, minimize movement."""
        if self.ctx.is_charging:
            await self._set_mode(RobotMode.IDLE)
        else:
            # Minimal movement, sad mood
            if self.ctx.mood != Mood.SAD:
                await self._set_mood(Mood.SAD)

    async def _tick_sleeping(self, now: float):
        """Sleeping behavior: minimal updates."""
        # Only wake on significant interaction
        if self.ctx.face_detected or self.ctx.voice_detected:
            await self._set_mode(RobotMode.IDLE)
            await self._set_mood(Mood.IDLE)
            self.ctx.last_interaction = now

    async def _set_mode(self, mode: RobotMode):
        """Change robot mode."""
        if self.ctx.mode != mode:
            old_mode = self.ctx.mode
            self.ctx.mode = mode
            logger.info(f"Mode: {old_mode.value} -> {mode.value}")
            for cb in self.mode_callbacks:
                try:
                    await cb(mode)
                except Exception as e:
                    logger.error(f"Mode callback error: {e}")

    async def _set_mood(self, mood: Mood):
        """Change robot mood and apply pose."""
        if self.ctx.mood != mood:
            old_mood = self.ctx.mood
            self.ctx.mood = mood
            self.ctx.last_mood_change = time.time()
            logger.info(f"Mood: {old_mood.value} -> {mood.value}")

            # Apply mood pose to robot
            response = await self.serial.set_mood(mood.value)
            if not response.ok:
                logger.warning(f"Failed to set mood {mood.value}: {response.msg}")

            for cb in self.mood_callbacks:
                try:
                    await cb(mood)
                except Exception as e:
                    logger.error(f"Mood callback error: {e}")

    # Public API for external triggers
    async def on_face_detected(self, distance: float):
        """Called when vision service detects a face."""
        self.ctx.face_detected = True
        self.ctx.face_distance = distance
        self.ctx.last_interaction = time.time()

        if self.ctx.mode == RobotMode.IDLE:
            await self._set_mode(RobotMode.CURIOUS)
            await self._set_mood(Mood.CURIOUS)
        elif self.ctx.mode == RobotMode.SLEEPING:
            await self._set_mode(RobotMode.IDLE)
            await self._set_mood(Mood.IDLE)

    async def on_face_lost(self):
        """Called when face is no longer detected."""
        self.ctx.face_detected = False
        self.ctx.face_distance = 0.0

    async def on_voice_detected(self, text: str = ""):
        """Called when audio service detects speech."""
        self.ctx.voice_detected = True
        self.ctx.last_interaction = time.time()

        if self.ctx.mode in (RobotMode.IDLE, RobotMode.CURIOUS):
            await self._set_mode(RobotMode.INTERACTING)
            await self._set_mood(Mood.HAPPY)

    async def on_voice_end(self):
        """Called when speech ends."""
        self.ctx.voice_detected = False

    async def on_wake_word(self):
        """Called when wake word detected."""
        self.ctx.last_interaction = time.time()
        if self.ctx.mode == RobotMode.SLEEPING:
            await self._set_mode(RobotMode.IDLE)
            await self._set_mood(Mood.IDLE)
        elif self.ctx.mode == RobotMode.IDLE:
            await self._set_mode(RobotMode.LISTENING)
            await self._set_mood(Mood.CURIOUS)

    async def on_speech_start(self):
        """Called when robot starts speaking."""
        await self._set_mode(RobotMode.SPEAKING)
        await self._set_mood(Mood.HAPPY)

    async def on_speech_end(self):
        """Called when robot finishes speaking."""
        await self._set_mode(RobotMode.INTERACTING)
        await self._set_mood(Mood.HAPPY)

    async def on_thinking_start(self):
        """Called when robot is processing/thinking."""
        await self._set_mode(RobotMode.THINKING)
        await self._set_mood(Mood.THINKING)

    async def on_thinking_end(self):
        """Called when thinking done."""
        await self._set_mode(RobotMode.INTERACTING)

    async def on_low_battery(self):
        """Called when battery is low."""
        await self._set_mode(RobotMode.LOW_BATTERY)

    async def on_charging_start(self):
        """Called when charging starts."""
        self.ctx.is_charging = True
        if self.ctx.mode == RobotMode.LOW_BATTERY:
            await self._set_mode(RobotMode.IDLE)

    async def on_charging_end(self):
        """Called when charging ends."""
        self.ctx.is_charging = False

    async def on_emergency_stop(self):
        """Called on emergency stop."""
        await self._set_mode(RobotMode.EMERGENCY_STOP)
        await self.serial.emergency_stop()

    async def on_error(self, error: str):
        """Called on error."""
        await self._set_mode(RobotMode.ERROR)
        logger.error(f"Robot error: {error}")

    def on_mode_change(self, callback: Callable[[RobotMode], Awaitable[None]]):
        self.mode_callbacks.append(callback)

    def on_mood_change(self, callback: Callable[[Mood], Awaitable[None]]):
        self.mood_callbacks.append(callback)

    def get_status(self) -> dict:
        """Get current status for UI/API."""
        return {
            "mode": self.ctx.mode.value,
            "mood": self.ctx.mood.value,
            "battery_percent": self.ctx.battery_percent,
            "is_charging": self.ctx.is_charging,
            "face_detected": self.ctx.face_detected,
            "face_distance": self.ctx.face_distance,
            "voice_detected": self.ctx.voice_detected,
            "obstacle_detected": self.ctx.obstacle_detected,
            "obstacle_distance_mm": self.ctx.obstacle_distance,
            "uptime": time.time() - self.ctx.last_interaction if self.ctx.last_interaction else 0,
        }