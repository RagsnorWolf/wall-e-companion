"""Web UI Server — Wall-E Companion Software.

FastAPI + WebSocket for real-time robot monitoring and control.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from loguru import logger


class ConnectionManager:
    """WebSocket connection manager."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        if not self.active_connections:
            return

        data = json.dumps(message)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# Pydantic models for API
class ServoCommand(BaseModel):
    servo_id: str
    angle: float
    speed: Optional[int] = None


class ServosCommand(BaseModel):
    positions: list[dict]


class MoodCommand(BaseModel):
    mood: str


class SpeakCommand(BaseModel):
    text: str


class PersonalityTraitCommand(BaseModel):
    trait: str
    value: float


def create_app(companion) -> FastAPI:
    """Create FastAPI app with all routes."""
    app = FastAPI(title="Wall-E Companion", version="1.0.0")

    # Static files and templates
    static_dir = Path(__file__).parent / "static"
    templates_dir = Path(__file__).parent / "templates"

    static_dir.mkdir(exist_ok=True)
    templates_dir.mkdir(exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/api/status")
    async def get_status():
        """Get full robot status."""
        if not companion.ai_engine:
            return JSONResponse({"error": "Not initialized"}, status_code=503)

        status = {
            "timestamp": time.time(),
            "state_machine": companion.state_machine.get_status() if companion.state_machine else {},
            "personality": companion.personality.get_status() if companion.personality else {},
            "ai_engine": {},
        }

        if companion.ai_engine:
            status["ai_engine"] = {
                "conversation_active": companion.ai_engine.conversation_active,
                "last_face_id": companion.ai_engine.last_face_id,
            }

        if companion.serial and hasattr(companion.serial, 'state'):
            state = companion.serial.state
            status["hardware"] = {
                "connected": companion.serial.connected,
                "battery_voltage": state.battery_voltage,
                "battery_percent": state.battery_percent,
                "temperature_c": state.temperature_c,
                "uptime_ms": state.uptime_ms,
                "servos": state.servos,
            }

        return status

    @app.get("/api/hardware-config")
    async def get_hardware_config():
        """Get hardware configuration."""
        hw = companion.hw if hasattr(companion, 'hw') else None
        if not hw:
            from core.hardware import get_hardware_config
            hw = get_hardware_config(companion.config_path)

        return {
            "servos": {k: {
                "channel": v.channel,
                "angle_range": v.angle_range,
                "default_angle": v.default_angle,
                "speed": v.speed,
            } for k, v in hw.servos.items()},
            "moods": {k: v.to_dict() for k, v in hw.moods.items()},
            "camera": {
                "width": hw.camera.width,
                "height": hw.camera.height,
                "fps": hw.camera.fps,
            },
            "behavior": {
                "idle_timeout": hw.behavior.idle_timeout,
                "watchdog_timeout": hw.behavior.watchdog_timeout,
            },
        }

    # Servo control
    @app.post("/api/servo/move")
    async def move_servo(cmd: ServoCommand):
        if not companion.serial:
            return JSONResponse({"error": "Serial not connected"}, status_code=503)

        response = await companion.serial.move_servo(cmd.servo_id, cmd.angle, cmd.speed)
        return {"ok": response.ok, "msg": response.msg}

    @app.post("/api/servo/move-multiple")
    async def move_servos(cmd: ServosCommand):
        if not companion.serial:
            return JSONResponse({"error": "Serial not connected"}, status_code=503)

        response = await companion.serial.move_servos(cmd.positions)
        return {"ok": response.ok, "msg": response.msg}

    @app.post("/api/mood/set")
    async def set_mood(cmd: MoodCommand):
        if not companion.serial:
            return JSONResponse({"error": "Serial not connected"}, status_code=503)

        response = await companion.serial.set_mood(cmd.mood)
        return {"ok": response.ok, "msg": response.msg}

    @app.post("/api/robot/reset")
    async def reset_robot():
        if not companion.serial:
            return JSONResponse({"error": "Serial not connected"}, status_code=503)

        response = await companion.serial.reset()
        return {"ok": response.ok, "msg": response.msg}

    @app.post("/api/robot/emergency-stop")
    async def emergency_stop():
        if not companion.serial:
            return JSONResponse({"error": "Serial not connected"}, status_code=503)

        response = await companion.serial.emergency_stop()
        if companion.state_machine:
            await companion.state_machine.on_emergency_stop()
        return {"ok": response.ok, "msg": response.msg}

    @app.post("/api/robot/speak")
    async def robot_speak(cmd: SpeakCommand):
        if not companion.audio:
            return JSONResponse({"error": "Audio not available"}, status_code=503)

        await companion.audio.speak(cmd.text)
        return {"ok": True}

    @app.post("/api/personality/trait")
    async def set_personality_trait(cmd: PersonalityTraitCommand):
        if not companion.ai_engine:
            return JSONResponse({"error": "AI engine not available"}, status_code=503)

        await companion.ai_engine.set_personality_trait(cmd.trait, cmd.value)
        return {"ok": True}

    @app.post("/api/ai/greet")
    async def trigger_greeting(face_id: Optional[str] = None):
        if not companion.ai_engine:
            return JSONResponse({"error": "AI engine not available"}, status_code=503)

        await companion.ai_engine.trigger_greeting(face_id)
        return {"ok": True}

    @app.post("/api/ai/celebrate")
    async def trigger_celebration():
        if not companion.ai_engine:
            return JSONResponse({"error": "AI engine not available"}, status_code=503)

        await companion.ai_engine.trigger_celebration()
        return {"ok": True}

    @app.post("/api/ai/surprise")
    async def trigger_surprise():
        if not companion.ai_engine:
            return JSONResponse({"error": "AI engine not available"}, status_code=503)

        await companion.ai_engine.trigger_surprise()
        return {"ok": True}

    # WebSocket for real-time updates
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # Handle incoming messages if needed
                try:
                    msg = json.loads(data)
                    await handle_ws_message(msg, websocket)
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    async def handle_ws_message(msg: dict, ws: WebSocket):
        """Handle incoming WebSocket messages."""
        msg_type = msg.get("type")

        if msg_type == "ping":
            await ws.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
        elif msg_type == "get_status":
            status = await get_status()
            await ws.send_text(json.dumps({"type": "status", "data": status.body.decode()}))
        elif msg_type == "move_servo":
            servo_id = msg.get("servo_id")
            angle = msg.get("angle")
            speed = msg.get("speed")
            if companion.serial:
                response = await companion.serial.move_servo(servo_id, angle, speed)
                await ws.send_text(json.dumps({
                    "type": "servo_response",
                    "servo_id": servo_id,
                    "ok": response.ok,
                }))

    # Status broadcast task
    async def broadcast_status():
        """Periodically broadcast status to all clients."""
        while True:
            await asyncio.sleep(0.1)  # 10Hz
            if manager.active_connections:
                status = await get_status()
                await manager.broadcast({
                    "type": "status_update",
                    "data": status.body.decode() if hasattr(status, 'body') else status,
                })

    # Start broadcast task on startup
    @app.on_event("startup")
    async def startup_event():
        asyncio.create_task(broadcast_status())

    return app