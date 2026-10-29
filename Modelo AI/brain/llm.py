"""Cliente mínimo de Ollama. Sin dependencias externas (stdlib pura).

Funciona en Windows, Linux y Android/Termux.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_HOST = "http://127.0.0.1:11434"


class OllamaError(RuntimeError):
    """Error de conexión o de respuesta de Ollama."""


class Ollama:
    def __init__(
        self,
        model: str = "walle",
        host: str = DEFAULT_HOST,
        timeout: float = 120.0,
        num_ctx: int = 4096,
        temperature: float = 0.25,
        num_predict: int = 160,
        keep_alive: str = "30m",
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.last_metrics: dict[str, Any] = {}
        self.options = {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "num_predict": num_predict,
        }

    # ------------------------------------------------------------------ HTTP
    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.host}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OllamaError(
                f"No puedo hablar con Ollama en {self.host}. ¿Está corriendo?"
            ) from exc
        except TimeoutError as exc:
            raise OllamaError("Ollama tardó demasiado en responder") from exc

    # ------------------------------------------------------------------ API
    def health(self) -> bool:
        try:
            self._request("/api/tags")
            return True
        except OllamaError:
            return False

    def models(self) -> list[str]:
        data = self._request("/api/tags")
        return [m.get("name", "") for m in data.get("models", [])]

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Devuelve el mensaje del asistente: {role, content, tool_calls?}."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": self.options,
            "keep_alive": self.keep_alive,
        }
        if tools:
            payload["tools"] = tools
        data = self._request("/api/chat", payload)
        self.last_metrics = {
            "load_ms": round((data.get("load_duration") or 0) / 1e6),
            "prompt_tokens": data.get("prompt_eval_count"),
            "prompt_ms": round((data.get("prompt_eval_duration") or 0) / 1e6),
            "out_tokens": data.get("eval_count"),
            "out_ms": round((data.get("eval_duration") or 0) / 1e6),
            "total_ms": round((data.get("total_duration") or 0) / 1e6),
        }
        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaError(f"Respuesta inesperada de Ollama: {data}")
        return message
