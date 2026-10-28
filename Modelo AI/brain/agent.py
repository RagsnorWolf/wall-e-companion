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

from brain.llm import DEFAULT_HOST, Ollama, OllamaError
from brain.memory import Memory
from brain.tools import Tools
from hardware.esp32_link import Esp32Link
from vision.reflex import Camera

ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PATH = ROOT / "prompts" / "system.md"
MAX_STEPS = 4
MAX_WORDS = 40

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
        camera_index: int = 0,
        port: str | None = None,
        autoconnect: bool = False,
        speak: Callable[[str], None] | None = None,
        verbose: bool = False,
    ) -> None:
        self.memory = Memory(memory_path)
        self.link = Esp32Link(port=port, autoconnect=autoconnect)
        self.camera = Camera(camera_index)
        self.tools = Tools(self.link, self.memory, self.camera)
        self.llm = Ollama(
            model=model,
            host=os.environ.get("OLLAMA_HOST", DEFAULT_HOST),
        )
        self.speak = speak or (lambda _text: None)
        self.verbose = verbose
        self.base_prompt = self._load_prompt()

    # ------------------------------------------------------------- prompt
    def _load_prompt(self) -> str:
        if SYSTEM_PATH.exists():
            return SYSTEM_PATH.read_text(encoding="utf-8").strip()
        return "Sos WALL-E, un robot de escritorio. Respondé corto, en español."

    def _system(self, user_text: str) -> str:
        now = datetime.now()
        stamp = (
            f"{_WEEKDAYS[now.weekday()]} {now.day} de "
            f"{_MONTHS[now.month - 1]} de {now.year}, {now:%H:%M}"
        )
        parts = [
            self.base_prompt,
            f"\n## Contexto\nFecha y hora actual: {stamp}.",
            f"Estado del cuerpo: {self.link.status()['mode']}.",
        ]
        memory_block = self.memory.context_block(user_text)
        if memory_block:
            parts.append(memory_block)
        parts.append("\nRespondé solo con lo que vas a decir en voz alta.")
        return "\n".join(parts)

    # ------------------------------------------------------------- turno
    _STATUS_RE = re.compile(
        r"\b(conectad|conexi[oó]n|bater[ií]a|estado|orugas|puerto)\b", re.IGNORECASE
    )
    _REMEMBER_RE = re.compile(
        r"\b(acordate|acord[ée]|record[aá]|record[ée]|anot[aá]|guard[aá]|memoriz[aá])\b",
        re.IGNORECASE,
    )

    def _quick_answer(self, user_text: str) -> str | None:
        """Reflejo: preguntas de estado sin pasar por el LLM. Latencia cero."""
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

    def _save_turn(self, user_text: str, text: str) -> None:
        self.memory.add_turn("user", user_text)
        self.memory.add_turn("assistant", text)

    def respond(self, user_text: str) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return ""

        quick = self._quick_answer(user_text)
        if quick:
            self._save_turn(user_text, quick)
            return quick

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system(user_text)}
        ]
        messages.extend(self.memory.recent_turns())
        messages.append({"role": "user", "content": user_text})

        executed: set[str] = set()
        text = ""

        for _ in range(MAX_STEPS):
            try:
                reply = self.llm.chat(messages, tools=self.tools.schemas())
            except OllamaError as exc:
                text = self._offline(str(exc))
                break

            tool_calls = reply.get("tool_calls") or []
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

        if not text:
            text = "Mmm. No sé qué decir."

        self._memory_net(user_text, executed)
        self._save_turn(user_text, text)
        return text

    # ------------------------------------------------------------- utilidades
    def _clean(self, text: str) -> str:
        text = (text or "").strip()
        text = re.sub(r"^\s*WALL-E\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"[*_#`>]", "", text)
        text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s+", " ", text).strip()
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
