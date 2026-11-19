"""
WALL-E · Fase 2 — Entrenamiento del Cerebro Motor (PPO)
=======================================================

Entrena el proxy físico de WALL-E en PyBullet para que aprenda a conducir
en la dirección frontal del robot (avance/retroceso relativo al frente) sin
volcarse ni chocar contra las paredes del arena.

El agente recibe 13 números (posición, orientación, velocidades y comando) y
devuelve 2 números entre -1 y 1 (velocidad normalizada de la oruga izquierda y
derecha). PPO ajusta la política para maximizar la recompensa acumulada.

Salidas (en esta misma carpeta):
    walle_ppo_model.zip    Modelo entrenado (se puede cargar con PPO.load)
    checkpoints/           Copias intermedias cada 10.000 pasos
    tb_logs/               Curvas para TensorBoard

Uso:
    python train_walle.py
    python train_walle.py --timesteps 100000
    python train_walle.py --gui                 # ver el entrenamiento
    python train_walle.py --resume walle_ppo_model.zip --timesteps 50000
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

# Permite ejecutar el script desde cualquier carpeta.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import gymnasium as gym  # noqa: E402
import numpy as np  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.callbacks import (  # noqa: E402
    BaseCallback,
    CallbackList,
    CheckpointCallback,
)
from stable_baselines3.common.monitor import Monitor  # noqa: E402
from stable_baselines3.common.vec_env import DummyVecEnv  # noqa: E402

from walle_env import WallEEnv  # noqa: E402


DEFAULT_MODEL = SCRIPT_DIR / "walle_ppo_model.zip"
CHECKPOINT_DIR = SCRIPT_DIR / "checkpoints"
TENSORBOARD_DIR = SCRIPT_DIR / "tb_logs"
DEFAULT_VISUAL_MESH = SCRIPT_DIR / "walle_visual.obj"

# --- Parámetros de sim-to-real para el robot físico -------------------- #
# Ruido gaussiano en las observaciones (posición, cuaternión y velocidades).
TRAIN_OBS_NOISE_STD = 0.02
# Penaliza cambios bruscos entre acciones consecutivas (suavidad motora).
TRAIN_ACTION_RATE_PENALTY = 0.05
# Penaliza acciones grandes (consumo de batería).
TRAIN_ACTION_MAGNITUDE_PENALTY = 0.002
# Variar posición y rumbo iniciales para que la política generalice.
TRAIN_RANDOMIZE_RESET = True
# Reparto de comandos: retroceder, quieto, avanzar. Damos más peso a
# "quieto" porque es el comando más difícil de estabilizar.
TRAIN_GOAL_PROBS = (0.35, 0.30, 0.35)
# Refuerzo del comando "quieto": deriva x2, castigo a la velocidad residual
# y penalización directa de acciones no nulas (evita que se arrastre).
TRAIN_STOP_DRIFT_SCALE = 2.0
TRAIN_STOP_VELOCITY_PENALTY = 0.5
TRAIN_STOP_ACTION_PENALTY = 1.0
# Castigo al giro no comandado (yaw rate). Evita que la política gire para
# acumular avance frontal y reduce la deriva de rumbo observada.
TRAIN_YAW_RATE_PENALTY = 0.05
# Domain randomization (sim-to-real): masa, fricción y fuerza varían por
# episodio. Se activa con --domain-randomization.
TRAIN_RANDOMIZE_PHYSICS = False
TRAIN_BASE_MASS_RANGE = (0.90, 1.10)
TRAIN_WHEEL_MASS_RANGE = (0.90, 1.10)
TRAIN_WHEEL_FRICTION_RANGE = (0.80, 1.20)
TRAIN_MOTOR_FORCE_RANGE = (0.80, 1.20)
# OOD fix: arrancar en cualquier punto del arena (con 2 m de margen) y con
# rumbo completo. Así el avance relativo al frente se aprende para cualquier
# orientación, no solo mirando hacia +X.
TRAIN_RESET_MARGIN = 2.0
TRAIN_RESET_YAW_DEG = 180.0
# La evaluación arranca en el centro para tener 20 m libres en ambos sentidos.
EVAL_START_POS = (0.0, 0.0, 0.15)
# Además del centro, evaluamos en posiciones variadas para detectar OOD.
EVAL_START_POSITIONS = (
    (-15.0, 0.0, 0.15),
    (0.0, 0.0, 0.15),
    (15.0, 0.0, 0.15),
    (0.0, -12.0, 0.15),
    (0.0, 12.0, 0.15),
)


def resolve_visual_mesh(cli_value: str | None) -> str | None:
    """Usa el OBJ de la Fase 1 si existe, salvo que se pase otro."""
    if cli_value:
        return cli_value
    if DEFAULT_VISUAL_MESH.exists():
        return str(DEFAULT_VISUAL_MESH)
    return None


class WalleStatsWrapper(gym.Wrapper):
    """Agrega métricas de episodio al `info` final para TensorBoard.

    El tutorial de balance bot insiste en leer las curvas correctas. Con
    `ep_rew_mean` solo no se distingue si el robot avanza, retrocede o deriva
    en "quieto"; este wrapper expone esas métricas por episodio.
    """

    def __init__(self, env: gym.Env) -> None:
        super().__init__(env)
        self._start_info: dict | None = None

    def reset(self, **kwargs):
        obs, info = self.env.reset(**kwargs)
        self._start_info = dict(info)
        return obs, info

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        if (terminated or truncated) and self._start_info is not None:
            start = self._start_info
            goal = float(start.get("goal", 0.0))
            forward = float(info.get("forward", 0.0))
            displacement = math.hypot(
                float(info.get("x", 0.0)) - float(start.get("x", 0.0)),
                float(info.get("y", 0.0)) - float(start.get("y", 0.0)),
            )
            yaw_drift = abs(
                math.degrees(
                    float(info.get("yaw", 0.0))
                    - float(start.get("yaw", 0.0))
                )
            )
            info["ep_goal"] = goal
            info["ep_forward"] = forward
            info["ep_displacement"] = displacement
            info["ep_yaw_drift"] = yaw_drift
        return obs, reward, terminated, truncated, info


class WalleMetricsCallback(BaseCallback):
    """Registra avance, deriva y giro por comando en TensorBoard."""

    def __init__(self, verbose: int = 0) -> None:
        super().__init__(verbose)
        self._forward: list[float] = []
        self._backward: list[float] = []
        self._stop_drift: list[float] = []
        self._yaw_drift: list[float] = []

    def _on_step(self) -> bool:
        infos = self.locals.get("infos") or []
        if not infos:
            return True
        info = infos[0]
        if "ep_goal" not in info:
            return True
        goal = float(info["ep_goal"])
        forward = float(info.get("ep_forward", 0.0))
        if goal > 0.5:
            self._forward.append(forward)
        elif goal < -0.5:
            self._backward.append(-forward)
        else:
            self._stop_drift.append(float(info.get("ep_displacement", 0.0)))
        if goal != 0.0:
            self._yaw_drift.append(float(info.get("ep_yaw_drift", 0.0)))
        return True

    def _on_rollout_end(self) -> None:
        if self._forward:
            self.logger.record("walle/forward_m", float(np.mean(self._forward)))
            self._forward.clear()
        if self._backward:
            self.logger.record("walle/backward_m", float(np.mean(self._backward)))
            self._backward.clear()
        if self._stop_drift:
            self.logger.record(
                "walle/stop_drift_m", float(np.mean(self._stop_drift))
            )
            self._stop_drift.clear()
        if self._yaw_drift:
            self.logger.record(
                "walle/yaw_drift_deg", float(np.mean(self._yaw_drift))
            )
            self._yaw_drift.clear()


# ---------------------------------------------------------------------- #
# Entorno vectorizado (1 entorno). DummyVecEnv es suficiente para PyBullet
# y deja la puerta abierta a SubprocVecEnv si algún día se paraleliza.
# ---------------------------------------------------------------------- #
def make_env(
    render_mode: str | None,
    visual_mesh: str | None,
    seed: int,
    domain_randomization: bool = False,
    yaw_rate_penalty: float = TRAIN_YAW_RATE_PENALTY,
):
    def _init():
        env = WallEEnv(
            render_mode=render_mode,
            visual_mesh_path=visual_mesh,
            obs_noise_std=TRAIN_OBS_NOISE_STD,
            action_rate_penalty=TRAIN_ACTION_RATE_PENALTY,
            action_magnitude_penalty=TRAIN_ACTION_MAGNITUDE_PENALTY,
            randomize_reset=TRAIN_RANDOMIZE_RESET,
            randomize_goal=True,
            goal_probs=TRAIN_GOAL_PROBS,
            stop_drift_scale=TRAIN_STOP_DRIFT_SCALE,
            stop_velocity_penalty=TRAIN_STOP_VELOCITY_PENALTY,
            stop_action_penalty=TRAIN_STOP_ACTION_PENALTY,
            yaw_rate_penalty=yaw_rate_penalty,
            randomize_physics=domain_randomization,
            base_mass_range=TRAIN_BASE_MASS_RANGE,
            wheel_mass_range=TRAIN_WHEEL_MASS_RANGE,
            wheel_friction_range=TRAIN_WHEEL_FRICTION_RANGE,
            motor_force_range=TRAIN_MOTOR_FORCE_RANGE,
            reset_margin=TRAIN_RESET_MARGIN,
            reset_yaw_range_deg=TRAIN_RESET_YAW_DEG,
        )
        env.reset(seed=seed)
        # Monitor registra recompensas y longitudes de episodio; el wrapper
        # agrega las métricas por comando.
        return Monitor(WalleStatsWrapper(env))

    return _init


def build_model(vec_env, seed: int) -> PPO:
    """PPO con una red chica: 13 observaciones -> 2 acciones."""
    return PPO(
        "MlpPolicy",
        vec_env,
        learning_rate=3e-4,
        n_steps=1024,
        batch_size=256,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
        vf_coef=0.5,
        max_grad_norm=0.5,
        policy_kwargs=dict(net_arch=dict(pi=[128, 128], vf=[128, 128])),
        tensorboard_log=str(TENSORBOARD_DIR),
        verbose=1,
        seed=seed,
        device="auto",
    )


# ---------------------------------------------------------------------- #
# Evaluación posterior al entrenamiento
# ---------------------------------------------------------------------- #
def evaluate_model(
    model: PPO,
    episodes: int,
    gui: bool,
    seed: int = 1000,
    visual_mesh: str | None = None,
) -> None:
    env = WallEEnv(
        render_mode="human" if gui else None,
        visual_mesh_path=visual_mesh,
        randomize_goal=False,
        randomize_reset=False,
    )
    env.training = False  # sin ruido de sensores en la evaluación

    goal_labels = {1.0: "avanzar", -1.0: "retroceder", 0.0: "quedarse quieto"}
    all_rewards: list[float] = []

    try:
        for goal, label in goal_labels.items():
            rewards: list[float] = []
            distances: list[float] = []

            for episode in range(episodes):
                start_pos = EVAL_START_POSITIONS[
                    episode % len(EVAL_START_POSITIONS)
                ]
                obs, info = env.reset(
                    seed=seed + episode,
                    options={"goal": goal, "start_pos": start_pos},
                )
                start_x = float(info["x"])
                start_y = float(info["y"])
                total_reward = 0.0
                steps = 0
                done = False

                while not done:
                    action, _ = model.predict(obs, deterministic=True)
                    obs, reward, terminated, truncated, info = env.step(
                        action
                    )
                    total_reward += float(reward)
                    steps += 1
                    done = bool(terminated or truncated)

                    if gui:
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
                metric_distance = displacement if goal == 0.0 else forward
                rewards.append(total_reward)
                distances.append(metric_distance)
                all_rewards.append(total_reward)

                if goal == 0.0:
                    metric = f"deriva={displacement:5.2f} m"
                else:
                    metric = f"progreso={forward * goal:+5.2f} m"

                print(
                    f"  [{label:15s}] Ep {episode + 1}/{episodes}: "
                    f"inicio=({start_x:+.1f},{start_y:+.1f}) | "
                    f"recompensa={total_reward:8.2f} | "
                    f"avance={forward:+6.2f} m | "
                    f"{metric} | "
                    f"pasos={steps:4d} | fin: {reason}"
                )

            if goal == 0.0:
                summary = (
                    f"deriva media={np.mean(np.abs(distances)):5.2f} m"
                )
            else:
                summary = (
                    f"progreso medio="
                    f"{np.mean(np.asarray(distances) * goal):+5.2f} m"
                )

            print(
                f"  --> {label:15s}: recompensa media="
                f"{np.mean(rewards):8.2f} | {summary}\n"
            )
    finally:
        env.close()

    print(f"  Media global de recompensa: {np.mean(all_rewards):.2f}")


# ---------------------------------------------------------------------- #
# Programa principal
# ---------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Entrena el cerebro motor de WALL-E con PPO"
    )
    parser.add_argument(
        "--timesteps",
        type=int,
        default=50_000,
        help="Pasos de entrenamiento (por defecto 50.000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla para reproducibilidad",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Mostrar PyBullet durante el entrenamiento (mucho más lento)",
    )
    parser.add_argument(
        "--gui-eval",
        action="store_true",
        help="Mostrar la evaluación final en PyBullet",
    )
    parser.add_argument(
        "--visual-mesh",
        type=str,
        default=None,
        help="OBJ opcional para la apariencia del robot (Fase 1)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Ruta a un modelo .zip para seguir entrenando",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=str(DEFAULT_MODEL),
        help="Ruta de salida del modelo entrenado",
    )
    parser.add_argument(
        "--eval-episodes",
        type=int,
        default=5,
        help="Cantidad de episodios de evaluación final",
    )
    parser.add_argument(
        "--domain-randomization",
        action="store_true",
        help=(
            "Variar masa, fricción y fuerza por episodio (sim-to-real). "
            "Recomendado para un fine-tune final, no para el primer entrenamiento."
        ),
    )
    parser.add_argument(
        "--yaw-rate-penalty",
        type=float,
        default=TRAIN_YAW_RATE_PENALTY,
        help=(
            "Castigo al giro no comandado (por defecto %(default)s). "
            "Subirlo si la política gira para acumular avance frontal."
        ),
    )
    args = parser.parse_args()

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    TENSORBOARD_DIR.mkdir(parents=True, exist_ok=True)

    render_mode = "human" if args.gui else None
    visual_mesh = resolve_visual_mesh(args.visual_mesh)
    if visual_mesh:
        print(f"Apariencia visual: {visual_mesh}")
    vec_env = DummyVecEnv(
        [
            make_env(
                render_mode,
                visual_mesh,
                args.seed,
                domain_randomization=args.domain_randomization,
                yaw_rate_penalty=args.yaw_rate_penalty,
            )
        ]
    )

    if args.resume:
        resume_path = Path(args.resume)
        if not resume_path.exists():
            raise FileNotFoundError(f"No existe el modelo: {resume_path}")
        print(f"Cargando modelo para continuar: {resume_path}")
        model = PPO.load(resume_path, env=vec_env, device="auto")
        model.tensorboard_log = str(TENSORBOARD_DIR)
    else:
        model = build_model(vec_env, args.seed)

    checkpoint = CheckpointCallback(
        save_freq=10_000,
        save_path=str(CHECKPOINT_DIR),
        name_prefix="walle_ppo",
    )
    metrics = WalleMetricsCallback()

    print(f"\nEntrenando {args.timesteps:,} pasos...")
    started = time.perf_counter()
    model.learn(
        total_timesteps=args.timesteps,
        callback=CallbackList([checkpoint, metrics]),
        reset_num_timesteps=not bool(args.resume),
    )
    elapsed = time.perf_counter() - started
    vec_env.close()

    model_path = Path(args.model)
    if model_path.suffix.lower() != ".zip":
        model_path = model_path.with_suffix(".zip")
    model.save(str(model_path))

    print(f"\nModelo guardado en: {model_path}")
    print(f"Tiempo de entrenamiento: {elapsed / 60.0:.1f} minutos")
    print(
        f"Cortes intermedios en: {CHECKPOINT_DIR}\n"
        f"TensorBoard: tensorboard --logdir \"{TENSORBOARD_DIR}\""
    )

    print("\nEvaluación final (política determinista):")
    evaluate_model(
        model,
        episodes=args.eval_episodes,
        gui=args.gui_eval,
        seed=args.seed + 1000,
        visual_mesh=visual_mesh,
    )


if __name__ == "__main__":
    main()
