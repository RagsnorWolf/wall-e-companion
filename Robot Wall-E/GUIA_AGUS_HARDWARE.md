# 📋 GUÍA PARA AGUS — HARDWARE / ROBOT WALL-E
**Objetivo:** Tener el robot físico funcional (movimiento, visión, audio, energía) para conectar al software al final.
**Tiempo estimado:** 1-2 semanas según piezas disponibles.

---

## 1️⃣ LISTA DE PIEZAS (BOM) — COMPRAR / CONSEGUIR

| Componente | Modelo recomendado | Alternativas | ¿Tenés? | Notas |
|------------|-------------------|--------------|---------|-------|
| **MCU** | ESP32-S3-DevKitC-1 (N16R8) | ESP32-S3-WROOM-1, RP2040 (Pi Pico W) | ☐ | Preferible ESP32-S3 por WiFi+BLE+GPIO |
| **Servos (x7)** | MG90S (metal gears) | SG90 (plástico, más barato), MG996R (más torque) | ☐ | 7 canales: head_pan, head_tilt, eye_L, eye_R, body_lean, arm_L, arm_R |
| **Driver servos** | PCA9685 (16ch PWM, I2C) | 74HC595 + MOSFETs (más trabajo) | ☐ | Dirección I2C 0x40 default |
| **Cámara** | USB 720p UVC (OV2640/IMX219) | Raspberry Pi Camera v2 (CSI, solo Pi), ESP32-CAM (separado) | ☐ | USB es más fácil para PC |
| **Micrófono** | INMP441 (I2S MEMS) | SPH0645LM4H, MSM261S4030H0 | ☐ | I2S directo a ESP32 |
| **Altavoz + Amp** | MAX98357A (I2S Class-D) + 3W 4Ω | PAM8302A, DFPlayer Mini | ☐ | I2S a ESP32 |
| **Batería** | 2x 18650 3000mAh (2S = 7.4V) | 3S LiPo 11.1V (necesita otro BMS) | ☐ | 4-6h autonomía |
| **BMS 2S** | Protección carga/descarga 2S 5A | BMS 3S si usas 3S | ☐ | Con conector USB-C carga |
| **Cargador** | TP4056 USB-C 1A (para 2S) | Módulo carga TP4056 + USB-C aparte | ☐ | |
| **Buck 5V** | LM2596S (3A) o XL4015 (5A) | MP1584EN (1.5A, chiquito) | ☐ | Para servos (5V, 2-3A pico) |
| **LDO 3.3V** | AMS1117-3.3 (1A) | HT7833, ME6211 | ☐ | Para ESP32 + sensores |
| **Sensores extra** | VL53L0X (ToF), MPU6050 (IMU) | HC-SR04 (ultrasonico), BMI270 | ☐ | Opcionales pero recomendados |
| **Chasis** | Filamento PETG/ASA + STL | Madera, acrílico, aluminio | ☐ | Ver §3 |
| **Conectores** | JST-PH 2.0mm, DuPont, XH2.54 | Cables silicona 28AWG | ☐ | |

---

## 2️⃣ ESPECIFICACIONES MECÁNICAS (CAD / IMPRESIÓN)

### Grados de libertad (7 servos)
| ID | Nombre | Rango | Montaje | Prioridad |
|----|--------|-------|---------|-----------|
| 0 | head_pan | -90° a +90° | Cuello (base cabeza) | CRÍTICO |
| 1 | head_tilt | -45° a +45° | Cuello (inclinación cabeza) | CRÍTICO |
| 2 | eye_L | 0° a 100° | Ojo izquierdo (párpado) | ALTA |
| 3 | eye_R | 0° a 100° | Ojo derecho (párpado) | ALTA |
| 4 | body_lean | -30° a +30° | Cuerpo (inclinación torso) | MEDIA |
| 5 | arm_L | -90° a +90° | Brazo izquierdo (hombro) | BAJA |
| 6 | arm_R | -90° a +90° | Brazo derecho (hombro) | BAJA |

### Dimensiones aprox.
- **Altura total:** ~150mm (estilo Wall-E compacto)
- **Base:** ~100x100mm (ruedas/tracks internos)
- **Cabeza:** ~60mm diámetro
- **Peso objetivo:** <500g con batería

### Entregables CAD
1. **STL listos para imprimir** (orientados, con soportes marcados)
2. **STEP/Fusion360** editable para ajustes
3. **Guía de montaje** (PDF: orden, tornillos, cables)
4. **Lista de tornillos/inserts** (M2, M3, heat-set inserts)

---

## 3️⃣ ESQUEMÁTICO ELÉCTRICO (WIRING)

### Pinout ESP32-S3 (propuesta)
```
GPIO 1,2    → I2C SDA/SCL (PCA9685, VL53L0X, MPU6050, INA219)
GPIO 3,4    → I2S Mic (WS, SCK, SD en GPIO 3,4,5)
GPIO 6,7,8  → I2S Speaker (BCLK, LRCLK, DIN)
GPIO 9,10   → UART0 (USB-C debug)
GPIO 11-18  → SPI / libres (expansión)
GPIO 19,20  → USB D-/D+ (nativo)
GPIO 21-38  → Libres (LEDs, botones, más sensores)
```

### Alimentación
```
Batería 2S (7.4V) → BMS → ├─ Buck 5V (3A) → PCA9685 V+ (servos)
                          ├─ LDO 3.3V (1A) → ESP32 3V3, sensores
                          └─ USB-C carga → TP4056 → BMS
```

### Entregables eléctricos
1. **Esquemático KiCad** (`.kicad_sch` + `.kicad_pcb`)
2. **Netlist** y **BOM** (Footprints, LCSC/DigiKey part numbers)
3. **Foto del protoboard** funcionando (antes de PCB)
4. **PCB diseñado** (opcional: 2 capas, 100x80mm, JLCPCB $5)

---

## 4️⃣ FIRMWARE (ESP32) — PROTOCOLO SERIE JSON

El software en PC espera **JSON Lines** (newline-delimited) a **115200 baud 8N1**.

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
{"evt": "state", "data": {"uptime_ms": 12345, "servos": [{"id": "head_pan", "current_angle": 10.5, "target_angle": 10.0, "is_moving": false}], "battery_voltage": 7.82, "battery_percent": 85, "temperature_c": 36.2, "free_heap": 152000}}
{"evt": "ack", "cmd": "move_servo", "ok": true}
{"evt": "error", "cmd": "move_servo", "msg": "servo not found: invalid_id"}
{"evt": "log", "level": "INFO", "msg": "PCA9685 initialized at 0x40"}
```

### Tareas firmware
1. **Inicialización:** PCA9685 @ 50Hz, I2C scan, servos a posición home
2. **Loop principal:** Lee serial → parsea JSON → ejecuta → responde ACK/state
3. **Interpolación suave:** Movimiento servo con rampa (acel/desacel) no bloqueante
4. **Watchdog:** Si no hay comando en 5s → vuelve a idle pose
5. **Batería:** Lee INA219 cada 1s, envía en state, alerta <6.5V
6. **Temperatura:** Lee sensor interno ESP32 o DS18B20
7. **Calibración:** Guarda min/max pulse por servo en NVS/EEPROM

---

## 5️⃣ PRUEBAS DE VALIDACIÓN (CHECKLIST AGUS)

### Nivel 1 — Básico (día 1-2)
- [ ] ESP32 flashea y bootea (LED parpadea)
- [ ] I2C detecta PCA9685 (0x40) + sensores
- [ ] 7 servos responden a comando `move_servo` por serial
- [ ] PCA9685 alimentado por buck 5V (no por USB ESP32)
- [ ] Batería carga y descarga correctamente

### Nivel 2 — Movimiento (día 3-4)
- [ ] `move_servos` mueve múltiples servos simultáneo
- [ ] Interpolación suave (no tirones bruscos)
- [ ] `set_mood` aplica poses predefinidas (idle, curious, happy, sad, alert, thinking, sleeping)
- [ ] `reset` lleva todo a home position
- [ ] `emergency_stop` detiene todo inmediato

### Nivel 3 — Sensores (día 5)
- [ ] Cámara USB detectada en PC (`lsusb` / Administrador dispositivos)
- [ ] Mic I2S graba audio (test: `arecord` o serial plotter)
- [ ] Speaker I2S reproduce WAV/PCM (test: `aplay` o tono generado)
- [ ] ToF/IMU reportan datos en `state` event

### Nivel 4 — Integración (día 6-7)
- [ ] Python mock test: `python scripts/test_hardware_mock.py` pasa
- [ ] Latencia serial <50ms comando→respuesta
- [ ] Autonomía >4h con servos moviéndose cada 10s
- [ ] Sin reinicios espontáneos (watchdog, brownout)

---

## 6️⃣ INFO QUE AGUS DEBE PASAR A GONZALO (ANTES DE CONECTAR)

Crear archivo `hardware_specs.yaml` en repo (carpeta `Robot Wall-E/`):

```yaml
mcu:
  type: "esp32-s3"
  port: "COM3"           # Windows ejemplo
  baudrate: 115200
  protocol: "json_serial"

servos:
  - id: "head_pan"
    channel: 0
    min_pulse: 500
    max_pulse: 2500
    angle_range: [-90, 90]
    default_angle: 0
  - id: "head_tilt"
    channel: 1
    min_pulse: 500
    max_pulse: 2500
    angle_range: [-45, 45]
    default_angle: 0
  - id: "eye_L"
    channel: 2
    min_pulse: 500
    max_pulse: 2500
    angle_range: [0, 100]
    default_angle: 50
  - id: "eye_R"
    channel: 3
    min_pulse: 500
    max_pulse: 2500
    angle_range: [0, 100]
    default_angle: 50
  - id: "body_lean"
    channel: 4
    min_pulse: 500
    max_pulse: 2500
    angle_range: [-30, 30]
    default_angle: 0
  - id: "arm_L"
    channel: 5
    min_pulse: 500
    max_pulse: 2500
    angle_range: [-90, 90]
    default_angle: 0
  - id: "arm_R"
    channel: 6
    min_pulse: 500
    max_pulse: 2500
    angle_range: [-90, 90]
    default_angle: 0

camera:
  type: "usb"
  device_index: 0        # 0 = primera cámara
  width: 640
  height: 480
  fps: 30

audio:
  mic:
    type: "i2s"
    sample_rate: 16000
  speaker:
    type: "i2s"
    sample_rate: 22050

power:
  battery_type: "liion_2s"
  voltage_adc_pin: "GPIO 4"   # si usa divisor resistivo a ADC
  min_voltage: 6.5
  max_voltage: 8.4
```

---

## 7️⃣ PREGUNTAS PARA AGUS (RESPONDER EN REPO / DISCORD)

1. **¿MCU final?** ESP32-S3 / ESP32 / RP2040 / Otro
2. **¿Port serial real?** (COM3, /dev/ttyUSB0, /dev/ttyACM0)
3. **¿Servos exactos?** Modelo, torque, voltaje, deadband
4. **¿PCA9685 dirección I2C?** 0x40 default, ¿cambiada?
5. **¿Cámara USB index?** (0, 1, 2... probar con `python -c "import cv2; print([i for i in range(5) if cv2.VideoCapture(i).read()[0]])")`)
5. **¿Mic/Spkr I2S pines?** (WS, SCK, SD / BCLK, LRCLK, DIN)
6. **¿Batería monitor?** INA219 (I2C) / divisor resistivo a ADC / solo voltage
7. **¿STLs listos?** ¿Dónde subirlos? (repo `Robot Wall-E/cad/` o Drive link)
7. **¿PCB hecho?** ¿KiCad files en `Robot Wall-E/pcb/`?
8. **¿Firmware base subido?** ¿Compila sin errores?

---

## 8️⃣ CRONOGRAMA SUGERIDO (2 SEMANAS)

| Semana | Día | Entregable |
|--------|-----|------------|
| 1 | 1-2 | Piezas llegan, protoboard: ESP32 + PCA9685 + 1 servo test |
| 1 | 3-4 | 7 servos en protoboard, firmware básico JSON serial |
| 1 | 5-7 | Chasis impreso, montaje mecánico, cableado completo |
| 2 | 1-2 | Cámara + Mic + Speaker integrados, test audio/video |
| 2 | 3-4 | Batería + BMS + Buck + LDO, autonomía test |
| 2 | 5 | `hardware_specs.yaml` completado en repo |
| 2 | 6-7 | Integración con software mock (Gonzalo provee script test) |

---

## 9️⃣ ARCHIVOS QUE AGUS SUBE AL REPO (carpeta `Robot Wall-E/`)

```
Robot Wall-E/
├── cad/
│   ├── stl/              # .stl listos para slicer
│   ├── step/             # .step editable
│   └── assembly_guide.pdf
├── pcb/
│   ├── kicad/            # proyecto KiCad completo
│   ├── gerber/           # .zip para JLCPCB
│   └── bom.csv
├── firmware/
│   ├── src/main.cpp      # Arduino/PlatformIO
│   ├── platformio.ini
│   └── lib/              # librerías extra
├── docs/
│   ├── wiring_diagram.png
│   ├── pinout.md
│   └── calibration_procedure.md
├── hardware_specs.yaml   # ← CRÍTICO para Gonzalo
└── photos/               # fotos del robot real
```

---

## 🔟 CONEXIÓN FINAL (CUANDO AMBOS LISTOS)

1. Agus sube `hardware_specs.yaml`
2. Gonzalo actualiza `software/config/hardware.yaml` con esos valores
3. Gonzalo cambia `mock=False` en `software/core/hardware.py`
4. Conectan USB → `docker compose up -d`
5. Cockpit en `http://localhost:5173` muestra robot real
6. ¡Primer "Hola" del Wall-E físico!

---

## 📞 CONTACTO / DUDAS

- **Discord/WA:** Grupo "Wall-E Team"
- **Issues GitHub:** `https://github.com/RagsnorWolf/wall-e-companion/issues`
- **Daily async:** Cada uno actualiza `docs/meetings/YYYY-MM-DD.md` en su carpeta

---

**Agus: empezá por §1 (comprar piezas) y §3 (protoboard). Cualquier duda, avisá. El software va en paralelo y se conecta al final.** 🤖