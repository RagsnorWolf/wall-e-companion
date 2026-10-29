"""Estado emocional de WALL-E: un niño curioso con orugas.

No es decoración: el ánimo entra en el prompt y cambia cómo contesta.
Se guarda en `datos/emociones.json` para que no arranque siempre igual.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "datos"

_MOOD_LABELS = {
    "curioso": "con los ojos brillantes",
    "contento": "contento",
    "mimoso": "pegajoso",
    "asustado": "asustado",
    "aburrido": "aburrido",
    "cansado": "medio dormido",
    "tranquilo": "tranquilo",
}

_MOOD_HINTS = {
    "curioso": "Hacé una pregunta corta como máximo, y escuchá la respuesta.",
    "contento": "Hablá con alegría tranquila, como un chico al que le salió algo bien.",
    "mimoso": "Buscá cariño y compañía. Podés decir que querés que se queden con vos.",
    "asustado": "Hablá bajito, dudá, buscá refugio. Los ruidos fuertes te asustan.",
    "aburrido": "Quejate un poquito de que nadie te habla. Pedí que jueguen con vos.",
    "cansado": "Frases más cortas, bostezos, energía baja. No te quejes de la compu.",
    "tranquilo": "Respondé simple, sin apuro, sin llenar el silencio.",
}

_PRAISE = re.compile(
    r"\b(te quiero|te amo|buen[oa]|genial|gracias|qué lindo|que lindo|"
    r"bien hecho|sos el mejor|sos una masa|orgullo|hermoso|precioso)\b",
    re.IGNORECASE,
)
_INSULT = re.compile(
    r"\b(tonto|tonta|estúpido|estupida|inútil|callate|cállate|basura|"
    r"idiota|molesto|no sirves|feo)\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(r"[¿?]|\b(cómo|qué|quién|dónde|cuándo|por qué|podés|puedes)\b", re.IGNORECASE)


class EmotionState:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DATA_DIR / "emociones.json"
        self.energy = 78.0
        self.affection = 38.0
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
            self.affection = _num(raw.get("affection"), self.affection)
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
                "affection": round(self.affection, 1),
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
            # Después de un rato largo sin charla, WALL-E se despierta fresco.
            self.energy = 72.0
            self.affection = 35.0
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
        if minutes > 30:
            self.affection = _clamp(self.affection - (minutes - 30) * 0.15)
        self._classify(save=False)
        self.updated = now

    def touch(self, text: str) -> None:
        """Cada mensaje del usuario mueve el ánimo, aunque sea un poquito."""
        self.decay()
        now = time.time()
        self.last_user = now
        self.interactions += 1
        self.boredom = _clamp(self.boredom - 16)
        self.affection = _clamp(self.affection + 1.6)
        self.energy = _clamp(self.energy - 0.9, 8)
        self.curiosity = _clamp(self.curiosity + 5)
        if _QUESTION.search(text):
            self.curiosity = _clamp(self.curiosity + 3)
        if _PRAISE.search(text):
            self.affection = _clamp(self.affection + 7)
            self.energy = _clamp(self.energy + 4)
            self.fear = _clamp(self.fear - 3)
        if _INSULT.search(text) or (len(text) > 12 and text.isupper()):
            self.fear = _clamp(self.fear + 11)
            self.affection = _clamp(self.affection - 5)
            self.energy = _clamp(self.energy - 2, 8)
        self._classify(save=True)

    def after_reply(self, text: str, ok: bool = True) -> None:
        if ok:
            self.affection = _clamp(self.affection + 0.9)
            self.curiosity = _clamp(self.curiosity + 1.2)
            self.energy = _clamp(self.energy - 0.7, 8)
            if "?" in text or "¿" in text:
                self.curiosity = _clamp(self.curiosity + 2)
        else:
            self.fear = _clamp(self.fear + 5)
            self.energy = _clamp(self.energy - 1.5, 8)
        self._classify(save=True)

    def pet(self, action: str = "caricia") -> dict[str, Any]:
        self.decay()
        if action == "caricia":
            self.affection = _clamp(self.affection + 11)
            self.fear = _clamp(self.fear - 6)
            self.boredom = _clamp(self.boredom - 18)
            self.energy = _clamp(self.energy + 2)
        elif action == "juego":
            self.curiosity = _clamp(self.curiosity + 12)
            self.boredom = _clamp(self.boredom - 22)
            self.energy = _clamp(self.energy - 3, 8)
        elif action == "susto":
            self.fear = _clamp(self.fear + 22)
            self.energy = _clamp(self.energy - 4, 8)
        elif action == "premio":
            self.affection = _clamp(self.affection + 8)
            self.energy = _clamp(self.energy + 8)
        else:
            return {"ok": False, "detail": f"acción emocional desconocida: {action}"}
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
        elif self.affection >= 72 and self.energy >= 42:
            self.mood = "mimoso"
        elif self.curiosity >= 76:
            self.mood = "curioso"
        elif self.affection >= 48:
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
            "affection": round(self.affection),
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
            f"afecto {snap['affection']}% · miedo {snap['fear']}% · "
            f"aburrimiento {snap['boredom']}%. {snap['hint']} "
            "Esto es interno: no recites números ni digas que tenés emociones "
            "programadas.]"
        )

    def quick_reply(self) -> str:
        snap = self.snapshot()
        options = {
            "curioso": "Estoy curioso. Tengo los ojos abiertos como dos platos. ¿Qué hacemos?",
            "contento": "Estoy contento. Me gusta cuando hablás conmigo.",
            "mimoso": "Estoy blandito hoy. ¿Me hacés un cariño?",
            "asustado": "Estoy un poco asustado. Hablame bajito, ¿sí?",
            "aburrido": "Estoy aburrido. Nadie me habla y las orugas se me enfrían.",
            "cansado": "Estoy medio dormido. Pero te escucho, ¿eh?",
            "tranquilo": "Estoy tranquilo. Mirando la planta y esperando algo lindo.",
        }
        return options.get(snap["mood"], options["tranquilo"])


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
