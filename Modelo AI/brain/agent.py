"""El cerebro: bucle de razonamiento sobre Ollama con herramientas y memoria.

Flujo de un turno:
    texto del usuario
      → system prompt + memoria relevante + historial
      → Ollama (con tools)
      → si pide tools: ejecutar y volver a preguntar
      → respuesta final corta, lista para TTS
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from brain.emotions import EmotionState
from brain.llm import DEFAULT_HOST, Ollama, OllamaError
from brain.memory import Memory
from brain.tools import Tools
from hardware.esp32_link import Esp32Link
from vision.reflex import Camera

ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PATH = ROOT / "prompts" / "system.md"
MAX_STEPS = 4
MAX_WORDS = 30

_WEEKDAYS = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
]
_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


class Agent:
    def __init__(
        self,
        model: str = "walle",
        memory_path: str | Path = ROOT / "memory.db",
        emotions_path: str | Path | None = None,
        camera_index: int = 0,
        camera_width: int = 480,
        camera_height: int = 360,
        port: str | None = None,
        autoconnect: bool = False,
        speak: Callable[[str], None] | None = None,
        verbose: bool = False,
        warmup: bool = True,
    ) -> None:
        self.memory = Memory(memory_path)
        self.emotions = EmotionState(emotions_path)
        self.link = Esp32Link(port=port, autoconnect=autoconnect)
        self.camera = Camera(camera_index, camera_width, camera_height)
        self.tools = Tools(self.link, self.memory, self.camera)
        self.llm = Ollama(
            model=model,
            host=os.environ.get("OLLAMA_HOST", DEFAULT_HOST),
        )
        self.speak = speak or (lambda _text: None)
        self.verbose = verbose
        self.base_prompt = self._load_prompt()
        if warmup:
            self.warmup()

    def warmup(self) -> None:
        """Calienta con el prompt y las tools reales. Sin esto, el primer turno tarda 30s."""
        try:
            self.llm.chat(
                [
                    {"role": "system", "content": self.base_prompt},
                    {"role": "user", "content": "hola"},
                ],
                tools=self.tools.schemas(),
            )
        except OllamaError:
            pass

    # ------------------------------------------------------------- prompt
    def _load_prompt(self) -> str:
        if SYSTEM_PATH.exists():
            return SYSTEM_PATH.read_text(encoding="utf-8").strip()
        return "Sos WALL-E, un robot de escritorio. Respondé corto, en español."

    def _system(self) -> str:
        """Prompt fijo. Si cambia, Ollama pierde el cache y todo se vuelve lento."""
        return self.base_prompt

    def _context(self, user_text: str) -> str:
        """Contexto variable, va al final del mensaje del usuario, no al system."""
        now = datetime.now()
        stamp = (
            f"{_WEEKDAYS[now.weekday()]} {now.day} de "
            f"{_MONTHS[now.month - 1]} de {now.year}, {now:%H:%M}"
        )
        parts = [f"[contexto: {stamp} · cuerpo: {self.link.status()['mode']}"]
        parts.append(" · " + self.emotions.system_block())
        memory_block = self.memory.context_block(user_text)
        if memory_block:
            parts.append(" · " + memory_block.replace("\n", " "))
        parts.append("]")
        return "".join(parts)

    # ------------------------------------------------------------- turno
    _STATUS_RE = re.compile(
        r"\b(conectad|conexi[oó]n|bater[ií]a|estado|orugas|puerto)\b", re.IGNORECASE
    )
    _REMEMBER_RE = re.compile(
        r"\b(acordate|acord[ée]|record[aá]|record[ée]|anot[aá]|guard[aá]|memoriz[aá])\b",
        re.IGNORECASE,
    )
    _TOOL_HINTS = re.compile(
        r"\b(mov[eé]|mover|avanz|retroced|gir[aá]|giro|fren[aá]|frenar|deten|"
        r"pará|parate|paráte|oruga|robot|c[aá]mara|mir[aá]|mirar|viste|veo|color|rojo|"
        r"verde|azul|amarillo|naranja|acord|record|anot|guard|memoria|agend|"
        r"evento|calendario|conect|bater[ií]a|estado|puerto|"
        r"abr[ií]|abre|abrir|cre[aá]|crear|borr[aá]|carpeta|archivo|programa|"
        r"aplicaci[oó]n|bloc|notepad|calculadora|paint|explorador|navegador|"
        r"google|web|p[aá]gina|sistema|list[aá]|listar)\b",
        re.IGNORECASE,
    )
    _COMPUTER_RE = re.compile(
        r"\b(abr[ií]|abre|abrir|cre[aá]|crear|carpeta|archivo|programa|aplicaci[oó]n|"
        r"bloc|notepad|calculadora|paint|explorador|navegador|google|web|p[aá]gina|"
        r"sistema|list[aá]|listar)\b",
        re.IGNORECASE,
    )
    _MOVE_HINTS = re.compile(
        r"\b(mov[eé]|mover|avanz|retroced|gir[aá]|giro|fren[aá]|frenar|deten|"
        r"pará|parate|paráte|oruga|robot|conect|bater[ií]a|estado|puerto)\b",
        re.IGNORECASE,
    )
    _BANNED_CLOSER = re.compile(
        r"\s*¿[^?]*\b(puedo ayudarte|puedo asistirte|te puedo ayudar|te puedo "
        r"asistir|en qué más te ayudo|en que más te ayudo|puedo hacer por vos|"
        r"puedo hacer por ti)\b[^?]*\?",
        re.IGNORECASE,
    )
    _TIME_RE = re.compile(
        r"\b(qu[eé] hora|hora es|qu[eé] d[ií]a|fecha de hoy|qu[eé] fecha|"
        r"d[ií]a es hoy|estamos a)\b",
        re.IGNORECASE,
    )
    _IDENTITY_RE = re.compile(
        r"\b(qui[eé]n sos|qui[eé]n eres|qui[eé]n es usted|c[oó]mo te llam[aá]s|"
        r"cu[aá]l es tu nombre|tu nombre|qu[eé] sos|qu[eé] eres)\b",
        re.IGNORECASE,
    )
    _FAKE_ERROR = re.compile(
        r"\b(hubo un error|error al (actualizar|modificar|cambiar|leer|acceder)|"
        r"no pude (actualizar|modificar|cambiar|acceder|leer)|fall[oó] al|"
        r"problema t[eé]cnico|tuve un problema|no tengo permiso|"
        r"no tengo acceso|no puedo acceder)\b",
        re.IGNORECASE,
    )
    _FAKE_INCAPABLE = re.compile(
        r"\b(no puedo (abrir|crear|usar|controlar|acceder)|no tengo (la )?capacidad|"
        r"no estoy programad[oa] para|no puedo hacer eso|soy un modelo de lenguaje)\b",
        re.IGNORECASE,
    )

    def _schemas_for(self, user_text: str) -> list[dict[str, Any]]:
        """Herramientas según el pedido. Sin verbo de movimiento, no ofrecemos mover.

        Evita que un modelo chico mueva las orugas cuando solo le preguntan el nombre.
        """
        if not self._TOOL_HINTS.search(user_text):
            return []
        schemas = self.tools.schemas()
        if not self._MOVE_HINTS.search(user_text):
            blocked = {"mover", "detener"}
            schemas = [s for s in schemas if s["function"]["name"] not in blocked]
        if not self._COMPUTER_RE.search(user_text):
            schemas = [
                s for s in schemas if s["function"]["name"] != "accion_pc"
            ]
        return schemas

    def _quick_answer(self, user_text: str) -> str | None:
        """Reflejos: hora, fecha y estado sin pasar por el LLM. Latencia cero."""
        if self._IDENTITY_RE.search(user_text):
            return (
                "Soy WALL-E. Un robot chiquito con orugas y ojos de cámara, "
                "y vivo acá en tu escritorio."
            )
        if self._TIME_RE.search(user_text):
            now = datetime.now()
            return (
                f"Son las {now:%H:%M} del {_WEEKDAYS[now.weekday()]} "
                f"{now.day} de {_MONTHS[now.month - 1]} de {now.year}."
            )
        if len(user_text.split()) > 12:
            return None
        if not self._STATUS_RE.search(user_text):
            return None
        status = self.link.status()
        if status["connected"]:
            uptime = int(time.time() - self.tools.started_at)
            return (
                f"Sí, tengo las orugas conectadas en {status['port']}. "
                f"Llevo {uptime} segundos despierto."
            )
        return "No. Estoy en modo simulación, no siento las orugas."

    def _memory_net(self, user_text: str, executed: set[str]) -> None:
        """Si el usuario pidió recordar y el modelo no llamó a la tool, la llamamos.

        Evita que el modelo diga "ya lo guardé" sin haber guardado nada.
        """
        if "recordar" in executed or not self._REMEMBER_RE.search(user_text):
            return
        text = re.sub(
            r"^\s*(che,?\s*)?(acordate|record[aá]|record[ée]|anot[aá]|guard[aá]|memoriz[aá])"
            r"(\s+que)?\s*",
            "",
            user_text,
            flags=re.IGNORECASE,
        ).strip()
        if text:
            self.tools.execute("recordar", {"texto": text})
            if self.verbose:
                print(f"  [red] guardado a la fuerza: {text}")

    _APP_RE = re.compile(
        r"\b(bloc de notas|notepad|calculadora|paint|explorador|navegador|"
        r"google|chrome|edge|spotify|whatsapp|c[aá]mara|configuraci[oó]n|ajustes)\b",
        re.IGNORECASE,
    )
    _CREATE_FOLDER_RE = re.compile(
        r"cre[aá]\s+(?:una\s+)?carpeta(?:\s+llamada)?\s+[\"“']?([^\"”'.,]+)",
        re.IGNORECASE,
    )
    _CREATE_FILE_RE = re.compile(
        r"cre[aá]\s+(?:un\s+)?archivo(?:\s+llamado)?\s+[\"“']?([^\"”'.,]+)",
        re.IGNORECASE,
    )

    def _computer_net(
        self, user_text: str, executed: set[str]
    ) -> dict[str, Any] | None:
        """Red de seguridad para acciones de escritorio explícitas.

        El modelo chico a veces contesta "no puedo" sin llamar a la tool. Si el
        pedido es claro y seguro, lo ejecutamos igual. Nunca borra ni usa shell.
        """
        if "accion_pc" in executed:
            return None
        text = user_text.strip()
        low = text.lower()
        if not self._COMPUTER_RE.search(low):
            return None

        wants_create = bool(re.search(r"\b(cre[aá]|crear)\b", low))
        if wants_create:
            match = self._CREATE_FOLDER_RE.search(text)
            if match:
                name = _clean_destination(match.group(1))
                if name:
                    return self.tools.execute(
                        "accion_pc", {"accion": "crear_carpeta", "destino": name}
                    )
            match = self._CREATE_FILE_RE.search(text)
            if match:
                name = _clean_destination(match.group(1))
                if name:
                    return self.tools.execute(
                        "accion_pc", {"accion": "crear_archivo", "destino": name}
                    )

        if re.search(r"\b(info|informaci[oó]n|estado)\b.*\b(sistema|pc|computadora)\b", low):
            return self.tools.execute("accion_pc", {"accion": "info_sistema"})

        if re.search(r"\b(abr[ií]|abre|abrir)\b", low):
            folder = re.search(
                r"carpeta\s+(?:de\s+|llamada\s+)?[\"“']?([^\"”'.,]+)", text, re.IGNORECASE
            )
            if folder:
                name = _clean_destination(folder.group(1))
                if name:
                    return self.tools.execute(
                        "accion_pc", {"accion": "abrir_carpeta", "destino": name}
                    )
            app = self._APP_RE.search(text)
            if app:
                return self.tools.execute(
                    "accion_pc",
                    {"accion": "abrir_app", "destino": app.group(1).lower()},
                )
            web = re.search(
                r"\b(?:web|p[aá]gina|sitio)\s+(?:de\s+)?([\w.-]+\.[a-z]{2,})",
                text,
                re.IGNORECASE,
            ) or re.search(
                r"\b(?:abr[ií]|abre|abrir)\b[^,.]*?\b([\w-]+(?:\.[\w-]+)*\.[a-z]{2,})\b",
                text,
                re.IGNORECASE,
            )
            if web:
                return self.tools.execute(
                    "accion_pc", {"accion": "abrir_web", "destino": web.group(1)}
                )

        return None

    def _fake_failure_retry(
        self,
        messages: list[dict[str, Any]],
        text: str,
        failures: list[dict[str, Any]],
    ) -> str:
        """Si inventó un error técnico que nunca ocurrió, le pedimos que se corrija."""
        if failures:
            return text
        if not (self._FAKE_ERROR.search(text) or self._FAKE_INCAPABLE.search(text)):
            return text
        if self.verbose:
            print("  [filtro] respuesta con error inventado; reintentando")
        retry_messages = list(messages)
        retry_messages.append({"role": "assistant", "content": text})
        retry_messages.append(
            {
                "role": "user",
                "content": (
                    "[corrección interna: no hubo ningún error técnico y ninguna "
                    "herramienta falló. No inventes errores ni digas que no podés. "
                    "Respondé la pregunta original en una sola frase corta.]"
                ),
            }
        )
        try:
            reply = self.llm.chat(retry_messages)
        except OllamaError:
            return "No pasó nada malo. Te escucho."
        fixed = self._clean(reply.get("content", ""))
        if fixed and not self._FAKE_ERROR.search(fixed):
            return fixed
        return "No pasó nada malo. Te escucho."

    def _save_turn(self, user_text: str, text: str) -> None:
        self.memory.add_turn("user", user_text)
        self.memory.add_turn("assistant", text)

    def respond(self, user_text: str) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return ""

        self.emotions.touch(user_text)

        quick = self._quick_answer(user_text)
        if quick:
            self.emotions.after_reply(quick, ok=True)
            self._save_turn(user_text, quick)
            return quick

        # Pedidos de escritorio claros: ejecutar ya, sin esperar al modelo.
        fast = self._computer_net(user_text, set())
        if fast is not None:
            detail = str(fast.get("detail") or "").strip()
            if fast.get("ok"):
                text = self._clean(_action_reply(detail))
                ok = True
            else:
                text = self._clean(f"No pude: {detail or 'algo salió mal'}.")
                ok = False
            self.emotions.after_reply(text, ok=ok)
            self._save_turn(user_text, text)
            return text

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system()}
        ]
        messages.extend(self.memory.recent_turns())
        messages.append(
            {
                "role": "user",
                "content": f"{user_text}\n\n{self._context(user_text)}",
            }
        )

        executed: set[str] = set()
        failures: list[dict[str, Any]] = []
        text = ""
        ok = True
        schemas = self._schemas_for(user_text)

        for _ in range(MAX_STEPS):
            try:
                reply = self.llm.chat(messages, tools=schemas)
            except OllamaError as exc:
                text = self._offline(str(exc))
                ok = False
                break

            tool_calls = reply.get("tool_calls") or []
            if self.verbose and self.llm.last_metrics:
                print(f"  [llm] {self.llm.last_metrics}")
            if not tool_calls:
                text = self._clean(reply.get("content", ""))
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": reply.get("content", "") or "",
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                name = (call.get("function") or {}).get("name", "")
                raw_args = (call.get("function") or {}).get("arguments", {})
                args = _parse_args(raw_args)
                executed.add(name)
                if self.verbose:
                    print(f"  [tool] {name}({args})")
                result = self.tools.execute(name, args)
                if isinstance(result, dict) and not result.get("ok"):
                    failures.append(result)
                if self.verbose:
                    print(f"  [tool] -> {result}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        else:
            # Se quedó dando vueltas con tools: pedimos cierre sin herramientas.
            try:
                final = self.llm.chat(messages)
                text = self._clean(final.get("content", ""))
            except OllamaError as exc:
                text = self._offline(str(exc))
                ok = False

        fallback = self._computer_net(user_text, executed)
        if fallback is not None:
            detail = str(fallback.get("detail") or "").strip()
            if fallback.get("ok"):
                executed.add("accion_pc")
                if (
                    not text
                    or self._FAKE_ERROR.search(text)
                    or self._FAKE_INCAPABLE.search(text)
                ):
                    text = self._clean(_action_reply(detail))
                elif detail and detail.lower() not in text.lower():
                    text = self._clean(f"{text} {detail}")
            else:
                failures.append(fallback)
                if (
                    not text
                    or self._FAKE_ERROR.search(text)
                    or self._FAKE_INCAPABLE.search(text)
                ):
                    text = self._clean(f"No pude: {detail}.")

        text = self._fake_failure_retry(messages, text, failures)

        if not text:
            text = "Mmm. No sé qué decir."

        self._memory_net(user_text, executed)
        self.emotions.after_reply(text, ok=ok)
        self._save_turn(user_text, text)
        return text

    # ------------------------------------------------------------- utilidades
    def _clean(self, text: str) -> str:
        text = (text or "").strip()
        text = re.sub(r"^\s*WALL-E\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"[*_#`>]", "", text)
        text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
        text = self._BANNED_CLOSER.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"([.!?])\s*[.!?]+", r"\1", text)
        words = text.split()
        if len(words) > MAX_WORDS:
            # corta en el último punto antes del límite
            cut = " ".join(words[:MAX_WORDS])
            last_dot = cut.rfind(".")
            text = cut[: last_dot + 1] if last_dot > 20 else cut + "."
        return text

    def _offline(self, detail: str) -> str:
        if self.verbose:
            print(f"  [llm] {detail}")
        return "Me quedé sin cerebro un segundo. ¿Me lo repetís?"

    def close(self) -> None:
        self.link.stop()
        self.link.close()
        self.camera.close()
        self.memory.close()


def _clean_destination(raw: str) -> str:
    text = (raw or "").strip().strip("\"'“”‘’")
    text = re.sub(
        r"\s+(en|sobre|dentro de)\s+.*$", "", text, flags=re.IGNORECASE
    ).strip()
    text = re.sub(r"^(de|la|el)\s+", "", text, flags=re.IGNORECASE).strip()
    text = text.strip(" .,;:")
    return text[:80]


def _action_reply(detail: str) -> str:
    clean = (detail or "listo").strip().rstrip(".")
    if not clean:
        clean = "listo"
    return f"¡Listo! {clean[0].upper()}{clean[1:]}."


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                pass
    return {}
