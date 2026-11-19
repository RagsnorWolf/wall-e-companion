"""
WALL-E · Exportación del cerebro PPO para el ESP32
==================================================

Extrae la red del actor (política determinista) de
`walle_ppo_model_physical.zip` y genera:

- deploy/walle_brain_weights.json  -> pesos + metadatos del mapeo 13D.
- deploy/walle_brain_weights.h     -> arrays C + función inline de inferencia.
- deploy/README_ESP32.md           -> mapeo de sensores y ejemplo de uso.

La política exportada es la media de la distribución gaussiana (acción
determinista), tal como la usa `model.predict(..., deterministic=True)`.
La salida es lineal y se recorta a [-1, 1] antes de escalar a las orugas.

Uso:
    python export_brain.py
    python export_brain.py --model walle_ppo_model_physical.zip --out-dir deploy
    python export_brain.py --samples 256 --skip-env-test
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = SCRIPT_DIR / "walle_ppo_model_physical.zip"
DEFAULT_OUT_DIR = SCRIPT_DIR / "deploy"

OBS_ORDER = (
    "x_m",
    "y_m",
    "qx",
    "qy",
    "qz",
    "qw",
    "vx_m_s",
    "vy_m_s",
    "vz_m_s",
    "wx_rad_s",
    "wy_rad_s",
    "wz_rad_s",
    "goal",
)

OBS_DESCRIPTIONS = {
    "x_m": "Posición X en el mundo (m). En el ESP32: odometría o 0.0 si no hay localización.",
    "y_m": "Posición Y en el mundo (m). En el ESP32: odometría o 0.0 si no hay localización.",
    "qx": "Componente X del cuaternión de orientación (IMU fusionada).",
    "qy": "Componente Y del cuaternión de orientación (IMU fusionada).",
    "qz": "Componente Z del cuaternión de orientación (IMU fusionada).",
    "qw": "Componente W del cuaternión de orientación (IMU fusionada).",
    "vx_m_s": "Velocidad lineal X en el mundo (m/s). En el ESP32: encoders + IMU o 0.0.",
    "vy_m_s": "Velocidad lineal Y en el mundo (m/s). En el ESP32: encoders + IMU o 0.0.",
    "vz_m_s": "Velocidad lineal Z en el mundo (m/s). Normalmente 0.0.",
    "wx_rad_s": "Velocidad angular X en el mundo (rad/s). Giroscopio.",
    "wy_rad_s": "Velocidad angular Y en el mundo (rad/s). Giroscopio.",
    "wz_rad_s": "Velocidad angular Z en el mundo (rad/s). Giroscopio (yaw rate).",
    "goal": "+1 avanzar, -1 retroceder, 0 quedarse quieto. No se corrompe con ruido.",
}


# --------------------------------------------------------------------------- #
# Extracción de pesos
# --------------------------------------------------------------------------- #
def load_actor_weights(model_path: Path) -> tuple[dict[str, np.ndarray], Any]:
    """Carga el PPO y devuelve las matrices del actor como NumPy float32."""
    from stable_baselines3 import PPO

    model = PPO.load(str(model_path), device="cpu")
    obs_shape = tuple(model.observation_space.shape or ())
    if obs_shape != (13,):
        raise SystemExit(
            f"El modelo {model_path.name} usa observación {obs_shape}; "
            "este exportador espera el cerebro físico de 13D."
        )

    state = model.policy.state_dict()
    required = {
        "fc1_weight": "mlp_extractor.policy_net.0.weight",
        "fc1_bias": "mlp_extractor.policy_net.0.bias",
        "fc2_weight": "mlp_extractor.policy_net.2.weight",
        "fc2_bias": "mlp_extractor.policy_net.2.bias",
        "fc3_weight": "action_net.weight",
        "fc3_bias": "action_net.bias",
    }
    missing = [key for key in required.values() if key not in state]
    if missing:
        raise SystemExit(
            "La arquitectura del modelo no coincide con la esperada. "
            f"Faltan claves: {missing}"
        )

    weights = {
        name: state[key].detach().cpu().numpy().astype(np.float32)
        for name, key in required.items()
    }

    expected = {
        "fc1_weight": (128, 13),
        "fc1_bias": (128,),
        "fc2_weight": (128, 128),
        "fc2_bias": (128,),
        "fc3_weight": (2, 128),
        "fc3_bias": (2,),
    }
    for name, shape in expected.items():
        if weights[name].shape != shape:
            raise SystemExit(
                f"Peso {name}: forma {weights[name].shape}, esperaba {shape}."
            )
    return weights, model


# --------------------------------------------------------------------------- #
# Inferencia NumPy (referencia para el self-test y para el ESP32)
# --------------------------------------------------------------------------- #
def numpy_forward(obs: np.ndarray, weights: dict[str, np.ndarray]) -> np.ndarray:
    """13 -> 128 tanh -> 128 tanh -> 2 lineal. Devuelve la acción sin recortar."""
    x = np.asarray(obs, dtype=np.float32).reshape(13)
    h1 = np.tanh(weights["fc1_weight"] @ x + weights["fc1_bias"])
    h2 = np.tanh(weights["fc2_weight"] @ h1 + weights["fc2_bias"])
    return weights["fc3_weight"] @ h2 + weights["fc3_bias"]


def self_test(
    model: Any,
    weights: dict[str, np.ndarray],
    samples: int,
    seed: int,
    use_env: bool,
) -> dict[str, float]:
    """Compara la inferencia NumPy contra SB3 en observaciones reales/aleatorias."""
    rng = np.random.default_rng(seed)
    observations: list[np.ndarray] = []

    low = model.observation_space.low.astype(np.float32)
    high = model.observation_space.high.astype(np.float32)
    for _ in range(samples):
        observations.append(rng.uniform(low, high).astype(np.float32))

    if use_env:
        from walle_env import WallEEnv

        env = WallEEnv(render_mode=None, show_proxy_visuals=False)
        try:
            goals = (-1.0, 0.0, 1.0)
            for index in range(samples):
                goal = goals[index % len(goals)]
                env.reset(
                    seed=seed + index,
                    options={"goal": goal},
                )
                observations.append(env.get_observation(goal))
        finally:
            env.close()

    max_diff = 0.0
    max_raw_action = 0.0
    clipped = 0
    for obs in observations:
        expected = np.asarray(
            model.predict(obs, deterministic=True)[0], dtype=np.float32
        ).reshape(2)
        raw = numpy_forward(obs, weights)
        # SB3 recorta las acciones al espacio de acción antes de devolverlas.
        actual = np.clip(raw, -1.0, 1.0)
        max_diff = max(max_diff, float(np.max(np.abs(expected - actual))))
        max_raw_action = max(
            max_raw_action, float(np.max(np.abs(raw)))
        )
        if float(np.max(np.abs(raw))) > 1.0:
            clipped += 1

    return {
        "samples": float(len(observations)),
        "max_abs_diff": max_diff,
        "max_abs_action_raw": max_raw_action,
        "samples_outside_action_range": float(clipped),
    }


# --------------------------------------------------------------------------- #
# JSON y header C
# --------------------------------------------------------------------------- #
def build_payload(
    model_path: Path,
    weights: dict[str, np.ndarray],
    test: dict[str, float],
) -> dict[str, Any]:
    return {
        "format": "walle-ppo-actor-v1",
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": model_path.name,
        "observation_size": 13,
        "action_size": 2,
        "observation_order": list(OBS_ORDER),
        "observation_description": OBS_DESCRIPTIONS,
        "observation_normalization": {
            "type": "none",
            "note": (
                "La red recibe los 13 valores crudos. No se usó VecNormalize "
                "ni media/desvío estándar en el entrenamiento."
            ),
        },
        "action_order": ["left_track", "right_track"],
        "architecture": {
            "layers": [13, 128, 128, 2],
            "hidden_activation": "tanh",
            "output_activation": "linear",
            "deterministic": True,
            "description": (
                "Media de la gaussiana del actor. Sin squashing; el despliegue "
                "debe recortar la salida a [-1, 1]."
            ),
        },
        "action_mapping": {
            "range": [-1.0, 1.0],
            "clip_before_mapping": True,
            "left_motor": "action[0] * max_wheel_speed",
            "right_motor": "action[1] * max_wheel_speed",
            "max_wheel_speed_rad_s": 10.0,
            "note": (
                "En PyBullet se usa VELOCITY_CONTROL con max_force=1.0 N·m. "
                "En el ESP32 calibrar PWM/encoder para reproducir esa escala."
            ),
        },
        "sensor_noise": {
            "training_std": 0.02,
            "inference": "sin ruido; usar la lectura filtrada de la IMU/encoders",
            "goal_index_never_noisy": 12,
        },
        "self_test": test,
        "weights": {name: array.tolist() for name, array in weights.items()},
    }


def _format_array(
    values: np.ndarray,
    name: str,
    rows: int,
    cols: int,
    row_prefix: str = "    ",
) -> str:
    lines = [f"static const float {name}[{rows}][{cols}] = {{"]
    for row in values:
        body = ", ".join(f"{float(value):.9g}f" for value in row)
        lines.append(f"{row_prefix}{{ {body} }},")
    lines.append("};")
    return "\n".join(lines)


def build_header(
    model_path: Path,
    weights: dict[str, np.ndarray],
    test: dict[str, float],
) -> str:
    fc1_w = _format_array(weights["fc1_weight"], "WALLE_FC1_W", 128, 13)
    fc2_w = _format_array(weights["fc2_weight"], "WALLE_FC2_W", 128, 128)
    fc3_w = _format_array(weights["fc3_weight"], "WALLE_FC3_W", 2, 128)

    fc1_b = ", ".join(f"{float(v):.9g}f" for v in weights["fc1_bias"])
    fc2_b = ", ".join(f"{float(v):.9g}f" for v in weights["fc2_bias"])
    fc3_b = ", ".join(f"{float(v):.9g}f" for v in weights["fc3_bias"])

    return f"""/*
 * WALL-E · Cerebro motor PPO exportado para el ESP32
 * ==================================================
 * Modelo: {model_path.name}
 * Generado: {datetime.now().astimezone().isoformat(timespec="seconds")}
 *
 * Observación (13 float, en este orden):
 *   [0] x_m      [1] y_m      [2] qx   [3] qy   [4] qz   [5] qw
 *   [6] vx       [7] vy       [8] vz
 *   [9] wx      [10] wy      [11] wz      [12] goal (+1/-1/0)
 *
 * Acción (2 float): [0] oruga izquierda, [1] oruga derecha, rango [-1, 1].
 * La salida de la red es lineal; esta función la recorta a [-1, 1].
 * Sin normalización de observaciones: pasá los 13 valores crudos.
 *
 * Self-test NumPy vs Stable Baselines3:
 *   muestras={int(test["samples"])}  max_abs_diff={test["max_abs_diff"]:.3e}
 *   max_abs_action_raw={test["max_abs_action_raw"]:.3f}
 *
 * Uso:
 *   float obs[WALLE_OBS_SIZE] = {{...}};
 *   float action[WALLE_ACT_SIZE];
 *   walle_brain_forward(obs, action);
 *   int left_pwm  = (int)(action[0] * WALLE_MAX_WHEEL_SPEED);
 *   int right_pwm = (int)(action[1] * WALLE_MAX_WHEEL_SPEED);
 */

#ifndef WALLE_BRAIN_WEIGHTS_H
#define WALLE_BRAIN_WEIGHTS_H

#include <math.h>

#define WALLE_OBS_SIZE 13
#define WALLE_ACT_SIZE 2
#define WALLE_HIDDEN_1 128
#define WALLE_HIDDEN_2 128
#define WALLE_MAX_WHEEL_SPEED 10.0f

{fc1_w}

static const float WALLE_FC1_B[WALLE_HIDDEN_1] = {{ {fc1_b} }};

{fc2_w}

static const float WALLE_FC2_B[WALLE_HIDDEN_2] = {{ {fc2_b} }};

{fc3_w}

static const float WALLE_FC3_B[WALLE_ACT_SIZE] = {{ {fc3_b} }};

static inline void walle_brain_forward(
    const float obs[WALLE_OBS_SIZE],
    float action[WALLE_ACT_SIZE]
) {{
    float h1[WALLE_HIDDEN_1];
    float h2[WALLE_HIDDEN_2];

    for (int i = 0; i < WALLE_HIDDEN_1; ++i) {{
        float acc = WALLE_FC1_B[i];
        for (int j = 0; j < WALLE_OBS_SIZE; ++j) {{
            acc += WALLE_FC1_W[i][j] * obs[j];
        }}
        h1[i] = tanhf(acc);
    }}

    for (int i = 0; i < WALLE_HIDDEN_2; ++i) {{
        float acc = WALLE_FC2_B[i];
        for (int j = 0; j < WALLE_HIDDEN_1; ++j) {{
            acc += WALLE_FC2_W[i][j] * h1[j];
        }}
        h2[i] = tanhf(acc);
    }}

    for (int i = 0; i < WALLE_ACT_SIZE; ++i) {{
        float acc = WALLE_FC3_B[i];
        for (int j = 0; j < WALLE_HIDDEN_2; ++j) {{
            acc += WALLE_FC3_W[i][j] * h2[j];
        }}
        if (acc > 1.0f) {{
            acc = 1.0f;
        }} else if (acc < -1.0f) {{
            acc = -1.0f;
        }}
        action[i] = acc;
    }}
}}

#endif /* WALLE_BRAIN_WEIGHTS_H */
"""


def build_deploy_readme(
    model_path: Path, test: dict[str, float]
) -> str:
    rows = "\n".join(
        f"| `{index}` | `{name}` | {OBS_DESCRIPTIONS[name]} |"
        for index, name in enumerate(OBS_ORDER)
    )
    return f"""# WALL-E · Cerebro PPO en el ESP32

Generado desde `{model_path.name}` con `export_brain.py`.

## Archivos

| Archivo | Uso |
| --- | --- |
| `walle_brain_weights.h` | Arrays C y `walle_brain_forward()` listos para el firmware. |
| `walle_brain_weights.json` | Mismos pesos + metadatos, para Python/JS u otra herramienta. |

## Observación (13D)

| Índice | Nombre | Descripción |
| --- | --- | --- |
{rows}

### Orden y convención

1. La posición y la orientación son **absolutas del mundo** de PyBullet.
   En el robot físico no hay GPS: usá odometría de encoders para `x,y` y una
   IMU fusionada (BNO055, MPU6050 + Madgwick) para el cuaternión.
2. `vx,vy,vz` y `wx,wy,wz` están en el **marco del mundo**, no en el marco
   del robot. Si el firmware solo tiene velocidades locales, rotarlas por la
   orientación antes de pasarlas a la red.
3. `goal` es el único canal de comando: `+1` avanzar, `-1` retroceder,
   `0` quedarse quieto. No tiene ruido.
4. El cerebro se entrenó con ruido gaussiano de 0.02 en los 12 primeros
   canales. En inferencia usar lecturas filtradas, sin agregar ruido.
5. **No hay normalización de observaciones**: no se usó `VecNormalize` ni
   media/desvío estándar. Pasá los 13 valores crudos en el orden indicado.

## Acción (2D)

- `action[0]` = oruga izquierda, `action[1]` = oruga derecha.
- Rango `[-1, 1]`; la red puede producir valores algo mayores, por eso el
  header recorta antes de mapear.
- En PyBullet: `targetVelocity = action * 10.0 rad/s`, con
  `max_force = 1.0 N·m`.
- En el ESP32: calibrar `PWM = action * PWM_MAX` con control de velocidad por
  encoder para que la oruga real siga la consigna en rad/s.

## Ejemplo mínimo

```c
#include "walle_brain_weights.h"

float obs[WALLE_OBS_SIZE] = {{
    0.0f, 0.0f,          /* x, y */
    0.0f, 0.0f, 0.0f, 1.0f, /* cuaternión identidad */
    0.0f, 0.0f, 0.0f,    /* velocidad lineal */
    0.0f, 0.0f, 0.0f,    /* velocidad angular */
    1.0f                 /* goal: avanzar */
}};
float action[WALLE_ACT_SIZE];
walle_brain_forward(obs, action);
/* action[0] y action[1] en [-1, 1] */
```

## Self-test

La exportación compara la inferencia NumPy contra
`model.predict(obs, deterministic=True)`:

- Muestras: **{int(test["samples"])}**
- Diferencia máxima absoluta: **{test["max_abs_diff"]:.3e}**
- Acción máxima absoluta observada (antes del recorte): **{test["max_abs_action_raw"]:.3f}**
- Muestras fuera de `[-1,1]`: **{int(test["samples_outside_action_range"])}**

Si `max_abs_diff` es mayor que `1e-5`, no uses los pesos: revisá la versión de
PyTorch/Stable Baselines3 con la que se entrenó el modelo.

## Puesta en marcha en el robot real

Antes de culpar a la red, verificá que la observación signifique lo mismo en
simulación y en hardware:

1. **Lazo fijo a 60 Hz** (16,67 ms). Medí el ciclo completo con `micros()`
   (leer IMU + encoders, ejecutar la red, escribir PWM) y no uses `delay()`
   largos. Si el lazo real tarda 30 ms, la política está viviendo un mundo más
   lento que el de entrenamiento.
2. **Signos de la IMU**: con el robot quieto y mirando a +X, el cuaternión debe
   ser aproximadamente `(0, 0, 0, 1)`. Si `yaw` gira al revés, invertí el signo
   del giroscopio Z antes de pasarlo a la red.
3. **Unidades**: `vx,vy,vz` en m/s y `wx,wy,wz` en rad/s, en el **marco del
   mundo**. Si el firmware entrega velocidades locales, rotarlas por la
   orientación. Si la IMU entrega grados/s, convertir a rad/s.
4. **Encoders**: comprobá que la oruga izquierda avance con acción positiva y
   que la derecha también. Si una está invertida, el robot girará en vez de
   avanzar.
5. **Prueba en banco**: con el robot colgado o sobre bloques, mandá `goal=+1`
   y verificá que ambas orugas giren hacia adelante; después `goal=-1`.
6. **Calibración PWM → rad/s**: medí la velocidad real de cada oruga a varios
   PWM y ajustá `PWM_MAX` hasta que `action=1.0` corresponda a los 10 rad/s
   usados en simulación.
7. **Comparación de observaciones**: imprimí por serial el vector de 13
   valores con el robot quieto y compará con el de PyBullet en la misma pose.
   Antes de reentrenar, corregí cualquier diferencia de signo, unidad o
   convención de cuaternión.

## Seguridad y watchdog

- Enviar un **heartbeat** por UDP cada 200 ms. Si el ESP32 no recibe comandos
  en 500 ms, poner PWM=0 en ambos motores.
- Recortar `action` a `[-1, 1]` y aplicar una rampa de aceleración para no
  quemar el driver ni las ruedas.
- Instalar una **parada de emergencia física** que corte la alimentación de
  los motores, independiente del firmware.
- Monitorear la tensión de la batería; si cae por debajo del mínimo, detener.
- Si la IMU detecta `up.z < 0.5` (volcado), cortar motores y entrar en la
  secuencia de recuperación.
- Usar el watchdog del ESP32 y no bloquear el loop con `delay()` largos.

## Limitaciones

- El cerebro actual solo entiende avance/retroceso/quieto. **No tiene comando
  de giro**; para girar en el robot físico usá un lazo de rumbo (PID) sobre la
  IMU, igual que en el simulador interactivo.
- Se entrenó con `max_wheel_speed=10 rad/s`, `max_force=1.0 N·m` y masa
  `3.5 kg`. Si el robot real cambia de peso, fricción o batería, conviene un
  fine-tune en simulación con esos parámetros.
- El comando `goal=0` (“quieto”) es más débil que avance/retroceso; para
  detener el robot físico usá frenado activo y el watchdog.
"""


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exporta el actor PPO de WALL-E a JSON y header C."
    )
    parser.add_argument(
        "--model",
        default=str(DEFAULT_MODEL),
        help="Modelo PPO de 13D (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Carpeta de salida (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=64,
        help="Muestras del self-test NumPy vs SB3 (por defecto: 64)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Semilla del self-test (por defecto: 7)",
    )
    parser.add_argument(
        "--skip-env-test",
        action="store_true",
        help="No generar observaciones reales con PyBullet en el self-test",
    )
    args = parser.parse_args(argv)

    model_path = Path(args.model).expanduser().resolve()
    if not model_path.exists():
        parser.error(f"No existe el modelo: {model_path}")

    print(f"[EXPORT] Modelo: {model_path}")
    weights, model = load_actor_weights(model_path)

    print(
        "[EXPORT] Self-test NumPy vs SB3 "
        f"({args.samples} aleatorias"
        + ("" if args.skip_env_test else f" + {args.samples} reales")
        + ")..."
    )
    test = self_test(
        model,
        weights,
        samples=max(1, args.samples),
        seed=args.seed,
        use_env=not args.skip_env_test,
    )
    print(
        f"[EXPORT] max_abs_diff={test['max_abs_diff']:.3e} | "
        f"max_abs_action_raw={test['max_abs_action_raw']:.3f} | "
        f"fuera de [-1,1]={int(test['samples_outside_action_range'])}"
    )
    if test["max_abs_diff"] > 1e-5:
        raise SystemExit(
            "ERROR: la inferencia NumPy no coincide con SB3 "
            f"(diff={test['max_abs_diff']:.3e}). No se exportaron los pesos."
        )

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = build_payload(model_path, weights, test)
    json_path = out_dir / "walle_brain_weights.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    header_path = out_dir / "walle_brain_weights.h"
    header_path.write_text(
        build_header(model_path, weights, test), encoding="utf-8"
    )

    readme_path = out_dir / "README_ESP32.md"
    readme_path.write_text(
        build_deploy_readme(model_path, test), encoding="utf-8"
    )

    print(f"[EXPORT] JSON:   {json_path}")
    print(f"[EXPORT] Header: {header_path}")
    print(f"[EXPORT] Guía:   {readme_path}")
    print("[EXPORT] Listo. El header compila con math.h (tanhf).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
