"""
train_walle_v4.py — Entrenamiento del Explorador Autónomo V4 (LiDAR 72, 50D)

Usa RecurrentPPO (LSTM) de sb3-contrib para que WALL-E tenga memoria a corto
plazo y no se quede atrapado repitiendo zonas ya visitadas.

Red: [256, 256] + LSTM de 256 unidades.
Entorno: WallEEnvV3 con LiDAR de 72 rayos, obstáculos complejos, rampas,
paredes en L y zonas de fricción variable.

Uso:
    python train_walle_v4.py --timesteps 1000000 --output_dir ./models
"""

from __future__ import annotations

import argparse
import os
import time

import torch
from sb3_contrib import RecurrentPPO
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.vec_env import SubprocVecEnv

from walle_env_v3 import WallEEnvV3


def make_env(seed: int, stage: int = 3, obstacle_count: int = 6):
    """Factory para crear entornos V4 con semilla determinada."""

    def _init():
        env = WallEEnvV3(
            render_mode=None,
            stage=stage,
            max_episode_steps=900,
            max_wheel_speed=2.5,
            max_force=0.5,
            arena_half_size=12.0,
            obstacle_count=obstacle_count,
            stage3_min_obstacle_distance=2.5,
            obstacle_max_distance=10.0,
            obstacle_min_separation=1.5,
            enable_sensors=True,
            sensor_noise_std=0.02,
        )
        env.reset(seed=seed)
        return env

    return _init


def main() -> None:
    # Con 4 workers de PyBullet en 4 núcleos, limitar los hilos de PyTorch
    # evita sobre-suscripción y mejora el rendimiento global del entrenamiento.
    torch.set_num_threads(4)

    parser = argparse.ArgumentParser(
        description="Entrenar modelo V4 de exploración autónoma (LiDAR 72)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="Ruta a un modelo existente para continuar entrenamiento",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="./models",
        help="Directorio donde guardar el modelo entrenado",
    )
    parser.add_argument(
        "--timesteps",
        type=int,
        default=1000000,
        help="Total de pasos de entrenamiento",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Número de entornos en paralelo",
    )
    parser.add_argument(
        "--stage",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="Etapa de entrenamiento (3 = combinado con obstáculos)",
    )
    parser.add_argument(
        "--obstacle_count",
        type=int,
        default=6,
        help="Número de obstáculos base (cajas + cilindros)",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Entornos vectorizados
    env_fns = [
        make_env(i, args.stage, args.obstacle_count)
        for i in range(max(args.workers, 1))
    ]
    env = SubprocVecEnv(env_fns)

    model_path = args.model if args.model else None
    if model_path and os.path.exists(model_path):
        print(f"[TRAIN_V4] Cargando modelo existente: {model_path}")
        model = RecurrentPPO.load(model_path, env)
    else:
        print("[TRAIN_V4] Entrenando desde cero (LiDAR 72, obs 50D, LSTM)")
        model = RecurrentPPO(
            "MlpLstmPolicy",
            env,
            verbose=1,
            device="cuda" if torch.cuda.is_available() else "cpu",
            learning_rate=3e-4,
            n_steps=1024,
            batch_size=128,
            n_epochs=8,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            policy_kwargs=dict(
                net_arch=[256, 256],
                lstm_hidden_size=256,
                n_lstm_layers=1,
                enable_critic_lstm=True,
            ),
        )

    print(f"[TRAIN_V4] Entrenando por {args.timesteps} pasos de tiempo...")
    start = time.time()
    # Guardar checkpoints periódicos para poder probar PPO durante el
    # entrenamiento (la GUI carga el más reciente si aún no existe el final).
    checkpoint_dir = os.path.join(args.output_dir, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_cb = CheckpointCallback(
        save_freq=max(1, 50000 // max(1, env.num_envs)),
        save_path=checkpoint_dir,
        name_prefix="walle_v4",
        save_replay_buffer=False,
        save_vecnormalize=False,
    )
    model.learn(
        total_timesteps=args.timesteps,
        progress_bar=True,
        callback=checkpoint_cb,
        reset_num_timesteps=False,
    )
    dur = time.time() - start
    print(f"[TRAIN_V4] Entrenamiento finalizado en {dur:.1f}s")

    out_path = os.path.join(args.output_dir, "walle_ppo_model_v4_lidar.zip")
    model.save(out_path)
    print(f"[TRAIN_V4] Modelo guardado: {out_path}")

    env.close()


if __name__ == "__main__":
    main()
