# 🤖 PREGUNTAS PARA AGUS — CONTEXTO ROBOT EXISTENTE
**Copiá y pegale esto a Agus por WhatsApp/Discord. Que responda lo que sepa, "no sé" es válido.**

---

## 1. HARDWARE BÁSICO
- **MCU:** ¿Qué placa usa? (ESP32, ESP32-S3, Arduino Nano, Raspberry Pi Pico, Raspberry Pi 4, Jetson, otro)
- **¿Cómo se programa?** (Arduino IDE, PlatformIO, MicroPython, CircuitPython, Python en Linux, otro)
- **Alimentación:** ¿Batería? ¿Cuántas celdas? ¿Cuánto dura? ¿Tiene BMS? ¿Se carga por USB?
- **Conectividad a PC:** ¿USB serial? ¿WiFi? ¿Bluetooth? ¿Ethernet?

## 2. MOVIMIENTO (SERVOS / MOTORES)
- **¿Cuántos servos/motores tiene?** Número exacto.
- **¿Qué modelos?** (MG90S, SG90, MG996R, Dynamixel XL330, motores DC con encoder, stepper, otro)
- **Driver:** ¿PCA9685? ¿Control directo por GPIO? ¿Driver propio (L298N, TB6612)? ¿Bus I2C/SPI?
- **Rangos reales:** ¿Sabés los ángulos mín/máx de cada junta? ¿O se mueven "a ojo"?
- **¿Tiene calibración guardada?** (EEPROM, NVS, archivo, nada)

## 3. CABEZA / OJOS / EXPRESIONES
- **¿Tiene head pan/tilt?** (sí/no)
- **¿Ojos móviles?** (párpados servos, pantalla OLED, matriz LED, fijos)
- **¿Brazos?** (cuántos DOF cada uno)
- **¿Cuerpo/ruedas?** (diferencial, tracks, estático)

## 4. VISIÓN (CÁMARA)
- **¿Qué cámara?** (USB UVC, CSI Pi Cam, ESP32-CAM, OpenMV, Kinect, RealSense, webcam genérica)
- **Resolución/FPS:** ¿640x480@30? ¿1280x720? ¿Otra?
- **¿Qué hace hoy?** (face tracking, object detection, line following, QR, nada, otro)
- **¿Dónde corre la visión?** (en la MCU, en la PC, en Raspberry Pi, en Jetson)

## 5. AUDIO — MICRÓFONO
- **¿Qué mic?** (INMP441 I2S, MEMS USB, analógico, matriz ReSpeaker, webcam mic, ninguno)
- **Sample rate:** ¿16kHz? ¿44.1kHz? ¿Otro?
- **¿VAD (Voice Activity Detection)?** ¿Cómo detecta "empezó a hablar"?

## 6. AUDIO — ALTAVOZ / TTS
- **¿Qué speaker/amp?** (MAX98357A I2S, PAM8302A, DFPlayer Mini, buzzer pasivo, jack 3.5mm a PC, Bluetooth speaker)
- **¿TTS actual?** (Piper, eSpeak, Festival, Google TTS cloud, ElevenLabs, Coqui, ninguno)
- **Idioma:** ¿Español? ¿Inglés? ¿Otro?
- **¿Reproduce WAV/MP3/PCM raw?**

## 7. CEREBRO / RAZONAMIENTO (LLM)
- **¿Dónde corre el LLM?** (PC local Ollama/LM Studio, Raspberry Pi, Jetson, API cloud OpenAI/Anthropic/Gemini, otro)
- **Modelo:** ¿Llama 3.1 8B? ¿Phi-3? ¿Gemma? ¿GPT-4o? ¿Claude? ¿Otro?
- **¿Tiene system prompt / personalidad definida?** ¿Me lo pasás?
- **¿Memoria?** (contexto ventana, ChromaDB, SQLite, archivos, nada)
- **¿Function calling / tools?** (sí/no, cuáles)

## 8. COMUNICACIÓN ROBOT ↔ PC
- **Protocolo:** ¿JSON por serial? ¿MQTT? ¿ROS/ROS2 topics? ¿WebSocket? ¿gRPC? ¿TCP raw? ¿Otro?
- **Formato comandos:** ¿Ejemplo real de un mensaje que manda la PC al robot?
- **Formato eventos:** ¿Ejemplo real de un mensaje que manda el robot a la PC?
- **Frecuencia:** ¿Cada cuánto mandan state? ¿10Hz? ¿30Hz? ¿Solo on-change?

## 9. SOFTWARE ACTUAL EN PC (SI HAY)
- **¿Qué corre en la PC hoy?** (Python script, Node, Electron, Tauri, web app, nada)
- **Lenguaje/framework:** ¿FastAPI? ¿Flask? ¿Socket.io? ¿PyQt? ¿Tkinter? ¿React + Electron?
- **¿Tiene GUI?** (dashboard, joystick, logs, camera view)
- **¿Skills/behaviors?** (face follow, voice chat, pomodoro, dance, patrol, otro)

## 10. ESTADO ACTUAL — QUÉ FUNCIONA / QUÉ NO
| Función | Funciona | Parcial | No | Notas |
|---------|----------|---------|-----|-------|
| Movimiento servos | ☐ | ☐ | ☐ | |
| Face tracking | ☐ | ☐ | ☐ | |
| STT (voz→texto) | ☐ | ☐ | ☐ | |
| TTS (texto→voz) | ☐ | ☐ | ☐ | |
| LLM chat | ☐ | ☐ | ☐ | |
| Memoria/contexto | ☐ | ☐ | ☐ | |
| Batería monitor | ☐ | ☐ | ☐ | |
| Calibración servos | ☐ | ☐ | ☐ | |
| Emergency stop | ☐ | ☐ | ☐ | |

## 11. ARCHIVOS QUE TENÉS (PASÁME LOS QUE EXISTAN)
- [ ] Esquemático / wiring diagram (foto, KiCad, Fritzing, dibujo a mano)
- [ ] Código firmware (`.ino`, `.cpp`, `.py`, `main.py`, `platformio.ini`)
- [ ] Código PC (carpeta proyecto, `requirements.txt`, `package.json`)
- [ ] Modelos 3D (`.stl`, `.step`, `.f3d`, Fusion360, Onshape link)
- [ ] System prompt / personality (`.txt`, `.md`, `.json`)
- [ ] Config YAML/JSON de pines, servos, calibración
- [ ] Fotos/video del robot funcionando

## 12. BLOQUEOS / DUDAS DE AGUS
- ¿Qué te frena hoy? (piezas, tiempo, código, cableado, no sé cómo seguir)
- ¿Qué te gustaría que haga el robot que NO hace hoy?
- ¿Hay algo que NO quieras tocar? (ej: "el firmware no lo toco más", "la mecánica está fija")

---

## 📤 CÓMO ENVIARME LA INFO
Opción A: **Crea un issue en GitHub** → `https://github.com/RagsnorWolf/wall-e-companion/issues/new` → pega respuestas ahí.
Opción B: **Carpeta en Drive** → sube archivos + un `README_AGUS.md` con respuestas.
Opción C: **Discord/WA** → mandame capturas + texto, yo lo estructuro.

---

**Mientras Agus responde, yo sigo con el software en otro chat.**