"""
train_walle_v3.py  –  Entrenamiento del Explorador Autónomo WALL-E (V3, 19D)

Entrena una política PPO para que WALL-E explore un entorno con obstáculos
variados (cajas, cilindros, paredes largas), usando 5 sensores raycast
frontales y un mapa de chunks dinámico.

Uso:
    python train_walle_v3.py --timesteps 300000 --output_dir ./models
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv

from walle_env_v3 import WallEEnvV3


def make_env(seed: int, stage: int = 3, obstacle_count: int = 6):
    """Factory para crear entornos V3 con semilla determinada."""

    def _init():
        return WallEEnvV3(
            render_mode=None,
            stage=stage,
            max_episode_steps=600,
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

    return _init


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Entrenar modelo V3 de exploración autónoma"
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
        default=300000,
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
        help="Número de obstáculos (cajas + cilindros)",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Entornos vectorizados
    env_fns = [make_env(i, args.stage, args.obstacle_count) for i in range(max(args.workers, 1))]
    env = SubprocVecEnv(env_fns)

    model_path = args.model if args.model else None
    if model_path and os.path.exists(model_path):
        print(f"[TRAIN_V3] Cargando modelo existente: {model_path}")
        model = PPO.load(model_path, env)
    else:
        print("[TRAIN_V3] Entrenando desde cero (observación 19D)")
        model = PPO(
            "MlpPolicy",
            env,
            verbose=1,
            device="cuda" if torch.cuda.is_available() else "cpu",
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
        )

    print(f"[TRAIN_V3] Entrenando por {args.timesteps} pasos de tiempo...")
    start = time.time()
    model.learn(total_timesteps=args.timesteps, progress_bar=True)
    dur = time.time() - start
    print(f"[TRAIN_V3] Entrenamiento finalizado en {dur:.1f}s")

    out_path = os.path.join(args.output_dir, "walle_ppo_model_v3_explorer.zip")
    model.save(out_path)
    print(f"[TRAIN_V3] Modelo guardado: {out_path}")

    env.close()


if __name__ == "__main__":
    main()
