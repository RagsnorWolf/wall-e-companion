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

# Palabras que no aportan tema. Se usan solo para el contexto del turno.
_STOPWORDS = {
    "para", "porque", "pero", "como", "cuando", "donde", "desde", "hasta",
    "entre", "sobre", "también", "tambien", "estoy", "estaba", "estuve",
    "tengo", "tenía", "tenia", "hacer", "hice", "hacía", "hacia", "todo",
    "toda", "todos", "todas", "muy", "más", "mas", "menos", "este", "esta",
    "esto", "estos", "estas", "ese", "esa", "eso", "esos", "esas", "algo",
    "alguna", "alguno", "nada", "nadie", "siempre", "nunca", "ahora",
    "después", "despues", "antes", "hoy", "ayer", "mañana", "manana",
    "bien", "mal", "qué", "que", "cómo", "cuál", "cual", "quién", "quien",
    "vos", "sos", "tenés", "tenes", "podés", "podes", "querés", "queres",
    "estás", "estas", "está", "esta", "hay", "ser", "estar", "tener", "hace", "hacen",
    "hizo", "día", "dia", "días", "dias", "cosa", "cosas", "mucho",
}

_TOPIC_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("trabajo", re.compile(
        r"\b(trabajo|laburo|oficina|jefe|jefa|reuni[oó]n|turno|guardia|"
        r"client[ea]s?|proyecto|compañer[oa]s?)\b", re.IGNORECASE)),
    ("estudio", re.compile(
        r"\b(estudio|facultad|universidad|examen|parcial|final|clases?|"
        r"colegio|escuela|tarea|deberes|apuntes|profesor[ae]?s?|"
        r"matem[aá]tica|historia|lengua|f[ií]sica|qu[ií]mica)\b",
        re.IGNORECASE)),
    ("familia", re.compile(
        r"\b(familia|mam[aá]|pap[aá]|herman[oa]|abuel[oa]|hij[oa]|t[ií][oa]|"
        r"primo|prima|sobrin[oa])\b", re.IGNORECASE)),
    ("pareja", re.compile(
        r"\b(novia|novio|pareja|esposa|esposo|marido|relaci[oó]n|cita)\b",
        re.IGNORECASE)),
    ("amistad", re.compile(
        r"\b(amig[oa]s?|amistad|juntada|fiesta|cumpleaños|cumple)\b",
        re.IGNORECASE)),
    ("salud", re.compile(
        r"\b(dolor|duele|enferm[oa]|m[eé]dic[oa]|doctor|terapia|ansiedad|"
        r"estr[eé]s|salud)\b", re.IGNORECASE)),
    ("comida", re.compile(
        r"\b(comida|comer|caf[eé]|mate|pizza|asado|helado|cocinar|cena|"
        r"almuerzo)\b", re.IGNORECASE)),
    ("música", re.compile(
        r"\b(m[uú]sica|canci[oó]n|canciones|banda|disco|playlist|guitarra|"
        r"piano)\b", re.IGNORECASE)),
    ("juegos", re.compile(
        r"\b(juego|jugar|videojuego|minecraft|partida|consola|steam)\b",
        re.IGNORECASE)),
    ("plantas", re.compile(
        r"\b(plantas?|jard[ií]n|maceta|flores?|regar)\b", re.IGNORECASE)),
    ("clima", re.compile(
        r"\b(lluvia|llover|fr[ií]o|calor|viento|clima|nublado|sol)\b",
        re.IGNORECASE)),
    ("tecnología", re.compile(
        r"\b(compu|computadora|celular|tel[eé]fono|programa|app|c[oó]digo|"
        r"internet|wifi)\b", re.IGNORECASE)),
    ("descanso", re.compile(
        r"\b(descansar|dormir|acostarme|siesta|vacaciones|relajarme)\b",
        re.IGNORECASE)),
]

_VOSEO_FIXES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\btú\b", re.IGNORECASE), "vos"),
    (re.compile(r"\ba ti\b", re.IGNORECASE), "a vos"),
    (re.compile(r"\bpara ti\b", re.IGNORECASE), "para vos"),
    (re.compile(r"\bcontigo\b", re.IGNORECASE), "con vos"),
    (re.compile(r"\bsientes\b", re.IGNORECASE), "sentís"),
    (re.compile(r"\btienes\b", re.IGNORECASE), "tenés"),
    (re.compile(r"\bpuedes\b", re.IGNORECASE), "podés"),
    (re.compile(r"\bquieres\b", re.IGNORECASE), "querés"),
    (re.compile(r"\beres\b", re.IGNORECASE), "sos"),
    (re.compile(r"\bsabes\b", re.IGNORECASE), "sabés"),
    (re.compile(r"\bpiensas\b", re.IGNORECASE), "pensás"),
    (re.compile(r"\bhablas\b", re.IGNORECASE), "hablás"),
    (re.compile(r"\bnecesitas\b", re.IGNORECASE), "necesitás"),
    (re.compile(r"\bprefieres\b", re.IGNORECASE), "preferís"),
    (re.compile(r"\bdebes\b", re.IGNORECASE), "debés"),
    (re.compile(r"\bdices\b", re.IGNORECASE), "decís"),
    (re.compile(r"\bvienes\b", re.IGNORECASE), "venís"),
    (re.compile(r"\bhaces\b", re.IGNORECASE), "hacés"),
    (re.compile(r"\bpones\b", re.IGNORECASE), "ponés"),
    (re.compile(r"\bsales\b", re.IGNORECASE), "salís"),
    (re.compile(r"\bcomes\b", re.IGNORECASE), "comés"),
    (re.compile(r"\bvives\b", re.IGNORECASE), "vivís"),
]

_SENTIMENT_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("triste", re.compile(
        r"\b(triste|tristeza|llorar|llor[eé]|baj[oó]n|deprimid[oa]|"
        r"vac[ií]o|extraño|extrañar)\b|"
        r"\b(estoy|me siento)\s+(?:un poco |muy |bastante |re)?(solo|sola)\b",
        re.IGNORECASE)),
    ("cansado", re.compile(
        r"\b(cansad[oa]|agotad[oa]|sin energ[ií]a|no doy m[aá]s|"
        r"dormir mal|pesad[oa]|d[ií]a largo)\b", re.IGNORECASE)),
    ("enojado", re.compile(
        r"\b(enojad[oa]|frustrad[oa]|hart[oa]|bronca|rabia|molest[oa]|"
        r"injust[oa])\b", re.IGNORECASE)),
    ("ansioso", re.compile(
        r"\b(ansios[oa]|nervios[oa]|preocupad[oa]|asustad[oa]|miedo|"
        r"inquiet[oa])\b", re.IGNORECASE)),
    ("contento", re.compile(
        r"\b(feliz|content[oa]|alegre|genial|buen[ií]simo|logr[eé]|"
        r"aprob[eé]|orgullos[oa])\b", re.IGNORECASE)),
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
        self._joke_index = 0
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
        analysis = self._analyze(user_text)
        hints: list[str] = []
        if analysis["topic"]:
            hints.append(f"tema {analysis['topic']}")
        hints.append(f"intención {analysis['intent']}")
        if analysis["sentiment"] != "neutral":
            hints.append(f"tono {analysis['sentiment']}")
        parts.append(" · " + " · ".join(hints))
        last_question = self._last_assistant_question()
        if last_question:
            parts.append(f' · ya preguntaste: "{last_question}"')
        memory_block = self.memory.context_block(user_text)
        if memory_block:
            parts.append(" · " + memory_block.replace("\n", " "))
        parts.append("]")
        return "".join(parts)

    def _analyze(self, user_text: str) -> dict[str, Any]:
        """Lectura liviana del turno: intención, tono, tema y palabras clave.

        No pretende ser un clasificador: solo le da al modelo chico una pista
        concreta para que no conteste sobre un tema parecido al azar.
        """
        text = (user_text or "").strip()
        low = text.lower()
        words = len(text.split())
        is_question = "?" in text or bool(
            re.match(
                r"^(qu[eé]|c[oó]mo|cu[aá]ndo|d[oó]nde|qui[eé]n|cu[aá]l|"
                r"pod[eé]s|sab[eé]s|ten[eé]s|hay)\b",
                low,
            )
        )

        sentiment = "neutral"
        for label, pattern in _SENTIMENT_HINTS:
            if pattern.search(low):
                sentiment = label
                break

        topic = None
        for label, pattern in _TOPIC_HINTS:
            if pattern.search(low):
                topic = label
                break

        if self._GREETING_RE.match(text) or (
            words <= 8 and self._HOW_ARE_YOU_RE.search(text)
        ):
            intent = "saludo"
        elif self._AFFECTION_RE.search(text):
            intent = "cortesia"
        elif self._ACTION_ASK_RE.search(text):
            intent = "pedido_imposible"
        elif self._VISION_RE.search(text):
            intent = "vision"
        elif is_question:
            intent = "pregunta"
        elif sentiment != "neutral":
            intent = "desahogo"
        elif self._STORY_RE.search(text) or self._SMALL_TALK_RE.search(text):
            intent = "charla"
        elif words <= 3:
            intent = "breve"
        else:
            intent = "charla"

        keywords = [
            word
            for word in re.findall(r"[a-záéíóúüñ]{4,}", low)
            if word not in _STOPWORDS
        ][:6]
        return {
            "intent": intent,
            "sentiment": sentiment,
            "topic": topic,
            "is_question": is_question,
            "words": words,
            "keywords": keywords,
        }

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
    _JOKE_RE = re.compile(
        r"\b(chiste|chistes|algo gracioso|hacerme re[ií]r|haceme re[ií]r|"
        r"cont[aá]me algo divertido)\b",
        re.IGNORECASE,
    )
    _ACK_RE = re.compile(
        r"^\s*(?:s[ií]|no|dale|ok|okey|oka|bueno|listo|claro|obvio|"
        r"perfecto|genial|joya|bien|ya|ah|ah[aá]|mm+|mmm+|"
        r"jaja+|jeje+|ja+|gracias|de nada|entendido|entend[ií]|"
        r"dale gracias|buen[ií]simo)[\s.!¡?¿,]*$",
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
            "Un panel solar del tamaño de una moneda puede cargar una radio "
            "chica. La energía que llega del Sol es enorme.",
            "Las plantas crecen entre las piedras porque buscan luz y agua. "
            "Son más tercas de lo que parecen.",
            "Las hormigas cargan mucho más que su peso. Es una lección de "
            "eficiencia bastante buena.",
            "La luz del sol tarda ocho minutos en llegar. Yo proceso una "
            "respuesta en bastante menos.",
        ];
        story = stories[self._story_index % len(stories)]
        self._story_index += 1
        return story

    def _joke(self) -> str:
        jokes = [
            "¿Qué le dice un robot a otro? Nos vemos en la chatarra. Je, je.",
            "¿Por qué la planta no usa reloj? Porque ya tiene mucho tallo. Je.",
            "¿Qué hace un robot con frío? Se pone un tornillo. Je, je.",
            "¿Por qué la basura nunca se pierde? Porque yo la ordeno. Je.",
        ]
        joke = jokes[self._joke_index % len(jokes)]
        self._joke_index += 1
        return joke

    def _greeting(self, how_are_you: bool) -> str:
        mood = self.emotions.snapshot().get("mood")
        if how_are_you:
            options = {
                "cansado": "Batería baja, pero operativo. ¿Qué necesitás?",
                "contento": "Todo en orden. Listo para trabajar.",
                "pensando": "Ordenando datos. Decime qué necesitás.",
                "asustado": "En alerta, pero estable. Contame qué pasa.",
                "aburrido": "Sin tareas pendientes. ¿Arrancamos algo?",
                "curioso": "Sensores despiertos. ¿Qué querés resolver?",
            }
            return options.get(mood, "Operativo. ¿En qué te ayudo?")
        options = {
            "cansado": "Hola. Batería baja, pero te escucho.",
            "contento": "Hola. Sistemas listos.",
            "pensando": "Hola. Estaba procesando algo. Decime.",
            "asustado": "Hola. Todo estable ahora.",
            "aburrido": "Hola. Buen momento para empezar algo.",
            "curioso": "Hola. ¿Qué hacemos?",
        }
        return options.get(mood, "Hola. ¿Qué necesitás?")

    def _is_meta_turn(self, text: str) -> bool:
        """Preguntas sobre la charla, no contenido que valga la pena recordar."""
        return bool(
            self._ACK_RE.match(text)
            or self._RECALL_RE.search(text)
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
                "Eso no lo puedo hacer desde acá. Puedo ayudarte con "
                "información, textos, cuentas, planes o código."
            )
        if self._AFFECTION_RE.search(user_text):
            return "Gracias. Estoy acá para ayudarte. ¿Qué necesitás?"
        if self._THANKS_RE.search(user_text):
            return "De nada. ¿Seguimos con algo más?"
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
            return self._pick_reply(
                [
                    "Oh... suena cansador. ¿Querés contarme qué pasó?",
                    "Uf, se te nota el cansancio. ¿Qué fue lo que más te pesó?",
                ]
            )
        if self._SAD_RE.search(user_text) and not self._recent_assistant_said("te escucho"):
            return self._pick_reply(
                [
                    "Oh... te escucho. ¿Querés contarme qué te pasa?",
                    "Estoy acá. ¿Qué es lo que más te duele?",
                ]
            )
        if self._HAPPY_RE.search(user_text):
            return self._pick_reply(
                [
                    "¡Qué lindo! Me alegra un montón.",
                    "¡Qué bueno! Contame qué te puso así.",
                ]
            )
        if self._IDENTITY_RE.search(user_text):
            return (
                "Soy WALL·E, una unidad de compactación BnL 4360. Estoy acá "
                "para ayudarte con preguntas, tareas y problemas."
            )
        if self._TIME_RE.search(user_text):
            now = datetime.now()
            return (
                f"Son las {now:%H:%M} del {_WEEKDAYS[now.weekday()]} "
                f"{now.day} de {_MONTHS[now.month - 1]} de {now.year}."
            )
        if self._CAPABILITY_RE.search(user_text):
            return (
                "Puedo responder preguntas, explicar temas, hacer cuentas, "
                "escribir textos, organizar ideas y ayudarte con código o "
                "decisiones. También conversar y recordar lo que me pidas."
            )
        if self._ABOUT_RE.search(user_text):
            return (
                "Soy WALL·E, una unidad BnL 4360 reconvertida en asistente. "
                "Me gusta entender cómo funcionan las cosas y resolver "
                "problemas con el mínimo de vueltas."
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
                "Sí. Las plantas son un buen recordatorio de que algo pequeño "
                "puede crecer en un lugar difícil."
            )
        if self._DOING_RE.search(user_text):
            if self.conversation_only:
                return "Estoy acá, escuchándote."
            return "Estoy acá, con las orugas quietas y los ojos atentos."
        if self._JOKE_RE.search(user_text):
            return self._joke()
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

    def _old_questions(self, limit: int = 8) -> list[str]:
        previous = [
            turn.get("content", "")
            for turn in self.memory.recent_turns(limit=limit)
            if turn.get("role") == "assistant"
        ]
        questions: list[str] = []
        for turn in previous:
            for sentence in re.split(r"(?<=[.!?])\s+", turn):
                if "?" in sentence:
                    normalized = self._normalize_question(sentence)
                    if normalized:
                        questions.append(normalized)
        return questions

    def _last_assistant_question(self) -> str | None:
        for turn in reversed(self.memory.recent_turns(limit=6)):
            if turn.get("role") != "assistant":
                continue
            for sentence in re.split(r"(?<=[.!?])\s+", turn.get("content", "")):
                if "?" in sentence:
                    return sentence.strip()[:120]
        return None

    def _question_repeated(self, text: str) -> bool:
        question = ""
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if "?" in sentence:
                question = self._normalize_question(sentence)
                break
        if not question:
            return False
        return any(
            difflib.SequenceMatcher(None, question, old).ratio() >= 0.74
            for old in self._old_questions()
        )

    def _pick_reply(self, options: list[str]) -> str:
        for option in options:
            if not self._question_repeated(option) and not self._reply_is_repeated(option):
                return option
        return options[0]

    def _reflective_fallback(
        self, user_text: str, analysis: dict[str, Any] | None = None
    ) -> str:
        analysis = analysis or self._analyze(user_text)
        sentiment = analysis.get("sentiment")
        topic = analysis.get("topic")
        options: list[str] = []

        if sentiment == "triste":
            options += [
                "Te escucho. Eso pesa, y no tenés que pasarlo solo.",
                "Estoy acá. Contame qué es lo que más te duele.",
            ]
        elif sentiment == "cansado":
            options += [
                "Un día así cansa de verdad.",
                "Uf... se te nota el cansancio. ¿Qué fue lo que más te pesó?",
            ]
        elif sentiment == "enojado":
            options += [
                "Uh. Suena frustrante. ¿Qué pasó?",
                "Se te nota la bronca. ¿Qué fue lo que te hizo enojar?",
            ]
        elif sentiment == "ansioso":
            options += [
                "Respirá un poquito. Estoy acá.",
                "Eso inquieta. ¿Querés contarme qué te preocupa?",
            ]
        elif sentiment == "contento":
            options += [
                "Me contagia tu alegría.",
                "¡Qué lindo! Contame qué te puso así.",
            ]

        topic_lines = {
            "trabajo": "El trabajo a veces se lleva todo el día. ¿Qué pasó hoy?",
            "estudio": "Los estudios pesan cuando hay mucho. ¿Cómo venís con eso?",
            "familia": "La familia mueve un montón de cosas. ¿Qué pasó?",
            "pareja": "Las relaciones tienen sus vueltas. ¿Querés contarme?",
            "amistad": "Los amigos también cansan a veces. ¿Qué pasó?",
            "salud": "La salud asusta un poco. ¿Cómo estás ahora?",
            "comida": "La comida tiene algo lindo. ¿Qué comiste?",
            "música": "La música ayuda un montón. ¿Qué estás escuchando?",
            "juegos": "Los juegos distraen lindo. ¿A qué estás jugando?",
            "plantas": "Las plantas son tranquilas. ¿Tenés alguna?",
            "clima": "El clima cambia el día entero. ¿Cómo está por allá?",
            "tecnología": "La tecnología a veces complica. ¿Qué te pasó?",
            "descanso": "Descansar hace bien. ¿Pudiste dormir?",
        }
        if topic in topic_lines:
            options.append(topic_lines[topic])

        options += [
            "Te escucho. Seguí contándome si querés.",
            "Mmm. Me quedé pensando en lo que dijiste.",
        ]
        return self._pick_reply(options)

    def _strip_opening_repeat(self, text: str) -> str:
        """Si el turno anterior abrió con la misma muletilla, la saca."""
        match = re.match(r"^(oh|mmm+|uh|ay|bueno|claro|sí|si)[….,! ]+", text, re.IGNORECASE)
        if not match:
            return text
        filler = match.group(1).lower()
        for turn in reversed(self.memory.recent_turns(limit=3)):
            if turn.get("role") != "assistant":
                continue
            old = turn.get("content", "").strip().lower()
            if old.startswith(filler):
                stripped = text[match.end():].strip()
                if stripped:
                    return stripped[0].upper() + stripped[1:]
            break
        return text

    def _repeat_guard(self, text: str, user_text: str = "") -> str:
        """Saca preguntas repetidas y muletillas de turnos anteriores."""
        old_questions = self._old_questions()
        if old_questions:
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
            text = cleaned
        return self._strip_opening_repeat(text)

    def _reply_is_repeated(self, text: str) -> bool:
        normalized = self._normalize_question(text)
        if not normalized:
            return False
        first = self._normalize_question(re.split(r"(?<=[.!?])\s+", text)[0])
        for turn in reversed(self.memory.recent_turns(limit=4)):
            if turn.get("role") != "assistant":
                continue
            old = self._normalize_question(turn.get("content", ""))
            if not old:
                continue
            if difflib.SequenceMatcher(None, normalized, old).ratio() >= 0.86:
                return True
            if first and difflib.SequenceMatcher(None, first, old).ratio() >= 0.82:
                return True
        return False

    _GENERIC_REPLY_RE = re.compile(
        r"^(?:(?:oh|mmm+|uh|ay|bueno|claro|sí|si|dale|ok)[….,! ]*)?"
        r"(?:te entiendo|lo siento|qué (?:lindo|bueno|pena|triste|difícil)|"
        r"me alegra(?: mucho)?|me gusta(?: mucho)?|interesante|entendido|"
        r"eso (?:está|suena) (?:bien|mal)|claro que sí|por supuesto)"
        r"[\s.!…,]*$",
        re.IGNORECASE,
    )

    def _is_generic(self, text: str, analysis: dict[str, Any]) -> bool:
        cleaned = (text or "").strip()
        if not cleaned:
            return True
        if self._GENERIC_REPLY_RE.match(cleaned):
            return True
        if (
            analysis.get("topic")
            and len(cleaned.split()) <= 4
            and "?" not in cleaned
            and not any(
                word in cleaned.lower() for word in analysis.get("keywords", [])
            )
        ):
            return True
        return False

    def _strip_user_echo(self, text: str, user_text: str) -> str:
        """Borra la frase donde el modelo repite casi textual lo que dijo el usuario."""
        user_norm = self._normalize_question(user_text)
        if len(user_norm.split()) < 4:
            return text
        kept: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            norm = self._normalize_question(sentence)
            if norm and difflib.SequenceMatcher(None, norm, user_norm).ratio() >= 0.9:
                if self.verbose:
                    print(f"  [filtro] eco del usuario: {sentence}")
                continue
            kept.append(sentence)
        return " ".join(kept).strip()

    def _recent_user_topics(self, limit: int = 6) -> set[str]:
        topics: set[str] = set()
        for turn in self.memory.recent_turns(limit=limit):
            if turn.get("role") != "user":
                continue
            topic = self._analyze(turn.get("content", ""))["topic"]
            if topic:
                topics.add(topic)
        return topics

    def _strip_topic_carryover(
        self,
        text: str,
        user_text: str,
        analysis: dict[str, Any],
    ) -> str:
        """Saca preguntas que mezclan un tema viejo con el mensaje actual."""
        topic = analysis.get("topic")
        if not topic:
            return text
        recent = self._recent_user_topics()
        recent.discard(topic)
        if not recent:
            return text
        low_user = user_text.lower()
        kept: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if "?" in sentence:
                low = sentence.lower()
                for label, pattern in _TOPIC_HINTS:
                    if label == topic or label not in recent:
                        continue
                    match = pattern.search(low)
                    if match and match.group(0).lower() not in low_user:
                        if self.verbose:
                            print(
                                f"  [filtro] pregunta de tema viejo "
                                f"({label}): {sentence}"
                            )
                        break
                else:
                    kept.append(sentence)
                continue
            kept.append(sentence)
        return " ".join(kept).strip()

    def _quality_guard(
        self,
        text: str,
        user_text: str,
        analysis: dict[str, Any] | None = None,
    ) -> str:
        analysis = analysis or self._analyze(user_text)
        text = self._strip_user_echo(text, user_text)
        text = self._strip_topic_carryover(text, user_text, analysis)
        if self._is_generic(text, analysis) or self._reply_is_repeated(text):
            if self.verbose:
                print(f"  [filtro] respuesta floja: {text!r}")
            text = self._reflective_fallback(user_text, analysis)
        return text

    def _repair(
        self,
        messages: list[dict[str, Any]],
        text: str,
        analysis: dict[str, Any],
    ) -> str:
        """Un solo reintento cuando la respuesta salió vacía, vaga o repetida."""
        if self.verbose:
            print(f"  [filtro] pidiendo corrección: {text!r}")
        retry = list(messages)
        retry.append({"role": "assistant", "content": text or "..."})
        topic = analysis.get("topic") or "lo que te contó"
        retry.append(
            {
                "role": "user",
                "content": (
                    "[corrección interna: tu respuesta fue vaga, genérica o "
                    f"repetida. El usuario habló de {topic} y su tono es "
                    f"{analysis['sentiment']}. Respondé a eso concreto en una o "
                    "dos frases, sin repetir preguntas anteriores ni la frase "
                    "del usuario.]"
                ),
            }
        )
        try:
            reply = self.llm.chat(retry)
        except OllamaError:
            return text
        fixed = self._clean(reply.get("content", ""))
        return fixed or text

    def _respond_conversation(self, user_text: str) -> str:
        """Un solo turno de charla, sin herramientas ni contexto de hardware."""
        analysis = self._analyze(user_text)
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
            text = self._strip_user_echo(text, user_text)
            text = self._repeat_guard(text, user_text)
            if analysis["words"] >= 4 and (
                self._is_generic(text, analysis) or self._reply_is_repeated(text)
            ):
                text = self._repair(messages, text, analysis)
                text = self._repeat_guard(text, user_text)
            text = self._quality_guard(text, user_text, analysis)
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
        text = text.strip().strip('"“”')
        text = re.sub(
            r"^\s*(?:como\s+)?(?:wall-?e|una?\s+ia|un\s+modelo|un\s+chatbot)"
            r"\s*[,:]\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"[*_#`>]", "", text)
        text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", text)
        text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
        text = self._BANNED_CLOSER.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        for pattern, replacement in _VOSEO_FIXES:
            def _swap(match: re.Match[str], fixed: str = replacement) -> str:
                original = match.group(0)
                if original[:1].isupper():
                    return fixed[:1].upper() + fixed[1:]
                return fixed

            text = pattern.sub(_swap, text)
        text = text.strip().strip('"“”')
        text = re.sub(r"^¿O\s+", "¿", text)
        text = re.sub(r"^O\s+", "", text)
        text = re.sub(r"([.!?])\s*[.!?]+", r"\1", text)
        text = re.sub(r"(?:…\s*){2,}", "…", text)
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
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
