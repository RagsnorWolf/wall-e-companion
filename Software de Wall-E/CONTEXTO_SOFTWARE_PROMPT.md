# 🧠 CONTEXTO COMPLETO — SOFTWARE WALL-E COMPANION
**Copiá este archivo completo a un chat nuevo (Claude, GPT, Cursor, Copilot) y decile: "Sos el lead developer. Construí esto."**

---

## 🎯 VISIÓN DEL PRODUCTO
**Wall-E Companion** = Robot de escritorio físico (estilo Wall-E) + Software local-first + Web UI + Modelo IA con personalidad.

**Usuario objetivo:** Developers, makers, streamers, estudiantes que quieren un "compañero de escritorio" que ve, oye, habla, se mueve y tiene personalidad.

**Diferenciador:** 100% local (privacidad), hardware abierto, personalidad programable, skills extensibles (Code Buddy, Focus Guardian, Desk Pet).

---

## 🏗️ ARQUITECTURA GENERAL

```
┌─────────────────┐     JSON/Serial      ┌──────────────────┐
│   ROBOT FÍSICO  │ ◄──────────────────► │   BACKEND PC     │
│  (ESP32 + HW)   │     115200 baud      │  (Python/FastAPI)│
└─────────────────┘                      └────────┬─────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
            ┌───────────────┐             ┌─────────────────┐            ┌────────────────┐
            │   FRONTEND    │             │     MODELO IA   │            │   HARDWARE     │
            │  (React/TS)   │             │   (Ollama/LLM)  │            │   (Config)     │
            │ Cockpit +     │             │  Personality    │            │  hardware.yaml │
            │ Landing       │             │  + Skills       │            │  + Specs Agus  │
            └───────────────┘             └─────────────────┘            └────────────────┘
```

---

## 🛠️ STACK TECNOLÓGICO (FIJO — NO CAMBIAR)

### Backend (Python 3.11+)
| Capa | Tech | Versión | Notas |
|------|------|---------|-------|
| API | FastAPI | 0.109+ | Async, OpenAPI auto |
| WebSocket | `websockets` + FastAPI WS | 12+ | Real-time state broadcast |
| Config | Pydantic Settings v2 | 2.2+ | `.env` + YAML + env vars |
| Vision | OpenCV | 4.9+ | Haar cascades + MediaPipe opcional |
| STT | whisper-cpp-python | 1.0+ | Local, CPU/GPU, streaming |
| TTS | piper-tts | 1.2+ | Local, voces ES/EN, streaming |
| VAD | webrtcvad | 2.0+ | Aggressiveness 0-3 |
| LLM | Ollama Python | 0.3+ | Local inference, function calling |
| Memory | ChromaDB | 0.4+ | Vector store persistente |
| Cache/Queue | Redis | 7+ | Pub/sub, session, rate limit |
| Serial | pyserial | 3.5+ | JSON Lines protocol |
| Testing | pytest + pytest-asyncio | 7.4+ | Mock hardware para CI |
| Lint/Format | Ruff + MyPy | Latest | Pre-commit hooks |

### Frontend — Cockpit (Privado, Local)
| Tech | Uso |
|------|-----|
| React 18 + TypeScript + Vite | SPA dashboard |
| Zustand | State global (WS connection, robot state) |
| Three.js + @react-three/fiber/drei | Robot 3D mirror (servos reales) |
| Tailwind CSS | Cyberpunk theme (verde matriz) |
| Socket.io-client | WS fallback si hace falta |

### Frontend — Landing (Público)
| Tech | Uso |
|------|-----|
| Next.js 14 (App Router) | SSR/SSG, SEO |
| Framer Motion | Animaciones scroll, hero |
| Tailwind CSS | Mismo design system |
| Lucide React | Iconos |

### Infra / DevOps
| Tool | Uso |
|------|-----|
| Docker Compose | Stack local: ollama, redis, chroma, api, cockpit, landing |
| GitHub Actions | CI: lint, test, typecheck, docker build |
| Git LFS | Model checkpoints, videos, STL |
| pre-commit | Ruff, MyPy, pytest en commit |

---

## 📁 ESTRUCTURA REPO (YA CREADA EN GITHUB)

```
wall-e-companion/
├── Robot Wall-E/              # Agus — Hardware
│   ├── GUIA_AGUS_HARDWARE.md  # Guía completa + cronograma
│   ├── hardware_specs.yaml    # Template → Agus completa valores reales
│   ├── cad/                   # STL, STEP, guide
│   ├── pcb/                   # KiCad, gerber, BOM
│   ├── firmware/              # PlatformIO/Arduino
│   └── photos/                # Fotos robot real
├── Software de Wall-E/        # Gonzalo — Backend
│   ├── pyproject.toml         # Deps + config ruff/mypy/pytest
│   ├── Dockerfile
│   ├── config/
│   │   └── hardware.yaml      # ← Se genera desde hardware_specs.yaml de Agus
│   ├── core/                  # Config, types, exceptions, hardware abstraction
│   ├── vision/                # Face tracker (OpenCV)
│   ├── voice/                 # STT, TTS, VAD
│   ├── brain/                 # State machine, skills, LLM, memory
│   ├── server/                # FastAPI + WebSocket (main.py)
│   └── tests/                 # Mocks + unit tests
├── Pagina Web/                # Gonzalo — Frontend
│   ├── cockpit/               # React dashboard (localhost:5173)
│   │   ├── src/pages/         # Dashboard, ManualControl, Logs, Settings
│   │   ├── src/components/    # Robot3D, MoodIndicator, ConnectionStatus
│   │   └── src/store/         # Zustand store (WS, commands)
│   └── landing/               # Next.js public site (localhost:3000)
│       └── src/app/page.tsx   # Hero, features, hardware, team, CTA
├── Modelo AI/                 # Delfi + Gonzalo — IA
│   ├── prompts/
│   │   ├── system.md          # System prompt completo (personalidad, moods, skills)
│   │   └── moods.json         # 10 moods → poses servos + voice config
│   ├── training/              # train_lora.py, eval_model.py
│   ├── data/                  # Datasets (git-lfs)
│   └── checkpoints/           # LoRA adapters (git-lfs)
├── scripts/
│   └── auto_commit.py         # Auto-commit + push cada N seg
├── .github/workflows/ci.yml   # CI completo
├── docker-compose.yml         # Stack local completo
├── .env.example               # Template variables
├── .gitignore                 # Python, Node, models, media
└── start_auto_commit.bat      # Launcher Windows
```

---

## 🔌 PROTOCOLO ROBOT ↔ BACKEND (CONTRATO FIJO)

**Transporte:** Serial USB (JSON Lines, newline-delimited) @ 115200 8N1
**Alternativas futuras:** MQTT, WebSocket, ROS2

### PC → Robot (Comandos)
```json
{"cmd": "move_servo", "id": "head_pan", "angle": 45.0, "speed": 100}
{"cmd": "move_servos", "positions": [{"id": "head_pan", "angle": 10}, {"id": "head_tilt", "angle": -15}]}
{"cmd": "set_mood", "mood": "curious"}
{"cmd": "get_state"}
{"cmd": "calibrate", "id": "eye_L", "points": [{"angle": 0, "pulse": 500}, {"angle": 90, "pulse": 2500}]}
{"cmd": "reset"}
{"cmd": "emergency_stop"}
```

### Robot → PC (Eventos)
```json
{"evt": "state", "data": {"uptime_ms": 12345, "servos": [...], "battery_voltage": 7.82, "battery_percent": 85, "temperature_c": 36.2, "free_heap": 152000}}
{"evt": "ack", "cmd": "move_servo", "ok": true}
{"evt": "error", "cmd": "move_servo", "msg": "servo not found"}
{"evt": "log", "level": "INFO", "msg": "PCA9685 initialized"}
```

### Servos (IDs fijos — coinciden con firmware)
| ID | Canal PCA9685 | Rango | Default |
|----|---------------|-------|---------|
| head_pan | 0 | -90 a +90 | 0 |
| head_tilt | 1 | -45 a +45 | 0 |
| eye_L | 2 | 0 a 100 | 50 |
| eye_R | 3 | 0 a 100 | 50 |
| body_lean | 4 | -30 a +30 | 0 |
| arm_L | 5 | -90 a +90 | 0 |
| arm_R | 6 | -90 a +90 | 0 |

---

## 🧠 BRAIN — STATE MACHINE + SKILLS

### Moods (10) — Definidos en `Modelo AI/prompts/moods.json`
`idle` → `curious` → `happy` → `thinking` → `sad` → `alert` → `sleeping` → `listening` → `speaking`

Cada mood = pose servos + config voz (rate, pitch) + comportamiento automático.

### Skills (3 base — extensibles)
| Skill | Trigger | Acción |
|-------|---------|--------|
| **Code Buddy** | Git push, test pass/fail, file change | Celebra/consuela, comenta código |
| **Focus Guardian** | Pomodoro start/pause/stop | Timer físico (ojos = progreso), alertas |
| **Desk Pet** | Idle >2min, música, notificación, clima, hora | Comportamientos autónomos |

### Memory
- **Short-term:** Últimas 50 interacciones en RAM (contexto LLM)
- **Long-term:** ChromaDB vector store (embeddings nomic-embed-text)
- **API:** `add_memory()`, `search_semantic()`, `get_context_for_llm()`

---

## 🎨 FRONTEND — COCKPIT (PRIVADO)

### Páginas (React Router)
| Ruta | Componente | Función |
|------|------------|---------|
| `/` | Dashboard | Robot 3D + status panels + quick actions |
| `/manual` | ManualControl | Sliders por servo + mood presets + poses guardadas |
| `/logs` | Logs | Stream logs tiempo real (filtro, search, export) |
| `/settings` | Settings | Config hardware, vision, voice, LLM, skills |

### Componentes clave
- **Robot3D** (Three.js): Espejo digital del robot real, animado por servo state real
- **MoodIndicator**: Icono + barra intensidad + label
- **ConnectionStatus**: LIVE/OFFLINE/CONNECTING + reconexión auto
- **Zustand Store**: WS connection, robot state, commands, audio queue

### Theme: Cyberpunk Terminal
- Colores: `#00ff41` (primary), `#00ccff` (secondary), `#ffcc00` (accent), `#ff3333` (danger)
- Font: JetBrains Mono (mono), Inter (sans), Space Grotesk (display)
- Scanlines overlay, glow effects, animaciones sutiles

---

## 🌐 FRONTEND — LANDING (PÚBLICO)

### Secciones (Single Page)
1. **Hero** — Headline + CTA + stats (100% Local, <100ms, Open Source, ∞ Personality)
2. **Features** — 6 cards: Vision, Voice, Local LLM, Movement, Skills, Dev API
3. **Hardware** — Esquemático visual + specs tablas + link CAD
4. **Software Stack** — Grid por categoría + Architecture diagram (SVG)
5. **Personality** — Mood cards interactivos
6. **Team** — 3 cards (Agus/Gonzalo/Delfi)
7. **CTA** — 3 pasos: Clone → Build → Flash
8. **Footer** — Links + contact

---

## 🤖 MODELO IA — PERSONALIDAD

### System Prompt (`Modelo AI/prompts/system.md`)
Define: identidad, traits, communication style, mood behaviors, skills, boundaries, quirks, ejemplos.

### Moods Config (`Modelo AI/prompts/moods.json`)
10 moods × {servo poses + voice config + description}

### Training Pipeline
- `train_lora.py`: LoRA sobre Llama 3.1 8B (4-bit QLoRA)
- Dataset: Sintético desde templates + few-shot de personalidad
- `eval_model.py`: 8 test cases (mood match, keywords, forbidden, length, language)

---

## ⚙️ CONFIGURACIÓN CENTRAL (`.env` + YAML)

### Variables críticas (`.env`)
```bash
# Hardware
MCU_PORT=COM3
MCU_BAUDRATE=115200

# Vision
CAMERA_DEVICE=0
FACE_CASCADE_PATH=models/haarcascade_frontalface_default.xml

# Voice
WHISPER_MODEL=base
PIPER_VOICE=es_MX-clara-low

# LLM
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
SYSTEM_PROMPT_PATH=../Modelo AI/prompts/system.md
MOODS_CONFIG_PATH=../Modelo AI/prompts/moods.json

# Skills
ENABLE_SKILL_CODE_BUDDY=true
ENABLE_SKILL_FOCUS_GUARDIAN=true
ENABLE_SKILL_DESK_PET=true

# Auto-commit
AUTO_COMMIT_INTERVAL=30
```

### `config/hardware.yaml` (generado desde Agus)
```yaml
mcu: {type, port, baudrate, protocol}
servos: [{id, channel, min_pulse, max_pulse, angle_range, default_angle, inverted}]
camera: {type, device_index, width, height, fps}
audio: {mic: {type, sample_rate, i2s_pins}, speaker: {type, sample_rate, i2s_pins}}
power: {battery_type, voltage_monitor, min_voltage, max_voltage}
sensors: {tof, imu, temp}
```

---

## 🚀 FLUJO DE DESARROLLO (DÍA A DÍA)

### 1. Mock Mode (AHORA — sin hardware)
```bash
docker compose up -d
# API: http://localhost:8000/health
# Cockpit: http://localhost:5173 (robot 3D animado, sliders, moods, logs)
# Landing: http://localhost:3000
```
- `mock=True` en `core/hardware.py` → `MockHardwareInterface`
- Vision: face tracker con cámara web local
- Voice: Whisper + Piper locales
- LLM: Ollama local (llama3.1:8b)

### 2. Hardware Integration (CUANDO AGUS TERMINE)
1. Agus pushea `hardware_specs.yaml` completado
2. Copiás valores a `Software de Wall-E/config/hardware.yaml`
3. En `core/hardware.py`: `mock=False` → usa `SerialJSONHardware`
4. Conectás USB → `docker compose restart api`
5. Cockpit controla robot real

### 3. Auto-commit (SIEMPRE CORRIENDO)
```bash
# Terminal aparte:
python scripts/auto_commit.py --interval 30 --push
# O doble clic: start_auto_commit.bat
```

---

## ✅ CHECKLIST DE ENTREGABLES SOFTWARE (DEFINICIÓN DE DONE)

### Backend
- [ ] FastAPI + WS server levanta sin errores
- [ ] `/health`, `/state`, `/command`, `/ws` responden
- [ ] Vision loop: face tracking → servo targets (mock + real)
- [ ] Voice pipeline: VAD → STT streaming → LLM → TTS queue → audio chunks WS
- [ ] State machine: moods, skills, events, memory
- [ ] Skills 3 base funcionando (eventos → reacciones)
- [ ] Config Pydantic carga `.env` + YAML + valida
- [ ] Tests unitarios >80% coverage (mock hardware)

### Cockpit
- [ ] Dashboard: 3D robot + panels status + quick actions
- [ ] Manual: sliders servo + mood buttons + preset poses
- [ ] Logs: stream real-time + filter + export
- [ ] Settings: formularios por sección + save → API
- [ ] WS reconexión automática + estado conexión visible
- [ ] Theme cyberpunk consistente + responsive

### Landing
- [ ] Hero + 6 sections + CTA + Footer
- [ ] Animaciones Framer Motion (scroll, hover, entrance)
- [ ] Architecture diagram SVG interactivo
- [ ] SEO meta tags + OG + Twitter cards
- [ ] Responsive mobile-first
- [ ] Build estático exportable (`next build && next export`)

### Modelo IA
- [ ] System prompt v1 en `prompts/system.md`
- [ ] Moods v1 en `prompts/moods.json`
- [ ] Dataset sintético generado (`train_lora.py --create-data`)
- [ ] LoRA training script funcional
- [ ] Eval script pasa 8/8 test cases

### Infra
- [ ] Docker compose levanta todo (ollama, redis, chroma, api, cockpit, landing)
- [ ] CI pasa: lint + typecheck + tests + docker build
- [ ] Git LFS track: `*.bin`, `*.safetensors`, `*.mp4`, `*.stl`
- [ ] Auto-commit script funcional + .bat launcher

---

## 📋 PRÓXIMOS PASOS INMEDIATOS (PARA VOS EN OTRO CHAT)

1. **Cloná repo** → `git clone https://github.com/RagsnorWolf/wall-e-companion.git`
2. **Leé `Software de Wall-E/pyproject.toml`** → instalá deps: `pip install -e ".[dev]"`
3. **Levantá stack mock** → `docker compose up -d` → verificá 3 puertos
4. **Abrí Cockpit** → `http://localhost:5173` → jugá con robot 3D mock
5. **Empezá por `Software de Wall-E/server/main.py`** → endpoints + WS
6. **Paralelo: `Pagina Web/cockpit/src/pages/Dashboard.tsx`** → Robot3D + panels
7. **Cuando Agus mande `hardware_specs.yaml`** → generá `config/hardware.yaml` + switch `mock=False`

---

## 📞 CONTACTO EQUIPO
- **Agus (Hardware):** Discord/WA — responde `Robot Wall-E/PREGUNTAS_AGUS.md`
- **Delfi (IA Personality):** Edita `Modelo AI/prompts/system.md` y `moods.json`
- **Gonzalo (Vos — Software):** Dueño de `Software de Wall-E/`, `Pagina Web/`, integración

---

## 🔗 LINKS ÚTILES
- Repo: https://github.com/RagsnorWolf/wall-e-companion
- Issues: https://github.com/RagsnorWolf/wall-e-companion/issues
- Ollama models: https://ollama.com/library
- Piper voices: https://github.com/rhasspy/piper/blob/master/VOICES.md
- Whisper.cpp: https://github.com/ggerganov/whisper.cpp
- PCA9685 datasheet: https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf

---

**¡A codear! El hardware llega cuando llega. El software se hace AHORA.** 🚀