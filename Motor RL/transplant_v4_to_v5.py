"""
transplant_v4_to_v5.py -- arrancar el cerebro V5 con lo que ya sabe el V4.

El problema: V5 observa 58 numeros (14 base + 36 LiDAR + 8 extras) y V4
observaba 50 (14 base + 36 LiDAR). Un modelo V5 desde cero tarda cientos de
miles de pasos en dejar de girar en el sitio.

La solucion: los primeros 50 numeros son EXACTAMENTE los mismos, en el mismo
orden. Asi que se copian todos los pesos del V4 y solo se ensancha la entrada
del LSTM de 50 a 58, dejando las 8 columnas nuevas en cero. La politica se
comporta igual que el V4 hasta que el entrenamiento decida usar los extras.

Uso:

    python transplant_v4_to_v5.py
    python transplant_v4_to_v5.py --out models\otro_nombre.zip
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import torch
from sb3_contrib import RecurrentPPO

from walle_env_v3 import WallEEnvV3

POLICY_KWARGS = dict(
    net_arch=[256, 256],
    lstm_hidden_size=256,
    n_lstm_layers=1,
    enable_critic_lstm=True,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Trasplante V4 (50D) -> V5 (58D)")
    parser.add_argument("--source", default="models/walle_ppo_model_v4_lidar.zip")
    parser.add_argument("--out", default="models/walle_ppo_model_v5_recovery.zip")
    parser.add_argument("--steps", type=int, default=120, help="pasos de verificacion")
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"No existe el modelo origen: {args.source}")
        return 1

    print(f"Cargando {args.source} ...")
    v4 = RecurrentPPO.load(args.source, device="cpu")
    src = v4.policy.state_dict()
    src_obs = int(v4.observation_space.shape[0])
    print(f"  V4: obs {src_obs}D, {v4.num_timesteps} pasos entrenados")

    env = WallEEnvV3(
        render_mode=None, stage=3, obstacle_count=6, connect_options="DIRECT"
    )
    dst_obs = int(env.observation_space.shape[0])
    print(f"  V5: obs {dst_obs}D")

    model = RecurrentPPO(
        "MlpLstmPolicy",
        env,
        device="cpu",
        learning_rate=3e-4,
        n_steps=1024,
        batch_size=256,
        n_epochs=8,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.02,
        policy_kwargs=POLICY_KWARGS,
    )

    dst = model.policy.state_dict()
    merged = {}
    copied: list[str] = []
    widened: list[tuple[str, tuple[int, ...], tuple[int, ...]]] = []
    fresh: list[str] = []

    for key, target in dst.items():
        source = src.get(key)
        if source is None:
            merged[key] = target
            fresh.append(key)
            continue
        if source.shape == target.shape:
            merged[key] = source.clone()
            copied.append(key)
            continue
        # Entrada del LSTM: (4*hidden, obs). Se copia lo viejo y se anula lo
        # nuevo para que las 8 features extra no aporten nada al principio.
        if (
            source.dim() == 2
            and source.shape[0] == target.shape[0]
            and source.shape[1] < target.shape[1]
        ):
            wide = torch.zeros_like(target)
            wide[:, : source.shape[1]] = source
            merged[key] = wide
            widened.append((key, tuple(source.shape), tuple(target.shape)))
            continue
        print(f"  OJO: {key} no encaja ({tuple(source.shape)} vs {tuple(target.shape)}), se deja al azar")
        merged[key] = target
        fresh.append(key)

    model.policy.load_state_dict(merged)
    print(f"  pesos copiados: {len(copied)}")
    print(f"  entrada ensanchada: {len(widened)}")
    for key, old, new in widened:
        print(f"    {key}: {old} -> {new}")
    if fresh:
        print(f"  sin origen (quedan al azar): {len(fresh)}")

    # Verificacion: que no se pase la vida girando.
    obs, _info = env.reset()
    lstm = None
    ep_start = np.ones((1,), dtype=bool)
    actions = []
    for _ in range(args.steps):
        action, lstm = model.predict(obs, state=lstm, episode_start=ep_start, deterministic=True)
        ep_start = np.zeros((1,), dtype=bool)
        actions.append(np.asarray(action, dtype=float))
        obs, _r, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            obs, _info = env.reset()
            lstm = None
            ep_start = np.ones((1,), dtype=bool)

    arr = np.array(actions)
    turning = int((np.sign(arr[:, 0]) != np.sign(arr[:, 1])).sum())
    print()
    print(f"verificacion ({len(arr)} pasos):")
    print(f"  media L={arr[:,0].mean():+.3f}  R={arr[:,1].mean():+.3f}")
    print(f"  gira (signos opuestos): {turning}/{len(arr)}")
    print(f"  avanza (mismo signo):   {len(arr)-turning}/{len(arr)}")

    model.save(args.out)
    print()
    print(f"Guardado: {args.out}")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
