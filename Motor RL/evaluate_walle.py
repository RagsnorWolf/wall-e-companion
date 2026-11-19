"""
WALL-E · Fase 2 — Evaluación visual del Cerebro Motor
=====================================================

Carga el modelo entrenado y lo ejecuta en PyBullet para ver a WALL-E
conducir por el arena. El cerebro es condicionado por comando:
  +1 = avanzar, -1 = retroceder, 0 = quedarse quieto.

Uso:
    python evaluate_walle.py                      # GUI, 3 episodios por comando
    python evaluate_walle.py --goal forward
    python evaluate_walle.py --goal backward --episodes 5
    python evaluate_walle.py --direct             # sin GUI (mide y sale)
    python evaluate_walle.py --stochastic         # acciones con muestreo
    python evaluate_walle.py --visual-mesh walle_visual.obj
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import numpy as np  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402

from walle_env import WallEEnv  # noqa: E402


DEFAULT_VISUAL_MESH = SCRIPT_DIR / "walle_visual.obj"
PHYSICAL_MODEL = SCRIPT_DIR / "walle_ppo_model_physical.zip"
LEGACY_MODEL = SCRIPT_DIR / "walle_ppo_model.zip"

# Centro del arena: deja 20 m libres hacia adelante y hacia atrás, así el
# retroceso no termina contra la pared trasera.
EVAL_START_POS = (0.0, 0.0, 0.15)


def default_model_path() -> Path:
    """Prefiere el modelo entrenado con la física final del robot físico."""
    if PHYSICAL_MODEL.exists():
        return PHYSICAL_MODEL
    return LEGACY_MODEL


def resolve_visual_mesh(cli_value: str | None) -> str | None:
    """Usa el OBJ de la Fase 1 si existe, salvo que se pase otro."""
    if cli_value:
        return cli_value
    if DEFAULT_VISUAL_MESH.exists():
        return str(DEFAULT_VISUAL_MESH)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reproduce el cerebro motor entrenado de WALL-E"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=str(default_model_path()),
        help="Ruta al modelo .zip entrenado",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=3,
        help="Cantidad de episodios por comando",
    )
    parser.add_argument(
        "--goal",
        choices=("forward", "backward", "stop", "all"),
        default="all",
        help="Comando a evaluar: avanzar, retroceder, quieto o todos",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Sin ventana de PyBullet (solo métricas)",
    )
    parser.add_argument(
        "--stochastic",
        action="store_true",
        help="Muestrear acciones en vez de usar la acción más probable",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1000,
        help="Máximo de pasos por episodio",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Semilla del primer episodio",
    )
    parser.add_argument(
        "--start-pos",
        type=float,
        nargs=2,
        metavar=("X", "Y"),
        default=None,
        help="Posición inicial fija en metros (por defecto: centro del arena)",
    )
    parser.add_argument(
        "--start-yaw",
        type=float,
        default=0.0,
        help="Rumbo inicial fijo en grados (por defecto: 0)",
    )
    parser.add_argument(
        "--random-starts",
        action="store_true",
        help="Arrancar en posiciones aleatorias del arena en cada episodio (test OOD)",
    )
    parser.add_argument(
        "--random-yaw",
        action="store_true",
        help="Arrancar con rumbo aleatorio en cada episodio (test tras giros)",
    )
    parser.add_argument(
        "--start-margin",
        type=float,
        default=2.0,
        help="Margen respecto de las paredes para --random-starts (por defecto: 2 m)",
    )
    parser.add_argument(
        "--visual-mesh",
        type=str,
        default=None,
        help="OBJ opcional para la apariencia del robot (Fase 1)",
    )
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(
            f"No se encontró el modelo: {model_path}\n"
            "Entrená primero con: python train_walle.py"
        )

    if not args.direct:
        print(
            "Cerrá la ventana de PyBullet o presioná Ctrl+C para terminar.\n"
        )

    env = WallEEnv(
        render_mode=None if args.direct else "human",
        max_episode_steps=args.max_steps,
        visual_mesh_path=resolve_visual_mesh(args.visual_mesh),
        randomize_goal=False,
        randomize_reset=False,
    )
    env.training = False  # evaluación limpia, sin ruido de sensores
    model = PPO.load(str(model_path), device="auto")

    goal_map = {
        "forward": [(1.0, "avanzar")],
        "backward": [(-1.0, "retroceder")],
        "stop": [(0.0, "quieto")],
        "all": [
            (1.0, "avanzar"),
            (-1.0, "retroceder"),
            (0.0, "quieto"),
        ],
    }
    goals = goal_map[args.goal]

    fixed_start = (
        (float(args.start_pos[0]), float(args.start_pos[1]), 0.15)
        if args.start_pos is not None
        else EVAL_START_POS
    )
    start_rng = np.random.default_rng(args.seed)
    yaw_rng = np.random.default_rng(args.seed + 1)
    start_limit = max(
        0.0, env.arena_half_size - max(0.0, args.start_margin)
    )

    rewards: list[float] = []

    try:
        for goal, label in goals:
            print(f"\n=== Comando: {label} (goal={goal:+.0f}) ===")
            goal_rewards: list[float] = []
            goal_distances: list[float] = []
            goal_yaw_drifts: list[float] = []

            for episode in range(args.episodes):
                if args.random_starts:
                    start_pos = (
                        float(start_rng.uniform(-start_limit, start_limit)),
                        float(start_rng.uniform(-start_limit, start_limit)),
                        0.15,
                    )
                else:
                    start_pos = fixed_start
                start_yaw_deg = (
                    float(yaw_rng.uniform(-180.0, 180.0))
                    if args.random_yaw
                    else float(args.start_yaw)
                )
                obs, info = env.reset(
                    seed=args.seed + episode,
                    options={
                        "goal": goal,
                        "start_pos": start_pos,
                        "start_yaw": math.radians(start_yaw_deg),
                    },
                )
                start_x = float(info["x"])
                start_y = float(info["y"])
                total_reward = 0.0
                steps = 0
                done = False

                while not done:
                    action, _ = model.predict(
                        obs, deterministic=not args.stochastic
                    )
                    obs, reward, terminated, truncated, info = env.step(
                        action
                    )
                    total_reward += float(reward)
                    steps += 1
                    done = bool(terminated or truncated)

                    if not args.direct:
                        time.sleep(1.0 / env.metadata["render_fps"])

                if info["collision"]:
                    reason = "choque con pared"
                elif info["flipped"]:
                    reason = "volcado"
                else:
                    reason = "límite de pasos"

                forward = float(info["forward"])
                displacement = math.hypot(
                    float(info["x"]) - start_x,
                    float(info["y"]) - start_y,
                )
                progress = forward * goal
                metric_distance = displacement if goal == 0.0 else forward
                duration = steps / env.metadata["render_fps"]
                speed = forward / duration if duration > 0 else 0.0
                final_yaw_deg = math.degrees(float(info["yaw"]))
                yaw_drift = final_yaw_deg - start_yaw_deg
                rewards.append(total_reward)
                goal_rewards.append(total_reward)
                goal_distances.append(metric_distance)
                goal_yaw_drifts.append(yaw_drift)

                if goal == 0.0:
                    metric = f"deriva={displacement:.2f} m"
                else:
                    metric = f"progreso={progress:+.2f} m"

                print(
                    f"Episodio {episode + 1}/{args.episodes}\n"
                    f"  inicio=({start_x:+.2f}, {start_y:+.2f}) "
                    f"yaw={start_yaw_deg:+.1f}° "
                    f"fin=({float(info['x']):+.2f}, "
                    f"{float(info['y']):+.2f})\n"
                    f"  avance={forward:+.2f} m | "
                    f"desplazamiento={displacement:.2f} m | "
                    f"{metric} | pasos={steps} | "
                    f"vel. media={speed:.2f} m/s\n"
                    f"  yaw_fin={final_yaw_deg:+.1f}° | "
                    f"deriva_yaw={yaw_drift:+.1f}°\n"
                    f"  recompensa={total_reward:+.2f} | fin: {reason}\n"
                )

            if goal == 0.0:
                print(
                    f"--> recompensa media="
                    f"{np.mean(goal_rewards):+.2f} | deriva media="
                    f"{np.mean(np.abs(goal_distances)):.2f} m | "
                    f"deriva yaw media="
                    f"{np.mean(np.abs(goal_yaw_drifts)):.1f}°\n"
                )
            else:
                print(
                    f"--> recompensa media="
                    f"{np.mean(goal_rewards):+.2f} | progreso medio="
                    f"{np.mean(np.asarray(goal_distances) * goal):+.2f} m | "
                    f"deriva yaw media="
                    f"{np.mean(np.abs(goal_yaw_drifts)):.1f}°\n"
                )
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        env.close()

    if rewards:
        print(
            f"Resumen global: recompensa media={np.mean(rewards):+.2f} | "
            f"episodios={len(rewards)}"
        )


if __name__ == "__main__":
    main()
