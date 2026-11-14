# Wall-E Companion Software

Software completo para el robot Wall-E: control de servos, visión por computadora, audio, IA y personalidad autónoma.

## Arquitectura

```
Software de Wall-E/
├── main.py                 # Punto de entrada principal
├── config/
│   └── hardware.yaml       # Configuración de hardware (espejo de Robot Wall-E/hardware_specs.yaml)
├── core/
│   ├── hardware.py         # Capa de abstracción de hardware (config tipada)
│   ├── serial_comm.py      # Comunicación serial JSON Lines con ESP32
│   ├── state_machine.py    # Máquina de estados de comportamiento
│   └── personality.py      # Motor de personalidad y expresiones
├── services/
│   ├── vision.py           # Cámara, detección facial, objetos, emociones
│   ├── audio.py            # Micrófono, Whisper STT, Piper TTS, VAD
│   └── ai_engine.py        # Orquestador central (visión + audio + personalidad)
├── ui/
│   ├── web_server.py       # FastAPI + WebSocket para cockpit web
│   ├── templates/
│   │   └── index.html      # Interfaz de control
│   └── static/
│       ├── style.css       # Estilos del cockpit
│       └── app.js          # Lógica frontend
├── scripts/
│   └── test_hardware.py    # Suite de pruebas de hardware
├── models/                 # Modelos ONNX (Whisper, YOLO, emociones)
├── sounds/                 # Efectos de sonido .wav
├── logs/                   # Logs de aplicación
├── Dockerfile              # Imagen Docker multi-stage
├── docker-compose.yml      # Orquestación de servicios
└── requirements.txt        # Dependencias Python
```

## Inicio Rápido

### 1. Instalar dependencias
```bash
cd "Software de Wall-E"
pip install -r requirements.txt
```

### 2. Configurar hardware
Edita `config/hardware.yaml` con tu puerto serial real (COM3, /dev/ttyUSB0, etc.)

### 3. Ejecutar (modo mock para desarrollo)
```bash
python main.py --mock
```

### 4. Abrir Cockpit Web
Navega a `http://localhost:5173`

## Con Hardware Real

### Docker (recomendado)
```bash
docker compose up -d
# Cockpit en http://localhost:5173
```

### Nativo
```bash
# Asegúrate de tener permisos en el puerto serial
sudo usermod -a -G dialout $USER
# Reconecta sesión

python main.py
```

## Pruebas de Hardware

```bash
# Modo mock (sin hardware)
python scripts/test_hardware.py

# Con hardware real
python scripts/test_hardware.py --real
```

## Protocolo Serial (ESP32 ↔ PC)

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

## Servos (7 canales PCA9685)

| ID | Nombre | Rango | Canal |
|----|--------|-------|-------|
| 0 | head_pan | -90° a +90° | 0 |
| 1 | head_tilt | -45° a +45° | 1 |
| 2 | eye_L | 0° a 100° | 2 |
| 3 | eye_R | 0° a 100° | 3 |
| 4 | body_lean | -30° a +30° | 4 |
| 5 | arm_L | -90° a +90° | 5 |
| 6 | arm_R | -90° a +90° | 6 |

## Moods Predefinidos

- `idle` - Neutral, observando
- `curious` - Cabeza inclinada, ojos abiertos
- `happy` - Expresión alegre, brazos abiertos
- `sad` - Cabeza baja, ojos medio cerrados
- `alert` - Atento, ojos muy abiertos
- `thinking` - Mirando arriba, asimétrico
- `sleeping` - Ojos cerrados, cabeza baja

## API REST (Cockpit)

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/status` | GET | Estado completo del robot |
| `/api/hardware-config` | GET | Configuración de hardware |
| `/api/servo/move` | POST | Mover un servo |
| `/api/servo/move-multiple` | POST | Mover múltiples servos |
| `/api/mood/set` | POST | Cambiar mood |
| `/api/robot/reset` | POST | Reset a posición home |
| `/api/robot/emergency-stop` | POST | Parada de emergencia |
| `/api/robot/speak` | POST | Síntesis de voz |
| `/api/personality/trait` | POST | Ajustar rasgo personalidad |
| `/api/ai/greet` | POST | Disparar saludo |
| `/api/ai/celebrate` | POST | Disparar celebración |
| `/api/ai/surprise` | POST | Disparar sorpresa |

## WebSocket (`/ws`)

Tiempo real a 10Hz con actualizaciones de estado, servo positions, battery, etc.

## Modelos IA Requeridos

Descarga automática en primera ejecución:
- **Whisper** (faster-whisper): STT español - `base` (~142MB)
- **Piper TTS**: Voz español - `es_ES-sharvard-medium` (~50MB)
- **YOLOv8n** (ONNX): Detección objetos - ~6MB
- **YuNet** (ONNX): Detección facial - ~3MB
- **FER2013** (ONNX): Emociones faciales - ~1MB

## Desarrollo

### Estructura de Módulos
```python
from core.hardware import get_hardware_config
from core.serial_comm import SerialComm
from core.state_machine import StateMachine, RobotMode, Mood
from core.personality import PersonalityEngine, PersonalityTrait
from services.vision import VisionService
from services.audio import AudioService
from services.ai_engine import AIEngine
```

### Añadir Comportamientos
1. Extiende `PersonalityEngine` con nuevos métodos de expresión
2. Añade moods en `config/hardware.yaml` y `core/hardware.py`
3. Registra callbacks en `StateMachine` para nuevos eventos

## Licencia

MIT - Proyecto educativo/personal