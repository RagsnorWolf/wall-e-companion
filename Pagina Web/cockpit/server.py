"""Cabina de WALL-E: servidor local del software completo.

Sin dependencias extra: usa la librería estándar de Python y el cerebro que
ya vive en `Modelo AI/`.

    python server.py
    python server.py --port 8765 --no-browser

Expone:
    /api/state          estado general
    /api/chat           conversación con el cerebro
    /api/robot/*        conexión y control manual de las orugas
    /api/emotion        caricias y estado emocional
    /api/camera/frame   foto + detección de color
    /api/vision/track   seguimiento automático (seguir un color)
    /api/memory         memoria de largo plazo
    /api/agenda         eventos locales
    /api/settings       modelo, puerto, cámara
    /api/events         registro de actividad
    /api/diagnostics    chequeos del sistema
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

try:
    import psutil
except ImportError:  # la cabina sigue funcionando sin telemetría fina
    psutil = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
AI_DIR = ROOT.parent.parent / "Modelo AI"
CONFIG_PATH = ROOT / "config.json"
AGENDA_PATH = AI_DIR / "datos" / "agenda.jsonl"

sys.path.insert(0, str(AI_DIR))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from brain.agent import Agent  # noqa: E402
from brain.llm import OllamaError  # noqa: E402
from hardware.esp32_link import list_ports, serial  # noqa: E402
from vision.reflex import (  # noqa: E402
    COLOR_RANGES,
    MIN_AREA,
    ColorTracker,
    cv2,
    np,
)

VERSION = "2.0.0"
DEFAULT_SETTINGS: dict[str, Any] = {
    "model": "walle",
    "port": None,
    "camera_index": 0,
}

_agent: Agent | None = None
_init_lock = threading.Lock()
_chat_lock = threading.Lock()
_motion_lock = threading.Lock()
_agenda_lock = threading.Lock()
_started_at = time.time()
_ready = False
_warming = True
_boot_error: str | None = None
_settings = DEFAULT_SETTINGS.copy()
_events: deque[dict[str, Any]] = deque(maxlen=160)
_events_lock = threading.Lock()
_tracker: ColorTracker | None = None
_tracker_lock = threading.Lock()
_last_drive = 0.0
_last_drive_cmd: tuple[int, int] | None = None
_timed_active = False


# ---------------------------------------------------------------- utilidades
def load_settings() -> dict[str, Any]:
    data = DEFAULT_SETTINGS.copy()
    try:
        if CONFIG_PATH.exists():
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                if isinstance(raw.get("model"), str) and raw["model"].strip():
                    data["model"] = raw["model"].strip()
                port = raw.get("port")
                data["port"] = str(port).strip() if port else None
                camera = raw.get("camera_index")
                if isinstance(camera, int) and 0 <= camera <= 12:
                    data["camera_index"] = camera
    except Exception as exc:
        print(f"[aviso] no pude leer config.json: {exc}")
    return data


def save_settings() -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(_settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[aviso] no pude guardar config.json: {exc}")


def log_event(kind: str, text: str, data: dict[str, Any] | None = None) -> None:
    entry = {
        "ts": time.time(),
        "kind": kind,
        "text": (text or "").strip()[:240],
    }
    if data:
        entry["data"] = data
    with _events_lock:
        _events.append(entry)


def recent_events(limit: int = 40) -> list[dict[str, Any]]:
    with _events_lock:
        items = list(_events)[-max(1, min(limit, 160)) :]
    return list(reversed(items))


def system_metrics() -> dict[str, Any]:
    """Telemetría de la PC. Si psutil no está, devuelve nulls y la UI aguanta."""
    data: dict[str, Any] = {
        "cpu": None,
        "ram": None,
        "temp": None,
        "battery": None,
        "process_ram": None,
    }
    if psutil is None:
        return data
    try:
        # ThreadingHTTPServer atiende cada request en un hilo nuevo, y psutil
        # guarda la última muestra por hilo: sin intervalo siempre daría 0.
        data["cpu"] = round(float(psutil.cpu_percent(interval=0.08)), 1)
    except Exception:
        pass
    try:
        data["ram"] = round(float(psutil.virtual_memory().percent), 1)
    except Exception:
        pass
    try:
        sensors = psutil.sensors_temperatures()  # type: ignore[attr-defined]
        for name in ("coretemp", "k10temp", "acpitz", "cpu_thermal"):
            if sensors.get(name):
                data["temp"] = round(float(sensors[name][0].current), 1)
                break
        if data["temp"] is None:
            for entries in sensors.values():
                if entries:
                    data["temp"] = round(float(entries[0].current), 1)
                    break
    except Exception:
        pass
    try:
        battery = psutil.sensors_battery()  # type: ignore[attr-defined]
        if battery is not None:
            data["battery"] = round(float(battery.percent), 1)
    except Exception:
        pass
    try:
        data["process_ram"] = int(psutil.Process().memory_info().rss)
    except Exception:
        pass
    return data


def list_serial_ports() -> list[dict[str, str]]:
    if list_ports is None:
        return []
    result = []
    try:
        for port in list_ports.comports():
            result.append(
                {
                    "device": port.device,
                    "description": port.description or "",
                    "hwid": port.hwid or "",
                }
            )
    except Exception:
        return []
    return result


def read_agenda() -> list[dict[str, Any]]:
    if not AGENDA_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = AGENDA_PATH.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                item["index"] = index
                events.append(item)
    except Exception:
        return []
    events.sort(key=lambda item: str(item.get("inicio", "")))
    return events


# ---------------------------------------------------------------- cerebro
def _instrument(agent: Agent) -> None:
    original = agent.tools.execute

    def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = original(name, arguments)
        detail = ""
        if isinstance(result, dict):
            detail = str(result.get("detail") or result.get("ok") or "")
        log_event("tool", f"{name} · {detail}", {"name": name, "args": arguments})
        return result

    agent.tools.execute = execute  # type: ignore[method-assign]


def _create_agent() -> Agent:
    return Agent(
        model=_settings["model"],
        memory_path=AI_DIR / "memory.db",
        camera_index=int(_settings["camera_index"]),
        port=_settings.get("port"),
        verbose=False,
        warmup=False,
    )


def get_agent() -> Agent:
    global _agent
    with _init_lock:
        if _agent is None:
            _agent = _create_agent()
            _instrument(_agent)
        return _agent


def warm_agent(agent: Agent) -> None:
    global _ready, _warming, _boot_error
    try:
        agent.warmup()
        _ready = True
        _boot_error = None
    except Exception as exc:
        _boot_error = str(exc)
        print(f"[error] calentando el modelo: {exc}")
    finally:
        _warming = False


def boot_agent() -> None:
    global _warming, _boot_error
    _warming = True
    try:
        agent = get_agent()
        print(f"[ok] cerebro cargado: {_settings['model']}")
        warm_agent(agent)
    except Exception as exc:
        _boot_error = str(exc)
        _warming = False
        print(f"[error] no pude iniciar el cerebro: {exc}")


def rebuild_agent(new_settings: dict[str, Any]) -> None:
    global _agent, _settings, _ready, _warming, _boot_error
    with _chat_lock:
        with _init_lock:
            old = _agent
            _agent = None
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
            _settings = new_settings
            save_settings()
            agent = _create_agent()
            _instrument(agent)
            _agent = agent
        _ready = False
        _warming = True
        _boot_error = None
        threading.Thread(target=warm_agent, args=(agent,), daemon=True).start()


# ---------------------------------------------------------------- watchdog
def motion_watchdog() -> None:
    """Frena si la interfaz dejó de mandar órdenes. Seguridad del cuerpo."""
    global _last_drive
    while True:
        time.sleep(0.25)
        if _timed_active or _tracker is not None:
            continue
        if not _last_drive or _agent is None:
            continue
        if time.time() - _last_drive < 1.2:
            continue
        try:
            command = _agent.link.last_command
            if command and command != (0, 0):
                _agent.link.stop()
                log_event("safety", "frené las orugas por inactividad")
        finally:
            _last_drive = 0


def stop_everything(reason: str = "") -> None:
    global _tracker, _last_drive, _last_drive_cmd
    with _tracker_lock:
        if _tracker is not None:
            try:
                _tracker.stop()
            except Exception:
                pass
            _tracker = None
    if _agent is not None:
        try:
            _agent.link.stop()
        except Exception:
            pass
    _last_drive = 0
    _last_drive_cmd = None
    if reason:
        log_event("safety", reason)


# ---------------------------------------------------------------- HTTP
class Handler(SimpleHTTPRequestHandler):
    server_version = f"WallECockpit/{VERSION}"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC), **kwargs)

    # ------------------------------------------------------------- helpers
    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"ok": False, "error": message}, status)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("JSON inválido")
        if not isinstance(data, dict):
            raise ValueError("se esperaba un objeto JSON")
        return data

    def log_message(self, fmt: str, *args: Any) -> None:
        # Consola limpia: la actividad real va al registro de la cabina.
        return

    def handle_one_request(self) -> None:
        # El navegador corta conexiones al cerrar pestañas o cambiar de vista.
        # No ensuciamos la consola con esos cortes normales.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self.close_connection = True

    def end_headers(self) -> None:
        if getattr(self, "_static", False):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _state_payload(self) -> dict[str, Any]:
        metrics = system_metrics()
        payload: dict[str, Any] = {
            "ok": True,
            "kind": "state",
            "version": VERSION,
            "ready": _ready,
            "warming": _warming,
            "boot_error": _boot_error,
            "model": _settings["model"],
            "mode": "simulacion",
            "port": _settings.get("port"),
            "connected": False,
            "moving": False,
            "last_command": None,
            "reason": None,
            "memory": 0,
            "uptime": int(time.time() - _started_at),
            "ollama": False,
            "camera_index": _settings["camera_index"],
            "opencv": cv2 is not None,
            "hardware": serial is not None,
            "tracking": {"enabled": False, "color": None, "last": {}},
            "system": metrics,
            "battery": metrics.get("battery"),
            "emotion": None,
        }

        if _agent is not None:
            status = _agent.link.status()
            payload.update(
                {
                    "model": _agent.llm.model,
                    "mode": status["mode"],
                    "port": status["port"],
                    "connected": status["connected"],
                    "moving": status["moving"],
                    "last_command": status["last_command"],
                    "reason": status["reason"],
                    "memory": _agent.memory.count(),
                    "ollama": _agent.llm.health(),
                    "emotion": _agent.emotions.snapshot(),
                }
            )

        if _tracker is not None:
            payload["tracking"] = {
                "enabled": True,
                "color": _tracker.color,
                "last": _tracker.last,
            }
        return payload

    # ------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/state":
                self._json(self._state_payload())
                return
            if path == "/api/events":
                query = parse_qs(parsed.query)
                try:
                    limit = int((query.get("limit") or ["40"])[0])
                except ValueError:
                    limit = 40
                self._json({"ok": True, "events": recent_events(limit)})
                return
            if path == "/api/ports":
                self._json({"ok": True, "ports": list_serial_ports()})
                return
            if path == "/api/settings":
                self._settings_payload()
                return
            if path == "/api/memory":
                self._memory_list(parsed)
                return
            if path == "/api/agenda":
                self._json(
                    {
                        "ok": True,
                        "events": read_agenda(),
                        "google": (AI_DIR / "credentials.json").exists(),
                    }
                )
                return
            if path == "/api/camera/frame":
                self._camera_frame(parsed)
                return
            if path == "/api/diagnostics":
                self._diagnostics()
                return
            if path == "/api/health":
                self._json({"ok": True, "version": VERSION})
                return
        except ValueError as exc:
            self._error(str(exc))
            return
        except Exception as exc:
            self._error(f"error interno: {exc}", 500)
            return

        if path == "/":
            self.path = "/index.html"
        self._static = True
        super().do_GET()

    # ------------------------------------------------------------- POST/DELETE
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            data = self._body()
        except ValueError as exc:
            self._error(str(exc))
            return

        try:
            if path == "/api/chat":
                self._chat(data)
            elif path == "/api/robot/move":
                self._robot_move(data)
            elif path == "/api/robot/drive":
                self._robot_drive(data)
            elif path == "/api/robot/stop":
                stop_everything("parada de emergencia desde la cabina")
                self._json({"ok": True, "state": self._state_payload()})
            elif path == "/api/robot/connect":
                self._robot_connect(data)
            elif path == "/api/robot/disconnect":
                stop_everything()
                if _agent is not None:
                    _agent.link.disconnect()
                log_event("serial", "cuerpo desconectado")
                self._json({"ok": True, "state": self._state_payload()})
            elif path == "/api/emotion":
                self._emotion(data)
            elif path == "/api/vision/track":
                self._vision_track(data)
            elif path == "/api/memory":
                self._memory_add(data)
            elif path == "/api/agenda":
                self._agenda_add(data)
            elif path == "/api/settings":
                self._settings_save(data)
            else:
                self._error("ruta desconocida", 404)
        except OllamaError as exc:
            self._json({"ok": False, "error": f"Ollama no responde: {exc}"}, 503)
        except ValueError as exc:
            self._error(str(exc))
        except Exception as exc:
            self._error(f"error interno: {exc}", 500)

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/memory/"):
                raw_id = unquote(parsed.path.rsplit("/", 1)[-1])
                if not raw_id.isdigit():
                    self._error("id inválido")
                    return
                agent = get_agent()
                ok = agent.memory.forget(int(raw_id))
                if ok:
                    log_event("memory", "recuerdo borrado")
                self._json({"ok": ok})
                return

            if parsed.path == "/api/agenda":
                query = parse_qs(parsed.query)
                raw_index = (query.get("index") or [""])[0]
                if not raw_index.isdigit():
                    self._error("índice inválido")
                    return
                self._agenda_delete(int(raw_index))
                return

            self._error("ruta desconocida", 404)
        except ValueError as exc:
            self._error(str(exc))
        except Exception as exc:
            self._error(f"error interno: {exc}", 500)

    # ------------------------------------------------------------- estado
    def _settings_payload(self) -> None:
        models: list[str] = []
        if _agent is not None:
            try:
                models = _agent.llm.models()
            except OllamaError:
                models = []
        prompt = ""
        prompt_path = AI_DIR / "prompts" / "system.md"
        try:
            if prompt_path.exists():
                prompt = prompt_path.read_text(encoding="utf-8")
        except Exception:
            prompt = ""
        self._json(
            {
                "ok": True,
                "settings": _settings,
                "models": models,
                "prompt": prompt,
                "paths": {
                    "ai": str(AI_DIR),
                    "memory": str(AI_DIR / "memory.db"),
                    "agenda": str(AGENDA_PATH),
                },
            }
        )

    def _diagnostics(self) -> None:
        checks: list[dict[str, Any]] = []
        models: list[str] = []
        ollama_ok = False
        if _agent is not None:
            ollama_ok = _agent.llm.health()
            if ollama_ok:
                try:
                    models = _agent.llm.models()
                except OllamaError:
                    models = []
        checks.append(
            {
                "name": "Ollama",
                "ok": ollama_ok,
                "detail": f"{len(models)} modelos instalados" if ollama_ok else "no responde",
            }
        )
        wanted = str(_settings["model"]).split(":")[0]
        installed = {m.split(":")[0] for m in models}
        checks.append(
            {
                "name": "Modelo WALL-E",
                "ok": wanted in installed,
                "detail": _settings["model"],
            }
        )
        checks.append(
            {
                "name": "OpenCV",
                "ok": cv2 is not None,
                "detail": "cámara y visión disponibles" if cv2 is not None else "no instalado",
            }
        )
        checks.append(
            {
                "name": "pyserial",
                "ok": serial is not None,
                "detail": f"{len(list_serial_ports())} puertos" if serial else "no instalado",
            }
        )
        checks.append(
            {
                "name": "Memoria",
                "ok": _agent is not None,
                "detail": f"{_agent.memory.count() if _agent else 0} recuerdos",
            }
        )
        checks.append(
            {
                "name": "Agenda local",
                "ok": True,
                "detail": f"{len(read_agenda())} eventos",
            }
        )
        checks.append(
            {
                "name": "Telemetría psutil",
                "ok": psutil is not None,
                "detail": (
                    "CPU, RAM y batería" if psutil is not None else "no instalado"
                ),
            }
        )
        self._json(
            {
                "ok": True,
                "checks": checks,
                "python": sys.version.split()[0],
                "version": VERSION,
                "paths": {
                    "ai": str(AI_DIR),
                    "memory": str(AI_DIR / "memory.db"),
                    "agenda": str(AGENDA_PATH),
                },
            }
        )

    # ------------------------------------------------------------- chat
    def _chat(self, data: dict[str, Any]) -> None:
        message = str(data.get("message") or "").strip()
        if not message:
            raise ValueError("mensaje vacío")
        if len(message) > 800:
            raise ValueError("mensaje demasiado largo")

        agent = get_agent()
        started = time.perf_counter()
        with _chat_lock:
            reply = agent.respond(message)
        elapsed = time.perf_counter() - started

        log_event("chat", f"vos: {message[:120]}", {"seconds": round(elapsed, 2)})
        log_event("chat", f"WALL·E: {reply[:120]}", {"seconds": round(elapsed, 2)})
        self._json(
            {
                "ok": True,
                "reply": reply,
                "seconds": round(elapsed, 2),
                "metrics": agent.llm.last_metrics,
                "mode": agent.link.status()["mode"],
                "state": self._state_payload(),
            }
        )

    # ------------------------------------------------------------- robot
    def _robot_move(self, data: dict[str, Any]) -> None:
        global _timed_active, _last_drive
        if _tracker is not None:
            raise ValueError("desactivá el seguimiento automático antes de manejar")
        try:
            left = int(data.get("left", 0))
            right = int(data.get("right", 0))
            seconds = float(data.get("seconds", 0.6))
        except (TypeError, ValueError):
            raise ValueError("left, right y seconds deben ser números")

        left = max(-220, min(220, left))
        right = max(-220, min(220, right))
        seconds = max(0.1, min(3.0, seconds))

        agent = get_agent()
        with _motion_lock:
            _timed_active = True
            try:
                agent.link.timed_move(left, right, seconds)
            finally:
                _timed_active = False
                _last_drive = 0

        log_event("robot", f"mover {left},{right} · {seconds:.1f}s")
        self._json(
            {
                "ok": True,
                "left": left,
                "right": right,
                "seconds": seconds,
                "state": self._state_payload(),
            }
        )

    def _robot_drive(self, data: dict[str, Any]) -> None:
        global _last_drive, _last_drive_cmd
        if _tracker is not None:
            raise ValueError("desactivá el seguimiento automático antes de manejar")
        if _timed_active:
            raise ValueError("esperá a que termine el movimiento actual")
        try:
            left = int(data.get("left", 0))
            right = int(data.get("right", 0))
        except (TypeError, ValueError):
            raise ValueError("left y right deben ser números")

        left = max(-220, min(220, left))
        right = max(-220, min(220, right))

        agent = get_agent()
        agent.link.move(left, right)
        _last_drive = time.time()

        command = (left, right)
        if command != _last_drive_cmd:
            _last_drive_cmd = command
            log_event("robot", f"drive {left},{right}")
        self._json({"ok": True, "left": left, "right": right})

    def _robot_connect(self, data: dict[str, Any]) -> None:
        global _settings
        port = str(data.get("port") or "").strip()
        if not port:
            raise ValueError("elegí un puerto, por ejemplo COM3")
        if _tracker is not None:
            stop_everything()

        agent = get_agent()
        ok = agent.link.connect(port)
        if ok:
            _settings["port"] = port
            save_settings()
            log_event("serial", f"conectado a {port}")
        else:
            reason = agent.link.status().get("reason") or "no se pudo abrir"
            log_event("serial", f"falló la conexión a {port}: {reason}")

        self._json(
            {
                "ok": ok,
                "port": port,
                "reason": agent.link.status().get("reason"),
                "state": self._state_payload(),
            }
        )

    # ------------------------------------------------------------- emoción
    def _emotion(self, data: dict[str, Any]) -> None:
        action = str(data.get("action") or "caricia").strip().lower()
        agent = get_agent()
        result = agent.emotions.pet(action)
        if not result.get("ok"):
            raise ValueError(str(result.get("detail") or "acción emocional inválida"))
        log_event("emotion", f"interacción emocional: {action}")
        self._json({"ok": True, **result, "state": self._state_payload()})

    # ------------------------------------------------------------- visión
    def _camera_frame(self, parsed: Any) -> None:
        if cv2 is None or np is None:
            self._json({"ok": False, "error": "OpenCV no está instalado"}, 501)
            return
        query = parse_qs(parsed.query)
        color = str((query.get("color") or ["rojo"])[0]).lower().strip()
        if color not in COLOR_RANGES:
            color = "rojo"

        agent = get_agent()
        frame = agent.camera.read()
        if frame is None:
            self._json({"ok": False, "error": "no hay cámara disponible"})
            return

        detection = _detect(frame, color)
        quality = 72
        try:
            ok, buffer = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            )
        except Exception as exc:
            self._json({"ok": False, "error": f"no pude codificar la imagen: {exc}"})
            return
        if not ok:
            self._json({"ok": False, "error": "no pude codificar la imagen"})
            return

        height, width = frame.shape[:2]
        encoded = base64.b64encode(buffer.tobytes()).decode("ascii")
        self._json(
            {
                "ok": True,
                "image": f"data:image/jpeg;base64,{encoded}",
                "width": int(width),
                "height": int(height),
                "color": color,
                "detection": detection,
                "tracking": _tracker is not None,
            }
        )

    def _vision_track(self, data: dict[str, Any]) -> None:
        global _tracker
        enabled = bool(data.get("enabled"))
        color = str(data.get("color") or "rojo").lower().strip()
        if color not in COLOR_RANGES:
            raise ValueError(f"color desconocido: {color}")

        with _tracker_lock:
            if enabled:
                if _tracker is not None:
                    try:
                        _tracker.stop()
                    except Exception:
                        pass
                    _tracker = None
                agent = get_agent()
                tracker = ColorTracker(agent.link, agent.camera, color=color, hz=10.0)
                tracker.start()
                _tracker = tracker
                log_event("vision", f"seguimiento de {color} activado")
            else:
                if _tracker is not None:
                    try:
                        _tracker.stop()
                    except Exception:
                        pass
                    _tracker = None
                if _agent is not None:
                    _agent.link.stop()
                log_event("vision", "seguimiento desactivado")

        self._json({"ok": True, "state": self._state_payload()})

    # ------------------------------------------------------------- memoria
    def _memory_list(self, parsed: Any) -> None:
        agent = get_agent()
        query = parse_qs(parsed.query)
        text = str((query.get("q") or [""])[0]).strip()
        hits = agent.memory.search(text, limit=200)
        items = [
            {
                "id": item.get("id"),
                "ts": item.get("ts"),
                "kind": item.get("kind", "fact"),
                "text": item.get("text", ""),
            }
            for item in hits
        ]
        self._json({"ok": True, "items": items, "count": agent.memory.count()})

    def _memory_add(self, data: dict[str, Any]) -> None:
        text = str(data.get("text") or "").strip()
        if not text:
            raise ValueError("el recuerdo está vacío")
        agent = get_agent()
        memory_id = agent.memory.remember(text)
        log_event("memory", f"guardado: {text[:100]}")
        self._json(
            {
                "ok": memory_id > 0,
                "id": memory_id,
                "count": agent.memory.count(),
            }
        )

    # ------------------------------------------------------------- agenda
    def _agenda_add(self, data: dict[str, Any]) -> None:
        title = str(data.get("titulo") or "").strip()
        start = str(data.get("inicio") or "").strip()
        if not title:
            raise ValueError("el evento necesita título")
        if not start:
            raise ValueError("el evento necesita fecha y hora")
        try:
            duration = int(data.get("duracion_minutos") or 60)
        except (TypeError, ValueError):
            duration = 60
        description = str(data.get("descripcion") or "").strip()

        agent = get_agent()
        result = agent.tools.execute(
            "agendar",
            {
                "titulo": title,
                "inicio": start,
                "duracion_minutos": duration,
                "descripcion": description,
            },
        )
        if not result.get("ok"):
            raise ValueError(str(result.get("detail") or "no pude agendar"))
        self._json({"ok": True, "result": result, "events": read_agenda()})

    def _agenda_delete(self, index: int) -> None:
        with _agenda_lock:
            if not AGENDA_PATH.exists():
                raise ValueError("no hay agenda local")
            lines = AGENDA_PATH.read_text(encoding="utf-8").splitlines()
            if index < 0 or index >= len(lines):
                raise ValueError("evento inexistente")
            removed = lines.pop(index)
            AGENDA_PATH.write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
        log_event("agenda", "evento borrado")
        self._json({"ok": True, "removed": removed, "events": read_agenda()})

    # ------------------------------------------------------------- ajustes
    def _settings_save(self, data: dict[str, Any]) -> None:
        global _settings
        model = str(data.get("model") or _settings["model"]).strip()
        port_raw = data.get("port", _settings.get("port"))
        port = str(port_raw).strip() if port_raw else None
        try:
            camera_index = int(data.get("camera_index", _settings["camera_index"]))
        except (TypeError, ValueError):
            raise ValueError("camera_index debe ser un número")
        if not model:
            raise ValueError("elegí un modelo")
        if not 0 <= camera_index <= 12:
            raise ValueError("camera_index fuera de rango")

        needs_rebuild = (
            model != _settings["model"]
            or camera_index != int(_settings["camera_index"])
        )
        port_changed = port != _settings.get("port")

        if model != _settings["model"] and _agent is not None:
            try:
                installed = _agent.llm.models()
            except OllamaError:
                installed = []
            if installed and model.split(":")[0] not in {
                name.split(":")[0] for name in installed
            }:
                raise ValueError(f"el modelo {model} no está instalado en Ollama")

        new_settings = {
            "model": model,
            "port": port,
            "camera_index": camera_index,
        }

        if needs_rebuild:
            if _tracker is not None:
                stop_everything()
            rebuild_agent(new_settings)
            log_event("config", f"cerebro reconstruido con {model}")
        else:
            _settings = new_settings
            save_settings()
            if port_changed:
                stop_everything()
                if port:
                    ok = _agent.link.connect(port) if _agent is not None else False
                    log_event(
                        "serial",
                        f"conectado a {port}" if ok else f"no pude conectar a {port}",
                    )
                elif _agent is not None:
                    _agent.link.disconnect()
                log_event("config", "puerto actualizado")
            log_event("config", "ajustes guardados")

        self._json(
            {
                "ok": True,
                "settings": _settings,
                "rebuild": needs_rebuild,
                "state": self._state_payload(),
            }
        )

    # ------------------------------------------------------------- cierre
    def do_SHUTDOWN(self) -> None:  # pragma: no cover - cortesía
        self._json({"ok": True})


def _detect(frame: Any, color: str) -> dict[str, Any]:
    if cv2 is None or np is None:
        return {"found": False, "error": "OpenCV no instalado"}
    ranges = COLOR_RANGES.get(color)
    if not ranges:
        return {"found": False, "error": f"color desconocido: {color}"}

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = None
    for low, high in ranges:
        band = cv2.inRange(hsv, np.array(low), np.array(high))
        mask = band if mask is None else cv2.bitwise_or(mask, band)

    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"found": False, "color": color}

    biggest = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(biggest))
    if area < MIN_AREA:
        return {"found": False, "color": color, "area": round(area, 1)}

    x, y, w, h = cv2.boundingRect(biggest)
    moments = cv2.moments(biggest)
    if moments["m00"] == 0:
        return {"found": False, "color": color}
    cx = int(moments["m10"] / moments["m00"])
    cy = int(moments["m01"] / moments["m00"])
    width = frame.shape[1]
    height = frame.shape[0]
    offset = (cx - width / 2) / (width / 2)
    where = "izquierda" if offset < -0.25 else "derecha" if offset > 0.25 else "centro"

    return {
        "found": True,
        "color": color,
        "x": int(x),
        "y": int(y),
        "w": int(w),
        "h": int(h),
        "cx": cx,
        "cy": cy,
        "area": round(area, 1),
        "offset": round(offset, 2),
        "where": where,
        "closeness": round(min(1.0, area / (width * height * 0.15)), 2),
    }


class Server(ThreadingHTTPServer):
    daemon_threads = True


def main() -> None:
    global _settings
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    _settings = load_settings()
    print(f"[..] WALL-E cabina {VERSION}")
    print(f"[..] modelo={_settings['model']} camara={_settings['camera_index']} puerto={_settings['port']}")
    print("[..] el cerebro se calienta en segundo plano")

    threading.Thread(target=boot_agent, daemon=True).start()
    threading.Thread(target=motion_watchdog, daemon=True).start()

    server = Server(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"[ok] cabina en {url}")
    print("[..] Ctrl+C para cerrar")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[..] cerrando")
    finally:
        server.server_close()
        stop_everything()
        if _agent is not None:
            try:
                _agent.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
