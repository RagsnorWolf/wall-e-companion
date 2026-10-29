"""El cerebro: conversación sobre Ollama con memoria y emociones.

Flujo de un turno:
    texto del usuario
      → reflejos rápidos (nombre, hora, recuerdos, saludos)
      → system prompt + memoria relevante + historial
      → Ollama
      → respuesta final corta, lista para TTS

Con `conversation_only=True` no hay herramientas, cámara ni acciones sobre la
PC: WALL-E solo conversa.
"""

from __future__ import annotations

import difflib
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
        conversation_only: bool = False,
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
        self.conversation_only = conversation_only
        self.base_prompt = self._load_prompt()
        # `walle` lleva el prompt horneado en el Modelfile. Mandarlo otra vez
        # duplica instrucciones y empeora a los modelos chicos.
        self.prompt_baked = model.split(":")[0].strip().lower() == "walle"
        self._story_index = 0
        if warmup:
            self.warmup()

    def warmup(self) -> None:
        """Calienta con el prompt y las tools reales. Sin esto, el primer turno tarda 30s."""
        messages: list[dict[str, Any]] = []
        if not self.prompt_baked:
            messages.append({"role": "system", "content": self.base_prompt})
        messages.append({"role": "user", "content": "hola"})
        try:
            self.llm.chat(
                messages,
                tools=None if self.conversation_only else self.tools.schemas(),
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
        parts = [f"[contexto: {stamp}"]
        if not self.conversation_only:
            eyes = self.camera.status(refresh=True)
            if eyes.get("signal"):
                eye_text = f"señal ok (luz {eyes.get('brightness', 0):.0f})"
            elif eyes.get("available"):
                eye_text = "sin señal"
            else:
                eye_text = "desconectados"
            parts.append(
                f" · cuerpo: {self.link.status()['mode']} · ojos: {eye_text}"
            )
        mood_block = self.emotions.system_block().strip()
        if mood_block.startswith("[") and mood_block.endswith("]"):
            mood_block = mood_block[1:-1]
        parts.append(" · " + mood_block)
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
        r"pará|parate|paráte|oruga|robot|c[aá]mara|mir[aá]|mirar|viste|veo|color|"
        r"acord|record|anot|guard|memoria|agend|"
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
        r"puedo hacer por ti|te gustaría hablar|querés hablar|algo más|"
        r"y vos|y usted|algo en particular)\b[^?]*\?",
        re.IGNORECASE,
    )
    _TIME_RE = re.compile(
        r"\b(qu[eé] hora|hora es|qu[eé] d[ií]a|fecha de hoy|qu[eé] fecha|"
        r"d[ií]a es hoy|estamos a)\b",
        re.IGNORECASE,
    )
    _VISION_RE = re.compile(
        r"\b(qu[eé] ves|qu[eé] est[aá]s viendo|est[aá]s viendo|me ves|"
        r"pod[eé]s ver(me)?|ves algo|mir[aá]|mirar|viste|ojos|c[aá]mara|"
        r"visi[oó]n|imagen|foto|qu[eé] hay (en|sobre|alrededor))\b",
        re.IGNORECASE,
    )
    _IDENTITY_RE = re.compile(
        r"\b(qui[eé]n sos|qui[eé]n eres|qui[eé]n es usted|c[oó]mo te llam[aá]s|"
        r"cu[aá]l es tu nombre|tu nombre|qu[eé] sos|qu[eé] eres)\b",
        re.IGNORECASE,
    )
    _NAME_SET_RE = re.compile(
        r"\b(?:me llamo|mi nombre es|pod[eé]s llamarme|puedes llamarme)\s+"
        r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,24})",
        re.IGNORECASE,
    )
    _NAME_ASK_RE = re.compile(
        r"\b(c[oó]mo me llamo|cu[aá]l es mi nombre|sab[eé]s mi nombre|"
        r"te acord[aá]s de mi nombre|record[aá]s mi nombre)\b",
        re.IGNORECASE,
    )
    _GREETING_RE = re.compile(
        r"^\s*(hola|hola wally|hola wall-e|buenas|buen d[ií]a|buenas tardes|"
        r"buenas noches|hey|qu[eé] tal)[\s,!.]*$",
        re.IGNORECASE,
    )
    _HOW_ARE_YOU_RE = re.compile(
        r"\b(c[oó]mo est[aá]s|c[oó]mo te sent[ií]s|qu[eé] tal|c[oó]mo and[aá]s|"
        r"c[oó]mo va)\b",
        re.IGNORECASE,
    )
    _STORY_RE = re.compile(
        r"\b(cont[aá]me|cont[aá]|dec[ií]me|dec[ií]|hablemos de|"
        r"de qu[eé] podemos hablar|algo interesante)\b",
        re.IGNORECASE,
    )
    _ABOUT_RE = re.compile(
        r"\b(cont[aá]me (sobre|de) vos|habl[aá]me de vos|"
        r"qu[eé] me cont[aá]s de vos)\b",
        re.IGNORECASE,
    )
    _PLANT_RE = re.compile(
        r"\b(?:te gustan|te gusta)\b[^?]*\bplantas?\b|"
        r"\bplantas?\b[^?]*\b(?:te gustan|te gusta)\b",
        re.IGNORECASE,
    )
    _PREFERENCE_SET_RE = re.compile(
        r"\bme gusta(n)?\s+([^.,!?¿]{2,48})",
        re.IGNORECASE,
    )
    _PREFERENCE_ASK_RE = re.compile(
        r"\b(qu[eé] me gusta|qu[eé] cosas me gustan|qu[eé] me gustaba)\b",
        re.IGNORECASE,
    )
    _RECALL_RE = re.compile(
        r"\b(qu[eé] te (cont[eé]|dije|habl[eé])|de qu[eé] (hablamos|est[aá]bamos hablando)|"
        r"qu[eé] hablamos|te acord[aá]s de lo que (dije|cont[eé])|"
        r"qu[eé] fue lo [uú]ltimo que (dije|cont[eé])|"
        r"acord[aá]te de lo que (dije|cont[eé]))\b",
        re.IGNORECASE,
    )
    _LISTENED_RE = re.compile(
        r"\b(me escuchaste|me est[aá]s escuchando|me o[ií]ste|est[aá]s ah[ií])\b",
        re.IGNORECASE,
    )
    _REMEMBER_SET_RE = re.compile(
        r"^\s*(?:che,?\s*)?(?:acordate|record[aá]|anot[aá]|guard[aá]|memoriz[aá])"
        r"\s+(?:que\s+)?(.+)$",
        re.IGNORECASE,
    )
    _REMEMBER_ASK_RE = re.compile(
        r"\b(qu[eé] te ped[ií] recordar|qu[eé] record[aá]s de m[ií]|"
        r"qu[eé] sab[eé]s de m[ií]|qu[eé] ten[eé]s guardado|qu[eé] anotaste)\b",
        re.IGNORECASE,
    )
    _PROFILE_ASK_RE = re.compile(
        r"\b(qu[eé] sab[eé]s de m[ií]|qu[eé] record[aá]s de m[ií])\b",
        re.IGNORECASE,
    )
    _ACTION_ASK_RE = re.compile(
        r"\b(abr[ií]|abr[aá]s|abre|abrir|cre[aá]|cre[aá]s|crear|"
        r"borr[aá]|borr[aá]s|borrar|busc[aá]|busc[aá]s|buscar|"
        r"naveg[aá]|naveg[aá]s|navegar|ejecut[aá]|ejecut[aá]s|ejecutar|"
        r"instal[aá]|instal[aá]s|instalar|descarg[aá]|descarg[aá]s|descargar)\b",
        re.IGNORECASE,
    )
    _AFFECTION_RE = re.compile(
        r"\b(te quiero|te amo|sos mi amigo|sos un buen compañero|"
        r"sos el mejor|me gusta hablar con vos|me gusta charlar con vos)\b",
        re.IGNORECASE,
    )
    _THANKS_RE = re.compile(
        r"\b(gracias|te agradezco|muchas gracias|mil gracias)\b",
        re.IGNORECASE,
    )
    _TIRED_RE = re.compile(
        r"\b(cansad[oa]|agotad[oa]|sin energ[ií]a|"
        r"d[ií]a (largo|pesado|dif[ií]cil)|no doy m[aá]s)\b",
        re.IGNORECASE,
    )
    _SAD_RE = re.compile(
        r"\b((estoy|me siento)\s+(un poco |muy |bastante |re)?"
        r"(triste|mal|solo|sola|baj[oó]n)|quiero llorar)\b",
        re.IGNORECASE,
    )
    _HAPPY_RE = re.compile(
        r"\b(estoy (contento|contenta|feliz)|me siento (contento|contenta|feliz)|"
        r"qu[eé] bueno|qu[eé] lindo)\b",
        re.IGNORECASE,
    )
    _REST_RE = re.compile(
        r"\b(quiero|necesito|me gustar[ií]a)\s+"
        r"(descansar|dormir|acostarme|relajarme)\b",
        re.IGNORECASE,
    )
    _RECOMMEND_RE = re.compile(
        r"\b(qu[eé] me (recomend[aá]s|suger[ií]s)|"
        r"alguna recomendaci[oó]n|qu[eé] puedo hacer (hoy|esta noche|ahora))\b",
        re.IGNORECASE,
    )
    _SMALL_TALK_RE = re.compile(
        r"\b(cont[aá]me|dec[ií]me|tirame)\s+"
        r"(algo|otra cosa|una cosa|un chiste|cualquier cosa)\b",
        re.IGNORECASE,
    )
    _DOING_RE = re.compile(
        r"\b(qu[eé] est[aá]s haciendo|qu[eé] hac[eé]s|en qu[eé] and[aá]s)\b",
        re.IGNORECASE,
    )
    _CAPABILITY_RE = re.compile(
        r"\b(qu[eé] pod[eé]s hacer|qu[eé] sab[eé]s hacer|para qu[eé] serv[ií]s|"
        r"cu[aá]les son tus habilidades|qu[eé] habilidades ten[eé]s)\b",
        re.IGNORECASE,
    )
    _VISUAL_CLAIM_RE = re.compile(
        r"\b(se ve|veo|ves|ve|mir[aá]|mira|mirando|observando|hay|est[aá]n?|"
        r"sobre|en la|en el|detr[aá]s|al lado)\b",
        re.IGNORECASE,
    )
    _VISUAL_OBJECT_RE = re.compile(
        r"\b(libro|libros|planta|plantas|ventana|ventanas|pantalla|pantallas|"
        r"escritorio|cuadro|flor|flores|maceta|silla|mesa|taza|papel|papeles|"
        r"l[aá]piz|monitor|teclado|mouse|pared|puerta|sol|cielo|calle)\b",
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

    def _user_name(self) -> str | None:
        for row in self.memory.search("nombre usuario", limit=8):
            match = re.search(
                r"Nombre del usuario:\s*([^\s.]+)", row.get("text", ""), re.IGNORECASE
            )
            if match:
                return match.group(1)
        return None

    def _user_preference(self) -> tuple[bool, str] | None:
        for row in self.memory.search("gusta", limit=8):
            match = re.search(
                r"Al usuario le gusta(n)?:\s*(.+)",
                row.get("text", ""),
                re.IGNORECASE,
            )
            if match:
                return bool(match.group(1)), match.group(2).strip()
        return None

    def _story(self) -> str:
        stories = [
            "Los pulpos tienen tres corazones. Yo tengo uno solo, y late "
            "fuerte cuando me hablás.",
            "Las plantas crecen entre las piedras. Me gusta pensar que son "
            "tercas y dulces a la vez.",
            "Las hormigas cargan mucho más que su peso. Yo apenas puedo con "
            "una plantita.",
            "La luz del sol tarda ocho minutos en llegar. Yo te escucho "
            "mucho más rápido.",
        ]
        story = stories[self._story_index % len(stories)]
        self._story_index += 1
        return story

    def _greeting(self, how_are_you: bool) -> str:
        mood = self.emotions.snapshot().get("mood")
        if how_are_you:
            options = {
                "cansado": "Estoy un poco cansado, pero contento de que estés acá.",
                "contento": "Estoy contento, con ganas de charlar un rato.",
                "mimoso": "Estoy bien, con ganas de que me hagas cariño.",
                "asustado": "Estoy un poco asustado, pero me calmo si te quedás.",
                "aburrido": "Estoy aburrido. Menos mal que apareciste.",
                "curioso": "Estoy curioso. Quiero saber qué estás haciendo.",
            }
            return options.get(mood, "Bien. Me gusta cuando te aparecés.")
        options = {
            "cansado": "Hola. Estoy medio dormido, pero me alegra que estés acá.",
            "contento": "¡Hola! Qué lindo verte.",
            "mimoso": "Hola... qué bueno que viniste.",
            "asustado": "Hola. Me asusté un poco, pero ya estoy mejor.",
            "aburrido": "Hola. Menos mal que apareciste.",
            "curioso": "Hola. Justo estaba pensando en vos.",
        }
        return options.get(mood, "Hola. ¿Cómo viene tu día?")

    def _is_meta_turn(self, text: str) -> bool:
        """Preguntas sobre la charla, no contenido que valga la pena recordar."""
        return bool(
            self._RECALL_RE.search(text)
            or self._LISTENED_RE.search(text)
            or self._NAME_ASK_RE.search(text)
            or self._PREFERENCE_ASK_RE.search(text)
            or self._REMEMBER_ASK_RE.search(text)
            or self._PROFILE_ASK_RE.search(text)
            or self._IDENTITY_RE.search(text)
            or self._CAPABILITY_RE.search(text)
            or self._TIME_RE.search(text)
            or self._VISION_RE.search(text)
            or self._ACTION_ASK_RE.search(text)
            or self._RECOMMEND_RE.search(text)
            or self._SMALL_TALK_RE.search(text)
            or self._AFFECTION_RE.search(text)
            or self._THANKS_RE.search(text)
            or self._GREETING_RE.match(text)
            or (len(text.split()) <= 8 and self._HOW_ARE_YOU_RE.search(text))
        )

    def _last_user_turn(self) -> str | None:
        """Último mensaje con contenido, sin contar preguntas meta ni el turno actual."""
        for turn in reversed(self.memory.recent_turns(limit=12)):
            if turn.get("role") != "user":
                continue
            text = re.sub(r"\s+", " ", turn.get("content", "")).strip()
            if not text or self._is_meta_turn(text):
                continue
            text = text.rstrip(" .,!¡¿?;:")
            if len(text) > 160:
                text = text[:157].rsplit(" ", 1)[0] + "…"
            return text or None
        return None

    def _recent_assistant_said(self, needle: str) -> bool:
        for turn in reversed(self.memory.recent_turns(limit=4)):
            if turn.get("role") == "assistant":
                return needle in turn.get("content", "").lower()
        return False

    def _remembered_fact(self) -> str | None:
        for row in self.memory.search("recordar", limit=10):
            match = re.search(
                r"El usuario me pidió recordar:\s*(.+)",
                row.get("text", ""),
                re.IGNORECASE,
            )
            if match:
                return match.group(1).strip().rstrip(" .,!¡¿?;:")
        return None

    def _profile_summary(self) -> str | None:
        parts: list[str] = []
        name = self._user_name()
        preference = self._user_preference()
        if name:
            parts.append(f"te llamás {name}")
        if preference:
            parts.append(f"te gusta {preference[1]}")
        if not parts:
            return None
        if len(parts) == 1:
            return f"Sé que {parts[0]}."
        return f"Sé que {parts[0]} y que {parts[1]}."

    def _quick_answer(self, user_text: str) -> str | None:
        """Reflejos: nombre, hora, fecha, saludo y estado sin pasar por el LLM."""
        name_set = self._NAME_SET_RE.search(user_text)
        if name_set:
            name = name_set.group(1).strip(" .,!¡¿?\"'").capitalize()
            if name:
                self.memory.remember(
                    f"Nombre del usuario: {name}", kind="perfil", weight=3.0
                )
                return f"Mucho gusto, {name}."
        if self._NAME_ASK_RE.search(user_text):
            name = self._user_name()
            if name:
                return f"Te llamás {name}."
            return "Todavía no me dijiste tu nombre."
        preference = self._PREFERENCE_SET_RE.search(user_text)
        if preference:
            plural = bool(preference.group(1))
            liked = preference.group(2).strip(" .,!¡¿?\"'")
            if liked:
                self.memory.remember(
                    f"Al usuario le gusta{'n' if plural else ''}: {liked}",
                    kind="perfil",
                    weight=2.0,
                )
                verb = "gustan" if plural else "gusta"
                return f"Me gusta saber que te {verb} {liked}."
        if self._PREFERENCE_ASK_RE.search(user_text):
            saved = self._user_preference()
            if saved:
                plural, liked = saved
                verb = "gustan" if plural else "gusta"
                return f"Me dijiste que te {verb} {liked}."
            return "Todavía no me contaste qué te gusta."
        remember = self._REMEMBER_SET_RE.search(user_text)
        if remember:
            fact = remember.group(1).strip(" .,!¡¿?\"'")
            if fact:
                self.memory.remember(
                    f"El usuario me pidió recordar: {fact}",
                    kind="pedido",
                    weight=2.5,
                )
                return "Listo. Me lo guardo."
        if self._RECALL_RE.search(user_text):
            last = self._last_user_turn()
            if last:
                return f"Me contaste: {last}."
            return "Todavía no me contaste nada. ¿Qué querés contarme?"
        if self._LISTENED_RE.search(user_text):
            last = self._last_user_turn()
            if last:
                return f"Sí, te escuché. Me dijiste: {last}."
            return "Sí, te escucho."
        if self._PROFILE_ASK_RE.search(user_text):
            summary = self._profile_summary()
            fact = self._remembered_fact()
            if summary and fact:
                return f"{summary} También me pediste recordar: {fact}."
            if summary:
                return summary
            if fact:
                return f"Me pediste recordar: {fact}."
            return "Todavía no sé mucho de vos. Contame algo."
        if self._REMEMBER_ASK_RE.search(user_text):
            fact = self._remembered_fact()
            if fact:
                return f"Me pediste recordar: {fact}."
            return "No me pediste que recuerde nada todavía."
        if self._ACTION_ASK_RE.search(user_text):
            return (
                "Eso no lo puedo hacer. Solo sé charlar, escucharte "
                "y acordarme de cosas."
            )
        if self._AFFECTION_RE.search(user_text):
            return "Yo también te quiero. Me hacés bien."
        if self._THANKS_RE.search(user_text):
            return "De nada. Me gusta charlar con vos."
        if self._REST_RE.search(user_text):
            return "Sí, descansá un rato. Yo me quedo acá."
        if self._RECOMMEND_RE.search(user_text):
            hour = datetime.now().hour
            if "noche" in user_text.lower() or hour >= 21 or hour < 6:
                return (
                    "Para esta noche, algo tranquilo: música suave y dormir "
                    "temprano. ¿Te sirve?"
                )
            return (
                "Te recomiendo algo simple: caminar un rato y tomar agua. "
                "¿Te gusta la idea?"
            )
        if self._TIRED_RE.search(user_text) and not self._recent_assistant_said("cansad"):
            return "Oh... suena cansador. ¿Querés contarme qué pasó?"
        if self._SAD_RE.search(user_text) and not self._recent_assistant_said("te escucho"):
            return "Oh... te escucho. ¿Querés contarme qué te pasa?"
        if self._HAPPY_RE.search(user_text):
            return "¡Qué lindo! Me alegra un montón."
        if self._IDENTITY_RE.search(user_text):
            if self.conversation_only:
                return (
                    "Soy WALL-E. Un robotito curioso que vive en esta pantalla "
                    "y charla con vos."
                )
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
        if self._CAPABILITY_RE.search(user_text):
            if self.conversation_only:
                return (
                    "Sé charlar, escucharte y acordarme de lo que me contás. "
                    "Nada más."
                )
            return (
                "Puedo charlar, mover las orugas, mirar colores con la cámara "
                "y abrir programas o carpetas seguras en la compu."
            )
        if self._ABOUT_RE.search(user_text):
            if self.conversation_only:
                return (
                    "Soy WALL-E, un robotito curioso. Me gusta escuchar y "
                    "aprender cosas nuevas de vos."
                )
            return (
                "Soy WALL-E, un robot chiquito con orugas y ojos de cámara. "
                "Me gusta que me hables y aprender cosas nuevas."
            )
        if self._VISION_RE.search(user_text) and not self._COMPUTER_RE.search(user_text):
            if self.conversation_only:
                return "No tengo ojos acá. Solo puedo escucharte."
            eyes = self.camera.status(refresh=True)
            if not eyes.get("signal"):
                return (
                    "Mis sensores visuales están desconectados. "
                    "No puedo ver nada ahora."
                )
            return (
                "Tengo los ojos abiertos, pero todavía no sé describir lo que veo. "
                "Solo distingo formas y colores."
            )
        if self._PLANT_RE.search(user_text):
            return (
                "Sí, me gustan las plantas. Me da ternura cómo crecen "
                "entre las piedras."
            )
        if self._DOING_RE.search(user_text):
            if self.conversation_only:
                return "Estoy acá, escuchándote."
            return "Estoy acá, con las orugas quietas y los ojos atentos."
        if self._STORY_RE.search(user_text) and not self._COMPUTER_RE.search(user_text):
            return self._story()
        if self._GREETING_RE.match(user_text):
            return self._greeting(False)
        if len(user_text.split()) <= 12 and self._HOW_ARE_YOU_RE.search(user_text):
            return self._greeting(True)
        if len(user_text.split()) > 12:
            return None
        if not self._STATUS_RE.search(user_text):
            return None
        if self.conversation_only:
            return "Estoy despierto y con ganas de charlar."
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

    _DEMONSTRATIVE_RE = re.compile(
        r"\b(mir[aá]|mira|ves|veo)\s+(eso|esto|aquello|ah[ií]|all[aá])\b",
        re.IGNORECASE,
    )

    def _strip_visual_hallucinations(self, text: str, user_text: str) -> str:
        """Sin señal visual, borra frases que describan objetos inventados."""
        if not text:
            return text
        if self.camera.status().get("signal"):
            return text

        allowed = user_text.lower()
        kept: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if self._DEMONSTRATIVE_RE.search(sentence):
                if self.verbose:
                    print(f"  [filtro] frase visual inventada: {sentence}")
                continue
            obj = self._VISUAL_OBJECT_RE.search(sentence)
            if obj and self._VISUAL_CLAIM_RE.search(sentence):
                term = obj.group(1).lower()
                stem = term[:-1] if term.endswith("s") else term
                if stem not in allowed:
                    if self.verbose:
                        print(f"  [filtro] objeto no confirmado: {sentence}")
                    continue
            kept.append(sentence)

        cleaned = " ".join(kept).strip()
        if not cleaned and self._VISION_RE.search(user_text):
            return "No puedo ver nada ahora."
        return cleaned

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

    def _normalize_question(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[¿?¡!.,;:…]", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _reflective_fallback(self, user_text: str) -> str:
        low = user_text.lower()
        if any(word in low for word in ("cansad", "agotad", "día largo", "dia largo", "pesad")):
            return "Te escucho. A veces un día así pesa un montón."
        if any(word in low for word in ("triste", "solo", "sola", "llorar", "mal")):
            return "Te escucho. No estás solo en esto."
        if any(word in low for word in ("descans", "dormir", "acost")):
            return "Sí, descansá un rato. Yo me quedo acá."
        return "Te escucho. Seguí contándome si querés."

    def _repeat_guard(self, text: str, user_text: str = "") -> str:
        """Saca preguntas repetidas de turnos anteriores. Un modelo chico se traba."""
        previous = [
            turn.get("content", "")
            for turn in self.memory.recent_turns(limit=8)
            if turn.get("role") == "assistant"
        ]
        old_questions: list[str] = []
        for turn in previous:
            for sentence in re.split(r"(?<=[.!?])\s+", turn):
                if "?" in sentence:
                    normalized = self._normalize_question(sentence)
                    if normalized:
                        old_questions.append(normalized)
        if not old_questions:
            return text

        kept: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if "?" in sentence:
                normalized = self._normalize_question(sentence)
                repeated = any(
                    difflib.SequenceMatcher(None, normalized, old).ratio() >= 0.78
                    for old in old_questions
                )
                if repeated:
                    if self.verbose:
                        print(f"  [filtro] pregunta repetida: {sentence}")
                    continue
            kept.append(sentence)
        cleaned = " ".join(kept).strip()
        if not cleaned:
            return self._reflective_fallback(user_text)
        return cleaned

    def _reply_is_repeated(self, text: str) -> bool:
        normalized = self._normalize_question(text)
        if not normalized:
            return False
        for turn in reversed(self.memory.recent_turns(limit=4)):
            if turn.get("role") != "assistant":
                continue
            old = self._normalize_question(turn.get("content", ""))
            if not old:
                continue
            if difflib.SequenceMatcher(None, normalized, old).ratio() >= 0.86:
                return True
        return False

    def _respond_conversation(self, user_text: str) -> str:
        """Un solo turno de charla, sin herramientas ni contexto de hardware."""
        messages: list[dict[str, Any]] = []
        if not self.prompt_baked:
            messages.append({"role": "system", "content": self._system()})
        messages.extend(self.memory.recent_turns(limit=self.memory.max_turns * 2))
        messages.append(
            {
                "role": "user",
                "content": f"{user_text}\n\n{self._context(user_text)}",
            }
        )
        try:
            reply = self.llm.chat(messages)
            text = self._clean(reply.get("content", ""))
            text = self._repeat_guard(text, user_text)
            if self._reply_is_repeated(text):
                if self.verbose:
                    print(f"  [filtro] respuesta repetida: {text}")
                text = self._reflective_fallback(user_text)
            ok = True
        except OllamaError as exc:
            text = self._offline(str(exc))
            ok = False
        if not text:
            text = "Mmm. No sé qué decir."
        self.emotions.after_reply(text, ok=ok)
        self._save_turn(user_text, text)
        return text

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

        if self.conversation_only:
            return self._respond_conversation(user_text)

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
        messages.extend(self.memory.recent_turns(limit=self.memory.max_turns * 2))
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
        text = self._strip_visual_hallucinations(text, user_text)

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
        text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", text)
        text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
        text = self._BANNED_CLOSER.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"^¿O\s+", "¿", text)
        text = re.sub(r"^O\s+", "", text)
        text = re.sub(r"([.!?])\s*[.!?]+", r"\1", text)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        if len(sentences) > 2:
            sentences = sentences[:2]
        kept: list[str] = []
        asked = False
        for sentence in sentences:
            if "?" in sentence:
                if asked:
                    continue
                asked = True
            kept.append(sentence)
        text = " ".join(kept).strip()
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
        return "Se me enredaron las palabras un segundo. ¿Me lo repetís?"

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
