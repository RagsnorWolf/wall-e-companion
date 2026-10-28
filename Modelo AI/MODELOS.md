# Modelos — qué correr y por qué

WALL-E corre 100% local. La elección del modelo depende de la máquina donde
vive el cerebro, no del robot.

## Regla

El modelo tiene que responder en **menos de 2 segundos** para que la voz se
sienta natural. Si tarda más, la conversación se rompe.

## Referencia de la PC de desarrollo

```
CPU: AMD Ryzen 5 3400G (8 hilos)
RAM: 14 GB
GPU: ninguna (Vega 11 integrada)
```

| Modelo | Peso en RAM | Velocidad estimada | ¿Sirve? |
|---|---|---|---|
| `qwen2.5:14b` | ~9 GB | ~1 tok/s | ❌ swap, inusable |
| `qwen2.5-coder:14b` | ~9 GB | ~1 tok/s | ❌ además es para código |
| `qwen2.5:7b` | ~4.7 GB | ~3-5 tok/s | ⚠️ lento para voz |
| `qwen2.5:3b` | ~2 GB | ~8-12 tok/s | ✅ default |
| `qwen2.5:1.5b` | ~1 GB | ~18-25 tok/s | ✅ si hace falta velocidad |

Con GPU dedicada de 8 GB o más, `qwen2.5:7b` pasa a ser la mejor opción.

## Cómo cambiar de modelo

Sin tocar código:

```bash
python build_model.py --base qwen2.5:7b --name walle --create
python cli.py --model walle
```

O directamente contra el modelo base, sin personalidad:

```bash
python cli.py --model qwen2.5:3b
```

## Por qué no `-coder`

Los modelos `-coder` están afinados para autocompletar y razonar sobre código.
Pierden naturalidad conversacional. Para la personalidad de WALL-E conviene el
`instruct` estándar.

## Temperatura

`0.7` en el Modelfile. Más alta = más creativo e impredecible (malo para tools).
Más baja = repetitivo pero obediente. Para un robot con herramientas, no subir
de `0.8`.
