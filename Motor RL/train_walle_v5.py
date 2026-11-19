"""
train_walle_v5.py · Entrenamiento del Explorador Autónomo V5 (obs 58D)

Cambios respecto a V4 (prioridad: resolución de problemas):

1. Chocar ya NO termina el episodio. El robot aprende a retroceder, girar
   hacia el hueco libre y seguir explorando en vez de morir en el impacto.
2. La observación añade 8 valores de contexto:
      claridad frontal, distancia mínima, rumbo del obstáculo más cercano,
      dirección del hueco más ancho, contacto y atascado.
3. El LiDAR escanea a ras de suelo desde el centro del robot: ve lo que está
   a punto de tocar (antes el origen quedaba dentro del obstáculo al chocar).
4. Recompensas nuevas: castigo por paso en contacto, bonus por soltarse,
   bonus por ganar holgura y castigo por acercarse aún más estando pegado.

Uso:
    python train_walle_v5.py --timesteps 2000000 --output_dir ./models
    python train_walle_v5.py --resume ./models/checkpoints/walle_v5_500000_steps.zip
"""

from __future__ import annotations

import argparse
import os
import time

import torch
from sb3_contrib import RecurrentPPO
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

from walle_env_v3 import OBS_DIM, WallEEnvV3

MODEL_NAME = "walle_ppo_model_v5_recovery.zip"


def make_env(seed: int, stage: int = 3, obstacle_count: int = 8):
    """Factory para crear entornos V5 con semilla determinada."""

    def _init():
        env = WallEEnvV3(
            render_mode=None,
            stage=stage,
            max_episode_steps=1200,
            max_wheel_speed=2.5,
            max_force=0.5,
            arena_half_size=12.0,
            obstacle_count=obstacle_count,
            stage3_min_obstacle_distance=2.0,
            obstacle_max_distance=10.0,
            obstacle_min_separation=1.5,
            enable_sensors=True,
            sensor_noise_std=0.02,
            # Clave del V5: recuperarse del choque, no morir en él.
            collision_terminates=False,
        )
        env.reset(seed=seed)
        return env

    return _init


def main() -> None:
    # Limitar los hilos de PyTorch evita sobre-suscripción con los workers de
    # PyBullet. OJO: no tocar OMP_NUM_THREADS — pybullet pide numThreads=4 en
    # el barrido de rayos y si OpenMP queda con 1 hilo el worker muere.
    #
    # Con 2 hilos el backward del LSTM se comía 27 s por iteración. Medido en
    # este equipo (Ryzen 5 3400G, 8 lógicos): 6 hilos bajan la iteración de
    # 2048 pasos de ~35 s a ~22 s. Se deja aire para los dos entornos.
    _logical = os.cpu_count() or 4
    torch.set_num_threads(max(2, min(6, _logical - 2)))
    print(f"[TRAIN_V5] Hilos de torch: {torch.get_num_threads()} de {_logical} lógicos")

    parser = argparse.ArgumentParser(
        description="Entrenar modelo V5 (LiDAR a ras de suelo, obs 58D)"
    )
    parser.add_argument(
        "--resume",
        type=str,
        default="",
        help="Checkpoint o modelo V5 existente para continuar entrenamiento",
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
        default=2000000,
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
        default=8,
        help="Número de obstáculos base (cajas + cilindros)",
    )
    parser.add_argument(
        "--vec",
        type=str,
        default="auto",
        choices=["auto", "dummy", "subproc"],
        help=(
            "Tipo de vectorización. 'dummy' entrena en el proceso principal "
            "(estable; el más lento). 'subproc' reparte en procesos hijos."
        ),
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    n_envs = max(args.workers, 1)
    env_fns = [make_env(i, args.stage, args.obstacle_count) for i in range(n_envs)]

    # En esta build de PyBullet (Nov 2026) un entorno creado dentro de un
    # proceso hijo de SubprocVecEnv puede terminar en access violation, que el
    # padre sólo ve como EOFError. El entrenamiento tiene que arrancar siempre:
    # por defecto se usa DummyVecEnv (en proceso) y subproc queda como opción
    # explícita.
    use_subproc = args.vec == "subproc"
    if use_subproc:
        print(f"[TRAIN_V5] Vectorización: SubprocVecEnv x{n_envs}")
        env = SubprocVecEnv(env_fns)
    else:
        print(f"[TRAIN_V5] Vectorización: DummyVecEnv x{n_envs} (en proceso)")
        env = DummyVecEnv(env_fns)

    if args.resume and os.path.exists(args.resume):
        print(f"[TRAIN_V5] Cargando modelo existente: {args.resume}")
        model = RecurrentPPO.load(args.resume, env)
    else:
        print(f"[TRAIN_V5] Entrenando desde cero (obs {OBS_DIM}D, LSTM)")
        model = RecurrentPPO(
            "MlpLstmPolicy",
            env,
            verbose=1,
            device="cuda" if torch.cuda.is_available() else "cpu",
            learning_rate=3e-4,
            n_steps=1024,
            batch_size=256,
            n_epochs=8,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.02,
            policy_kwargs=dict(
                net_arch=[256, 256],
                lstm_hidden_size=256,
                n_lstm_layers=1,
                enable_critic_lstm=True,
            ),
        )

    print(f"[TRAIN_V5] Entrenando por {args.timesteps} pasos de tiempo...")
    start = time.time()
    checkpoint_dir = os.path.join(args.output_dir, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_cb = CheckpointCallback(
        # Cada 10 000 pasos y no 50 000: las corridas anteriores morian antes
        # del primer checkpoint y se perdia todo. A ~250 pasos/s son 40 s de
        # trabajo perdido como mucho.
        save_freq=max(1, 10000 // max(1, env.num_envs)),
        save_path=checkpoint_dir,
        name_prefix="walle_v5",
        save_replay_buffer=False,
        save_vecnormalize=False,
    )
    model.learn(
        total_timesteps=args.timesteps,
        # progress_bar usa rich sobre stdout: con la salida redirigida a un
        # fichero (como hace el lanzador) se queda bloqueado y el padre no
        # arranca el rollout. Log de texto con verbose=1 es suficiente.
        progress_bar=False,
        callback=checkpoint_cb,
        reset_num_timesteps=False,
    )
    dur = time.time() - start
    print(f"[TRAIN_V5] Entrenamiento finalizado en {dur:.1f}s")

    out_path = os.path.join(args.output_dir, MODEL_NAME)
    model.save(out_path)
    print(f"[TRAIN_V5] Modelo guardado: {out_path}")

    env.close()


if __name__ == "__main__":
    main()
