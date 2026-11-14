"""Serial Communication with ESP32 — Wall-E Companion Software.

Handles JSON Lines protocol over serial (USB/Bluetooth).
Auto-reconnect, command queue, response matching, state parsing.
"""

from __future__ import annotations

import asyncio
import json
import serial
import serial.tools.list_ports
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable
from loguru import logger
from core.hardware import get_hardware_config


@dataclass
class RobotState:
    uptime_ms: int = 0
    servos: dict = field(default_factory=dict)
    battery_voltage: float = 0.0
    battery_percent: int = 0
    temperature_c: float = 0.0
    free_heap: int = 0
    tof_distance_mm: int = 0
    imu_data: dict = field(default_factory=dict)
    last_update: float = 0.0


@dataclass
class CommandResponse:
    cmd: str
    ok: bool
    msg: str = ""
    data: dict = field(default_factory=dict)


class SerialComm:
    """Async serial communication with ESP32 using JSON Lines protocol."""

    def __init__(self, config_path: Optional[str] = None):
        self.hw = get_hardware_config(config_path)
        self.port: Optional[serial.Serial] = None
        self.reader_task: Optional[asyncio.Task] = None
        self.reconnect_task: Optional[asyncio.Task] = None
        self.connected = False
        self.state = RobotState()
        self.pending_commands: dict[str, asyncio.Future] = {}
        self.command_id = 0
        self.state_callbacks: list[Callable[[RobotState], Awaitable[None]]] = []
        self.log_callbacks: list[Callable[[str, str], Awaitable[None]]] = []
        self.error_callbacks: list[Callable[[str], Awaitable[None]]] = []
        self._running = False

    async def connect(self) -> bool:
        """Open serial port and start reader."""
        if self.connected:
            return True

        try:
            self.port = serial.Serial(
                port=self.hw.mcu.port,
                baudrate=self.hw.mcu.baudrate,
                timeout=self.hw.mcu.timeout,
                write_timeout=1.0,
            )
            # Wait for ESP32 to boot
            await asyncio.sleep(1.5)
            self.port.reset_input_buffer()
            self.port.reset_output_buffer()

            self.connected = True
            self._running = True
            self.reader_task = asyncio.create_task(self._reader_loop())
            logger.info(f"Connected to {self.hw.mcu.port} @ {self.hw.mcu.baudrate}")
            return True

        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.hw.mcu.port}: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        """Close serial port and stop tasks."""
        self._running = False

        if self.reader_task:
            self.reader_task.cancel()
            try:
                await self.reader_task
            except asyncio.CancelledError:
                pass

        if self.reconnect_task:
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass

        if self.port and self.port.is_open:
            self.port.close()

        self.connected = False
        logger.info("Disconnected from serial port")

    async def _reader_loop(self):
        """Background task: read lines, parse JSON, dispatch events."""
        buffer = ""

        while self._running and self.port and self.port.is_open:
            try:
                # Read available bytes
                data = self.port.read(self.port.in_waiting or 1)
                if not data:
                    await asyncio.sleep(0.01)
                    continue

                buffer += data.decode("utf-8", errors="ignore")

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    await self._parse_line(line)

            except UnicodeDecodeError:
                buffer = ""  # Reset on decode error
            except Exception as e:
                logger.error(f"Reader loop error: {e}")
                await asyncio.sleep(0.1)

    async def _parse_line(self, line: str):
        """Parse a single JSON line and dispatch."""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON: {line[:100]}")
            return

        evt = msg.get("evt")
        if evt == "state":
            await self._handle_state(msg.get("data", {}))
        elif evt == "ack":
            await self._handle_ack(msg)
        elif evt == "error":
            await self._handle_error(msg)
        elif evt == "log":
            await self._handle_log(msg)
        else:
            logger.debug(f"Unknown event type: {evt}")

    async def _handle_state(self, data: dict):
        """Update robot state from state event."""
        self.state.uptime_ms = data.get("uptime_ms", 0)
        self.state.battery_voltage = data.get("battery_voltage", 0.0)
        self.state.battery_percent = data.get("battery_percent", 0)
        self.state.temperature_c = data.get("temperature_c", 0.0)
        self.state.free_heap = data.get("free_heap", 0)
        self.state.tof_distance_mm = data.get("tof_distance_mm", 0)
        self.state.imu_data = data.get("imu", {})

        # Update servo states
        for servo_data in data.get("servos", []):
            sid = servo_data.get("id")
            if sid:
                self.state.servos[sid] = {
                    "current_angle": servo_data.get("current_angle", 0.0),
                    "target_angle": servo_data.get("target_angle", 0.0),
                    "is_moving": servo_data.get("is_moving", False),
                }

        import time
        self.state.last_update = time.time()

        # Notify callbacks
        for cb in self.state_callbacks:
            try:
                await cb(self.state)
            except Exception as e:
                logger.error(f"State callback error: {e}")

    async def _handle_ack(self, msg: dict):
        """Handle command acknowledgment."""
        cmd = msg.get("cmd", "")
        ok = msg.get("ok", False)
        response = CommandResponse(cmd=cmd, ok=ok, msg=msg.get("msg", ""))

        # Resolve pending future
        for cid, future in list(self.pending_commands.items()):
            if not future.done():
                future.set_result(response)
                del self.pending_commands[cid]
                break

    async def _handle_error(self, msg: dict):
        """Handle error event."""
        error_msg = msg.get("msg", "Unknown error")
        cmd = msg.get("cmd", "")
        logger.error(f"Robot error [{cmd}]: {error_msg}")

        for cb in self.error_callbacks:
            try:
                await cb(f"[{cmd}] {error_msg}")
            except Exception as e:
                logger.error(f"Error callback error: {e}")

    async def _handle_log(self, msg: dict):
        """Handle log event from robot."""
        level = msg.get("level", "INFO")
        log_msg = msg.get("msg", "")
        logger.log(level, f"[ROBOT] {log_msg}")

        for cb in self.log_callbacks:
            try:
                await cb(level, log_msg)
            except Exception as e:
                logger.error(f"Log callback error: {e}")

    def send_command(self, cmd: dict) -> asyncio.Future:
        """Send a command and return a future that resolves with the response."""
        if not self.connected or not self.port or not self.port.is_open:
            future = asyncio.Future()
            future.set_exception(RuntimeError("Not connected"))
            return future

        self.command_id += 1
        cmd["_cid"] = self.command_id
        future = asyncio.Future()
        self.pending_commands[str(self.command_id)] = future

        try:
            line = json.dumps(cmd, separators=(",", ":")) + "\n"
            self.port.write(line.encode("utf-8"))
            self.port.flush()
        except Exception as e:
            future.set_exception(e)
            del self.pending_commands[str(self.command_id)]

        return future

    # Convenience command methods
    async def move_servo(self, servo_id: str, angle: float, speed: Optional[int] = None) -> CommandResponse:
        servo = self.hw.get_servo(servo_id)
        if not servo:
            return CommandResponse(cmd="move_servo", ok=False, msg=f"Unknown servo: {servo_id}")

        speed = speed or servo.speed
        cmd = {"cmd": "move_servo", "id": servo_id, "angle": angle, "speed": speed}
        return await self.send_command(cmd)

    async def move_servos(self, positions: list[dict], speed: Optional[int] = None) -> CommandResponse:
        # Add speed to each position if provided
        if speed is not None:
            positions = [{**pos, "speed": speed} for pos in positions]
        cmd = {"cmd": "move_servos", "positions": positions}
        return await self.send_command(cmd)

    async def set_mood(self, mood: str) -> CommandResponse:
        cmd = {"cmd": "set_mood", "mood": mood}
        return await self.send_command(cmd)

    async def get_state(self) -> CommandResponse:
        cmd = {"cmd": "get_state"}
        return await self.send_command(cmd)

    async def calibrate(self, servo_id: str, points: list[dict]) -> CommandResponse:
        cmd = {"cmd": "calibrate", "id": servo_id, "points": points}
        return await self.send_command(cmd)

    async def reset(self) -> CommandResponse:
        cmd = {"cmd": "reset"}
        return await self.send_command(cmd)

    async def emergency_stop(self) -> CommandResponse:
        cmd = {"cmd": "emergency_stop"}
        return await self.send_command(cmd)

    # Callback registration
    def on_state(self, callback: Callable[[RobotState], Awaitable[None]]):
        self.state_callbacks.append(callback)

    def on_log(self, callback: Callable[[str, str], Awaitable[None]]):
        self.log_callbacks.append(callback)

    def on_error(self, callback: Callable[[str], Awaitable[None]]):
        self.error_callbacks.append(callback)

    @staticmethod
    def list_ports() -> list[str]:
        """List available serial ports."""
        return [p.device for p in serial.tools.list_ports.comports()]

    async def auto_reconnect(self):
        """Background task: attempt reconnection on disconnect."""
        while self._running:
            if not self.connected:
                logger.info("Attempting reconnect...")
                await self.connect()
            await asyncio.sleep(self.hw.mcu.reconnect_interval)


# Mock implementation for testing without hardware
class MockSerialComm(SerialComm):
    """Mock serial communication for development/testing."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__(config_path)
        self.mock_state = RobotState()
        self._mock_servo_angles = {s.id: s.default_angle for s in self.hw.servos.values()}

    async def connect(self) -> bool:
        self.connected = True
        self._running = True
        self.reader_task = asyncio.create_task(self._mock_reader_loop())
        logger.info("Mock serial connected")
        return True

    async def _mock_reader_loop(self):
        """Simulate periodic state updates."""
        import time
        while self._running:
            # Simulate servo movement toward targets
            for servo_id, target in self._mock_servo_angles.items():
                current = self.mock_state.servos.get(servo_id, {}).get("current_angle", 0)
                diff = target - current
                if abs(diff) > 0.5:
                    new_angle = current + diff * 0.1
                    self.mock_state.servos[servo_id] = {
                        "current_angle": new_angle,
                        "target_angle": target,
                        "is_moving": True,
                    }
                else:
                    self.mock_state.servos[servo_id] = {
                        "current_angle": target,
                        "target_angle": target,
                        "is_moving": False,
                    }

            self.mock_state.uptime_ms += 100
            self.mock_state.battery_voltage = 7.8
            self.mock_state.battery_percent = self.hw.power.voltage_to_percent(7.8)
            self.mock_state.temperature_c = 35.0
            self.mock_state.free_heap = 150000
            self.mock_state.last_update = time.time()

            for cb in self.state_callbacks:
                try:
                    await cb(self.mock_state)
                except Exception:
                    pass

            await asyncio.sleep(0.1)

    async def move_servo(self, servo_id: str, angle: float, speed: Optional[int] = None) -> CommandResponse:
        if servo_id in self._mock_servo_angles:
            self._mock_servo_angles[servo_id] = angle
            return CommandResponse(cmd="move_servo", ok=True)
        return CommandResponse(cmd="move_servo", ok=False, msg=f"Unknown servo: {servo_id}")

    async def move_servos(self, positions: list[dict], speed: Optional[int] = None) -> CommandResponse:
        for pos in positions:
            servo_id = pos.get("id")
            angle = pos.get("angle")
            if servo_id in self._mock_servo_angles:
                self._mock_servo_angles[servo_id] = angle
        return CommandResponse(cmd="move_servos", ok=True)

    async def set_mood(self, mood: str) -> CommandResponse:
        pose = self.hw.get_mood(mood)
        if pose:
            for servo_id, angle in pose.to_dict().items():
                self._mock_servo_angles[servo_id] = angle
            return CommandResponse(cmd="set_mood", ok=True)
        return CommandResponse(cmd="set_mood", ok=False, msg=f"Unknown mood: {mood}")

    async def get_state(self) -> CommandResponse:
        return CommandResponse(cmd="get_state", ok=True, data={"state": "mock"})

    async def reset(self) -> CommandResponse:
        for servo_id, servo in self.hw.servos.items():
            self._mock_servo_angles[servo_id] = servo.default_angle
        return CommandResponse(cmd="reset", ok=True)

    async def emergency_stop(self) -> CommandResponse:
        return CommandResponse(cmd="emergency_stop", ok=True)