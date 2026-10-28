"""Herramientas que el cerebro puede ejecutar.

Cada tool tiene: esquema JSON (para Ollama), handler y descripción corta.
Los handlers nunca levantan excepción hacia el LLM: devuelven un dict con
`ok` y `detail`, así el modelo puede contarlo en una frase.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from brain.computer import Computer
from brain.memory import Memory
from hardware.esp32_link import Esp32Link
from vision.reflex import Camera, probe_color

DATA_DIR = Path(__file__).resolve().parent.parent / "datos"


class Tools:
    def __init__(
        self,
        link: Esp32Link,
        memory: Memory,
        camera: Camera,
        computer: Computer | None = None,
    ) -> None:
        self.link = link
        self.memory = memory
        self.camera = camera
        self.computer = computer or Computer()
        self.started_at = time.time()
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "mover": self.mover,
            "detener": self.detener,
            "mirar_color": self.mirar_color,
            "estado_robot": self.estado_robot,
            "recordar": self.recordar,
            "buscar_memoria": self.buscar_memoria,
            "agendar": self.agendar,
            "accion_pc": self.accion_pc,
        }

    # ------------------------------------------------------------- esquemas
    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "mover",
                    "description": "Mueve las orugas. Avanzar 150,150. Girar izq -150,150.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "oruga_izquierda": {"type": "integer"},
                            "oruga_derecha": {"type": "integer"},
                            "segundos": {"type": "number"},
                        },
                        "required": ["oruga_izquierda", "oruga_derecha", "segundos"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "detener",
                    "description": "Frena las orugas.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mirar_color",
                    "description": "Mira si hay un color y dónde está.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "color": {
                                "type": "string",
                                "enum": ["rojo", "verde", "azul", "amarillo", "naranja"],
                            }
                        },
                        "required": ["color"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "estado_robot",
                    "description": "Conexión, uptime y memoria.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "recordar",
                    "description": "Guarda un dato para siempre.",
                    "parameters": {
                        "type": "object",
                        "properties": {"texto": {"type": "string"}},
                        "required": ["texto"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "buscar_memoria",
                    "description": "Busca datos guardados.",
                    "parameters": {
                        "type": "object",
                        "properties": {"consulta": {"type": "string"}},
                        "required": ["consulta"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "agendar",
                    "description": "Crea un evento. inicio: YYYY-MM-DDTHH:MM.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "titulo": {"type": "string"},
                            "inicio": {"type": "string"},
                            "duracion_minutos": {"type": "integer"},
                            "descripcion": {"type": "string"},
                        },
                        "required": ["titulo", "inicio"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "accion_pc",
                    "description": (
                        "Hace una acción real en la computadora. Usala cuando pidan "
                        "abrir un programa, carpeta o web, crear una carpeta o archivo, "
                        "listar una carpeta o ver el sistema."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "accion": {
                                "type": "string",
                                "enum": [
                                    "abrir_app",
                                    "abrir_carpeta",
                                    "abrir_web",
                                    "crear_carpeta",
                                    "crear_archivo",
                                    "listar_carpeta",
                                    "info_sistema",
                                ],
                            },
                            "destino": {
                                "type": "string",
                                "description": (
                                    "Programa, ruta, URL o nombre. Para crear carpeta "
                                    "usá solo el nombre, por ejemplo 'proyecto luna'."
                                ),
                            },
                            "contenido": {
                                "type": "string",
                                "description": "Texto del archivo, si corresponde.",
                            },
                        },
                        "required": ["accion"],
                    },
                },
            },
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            return {"ok": False, "detail": f"herramienta desconocida: {name}"}
        try:
            return handler(**arguments)
        except TypeError as exc:
            return {"ok": False, "detail": f"argumentos inválidos para {name}: {exc}"}
        except Exception as exc:
            return {"ok": False, "detail": f"{name} falló: {exc}"}

    # ------------------------------------------------------------- handlers
    def mover(
        self, oruga_izquierda: int, oruga_derecha: int, segundos: float = 1.0
    ) -> dict[str, Any]:
        seconds = max(0.1, min(float(segundos), 3.0))
        self.link.timed_move(int(oruga_izquierda), int(oruga_derecha), seconds)
        return {
            "ok": True,
            "detail": f"me moví {seconds:.1f}s",
            "left": int(oruga_izquierda),
            "right": int(oruga_derecha),
            "connected": self.link.connected,
        }

    def detener(self) -> dict[str, Any]:
        self.link.stop()
        return {"ok": True, "detail": "frenado"}

    def mirar_color(self, color: str = "rojo") -> dict[str, Any]:
        result = probe_color(self.camera, color)
        if not result.get("found"):
            return {
                "ok": bool(result.get("ok")),
                "found": False,
                "detail": result.get("error") or f"no veo {color}",
            }
        return {
            "ok": True,
            "found": True,
            "color": color,
            "where": result["where"],
            "offset": result["offset"],
            "closeness": result["closeness"],
            "detail": f"hay {color} a la {result['where']}",
        }

    def estado_robot(self) -> dict[str, Any]:
        status = self.link.status()
        uptime = int(time.time() - self.started_at)
        status.update(
            {
                "ok": True,
                "uptime_seconds": uptime,
                "memory_items": self.memory.count(),
                "detail": f"modo {status['mode']}, {uptime}s encendido",
            }
        )
        return status

    def recordar(self, texto: str) -> dict[str, Any]:
        memory_id = self.memory.remember(texto)
        return {"ok": memory_id > 0, "id": memory_id, "detail": "lo guardé"}

    def buscar_memoria(self, consulta: str) -> dict[str, Any]:
        hits = self.memory.search(consulta, limit=5)
        if not hits:
            return {"ok": True, "found": False, "detail": "no tengo nada de eso"}
        return {
            "ok": True,
            "found": True,
            "results": [h["text"] for h in hits],
            "detail": "; ".join(h["text"] for h in hits),
        }

    def agendar(
        self,
        titulo: str,
        inicio: str,
        duracion_minutos: int = 60,
        descripcion: str = "",
    ) -> dict[str, Any]:
        try:
            start = datetime.fromisoformat(inicio)
        except ValueError:
            return {"ok": False, "detail": f"fecha inválida: {inicio}"}

        end = start + timedelta(minutes=max(5, min(int(duracion_minutos), 480)))

        google = _google_calendar()
        if google is not None:
            ok, detail = google(titulo, descripcion, start, end)
            return {"ok": ok, "backend": "google", "detail": detail}

        # Sin Google configurado: guardamos local y lo decimos claro.
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / "agenda.jsonl"
        entry = {
            "titulo": titulo,
            "inicio": start.isoformat(),
            "fin": end.isoformat(),
            "descripcion": descripcion,
            "creado": datetime.now().isoformat(),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {
            "ok": True,
            "backend": "local",
            "detail": "anotado en la agenda local, Google Calendar no está configurado",
            "evento": entry,
        }

    def accion_pc(
        self, accion: str, destino: str = "", contenido: str = ""
    ) -> dict[str, Any]:
        """Delegado a la capa segura de escritorio."""
        return self.computer.ejecutar(accion, destino, contenido)


def _google_calendar():
    """Devuelve una función para crear eventos, o None si no está configurado."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None

    root = Path(__file__).resolve().parent.parent
    creds_path = root / "credentials.json"
    token_path = root / "token.json"
    if not creds_path.exists():
        return None

    scopes = ["https://www.googleapis.com/auth/calendar"]
    timezone = "America/Argentina/Mendoza"

    def create(title: str, description: str, start: datetime, end: datetime):
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)
                creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        service = build("calendar", "v3", credentials=creds)
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": timezone},
        }
        created = service.events().insert(calendarId="primary", body=event).execute()
        return True, f"evento creado: {created.get('htmlLink')}"

    return create
