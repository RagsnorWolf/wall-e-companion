# 🤖 WALL-E COMPANION — CONTEXTO COMPLETO DEL PROYECTO
**Versión:** 1.0 | **Fecha:** 2026-10-24 | **Repo:** https://github.com/RagsnorWolf/wall-e-companion

---

## 🎯 VISIÓN DEL PRODUCTO
**Wall-E Companion** = Robot de escritorio físico (estilo Wall-E) + Software local-first + Web UI + Modelo IA con personalidad propia.

**Usuario objetivo:** Developers, makers, streamers, estudiantes que quieren un "compañero de escritorio" que ve, oye, habla, se mueve y tiene personalidad.

**Diferenciadores clave:**
- 100% local (privacidad total, sin cloud)
- Hardware abierto (CAD, PCB, firmware en repo)
- Personalidad programable (system prompt + moods JSON)
- Skills extensibles (Code Buddy, Focus Guardian, Desk Pet)
- Arquitectura modular: robot ↔ backend ↔ frontend ↔ IA

---

## 👥 EQUIPO Y ROLES

| Miembro | Rol | Carpeta responsable | Qué hace |
|---------|-----|---------------------|----------|
| **Agus** | Hardware / Robótica | `Robot Wall-E/` | MCU, servos, sensores, CAD, PCB, firmware, wiring |
| **Gonzalo** | Software / Web / IA Integration | `Software de Wall-E/`, `Pagina Web/` | Backend (FastAPI), Frontend (React+Three.js, Next.js), Integración robot, Docker, CI/CD |
| **Delfi** | Personalidad IA / Prompts | `Modelo AI/` | System prompt, moods, voice config, training data, eval |

**Comunicación:** Discord/WA grupo "Wall-E Team" + GitHub Issues + Daily async en `docs/meetings/YYYY-MM-DD.md`

---

## 🏗️ ARQUITECTURA GENERAL

```
┌─────────────────┐     JSON Lines Serial      ┌──────────────────┐
│   ROBOT FÍSICO  │ ◄────────────────────────► │   BACKEND PC     │
│  (ESP32-S3 + HW)│      115200 baud 8N1       │  (Python/FastAPI)│
└─────────────────┘                            └────────┬─────────┘
                                                         │
                    ┌────────────────────────────────────┼────────────────────────────────────┐
                    ▼                                    ▼                                    ▼
            ┌───────────────┐                   ┌─────────────────┐                  ┌────────────────┐
            │   FRONTEND    │                   │     MODELO IA   │                  │   HARDWARE     │
            │  (React/TS)   │                   │   (Ollama/LLM)  │                  │   (Config)     │
            │ Cockpit +     │                   │  Personality    │                  │  hardware.yaml │
            │ Landing       │                   │  + Skills       │                  │  + Specs Agus  │
            └───────────────┘                   └─────────────────┘                  └────────────────┘
```

---

## 🤖 HARDWARE — ROBOT WALL-E (RESPONSABLE: AGUS)

### Estado actual: **EN CONSTRUCCIÓN** — Agus completa `hardware_specs.yaml`

### Especificaciones objetivo (definidas en `Robot Wall-E/GUIA_AGUS_HARDWARE.md`)

| Componente | Espec objetivo | Notas |
|------------|----------------|-------|
| **MCU** | ESP32-S3-DevKitC-1 (N16R8) | WiFi + BLE + 45 GPIO |
| **Servos (7)** | MG90S (metal gears) | head_pan, head_tilt, eye_L, eye_R, body_lean, arm_L, arm_R |
| **Driver** | PCA9685 (16ch PWM, I2C 0x40) | 50Hz, 12-bit resolution |
| **Cámara** | USB 720p UVC (OV2640/IMX219) | 640x480@30fps |
| **Micrófono** | INMP441 I2S MEMS | 16kHz, 24-bit |
| **Altavoz** | MAX98357A I2S + 3W 4Ω | 22.05kHz |
| **Batería** | 2x 18650 3000mAh (2S = 7.4V) | BMS 2S + TP4056 USB-C carga |
| **Reguladores** | LM2596S 5V/3A (servos) + AMS1117-3.3V (MCU) | Buck + LDO |
| **Sensores extra** | VL53L0X (ToF), MPU6050 (IMU) | Opcionales |

### Grados de libertad (7 servos)
| ID | Nombre | Canal PCA9685 | Rango | Default |
|----|--------|---------------|-------|---------|
| head_pan | Cabeza giro | 0 | -90° a +90° | 0° |
| head_tilt | Cabeza inclinación | 1 | -45° a +45° | 0° |
| eye_L | Ojo izquierdo | 2 | 0° a 100° | 50° |
| eye_R | Ojo derecho | 3 | 0° a 100° | 50° |
| body_lean | Cuerpo inclinación | 4 | -30° a +30° | 0° |
| arm_L | Brazo izquierdo | 5 | -90° a +90° | 0° |
| arm_R | Brazo derecho | 6 | -90° a +90° | 0° |

### Protocolo Robot ↔ PC (CONTRATO FIJO)
**Transporte:** Serial USB (JSON Lines, newline-delimited) @ 115200 8N1

**PC → Robot (Comandos):**
```json
{"cmd": "move_servo", "id": "head_pan", "angle": 45.0, "speed": 100}
{"cmd": "move_servos", "positions": [{"id": "head_pan", "angle": 10}, {"id": "head_tilt", "angle": -15}]}
{"cmd": "set_mood", "mood": "curious"}
{"cmd": "get_state"}
{"cmd": "calibrate", "id": "eye_L", "points": [{"angle": 0, "pulse": 500}, {"angle": 90, "pulse": 2500}]}
{"cmd": "reset"}
{"cmd": "emergency_stop"}
```

**Robot → PC (Eventos):**
```json
{"evt": "state", "data": {"uptime_ms": 12345, "servos": [...], "battery_voltage": 7.82, "battery_percent": 85, "temperature_c": 36.2, "free_heap": 152000}}
{"evt": "ack", "cmd": "move_servo", "ok": true}
{"evt": "error", "cmd": "move_servo", "msg": "servo not found"}
{"evt": "log", "level": "INFO", "msg": "PCA9685 initialized"}
```

### Archivos que Agus debe entregar en `Robot Wall-E/`
```
Robot Wall-E/
├── GUIA_AGUS_HARDWARE.md          # Guía completa (10 secciones)
├── hardware_specs.yaml            # Template → completa con valores reales
├── PREGUNTAS_AGUS.md              # 50+ preguntas para contexto
├── cad/
│   ├── stl/                       # .stl listos para slicer
│   ├── step/                      # .step editable
│   └── assembly_guide.pdf
├── pcb/
│   ├── kicad/                     # Proyecto KiCad
│   ├── gerber/                    # .zip para JLCPCB
│   └── bom.csv
├── firmware/
│   ├── src/main.cpp               # Arduino/PlatformIO
│   ├── platformio.ini
│   └── lib/
├── docs/
│   ├── wiring_diagram.png
│   ├── pinout.md
│   └── calibration_procedure.md
└── photos/                        # Fotos del robot real
```

---

## 💻 SOFTWARE — BACKEND (RESPONSABLE: GONZALO)

### Stack tecnológico
| Capa | Tech | Versión |
|------|------|---------|
| API | FastAPI | 0.109+ |
| WebSocket | websockets + FastAPI WS | 12+ |
| Config | Pydantic Settings v2 | 2.2+ |
| Vision | OpenCV | 4.9+ |
| STT | whisper-cpp-python | 1.0+ |
| TTS | piper-tts | 1.2+ |
| VAD | webrtcvad | 2.0+ |
| LLM | Ollama Python | 0.3+ |
| Memory | ChromaDB | 0.4+ |
| Cache/Queue | Redis | 7+ |
| Serial | pyserial | 3.5+ |
| Testing | pytest + pytest-asyncio | 7.4+ |
| Lint/Format | Ruff + MyPy | Latest |

### Estructura `Software de Wall-E/`
```
Software de Wall-E/
├── pyproject.toml                 # Deps + config ruff/mypy/pytest
├── Dockerfile
├── config/
│   └── hardware.yaml              # ← Generado desde hardware_specs.yaml de Agus
├── core/
│   ├── config.py                  # Pydantic Settings (env + YAML)
│   ├── types.py                   # Tipos compartidos (Pydantic → JSON Schema para TS)
│   ├── exceptions.py              # Excepciones custom
│   ├── hardware.py                # HardwareInterface (ABC + Mock + Serial)
│   └── hardware_serial.py         # Implementación JSON Lines serial
├── vision/
│   └── face_tracker.py            # OpenCV face tracking + servo mapping
├── voice/
│   ├── stt.py                     # Whisper.cpp wrapper async
│   ├── tts.py                     # Piper TTS + queue streaming
│   └── vad.py                     # WebRTC VAD streaming
├── brain/
│   ├── state_machine.py           # State machine + moods + events
│   ├── skills.py                  # CodeBuddy, FocusGuardian, DeskPet
│   ├── llm.py                     # Ollama client + function calling
│   └── memory.py                  # ConversationMemory + VectorMemory (ChromaDB)
├── server/
│   └── main.py                    # FastAPI + WS endpoints
├── tests/
│   └── test_hardware_mock.py      # Mocks para CI
└── scripts/
    └── calibrate_servos.py        # Calibración interactiva
```

### Endpoints principales (FastAPI)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/state` | Estado completo robot |
| GET | `/hardware` | Estado hardware |
| POST | `/command` | Enviar comando genérico |
| POST | `/mood` | Cambiar mood |
| POST | `/speak` | Hablar (TTS queue) |
| POST | `/skill` | Enable/disable/trigger skill |
| GET | `/memory` | Memoria conversacional |
| POST | `/memory/search` | Búsqueda semántica |
| WS | `/ws` | WebSocket tiempo real |
| GET | `/camera/stream` | MJPEG stream cámara |

### WebSocket Messages (Tiempo real)
```typescript
// Server → Client (100ms broadcast)
{ type: "state_update", payload: RobotState }
{ type: "log", payload: { level, module, message, timestamp } }
{ type: "audio_chunk", payload: { data: "hex" } }
{ type: "heartbeat", payload: { pong: true } }

// Client → Server
{ type: "command", payload: RobotCommand }
{ type: "ping", payload: {} }
```

---

## 🌐 FRONTEND — COCKPIT (PRIVADO, LOCAL) + LANDING (PÚBLICO)

### Stack
| Tech | Uso |
|------|-----|
| React 18 + TypeScript + Vite | SPA Cockpit |
| Zustand | State global (WS, robot state, commands) |
| Three.js + @react-three/fiber/drei | Robot 3D mirror (servos reales) |
| Tailwind CSS | Cyberpunk theme |
| Next.js 14 (App Router) | Landing pública |
| Framer Motion | Animaciones landing |

### Cockpit — Páginas (`Pagina Web/cockpit/src/pages/`)
| Ruta | Componente | Función |
|------|------------|---------|
| `/` | Dashboard | Robot 3D + status panels + quick actions |
| `/manual` | ManualControl | Sliders por servo + mood presets + poses guardadas |
| `/logs` | Logs | Stream logs tiempo real (filtro, search, export) |
| `/settings` | Settings | Config hardware, vision, voice, LLM, skills |

### Componentes clave (`Pagina Web/cockpit/src/components/`)
- **Robot3D** — Espejo digital Three.js animado por servo state real (100ms)
- **MoodIndicator** — Icono + barra intensidad + label
- **ConnectionStatus** — LIVE/OFFLINE/CONNECTING + reconexión auto
- **Zustand Store** (`src/store/robotStore.ts`) — WS connection, robot state, commands, audio queue

### Theme: Cyberpunk Terminal
- Colores: `#00ff41` (primary), `#00ccff` (secondary), `#ffcc00` (accent), `#ff3333` (danger)
- Fonts: JetBrains Mono (mono), Inter (sans), Space Grotesk (display)
- Scanlines overlay, glow effects, animaciones sutiles

### Landing — Secciones (`Pagina Web/landing/src/app/page.tsx`)
1. **Hero** — Headline + CTA + stats (100% Local, <100ms, Open Source, ∞ Personality)
2. **Features** — 6 cards: Vision, Voice, Local LLM, Movement, Skills, Dev API
3. **Hardware** — Esquemático visual + specs tablas + link CAD
4. **Software Stack** — Grid por categoría + Architecture diagram SVG
5. **Personality** — Mood cards interactivos
6. **Team** — 3 cards (Agus/Gonzalo/Delfi)
7. **CTA** — 3 pasos: Clone → Build → Flash
8. **Footer** — Links + contact

---

## 🧠 MODELO IA — PERSONALIDAD + SKILLS (RESPONSABLE: DELFI + GONZALO)

### System Prompt (`Modelo AI/prompts/system.md`)
Define: identidad, traits, communication style, mood behaviors, skills, boundaries, quirks, ejemplos de interacción.

**Identidad:** Wall-E (o "Wally"), desktop companion, curioso, expresivo, helpful, playful, observant, non-judgmental.

**Communication style:** Breve (1-2 oraciones), conversacional, context-aware, emocional, action-oriented.

### Moods (10) — `Modelo AI/prompts/moods.json`
Cada mood = pose servos + config voz (rate, pitch) + descripción + comportamiento automático.

| Mood | Pose clave | Voz | Trigger típico |
|------|------------|-----|----------------|
| `idle` | Relajado, breathing | rate 1.0, pitch 0 | Default |
| `curious` | Head tilt, ojos abiertos, lean forward | rate 1.15, pitch +2 | Face detected, pregunta |
| `happy` | Ojos brillantes, bounce, brazos arriba | rate 1.2, pitch +3 | Test pass, git push, elogio |
| `thinking` | Ojos async, head tilt leve | rate 0.85, pitch -1 | LLM inference, pregunta compleja |
| `sad` | Postura caída, ojos dim | rate 0.8, pitch -3 | Test fail, error, frustración user |
| `alert` | Ojos abiertos, upright | rate 1.25, pitch +2 | Pomodoro end, batería baja, notif importante |
| `sleeping` | Head down, ojos cerrados | rate 0.6, pitch -5 | Noche, inactividad prolongada |
| `listening` | Atento, slight forward | rate 1.0, pitch 0 | VAD detecta speech start |
| `speaking` | Engaged, ojos brillantes | rate 1.0, pitch 0 | TTS playing |

### Skills (3 base — extensibles via plugin architecture)
| Skill | Triggers | Acciones |
|-------|----------|----------|
| **Code Buddy** | Git push, test pass/fail, file change | Celebra/consuela, comenta código breve |
| **Focus Guardian** | Pomodoro start/pause/stop/skip | Timer físico (ojos = progreso), alertas 5min/1min, celebra ciclos |
| **Desk Pet** | Idle >2min, música, notificación, clima, hora | Stretch, look around, sleepy, excited, confused, dance, alert |

### Memory Architecture
- **Short-term (RAM):** Últimas 50 interacciones → contexto LLM inmediato
- **Long-term (ChromaDB):** Vector store persistente (embeddings nomic-embed-text)
- **API:** `add_memory()`, `search_semantic()`, `get_context_for_llm(max_tokens)`

### Training Pipeline (`Modelo AI/training/`)
- `train_lora.py`: LoRA sobre Llama 3.1 8B (4-bit QLoRA, r=16, alpha=32)
- Dataset: Sintético desde templates + few-shot personalidad (`--create-data`)
- `eval_model.py`: 8 test cases (mood match, keywords, forbidden, length, language)

---

## ⚙️ CONFIGURACIÓN CENTRAL

### Variables críticas (`.env` — copiar de `.env.example`)
```bash
# Hardware
MCU_PORT=COM3                    # Agus define
MCU_BAUDRATE=115200

# Vision
CAMERA_DEVICE=0                  # Agus define
FACE_CASCADE_PATH=models/haarcascade_frontalface_default.xml

# Voice
WHISPER_MODEL=base               # tiny|base|small|medium|large
PIPER_VOICE=es_MX-clara-low      # Ver https://github.com/rhasspy/piper/blob/master/VOICES.md

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

### `config/hardware.yaml` (generado desde `Robot Wall-E/hardware_specs.yaml`)
```yaml
mcu:
  type: "esp32-s3"
  port: "COM3"
  baudrate: 115200
  protocol: "json_serial"

servos:
  - id: "head_pan"
    channel: 0
    min_pulse: 500
    max_pulse: 2500
    angle_range: [-90, 90]
    default_angle: 0
  # ... (7 servos total)

camera:
  type: "usb"
  device_index: 0
  width: 640
  height: 480
  fps: 30

audio:
  mic: {type: "i2s", sample_rate: 16000, channels: 1, i2s_pins: {ws: 3, sck: 4, sd: 5}}
  speaker: {type: "i2s", sample_rate: 22050, i2s_pins: {bclk: 6, lrclk: 7, din: 8}}

power:
  battery_type: "liion_2s"
  voltage_monitor: "ina219"
  min_voltage: 6.5
  max_voltage: 8.4
```

---

## 🐳 INFRAESTRUCTURA — DOCKER COMPOSE

```yaml
services:
  ollama:      # LLM local inference (GPU si disponible)
  redis:       # Cache, pub/sub, sessions
  chroma:      # Vector DB memoria
  api:         # FastAPI backend (Python)
  web-cockpit: # React dashboard (puerto 5173)
  web-landing: # Next.js landing (puerto 3000)
  nginx:       # Reverse proxy (production profile)
```

**Puertos locales:**
- API: `http://localhost:8000` (docs: `/docs`)
- Cockpit: `http://localhost:5173`
- Landing: `http://localhost:3000`
- Ollama: `http://localhost:11434`
- Chroma: `http://localhost:8001`

---

## 🔄 FLUJO DE DESARROLLO

### 1. MOCK MODE (AHORA — SIN HARDWARE)
```bash
# Clonar repo
git clone https://github.com/RagsnorWolf/wall-e-companion.git
cd wall-e-companion

# Auto-commit (terminal aparte, se queda corriendo)
python scripts/auto_commit.py --interval 30 --push
# O Windows: doble clic start_auto_commit.bat

# Levantar stack completo
docker compose up -d

# Verificar
curl http://localhost:8000/health
open http://localhost:5173    # Cockpit (robot 3D mock + sliders + moods)
open http://localhost:3000    # Landing
```

**En mock mode:**
- `mock=True` en `core/hardware.py` → `MockHardwareInterface`
- Vision: face tracker con webcam local
- Voice: Whisper + Piper locales
- LLM: Ollama local (llama3.1:8b)
- Robot 3D en cockpit se anima solo (idle behaviors)

### 2. HARDWARE INTEGRATION (CUANDO AGUS TERMINE)
1. Agus pushea `Robot Wall-E/hardware_specs.yaml` **completado con valores reales**
2. Gonzalo copia valores a `Software de Wall-E/config/hardware.yaml`
3. En `Software de Wall-E/core/hardware.py`: cambia `mock=False`
4. Conecta robot por USB → `docker compose restart api`
5. Cockpit controla robot real

### 3. AUTO-COMMIT (SIEMPRE CORRIENDO)
```bash
# Guarda + commitea + pushea cada 30s (configurable)
python scripts/auto_commit.py --interval 30 --push
```

---

## 📋 DEFINITION OF DONE — CHECKLIST POR MÓDULO

### Backend (Software de Wall-E/)
- [ ] FastAPI + WS server levanta sin errores
- [ ] `/health`, `/state`, `/command`, `/ws` responden
- [ ] Vision loop: face tracking → servo targets (mock + real)
- [ ] Voice pipeline: VAD → STT streaming → LLM → TTS queue → audio chunks WS
- [ ] State machine: moods, skills, events, memory
- [ ] Skills 3 base funcionando (eventos → reacciones)
- [ ] Config Pydantic carga `.env` + YAML + valida
- [ ] Tests unitarios >80% coverage (mock hardware)

### Cockpit (Pagina Web/cockpit/)
- [ ] Dashboard: 3D robot + panels status + quick actions
- [ ] Manual: sliders servo + mood buttons + preset poses
- [ ] Logs: stream real-time + filter + export
- [ ] Settings: formularios por sección + save → API
- [ ] WS reconexión automática + estado conexión visible
- [ ] Theme cyberpunk consistente + responsive

### Landing (Pagina Web/landing/)
- [ ] Hero + 6 sections + CTA + Footer
- [ ] Animaciones Framer Motion (scroll, hover, entrance)
- [ ] Architecture diagram SVG interactivo
- [ ] SEO meta tags + OG + Twitter cards
- [ ] Responsive mobile-first
- [ ] Build estático exportable

### Modelo IA (Modelo AI/)
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

## 🚀 PRÓXIMOS PASOS INMEDIATOS (POR ROL)

### Agus (Hardware) — ESTA SEMANA
1. Lee `Robot Wall-E/GUIA_AGUS_HARDWARE.md` + `Robot Wall-E/PREGUNTAS_AGUS.md`
2. Compra/consegue piezas (BOM §1)
3. Protoboard test: ESP32 + PCA9685 + 1 servo + JSON serial
4. Completa `Robot Wall-E/hardware_specs.yaml` con valores reales
5. Monta mecánica + cableado completo
6. Sube STLs, KiCad, fotos a `Robot Wall-E/`
7. Avisa a Gonzalo cuando `hardware_specs.yaml` listo

### Gonzalo (Software) — EN PARALELO (OTRO CHAT)
1. Abre `Software de Wall-E/CONTEXTO_SOFTWARE_PROMPT.md` en nuevo chat
2. Clona repo → `docker compose up -d` → verifica 3 puertos
3. Codea backend: `Software de Wall-E/server/main.py` → endpoints + WS
4. Codea cockpit: `Pagina Web/cockpit/src/pages/Dashboard.tsx` → Robot3D + panels
5. Codea landing: `Pagina Web/landing/src/app/page.tsx`
6. Cuando Agus mande `hardware_specs.yaml` → genera `config/hardware.yaml` + `mock=False`

### Delfi (IA Personality) — CUANDO QUIERA
1. Edita `Modelo AI/prompts/system.md` (personalidad, quirks, boundaries)
2. Edita `Modelo AI/prompts/moods.json` (poses, voice config)
3. Genera dataset: `python Modelo AI/training/train_lora.py --create-data`
4. Entrena LoRA: `python Modelo AI/training/train_lora.py`
4. Evalúa: `python Modelo AI/training/eval_model.py`

---

## 📁 ESTRUCTURA REPO COMPLETA (GITHUB)

```
wall-e-companion/
├── .github/workflows/ci.yml       # CI: lint, test, typecheck, docker build
├── docker-compose.yml             # Stack local completo
├── .env.example                   # Template variables
├── .gitignore                     # Python, Node, models, media
├── start_auto_commit.bat          # Launcher Windows auto-commit
├── scripts/
│   └── auto_commit.py             # Auto-commit + push cada N seg
├── Robot Wall-E/                  # AGUS
│   ├── GUIA_AGUS_HARDWARE.md      # Guía completa (10 secciones)
│   ├── hardware_specs.yaml        # Template → Agus completa
│   ├── PREGUNTAS_AGUS.md          # 50+ preguntas para contexto
│   ├── cad/                       # STL, STEP, guide
│   ├── pcb/                       # KiCad, gerber, BOM
│   ├── firmware/                  # PlatformIO/Arduino
│   └── photos/                    # Fotos robot real
├── Software de Wall-E/            # GONZALO - BACKEND
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── config/hardware.yaml       # ← Generado desde Agus
│   ├── core/                      # Config, types, hardware abstraction
│   ├── vision/                    # Face tracker
│   ├── voice/                     # STT, TTS, VAD
│   ├── brain/                     # State machine, skills, LLM, memory
│   ├── server/                    # FastAPI + WebSocket
│   └── tests/                     # Mocks + unit tests
├── Pagina Web/                    # GONZALO - FRONTEND
│   ├── cockpit/                   # React dashboard (puerto 5173)
│   │   ├── src/pages/             # Dashboard, ManualControl, Logs, Settings
│   │   ├── src/components/        # Robot3D, MoodIndicator, ConnectionStatus
│   │   └── src/store/             # Zustand store (WS, state, commands)
│   └── landing/                   # Next.js public site (puerto 3000)
│       └── src/app/page.tsx       # Hero, features, hardware, team, CTA
├── Modelo AI/                     # DELFI + GONZALO
│   ├── prompts/
│   │   ├── system.md              # System prompt completo
│   │   └── moods.json             # 10 moods → poses + voice
│   ├── training/                  # train_lora.py, eval_model.py
│   ├── data/                      # Datasets (git-lfs)
│   └── checkpoints/               # LoRA adapters (git-lfs)
└── docs/                          # Documentación viva
    ├── specs/                     # Especificaciones técnicas
    ├── guides/                    # How-to, setup, troubleshooting
    └── meetings/                  # Actas daily async
```

---

## 🔗 LINKS ÚTILES

| Recurso | Link |
|---------|------|
| **Repo GitHub** | https://github.com/RagsnorWolf/wall-e-companion |
| **Issues** | https://github.com/RagsnorWolf/wall-e-companion/issues |
| **Ollama Models** | https://ollama.com/library |
| **Piper Voices** | https://github.com/rhasspy/piper/blob/master/VOICES.md |
| **Whisper.cpp** | https://github.com/ggerganov/whisper.cpp |
| **PCA9685 Datasheet** | https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf |
| **ESP32-S3 Datasheet** | https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf |

---

## 📤 CÓMO USAR ESTE ARCHIVO

### Para compartir con el equipo:
1. **Copiá este archivo completo** y pegalo en un mensaje/archivo compartido
2. **Cada integrante lo pasa a su OpenCode/IA** con: *"Este es el contexto completo del proyecto Wall-E Companion. Soy [Agus/Gonzalo/Delfi]. Ayudame con mi parte."*
3. **La IA ya tendrá todo el contexto** y podrá ayudar directamente sin explicaciones previas

### Para cada integrante en su OpenCode:
```bash
# 1. Clonan repo
git clone https://github.com/RagsnorWolf/wall-e-companion.git
cd wall-e-companion

# 2. Instalan dependencias base
pip install watchdog  # para auto-commit

# 3. Arrancan auto-commit (terminal aparte)
python scripts/auto_commit.py --interval 30 --push

# 4. Levantan stack (mock mode)
docker compose up -d

# 5. Empiezan en su carpeta según su rol
```

---

## ❓ FAQ RÁPIDO

| Pregunta | Respuesta |
|----------|-----------|
| **¿El robot ya existe?** | En construcción. Agus lo está armando. Software se desarrolla en mock mode paralelo. |
| **¿Qué pasa si Agus tarda?** | Software avanza 100% en mock. Integración final = cambiar `mock=False` + copiar `hardware_specs.yaml`. |
| **¿Es obligatorio Docker?** | Sí, para stack consistente (ollama, redis, chroma, api, web). En Windows: Docker Desktop. |
| **¿Qué GPU se necesita?** | Para Ollama: 8GB VRAM (llama3.1:8b 4-bit). Sin GPU: CPU-only (más lento). |
| **¿Cómo agrego un skill nuevo?** | Crea clase en `brain/skills.py` heredando `SkillHandler`, registra en `StateMachine._initialize_skills()`. |
| **¿Puedo usar otro LLM?** | Sí, cambia `OLLAMA_MODEL` en `.env` (ej: `phi3:mini`, `gemma2:9b`, `qwen2.5:7b`). |
| **¿Cómo hago deploy a producción?** | `docker compose --profile production up -d` (añade nginx reverse proxy + SSL). |

---

## 🎯 MILESTONES PRÓXIMOS

| Hito | Target | Responsable |
|------|--------|-------------|
| Mock stack completo funcionando | Semana 1 | Gonzalo |
| Hardware specs completadas por Agus | Semana 2 | Agus |
| Robot físico moviéndose (protoboard) | Semana 2 | Agus |
| Integración robot real + software | Semana 3 | Agus + Gonzalo |
| Personalidad IA v1 entrenada | Semana 3 | Delfi + Gonzalo |
| Landing page deployada | Semana 3 | Gonzalo |
| Demo completo funcional | Semana 4 | Todos |

---

**¡Este archivo ES el proyecto!** Cualquier duda, revisá los `.md` específicos en cada carpeta del repo. El auto-commit guarda todo automáticamente cada 30s.

**Repo:** https://github.com/RagsnorWolf/wall-e-companion