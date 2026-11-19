# WALL-E · Cerebro Motor (V1 13D + V2 14D) — Simulación + PPO

Este proyecto entrena el **cerebro motor** de WALL-E: un agente de
Reinforcement Learning que aprende a conducir el robot dentro de un sandbox
físico (PyBullet). La idea es entrenar primero en simulación y después
transferir la política al robot físico, calibrando velocidades, fricción y
sensores.

Hay **dos cerebros separados**, en archivos separados, que no se pisan:

| Cerebro | Contrato | Modelo final | Uso |
| --- | --- | --- | --- |
| **V1 13D** | `[x,y,qx,qy,qz,qw,vx,vy,vz,wx,wy,wz,goal]` | `walle_ppo_model_physical.zip` | Simulador interactivo y ESP32. |
| **V2 14D** | `[12 estados, goal, goal_bearing]` | `walle_ppo_model_v2_slow.zip` | Robot lento y estable, giros precisos, exploración de chunks. |

La V2 se documenta completa en la **sección 12**. La V1 sigue intacta y es la
que usa `interactive_walle.py`.

No usa el modelo animado como cuerpo físico: usa un **proxy** (chasis + dos
ruedas/orugas articuladas) que se comporta como el robot real. El modelo de la
Fase 1 se puede agregar como apariencia visual opcional.

---

## Archivos

| Archivo | Para qué sirve |
| --- | --- |
| `walle_env.py` | Entorno Gymnasium + PyBullet V1 (13D, recompensa condicionada). |
| `train_walle.py` | Entrena PPO V1 con física final, OOD y mejoras sim-to-real. |
| `evaluate_walle.py` | Evalúa el modelo V1 por comando, posición y rumbo inicial. |
| `interactive_walle.py` | Simulador con chat, toggle Manual/PPO, HUD, caídas y reportes. |
| `WALL-E Simulador Robot.bat` | Lanzador de doble clic del simulador interactivo. |
| `launcher_walle.py` | Ventana para evaluar, entrenar y abrir TensorBoard. |
| `export_brain.py` | Exporta el actor V1 13D a JSON, header C y guía para el ESP32. |
| `walle_env_v2.py` | Entorno V2 (14D) lento y estable para el robot físico. |
| `train_walle_v2.py` | Currículum PPO V2 de 3 etapas × 100k con checkpoints y reportes. |
| `evaluate_walle_v2.py` | Evaluación determinista del modelo V2 por etapa. |
| `chunk_mapper.py` | Mapa de chunks de 1×1 m (0=desconocido, 1=libre, 2=obstáculo). |
| `walle_body.py` | Autoconocimiento corporal: piezas, vértices, áreas, hitbox, precisión. |
| `walle_sensor.py` | Sensor frontal por raycast de 5 rayos ±25°, 2 m. |
| `walle_navigator.py` | Navegación por fronteras y exploración autónoma con el cerebro V2. |
| `convert_model.py` | Convierte el GLB de la Fase 1 a OBJ (apariencia). |
| `requirements.txt` | Dependencias de Python. |
| `walle_ppo_model_physical.zip` | Cerebro V1 final (13 entradas, 2 acciones). |
| `walle_ppo_model_v2_slow.zip` | Cerebro V2 final (14 entradas, 2 acciones, 301.056 pasos). |
| `walle_ppo_model_v2_slow_stage1.zip` | Modelo V2 al terminar la etapa 1. |
| `walle_ppo_model_v2_slow_stage2.zip` | Modelo V2 al terminar la etapa 2. |
| `walle_ppo_model_v2_slow_stage3.zip` | Modelo V2 al terminar la etapa 3 (= final). |
| `walle_ppo_model_physical_600k_globalx.zip` | Backup del cerebro V1 anterior (recompensa X global). |
| `walle_ppo_model.zip` | Modelo V1 anterior de referencia (12 entradas, solo avance). |
| `walle_ppo_model_50k.zip` | Modelo V1 exacto de 50.000 pasos (referencia histórica). |
| `walle_visual.obj` | Apariencia de WALL-E de la Fase 1 (auto-detectada). |
| `material.mtl`, `material_0.png` | Material y textura del OBJ (deben quedar junto a él). |
| `deploy/` | Pesos exportados y guía de firmware para el ESP32. |
| `reports/` | Reportes `.md` y `.json` de pruebas, currículum V2, evaluación y exploración. |
| `feedback_walle/` | Feedback humano RLHF en CSV y JSONL. |
| `checkpoints/` | Copias del modelo V1 cada 10.000 pasos. |
| `checkpoints_v2/` | Copias del modelo V2 por etapa. |
| `tb_logs/` | Curvas de TensorBoard V1. |
| `tb_logs_v2/` | Curvas de TensorBoard V2. |

---

## 1. Instalación

Requiere **Python 3.10–3.12 (64 bits)**. En Windows, desde PowerShell:

```powershell
cd "E:\Proyectos Ragsnor\Proyecto Wall - E\wall-e-companion\Motor RL"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> En esta PC ya quedó creado el entorno `.venv` dentro de `Motor RL` con
> todas las dependencias instaladas y verificadas (PyBullet 3.2.7 compilado
> para Python 3.12). Para usarlo, alcanza con activarlo:
> `.\.venv\Scripts\Activate.ps1`.

Si PowerShell bloquea la activación:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Verificación rápida:

```powershell
python -c "import gymnasium, pybullet, stable_baselines3; print('OK')"
```

> La primera instalación descarga PyTorch (~2 GB). Es normal que tarde.
> **PyBullet no publica binarios para Windows en PyPI**: pip lo compila desde
> el código fuente. Eso requiere Visual Studio Build Tools con la carga de
> trabajo "Desarrollo para escritorio con C++". Si no querés compilar, la
> alternativa es instalar PyBullet con conda-forge:
> `conda install -c conda-forge pybullet`. En esta PC ya están los Build
> Tools, así que `pip install` funciona (la compilación puede tardar varios
> minutos).

---

## 2. Probar el entorno (sin entrenar)

```powershell
python walle_env.py            # ventana PyBullet con acciones aleatorias
python walle_env.py --direct   # sin ventana, solo consola
```

Deberías ver el chasis amarillo con dos ruedas grises moviéndose de forma
errática dentro del arena. Con `Ctrl+C` se cierra.

---

## 3. Entrenar

```powershell
python train_walle.py --timesteps 300000 --model walle_ppo_model_physical.zip
```

Para **continuar** el cerebro físico existente con el fine-tune OOD:

```powershell
python train_walle.py --resume walle_ppo_model_physical.zip `
  --timesteps 300000 --model walle_ppo_model_physical.zip
```

El entrenamiento guarda `walle_ppo_model_physical.zip` y, al terminar, evalúa
5 episodios por comando (avanzar, retroceder y quedarse quieto) en cinco
posiciones del arena.

### Qué aprende y cómo se mide

- **Recompensa relativa al frente**: el avance se mide proyectando el
  desplazamiento sobre un **rumbo de referencia fijo** (`reference_yaw`), no
  sobre el eje X global ni sobre el yaw instantáneo. El rumbo de referencia se
  fija al inicio del episodio y, en el simulador, al comenzar cada movimiento
  PPO (`env.set_reference_yaw(...)`). Así la política no puede girar en
  círculos para acumular avance y sigue siendo correcta después de un giro o
  con rumbo inicial aleatorio.
- **Arranques OOD**: posición aleatoria en toda la arena (2 m de margen
  respecto de las paredes) y **rumbo aleatorio ±180°**. La política no depende
  de nacer cerca de `x=-18` ni de mirar hacia +X.
- **Comando `goal`**: `+1` avanzar, `-1` retroceder, `0` quedarse quieto.
- **“Quieto” reforzado**: además de castigar la deriva y la velocidad
  residual, se penaliza directamente cualquier acción no nula para que el
  robot frene en vez de arrastrarse.
- **Castigo al yaw rate**: se penaliza el giro no comandado para que la
  política no “haga trampa” rotando para acumular avance frontal. También
  reduce la deriva de rumbo observada en las pruebas.
- **Domain randomization opcional**: con `--domain-randomization`, la masa del
  chasis, la masa y fricción de las ruedas y la fuerza de los motores varían
  ±10–20 % por episodio. Es la recomendación del tutorial de balance bot para
  cerrar la brecha sim-to-real; conviene usarlo en un fine-tune, no en el
  primer entrenamiento desde cero.

Mejoras sim-to-real incluidas:

- **Ruido de sensores** (`obs_noise_std = 0.02`): la política aprende con
  lecturas imperfectas, como las de una IMU/encoders reales.
- **Suavidad de motores** (`action_rate_penalty = 0.05`): evita cambios
  bruscos de velocidad entre pasos consecutivos.
- **Ahorro de batería** (`action_magnitude_penalty = 0.002`): prefiere
  acciones moderadas.
- **Condicionamiento por comando**: un solo cerebro sirve para avanzar,
  retroceder y quedarse quieto.

### Opciones útiles

```powershell
python train_walle.py --timesteps 100000     # más entrenamiento
python train_walle.py --gui                  # ver el entrenamiento (lento)
python train_walle.py --gui-eval             # ver la evaluación final
python train_walle.py --resume walle_ppo_model_physical.zip --timesteps 100000
python train_walle.py --eval-episodes 10     # evaluación final más larga
python train_walle.py --resume walle_ppo_model_physical.zip `
  --timesteps 100000 --domain-randomization  # fine-tune sim-to-real
```

### No frenar la PC durante el entrenamiento

En Windows podés bajar la prioridad y limitar la afinidad a los núcleos 0–3:

```powershell
$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
$work = (Get-Location).Path
$p = Start-Process -FilePath $python `
  -ArgumentList @("train_walle.py", "--resume", "walle_ppo_model_physical.zip",
                  "--timesteps", "300000", "--model", "walle_ppo_model_physical.zip") `
  -WorkingDirectory $work -PassThru -WindowStyle Hidden
$p.PriorityClass = "BelowNormal"
$p.ProcessorAffinity = [IntPtr]15   # núcleos 0, 1, 2 y 3
```

### Ver las curvas con TensorBoard

```powershell
tensorboard --logdir tb_logs
```

Abrí `http://localhost:6006`. La curva `rollout/ep_rew_mean` debería subir y
`rollout/ep_len_mean` estabilizarse. Además, el callback de métricas registra:

| Métrica | Qué mide |
| --- | --- |
| `walle/forward_m` | Avance frontal medio al terminar un episodio de `goal=+1`. |
| `walle/backward_m` | Retroceso frontal medio con `goal=-1`. |
| `walle/stop_drift_m` | Desplazamiento total medio con `goal=0` (deriva). |
| `walle/yaw_drift_deg` | Cambio absoluto de rumbo medio en avance/retroceso. |

Estas curvas permiten distinguir si el agente avanza, retrocede o deriva, algo
que `ep_rew_mean` solo no muestra. Si `stop_drift_m` baja y `forward_m` se
mantiene, el comando “quieto” está mejorando. Si `yaw_drift_deg` sube, revisá
el castigo `yaw_rate_penalty`.

---

## 4. Evaluar el cerebro

```powershell
python evaluate_walle.py                    # GUI: avanzar, retroceder y quieto
python evaluate_walle.py --goal forward     # solo avanzar
python evaluate_walle.py --goal backward    # solo retroceder
python evaluate_walle.py --goal stop        # solo quedarse quieto
python evaluate_walle.py --episodes 5
python evaluate_walle.py --direct           # solo métricas, sin ventana
python evaluate_walle.py --stochastic       # acciones muestreadas
```

### Tests OOD (posición y rumbo)

```powershell
# 10 episodios desde posiciones aleatorias del arena
python evaluate_walle.py --goal forward --episodes 10 --random-starts --direct

# Además, rumbo inicial aleatorio (simula haber girado antes)
python evaluate_walle.py --goal forward --episodes 10 --random-starts --random-yaw --direct

# Rumbo fijo: avanzar mirando a 90°
python evaluate_walle.py --goal forward --episodes 3 --start-yaw 90 --direct

# Posición fija concreta
python evaluate_walle.py --goal backward --episodes 3 --start-pos -10 5 --direct
```

La evaluación reporta **avance frontal** (`info["forward"]`), **desplazamiento
total** y **deriva**. Para `goal=0` la métrica principal es el desplazamiento
total (deriva).

> La GUI se conecta con `--opengl2` porque el renderer OpenGL 3 por defecto
> se cuelga al crear cuerpos con el driver AMD de esta PC. Con OpenGL 2 la
> ventana funciona estable (validado). Si preferís no abrir ventana, usá
> `--direct`.

---

## 5. Simulador interactivo (Manual / PPO)

```powershell
python interactive_walle.py
```

También podés hacer doble clic en `WALL-E Simulador Robot.bat`.

### Toggle Manual / PPO

El botón de la cabecera alterna entre:

| Modo | Avance / retroceso | Giros | Uso |
| --- | --- | --- | --- |
| **Manual (PID)** | PID de posición y rumbo | PID de rumbo | Control clásico, ideal para calibrar. |
| **PPO** | Cerebro `walle_ppo_model_physical.zip` | PID de rumbo | Prueba del cerebro entrenado. |

En modo PPO el cerebro decide la velocidad de las dos orugas con
`goal=+1/-1/0`. El PID de rumbo corrige la deriva para que el avance pedido
sea recto incluso después de un giro. Los giros siguen siendo una orden de
ángulo del PID: el cerebro actual **no tiene comando de giro**.

El modelo se puede cambiar sin tocar el código:

```powershell
python interactive_walle.py --mode ppo --model walle_ppo_model_physical.zip
```

### Spawn, ejes y HUD

- WALL-E aparece en el **origen** `(0, 0, 0.15)` y el chat muestra
  `Posición inicial: X=0.00, Y=0.00, Z=0.00`.
- **Eje X rojo** = adelante; **X−** = atrás.
- **Eje Y verde** = izquierda; **Y−** = derecha.
- **Z+** = arriba.
- Hay marcas cada metro y una marca de origen.
- El **HUD flotante** muestra `x, y, z`, `yaw/pitch/roll`, velocidad lineal y
  `up.z`. La Z visible es relativa al suelo (`HOME_BASE_Z = 0.15`).

### Caídas y auto-recuperación

Si `up.z < 0.5`, WALL-E avisa:

> “¡Me caí! Iniciando secuencia de recuperación...”

Aplica un torque de **35 N·m** para enderezarse, espera **30 pasos** de
asentamiento y, si no lo logra en **240 pasos**, vuelve a la última pose
estable. El evento queda registrado en el reporte (`caidas`,
`recuperaciones`, `fallos_recuperacion`) y la orden pendiente continúa.

### Órdenes de ejemplo

- `avanza 2 metros`
- `retrocede 50 cm`
- `gira 90 grados`
- `gira 45 grados a la izquierda`
- `detente`

### Reportes automáticos

Cada orden genera dos archivos en `reports/`:

- `test_YYYYMMDD_HHMMSS_<slug>.md`
- `test_YYYYMMDD_HHMMSS_<slug>.json`

Incluyen timestamp, orden, tipo, modelo, posición inicial/final, yaw/pitch/roll,
distancia recorrida, errores de trayectoria, caídas, recuperaciones, fallos,
tiempo total y pasos. Al calificar con los botones, el reporte se regenera con
`calificacion_humana`.

En el chat de Tkinter se muestra un resumen:

> `Test completado: Avanzó 2.01 m. 0 caídas. Reporte guardado.`

### Feedback humano (RLHF)

Los botones de calificación guardan la experiencia en:

- `feedback_walle/experiencias_walle.csv`
- `feedback_walle/experiencias_walle.jsonl`

El JSONL incluye los campos nuevos (`caidas`, `recuperaciones`,
`fallos_recuperacion`, `calificacion`). **El feedback se registra para un
futuro fine-tune; no modifica los pesos PPO automáticamente.**

### CLI del simulador

```powershell
python interactive_walle.py --mode ppo
python interactive_walle.py --model ruta\otro_modelo.zip
python interactive_walle.py --reports-dir reports\pruebas
python interactive_walle.py --feedback-dir feedback_walle\sesion_01
python interactive_walle.py --direct --command "avanza 2 metros" --command "gira 90 grados"
python interactive_walle.py --direct --command "avanza 1 metro" --feedback good
```

`--direct` no abre PyBullet ni Tkinter: imprime el resultado y genera los
reportes. Es ideal para pruebas automáticas.

---

## 6. Exportar el cerebro al ESP32

```powershell
python export_brain.py
python export_brain.py --model walle_ppo_model_physical.zip --out-dir deploy
python export_brain.py --samples 256
```

Genera:

| Archivo | Uso |
| --- | --- |
| `deploy/walle_brain_weights.json` | Pesos + metadatos del mapeo 13D. |
| `deploy/walle_brain_weights.h` | Arrays C y `walle_brain_forward()`. |
| `deploy/README_ESP32.md` | Guía de sensores, acciones y firmware. |

### Arquitectura exportada

```
13 entradas → Linear(128) → Tanh → Linear(128) → Tanh → Linear(2) → recorte [-1, 1]
```

Se exporta la **media determinista** de la gaussiana del actor, tal como la usa
`model.predict(..., deterministic=True)`. La salida es lineal y el despliegue
debe recortarla a `[-1, 1]` antes de escalar a las orugas.

### Observación 13D (sin normalización)

No se usa `VecNormalize`: la red recibe los 13 valores **crudos** en este
orden. En el ESP32 no hay que aplicar media/desvío estándar.

| Índice | Contenido |
| --- | --- |
| 0–1 | Posición `x`, `y` de la base |
| 2–5 | Orientación como cuaternión `(qx, qy, qz, qw)` |
| 6–8 | Velocidad lineal `(vx, vy, vz)` |
| 9–11 | Velocidad angular `(wx, wy, wz)` |
| 12 | Comando: `+1` avanzar, `-1` retroceder, `0` quieto |

### Acción 2D

| Índice | Contenido |
| --- | --- |
| 0 | Velocidad de la oruga izquierda |
| 1 | Velocidad de la oruga derecha |

Se multiplican por `max_wheel_speed = 10 rad/s` y se aplican con
`setJointMotorControl2` en modo velocidad. En el ESP32 hay que calibrar
`PWM = action * PWM_MAX` con control de velocidad por encoder para reproducir
esa escala.

### Self-test

La exportación compara NumPy contra Stable Baselines3 en observaciones
aleatorias y reales. Si `max_abs_diff > 1e-5`, no exporta los pesos. El
resultado queda en el JSON y en el header.

---

## 7. Cómo aprende: espacio, acción y recompensa

### Recompensa

| Evento | Valor |
| --- | --- |
| Comando avanzar (`goal=+1`) | `+ delta_forward × 20` |
| Comando retroceder (`goal=-1`) | `- delta_forward × 20` |
| Comando quieto (`goal=0`) | `- ||delta_xy|| × 20 × 2` |
| Velocidad residual con comando quieto | `-0.5 × (||v||² + 0.5 × ||w||²)` |
| Acción no nula con comando quieto | `-1.0 × ||a||²` |
| Giro no comandado (yaw rate) | `-0.05 × |wz|` |
| Costo de tiempo por paso | `-0.01` |
| Cambio brusco de acción | `-0.05 × ||a_t - a_{t-1}||²` |
| Acción grande (batería) | `-0.002 × ||a_t||²` |
| Choque contra pared | **-10.0** y termina el episodio |
| Volcamiento | **-10.0** y termina el episodio |

`delta_forward` es la proyección del desplazamiento sobre el **rumbo de
referencia** fijado al inicio del episodio (o al comenzar un movimiento PPO):

```
delta_forward = dx · cos(reference_yaw) + dy · sin(reference_yaw)
```

Usar un rumbo fijo es importante: si se usara el yaw instantáneo, la política
podría girar en círculos y acumular `delta_forward` sin trasladarse de verdad
(reward hacking). El castigo al yaw rate se puede ajustar con
`--yaw-rate-penalty`; en los fine-tunes finales se usó `0.5`.

El episodio también termina (truncado) a los **1.000 pasos**, que a 60 Hz son
~16,7 segundos.

### Física

- PyBullet a **240 Hz**, 4 subpasos por acción → decisiones a **60 Hz**.
- Arena de **40 × 40 m** (±20 m) con paredes estáticas de 0,6 m.
- Entrenamiento: arranque aleatorio en toda la arena (2 m de margen) y rumbo
  ±180°. Evaluación: centro `(0, 0)` por defecto, con opción de posición y
  rumbo aleatorios.
- Chasis de **3,5 kg** (0,50 × 0,36 × 0,28 m) + dos ruedas de 0,45 kg
  (radio 0,09 m), unidas por joints revolutos. La base queda a 1 cm del
  piso para evitar que el robot bascule sobre el eje único de las ruedas.
- Torque máximo por oruga: **1,0 N·m**. Velocidad máxima: **10 rad/s**.
  Estos valores priorizan estabilidad y suavidad para el robot físico.

---

## 8. Del sandbox al robot físico (sim2real)

La política devuelve **velocidades normalizadas**, no PWM directo. Para
transferirla al WALL-E real:

1. Medir la velocidad real máxima de cada oruga (m/s) y su relación con PWM.
2. Ajustar en el entorno `max_wheel_speed` hasta que la velocidad simulada
   coincida con la real.
3. Calibrar fricción (`lateralFriction`) y torque (`max_force`) con el peso y
   los motores reales.
4. Usar el mismo orden de observaciones: posición, cuaternión y velocidades
   de la IMU/encoders del robot.
5. Empezar con el robot colgado o sobre bloques, validar que las orugas giren
   en el sentido correcto, y recién después apoyarlo.

El contrato de hardware está en
`..\Robot Wall-E\hardware_specs.yaml`. Cuando el robot físico esté listo, se
puede reemplazar el proxy por un URDF real y reentrenar con la misma política
como punto de partida.

### Hardware mínimo recomendado

- **ESP32** o ESP32-S3 (Wi-Fi/Bluetooth, no Arduino Uno).
- Driver **TB6612FNG** (o DRV8833) para los dos motores.
- **2 motores DC con encoder y caja reductora**.
- **IMU** (MPU6050 + Madgwick o BNO055) para el cuaternión y las velocidades
  angulares.
- Servos **MG90S** para brazos y **SG90** para cuello/cabeza.
- Batería LiPo 7.4 V o 2×18650 con regulador; una fuente USB de 5 V/2 A puede
  no alcanzar para los motores.

### Limitaciones actuales

- El cerebro **V1** no tiene comando de giro: para girar en el robot físico usá
  un lazo de rumbo (PID) sobre la IMU, igual que en el simulador. El cerebro
  **V2 14D** sí aprende giros con `goal_angle` (ver sección 12).
- El comando PPO `goal=0` (“quieto”) todavía es más débil que avance y
  retroceso. En el simulador, “detente” usa frenado activo, no el PPO.
- No hay sensores exteroceptivos (LIDAR/cámara): la política solo usa
  propiocepción.
- El `domain randomization` de masa, fricción y fuerza ya está implementado
  (`--domain-randomization`), pero está desactivado por defecto. Conviene
  activarlo en un fine-tune, no en el primer entrenamiento desde cero.
- El arena es fijo; se puede aleatorizar para una política más robusta.
- El feedback RLHF se registra, pero no reentrena automáticamente los pesos.

---

## 9. Auditoría y diferencias con la V2 de ChatGPT

La auditoría de ChatGPT propuso una **V2 de 14 dimensiones** con
`sin/cos(heading_error)`, fuerzas diferenciales por oruga, currículum
forward/reverse/turn/combined y `domain randomization`. Esa V2 **no es
compatible** con el cerebro actual de 13D: cambiar la entrada obliga a
entrenar desde cero y a reexportar los pesos.

Decisiones de esta implementación:

- Se mantiene el contrato **13D** y la exportación determinista al ESP32.
- Se corrigió la recompensa para que sea **relativa al frente** del robot.
- Se amplió el rumbo de entrenamiento a **±180°**.
- Se agregó una penalización directa a las acciones no nulas en `goal=0`.
- Los giros siguen siendo **PID de rumbo**, no PPO.
- La evaluación mide **avance frontal**, no solo `x` global.

Pendiente para una futura V2: observación de 14D con `sin/cos` del error de
rumbo, recompensa por alineación, currículum de giros y `domain
randomization` de masa/fricción. Eso permitiría que el PPO también aprenda a
girar, pero requiere un cerebro nuevo y otro exportador.

> **Actualización:** esa V2 ya está implementada, en archivos separados y sin
> tocar la V1. Ver la **sección 12**. La observación final no usa `sin/cos` del
> ángulo absoluto, sino `goal` + `goal_bearing` (egocéntrico), porque el
> `sin/cos` absoluto perdía el signo de avance/retroceso.

### Aportes del tutorial de balance bot (MechatronicStore)

El tutorial de PPO + MuJoCo para un robot balancín aportó varias prácticas
que se incorporaron sin romper el contrato 13D:

| Idea del tutorial | Aplicación en WALL-E |
| --- | --- |
| Castigar el `yaw rate` para que no rote “gratis” | `yaw_rate_penalty` en el entorno y en `train_walle.py`. |
| `domain randomization` en fase 2 | `--domain-randomization` para masa, fricción y fuerza. |
| Leer curvas por comando, no solo la recompensa media | Métricas `walle/forward_m`, `walle/backward_m`, `walle/stop_drift_m`, `walle/yaw_drift_deg`. |
| La observación debe significar lo mismo en sim y hardware | Guía de puesta en marcha del ESP32 con signos de IMU, unidades y prueba en banco. |
| La salida se recorta a `[-1, 1]` antes de escalar a PWM | Ya estaba implementado en `export_brain.py` y el header C. |
| Cuidado con el *reward hacking* | Es exactamente lo que pasaba en `goal=0`: el PPO se arrastraba en vez de frenar. |

La diferencia principal es que el tutorial usa MuJoCo y un péndulo invertido;
WALL-E usa PyBullet y un robot de orugas. El concepto de recompensa y las
prácticas de sim-to-real son transferibles; el modelo físico no.

---

## 10. Problemas comunes

| Problema | Solución |
| --- | --- |
| `ModuleNotFoundError: pybullet` | Activá el venv y reinstalá `requirements.txt`. |
| PyBullet abre y se cierra | Probá `python walle_env.py --direct` para ver el error real. |
| La GUI se cuelga con AMD | Usá `--opengl2` (ya es el default del simulador). |
| Entrenamiento muy lento | Cerrá otras apps; usá `--gui` solo para mirar. En CPU suele tardar pocos minutos. |
| No aprende / recompensa plana | Entrená más pasos (100k–300k) y revisá TensorBoard. |
| El modelo no existe al evaluar | Corré primero `python train_walle.py`. |
| `PPO.load` falla por dimensiones | Usá un modelo de 13D; los de 12D no son compatibles. |
| El robot deriva en “quieto” | Usá “detente” (frenado activo) o seguí entrenando `goal=0`. |
| No se genera el reporte | Verificá permisos de escritura en `reports/`. |
| La GUI no responde | Cerrá la ventana de PyBullet o `Ctrl+C`; luego reiniciá el script. |

---

## 11. Comandos de referencia rápida

```powershell
# Instalar
python -m pip install -r requirements.txt

# Probar el mundo
python walle_env.py

# Entrenar el cerebro físico (300k pasos)
python train_walle.py --timesteps 300000 --model walle_ppo_model_physical.zip

# Fine-tune OOD sobre el cerebro existente
python train_walle.py --resume walle_ppo_model_physical.zip `
  --timesteps 300000 --model walle_ppo_model_physical.zip

# Ver curvas
tensorboard --logdir tb_logs

# Evaluar por comando
python evaluate_walle.py --goal forward
python evaluate_walle.py --goal backward
python evaluate_walle.py --goal stop

# Test OOD multi-posición y multi-rumbo
python evaluate_walle.py --goal forward --episodes 10 --random-starts --random-yaw --direct

# Simulador interactivo
python interactive_walle.py
python interactive_walle.py --mode ppo
python interactive_walle.py --direct --command "avanza 2 metros" --command "gira 90 grados"

# Exportar al ESP32
python export_brain.py
```

---

## 12. Fase 3 — Cerebro V2 (14D): lento, estable y explorador

La V1 13D está pensada para el simulador. El robot físico de madera y cartón
necesita otra prioridad: **no velocidad, sino estabilidad, suavidad y
seguridad**. Por eso se creó una V2 separada, en archivos nuevos, que **no
modifica** `walle_env.py`, `train_walle.py`, `evaluate_walle.py` ni
`walle_ppo_model_physical.zip`.

### 12.1 Contrato V2 definitivo

**Observación (14D, sin normalizar):**

```
[x, y, qx, qy, qz, qw, vx, vy, vz, wx, wy, wz, goal, goal_bearing]
```

| Índice | Contenido |
| --- | --- |
| 0–1 | Posición `x`, `y` de la base |
| 2–5 | Cuaternión `(qx, qy, qz, qw)` |
| 6–8 | Velocidad lineal `(vx, vy, vz)` |
| 9–11 | Velocidad angular `(wx, wy, wz)` |
| 12 | `goal`: `+1` avanzar, `-1` retroceder, `0` solo girar |
| 13 | `goal_bearing`: `wrap(goal_angle - yaw)` en `[-π, π]` |

`goal_bearing` es **egocéntrico**: le dice a la red cuánto y hacia qué lado
girar sin que tenga que combinar el cuaternión con el ángulo global. El signo
de `goal` es imprescindible: sin él, avanzar y retroceder con el mismo rumbo
producen la misma observación.

> La primera versión de la V2 usaba `sin(goal_angle), cos(goal_angle)`. Perdía
> el signo de `goal` y la política no distinguía avanzar de retroceder: la
> etapa 1 quedó en 0,00 m de avance. Con `goal + goal_bearing` pasó a +2,02 m
> deterministas.

**Acción (2D):** `[oruga_izquierda, oruga_derecha]` en `[-1, 1]`.

**Red:** `14 → 128 → 128 → 2`, activación **Tanh**, salida lineal (media
gaussiana). No se usa `VecNormalize`.

### 12.2 Física y recompensa

- `max_wheel_speed = 2.5 rad/s`, `max_force = 0.5 N·m`.
- Control a **60 Hz**, física a **240 Hz**.
- `spinningFriction = 0.0` en las ruedas (con 0.05 el motor no vencía la
  resistencia al giro).
- Masa total aleatoria **3.0–6.0 kg** por episodio.
- **5 cajas** estáticas.
- `reset()` en `X=0`, `Y=0`, yaw aleatorio 0–360°.
- Tilt > **15°** termina el episodio con **-10**.
- Colisión con pared o caja: **-10** y fin del episodio.
- Castigo continuo por pitch/roll y por brusquedad (jerkiness).
- Filtro exponencial de acción `action_smoothing = 0.7`.
- Hitbox de colisión **30 × 30 × 28 cm**, radio envolvente **25 cm**
  (el chasis visual mide 35 × 30 × 28 cm).

Recompensas principales:

| Etapa | Recompensa |
| --- | --- |
| 1 · avanzar/retroceder | `goal × delta_forward × forward_reward_scale` − `0.05 × error_rumbo` − `0.2 × |wz|` |
| 2 · giros | `heading_reward_scale × progreso_rumbo` − castigo por trasladarse |
| 3 · combinado | avance/retroceso + orientación + castigos de estabilidad |

El avance se mide contra `goal_angle` (el frente comandado), no contra el yaw
instantáneo ni contra el eje X global. Así se evita el reward hacking de girar
en círculos que apareció en la V1.

### 12.3 Currículum y entrenamiento

```powershell
python train_walle_v2.py --timesteps-per-stage 100000 --stages 1,2,3 --seed 42
```

Se ejecutó con prioridad **BelowNormal** y afinidad a los núcleos **0–3**:
**301.056 pasos en 6,67 minutos**, sin volcaduras en ninguna etapa.

Resultados de entrenamiento (política estocástica; últimos 20% entre paréntesis):

| Etapa | Episodios | Recompensa media | Últimos 20% | Error de ángulo | Progreso | Volcaduras | Choques | Éxito 5° |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 · recto | 167 | 0.83 | 23.89 | 8.54° | +1.61 m | 0 | 0 | — |
| 2 · giros | 211 | 19.24 | 41.08 | 31.17° | +0.00 m | 0 | 0 | 40.8% |
| 3 · combinado | 101 | 42.43 | 50.24 | 9.76° | +2.95 m | 0 | 6 | — |

El éxito estocástico de la etapa 2 es bajo porque la política explora y la
tolerancia de 5° es estricta. **La métrica válida para el robot real es la
evaluación determinista.**

### 12.4 Evaluación determinista del modelo final

```powershell
python evaluate_walle_v2.py
```

| Prueba | Resultado |
| --- | --- |
| Etapa 1 · 6 episodios | recompensa **+20.88**, avance **2.02 m**, error **2.79°**, 0 volcaduras, 0 choques |
| Etapa 2 · 18 episodios (±45°, ±90°, ±180°) | recompensa **+52.25**, error medio **2.71°**, máximo **4.16°**, éxito **100%** a 5° y 10° |
| Etapa 3 · 10 episodios combinados | recompensa **+54.16**, error **6.78°**, progreso **+1.36 m**, **0 choques** |

Conclusión: el cerebro V2 es lento, estable y preciso; no se volcó ni chocó en
la evaluación determinista.

### 12.5 Autoconocimiento corporal — `walle_body.py`

El robot conoce su cuerpo con **11 piezas**: chasis, cabeza, rostro/pantalla,
dos ojos, dos brazos, dos manos y dos orugas. Cada pieza declara:

- centro, tamaño, masa y material;
- **8 vértices** y **6 caras** con centros y normales;
- área de superficie y área de apoyo;
- precisión (2 cm / 2.5°).

Totales: **4.89 kg** nominales, **35 × 30 × 28 cm** visuales, hitbox
**30 × 30 × 28 cm**, área de apoyo **0.1610 m²**, superficie **1.3481 m²**.
`awareness()` devuelve todo en coordenadas del mundo, incluida la **pose
inicial** (x, y, z, yaw) que el robot debe recordar.

```powershell
python walle_body.py    # self-test + resumen
```

### 12.6 Sensor frontal — `walle_sensor.py`

Raycast de **5 rayos** entre **-25° y +25°**, alcance **2 m**, desde el origen
frontal del cuerpo `(0.23, 0.0, 0.10)` local. Devuelve distancia frontal,
izquierda, derecha, mínima, puntos de impacto, tipo de objeto (pared, caja,
piso, robot, desconocido) y `path_clear` (frente > 0.45 m). Puede dibujar los
rayos en la GUI (verde libre, rojo impacto).

```powershell
python walle_sensor.py  # self-test con un mundo mínimo
```

### 12.7 Mapa de chunks y exploración — `chunk_mapper.py` + `walle_navigator.py`

`chunk_mapper.py` divide el mundo en celdas de **1×1 m**:

```
0 = DESCONOCIDO
1 = LIBRE
2 = OBSTÁCULO
```

`walle_navigator.py` agrega:

- actualización del mapa con la posición y los obstáculos detectados;
- marcado de celdas libres barridas por los rayos;
- búsqueda **BFS** de la frontera desconocida más cercana;
- cálculo de `goal` / `goal_angle` para el cerebro V2;
- **giro grueso** por el camino corto si el objetivo queda a más de 50°;
- **giro de seguridad** si el frente está a menos de 0.45 m;
- recuperación con `reset_robot_only()` sin perder el mapa;
- reporte de cobertura, celdas libres, obstáculos, visitadas y chunks
  cargados.

```powershell
# Self-test del mapa (sin PyBullet)
python walle_navigator.py

# Exploración sin GUI (12×12 m)
python walle_navigator.py --model walle_ppo_model_v2_slow.zip `
  --steps 1200 --arena-half-size 6 --target-coverage 0.5

# Exploración con GUI
python walle_navigator.py --model walle_ppo_model_v2_slow.zip `
  --steps 3000 --gui --arena-half-size 6 --target-coverage 0.5
```

Prueba de 1.200 pasos en 12×12 m: cobertura **24.3%**, **3 chunks**
cargados, **0 choques**, **0 volcaduras**, 145 pasos de giro grueso y **3.28 m**
recorridos. La cobertura crece despacio porque el robot es lento por diseño
(~0.22 m/s).

### 12.8 Reportes generados

- `reports/v2_curriculum_report.json` / `.md` — entrenamiento por etapa.
- `reports/v2_evaluation_report.json` / `.md` — evaluación determinista.
- `reports/v2_exploration_report.json` / `.md` — cuerpo, sensor, mapa y chunks.

### 12.9 Criterios de aceptación V2

- [x] Observación exactamente **14D**.
- [x] Red **128×128 Tanh**.
- [x] `max_wheel_speed = 2.5`, `max_force = 0.5`.
- [x] Origen `X=0`, `Y=0` y yaw aleatorio 0–360°.
- [x] Masa total **3.0–6.0 kg** por episodio.
- [x] **5 cajas** estáticas.
- [x] Tilt > 15° termina con **-10**.
- [x] Colisión con pared/caja: **-10** y fin.
- [x] Penalización por jerkiness y filtro de acción.
- [x] Currículum **3 × 100k**.
- [x] `chunk_mapper.py` creado y validado.
- [x] Modelo final **`walle_ppo_model_v2_slow.zip`**.
- [x] Reporte de recompensa media, error de ángulo y volcaduras.
- [x] Cuerpo, rostro, manos, orugas, vértices, áreas y precisión.
- [x] Sensor frontal y hitbox de **25–30 cm**.
- [x] Carga autónoma de chunks/áreas nuevas.
- [x] **V1 13D intacta**.

### 12.10 Limitaciones y próximos pasos V2

1. Falta un **`export_brain_v2.py`** que exporte la red 14D y documente
   `goal_bearing` para el ESP32. El exportador actual es el de la V1 13D.
2. Las manos y brazos están declarados en el esquema corporal, pero la pinza
   **no está articulada** en PyBullet. La carga de chunks es lógica (marcar la
   celda como cargada), no física.
3. El mapa de chunks es **2D** (x, y): no modela altura ni voladizos.
4. La exploración es lenta (~0.22 m/s). Para el robot real conviene un modo
   "exploración" con velocidad moderada y el mismo cerebro.
5. Falta calibrar en el robot físico: masa real, centro de gravedad, radio de
   oruga, `PWM → rad/s`, signos de IMU y frenado.
6. El modelo V2 **no se probó todavía** en el ESP32 ni en el robot de madera.
7. `interactive_walle.py` sigue usando la V1; integrar el navegador y el
   sensor V2 en el simulador interactivo es el siguiente paso natural.
