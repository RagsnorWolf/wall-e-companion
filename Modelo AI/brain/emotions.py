"""Estado operativo de WALL-E: energía, curiosidad y humor de trabajo.

No es decoración: el ánimo entra en el prompt y modula el tono. No hay métricas
de afecto ni de cariño: WALL-E es un asistente competente y amable, no una
mascota. Se guarda en `datos/emociones.json` para no arrancar siempre igual.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "datos"

_MOOD_LABELS = {
    "curioso": "con los sensores despiertos",
    "contento": "de buen humor",
    "asustado": "en alerta",
    "aburrido": "sin tareas",
    "cansado": "con poca batería",
    "tranquilo": "estable",
    "atento": "concentrado",
    "pensando": "procesando",
}

_MOOD_HINTS = {
    "curioso": "Mostrá interés técnico: preguntá lo justo para entender la tarea.",
    "contento": "Tono cordial y eficiente. Una respuesta clara vale más que una floritura.",
    "asustado": "Hablá con calma y precisión. Evitá dramatizar.",
    "aburrido": "Proponé algo útil o preguntá en qué trabajar.",
    "cansado": "Sé breve y directo. Priorizá la información esencial.",
    "tranquilo": "Respondé simple, sin apuro y sin llenar el silencio.",
    "atento": "Escuchá el pedido completo y respondé a eso puntual.",
    "pensando": "Ordená la respuesta antes de hablar; no divagues.",
}

_POSITIVE = re.compile(
    r"\b(buen[oa]|genial|gracias|qué lindo|que lindo|bien hecho|"
    r"sos el mejor|orgullo|hermoso|precioso|excelente|perfecto)\b",
    re.IGNORECASE,
)
_INSULT = re.compile(
    r"\b(tonto|tonta|estúpido|estupida|inútil|callate|cállate|basura|"
    r"idiota|molesto|no sirves|feo)\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"[¿?]|\b(cómo|qué|quién|dónde|cuándo|por qué|podés|puedes)\b",
    re.IGNORECASE,
)

VALID_ACTIONS = ("saludo", "juego", "susto", "premio", "descanso")


class EmotionState:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DATA_DIR / "emociones.json"
        self.energy = 78.0
        self.curiosity = 72.0
        self.fear = 8.0
        self.boredom = 28.0
        self.mood = "curioso"
        self.updated = time.time()
        self.last_user = time.time()
        self.interactions = 0
        self._load()
        self.decay()
        self._classify(save=False)

    # ------------------------------------------------------------- persistencia
    def _load(self) -> None:
        try:
            if not self.path.exists():
                return
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            self.energy = _num(raw.get("energy"), self.energy)
            self.curiosity = _num(raw.get("curiosity"), self.curiosity)
            self.fear = _num(raw.get("fear"), self.fear)
            self.boredom = _num(raw.get("boredom"), self.boredom)
            self.updated = _num(raw.get("updated"), time.time())
            self.last_user = _num(raw.get("last_user"), self.updated)
            self.interactions = int(_num(raw.get("interactions"), 0))
        except Exception:
            pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "energy": round(self.energy, 1),
                "curiosity": round(self.curiosity, 1),
                "fear": round(self.fear, 1),
                "boredom": round(self.boredom, 1),
                "mood": self.mood,
                "updated": time.time(),
                "last_user": self.last_user,
                "interactions": self.interactions,
            }
            self.path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.updated = time.time()
        except Exception:
            pass

    # ------------------------------------------------------------- dinámica
    def decay(self) -> None:
        now = time.time()
        elapsed = max(0.0, now - self.updated)
        if elapsed < 20:
            return
        if elapsed > 3600:
            # Después de un rato largo sin uso, el estado vuelve a un punto sano.
            self.energy = 72.0
            self.curiosity = 68.0
            self.fear = 8.0
            self.boredom = 30.0
            self.last_user = now
            self.updated = now
            self._classify(save=True)
            return
        minutes = elapsed / 60.0
        self.boredom = _clamp(self.boredom + minutes * 4.5)
        self.energy = _clamp(self.energy - minutes * 1.4, 8)
        self.curiosity = _clamp(self.curiosity + minutes * 1.8)
        self.fear = _clamp(self.fear - minutes * 3.0)
        self._classify(save=False)
        self.updated = now

    def touch(self, text: str) -> None:
        """Cada mensaje del usuario mueve el ánimo, aunque sea un poquito."""
        self.decay()
        now = time.time()
        self.last_user = now
        self.interactions += 1
        self.boredom = _clamp(self.boredom - 16)
        self.energy = _clamp(self.energy - 0.9, 8)
        self.curiosity = _clamp(self.curiosity + 5)
        if _QUESTION.search(text):
            self.curiosity = _clamp(self.curiosity + 3)
        if _POSITIVE.search(text):
            self.energy = _clamp(self.energy + 4)
            self.curiosity = _clamp(self.curiosity + 2)
            self.fear = _clamp(self.fear - 3)
        if _INSULT.search(text) or (len(text) > 12 and text.isupper()):
            self.fear = _clamp(self.fear + 11)
            self.energy = _clamp(self.energy - 2, 8)
        self._classify(save=True)

    def after_reply(self, text: str, ok: bool = True) -> None:
        if ok:
            self.curiosity = _clamp(self.curiosity + 1.2)
            self.energy = _clamp(self.energy - 0.7, 8)
            if "?" in text or "¿" in text:
                self.curiosity = _clamp(self.curiosity + 2)
        else:
            self.fear = _clamp(self.fear + 5)
            self.energy = _clamp(self.energy - 1.5, 8)
        self._classify(save=True)

    def interact(self, action: str = "saludo") -> dict[str, Any]:
        """Acciones neutras de estado, sin connotación afectiva.

        saludo   · reinicia el foco de conversación
        juego    · sube curiosidad y baja aburrimiento
        susto    · sube alerta
        premio   · recarga energía
        descanso · recupera batería y baja curiosidad
        """
        self.decay()
        action = (action or "saludo").strip().lower()
        if action == "saludo":
            self.boredom = _clamp(self.boredom - 18)
            self.curiosity = _clamp(self.curiosity + 8)
            self.fear = _clamp(self.fear - 4)
            self.energy = _clamp(self.energy + 1)
        elif action == "juego":
            self.curiosity = _clamp(self.curiosity + 12)
            self.boredom = _clamp(self.boredom - 22)
            self.energy = _clamp(self.energy - 3, 8)
        elif action == "susto":
            self.fear = _clamp(self.fear + 22)
            self.energy = _clamp(self.energy - 4, 8)
        elif action == "premio":
            self.energy = _clamp(self.energy + 10)
            self.boredom = _clamp(self.boredom - 8)
        elif action == "descanso":
            self.energy = _clamp(self.energy + 14)
            self.curiosity = _clamp(self.curiosity - 6)
            self.fear = _clamp(self.fear - 6)
        else:
            return {
                "ok": False,
                "detail": f"acción desconocida: {action}; usá {', '.join(VALID_ACTIONS)}",
            }
        self._classify(save=True)
        return {"ok": True, "action": action, "emotion": self.snapshot()}

    # ------------------------------------------------------------- lectura
    def _classify(self, save: bool = False) -> None:
        if self.fear >= 55:
            self.mood = "asustado"
        elif self.energy <= 22:
            self.mood = "cansado"
        elif self.boredom >= 70:
            self.mood = "aburrido"
        elif self.curiosity >= 82:
            self.mood = "pensando"
        elif self.curiosity >= 60:
            self.mood = "curioso"
        elif self.energy >= 80:
            self.mood = "contento"
        else:
            self.mood = "tranquilo"
        if save:
            self.save()

    def snapshot(self) -> dict[str, Any]:
        self.decay()
        return {
            "mood": self.mood,
            "label": _MOOD_LABELS.get(self.mood, self.mood),
            "hint": _MOOD_HINTS.get(self.mood, ""),
            "energy": round(self.energy),
            "curiosity": round(self.curiosity),
            "fear": round(self.fear),
            "boredom": round(self.boredom),
            "interactions": self.interactions,
            "silent_seconds": int(max(0, time.time() - self.last_user)),
        }

    def system_block(self) -> str:
        snap = self.snapshot()
        return (
            f"[ánimo: {snap['mood']} · energía {snap['energy']}% · "
            f"curiosidad {snap['curiosity']}% · alerta {snap['fear']}% · "
            f"aburrimiento {snap['boredom']}%. {snap['hint']} "
            "Esto es interno: no recites números ni digas que tenés estados "
            "programados.]"
        )

    def quick_reply(self) -> str:
        snap = self.snapshot()
        options = {
            "curioso": "Tengo los sensores despiertos. ¿Qué querés resolver?",
            "contento": "Todo estable por acá. ¿En qué te doy una mano?",
            "atento": "Te escucho. Contame el problema completo.",
            "pensando": "Estoy ordenando la información. Un segundo.",
            "asustado": "Estoy en alerta. Decime con calma qué necesitás.",
            "aburrido": "Sin tareas pendientes. ¿Arrancamos algo?",
            "cansado": "Batería baja. Puedo ayudarte con algo breve.",
            "tranquilo": "Sistemas estables. ¿Qué hacemos?",
        }
        return options.get(snap["mood"], options["tranquilo"])


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
