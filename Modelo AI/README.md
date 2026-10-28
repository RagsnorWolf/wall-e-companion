# 🧠 Modelo AI — Cerebro de WALL-E

El cerebro corre **local** con Ollama. No hay nube, no hay API keys.

## Qué hay acá

```
Modelo AI/
├── prompts/
│   ├── system.md          # personalidad y reglas (fuente de verdad)
│   └── moods.json         # estados emocionales
├── brain/
│   ├── llm.py             # cliente Ollama (stdlib, sin deps)
│   ├── memory.py          # memoria SQLite (turnos + recuerdos)
│   ├── tools.py           # herramientas del robot
│   └── agent.py           # bucle de razonamiento
├── hardware/
│   └── esp32_link.py      # serial M:izq,der @9600 (protocolo de Agus)
├── vision/
│   └── reflex.py          # detección de color + seguimiento
├── legacy/
│   └── walle_cerebro_agus.py   # código original de Agus, intacto
├── build_model.py         # genera Modelfile y crea el modelo
├── cli.py                 # probar sin robot
└── requirements.txt
```

## Arranque rápido

```bash
# 1. Dependencias
pip install -r requirements.txt

# 2. Traer el modelo base
ollama pull qwen2.5:3b

# 3. Crear el modelo "walle" con nuestra personalidad
python build_model.py --create

# 4. Probar
python cli.py --verbose
```

Sin robot conectado entra en **modo simulación**: imprime los comandos que
habría mandado al ESP32. Todo se puede desarrollar en la PC.

## Cómo cambiar la personalidad

1. Editá `prompts/system.md`
2. `python build_model.py --create`
3. Listo. El modelo queda actualizado.

## Herramientas disponibles

| Tool | Qué hace |
|---|---|
| `mover` | Orugas, velocidad -255..255, máximo 3s |
| `detener` | Frena |
| `mirar_color` | Busca rojo/verde/azul/amarillo/naranja |
| `estado_robot` | Conexión, modo, uptime, memoria |
| `recordar` | Guarda un dato |
| `buscar_memoria` | Busca datos guardados |
| `agendar` | Google Calendar o agenda local |

## Arquitectura

```
micrófono → STT → texto
                    ↓
              ┌───────────┐
              │  AGENTE   │
              │  Ollama   │
              │ + memoria │
              │ + tools   │
              └─────┬─────┘
        ┌───────────┼───────────┐
        ▼           ▼           ▼
     orugas       voz       calendario
```

**Reflejos fuera del LLM:** seguimiento de color y `detener` corren en código
duro. El LLM piensa; el código refleja. Así el robot no depende de la latencia
del modelo para esquivar algo o frenar.

## Estado

- [x] Modelo custom en Ollama
- [x] Memoria persistente
- [x] Tools + tool calling
- [x] Serial con reconexión y modo simulación
- [x] Visión por color
- [ ] STT local (Whisper) — hoy el micrófono lo maneja el celular
- [ ] TTS con voz Wall-E (Piper)
- [ ] Wake word
- [ ] Emociones conectadas a hardware
