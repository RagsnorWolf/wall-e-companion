"""Smoke test V4: valida obs 50D, LiDAR 72, recompensas y espacio Gymnasium."""

from __future__ import annotations

import numpy as np

from walle_env_v3 import WallEEnvV3


def main() -> None:
    env = WallEEnvV3(
        render_mode=None,
        stage=3,
        max_episode_steps=400,
        obstacle_count=6,
        enable_sensors=True,
        sensor_noise_std=0.02,
    )
    obs, info = env.reset(seed=42)
    assert obs.shape == (50,), obs.shape
    assert env.lidar_meters.shape == (72,), env.lidar_meters.shape
    assert env.observation_space.contains(obs), "obs inicial fuera del espacio"

    rewards: list[float] = []
    traps = 0
    collision_steps = 0
    chunks = 0
    for step in range(400):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        assert env.observation_space.contains(obs), (
            f"obs fuera del espacio en paso {step}: "
            f"min={obs.min():.3f} max={obs.max():.3f}"
        )
        assert np.isfinite(reward), f"reward no finito en paso {step}"
        rewards.append(float(reward))
        traps += int(bool(info.get("trapped", False)))
        collision_steps += int(bool(info.get("collision", False)))
        chunks += int(info.get("chunks_discovered", 0))
        if terminated or truncated:
            break

    print(f"Pasos ejecutados: {len(rewards)}")
    print(f"Recompensa total: {sum(rewards):+.2f}")
    print(f"Recompensa media: {np.mean(rewards):+.3f}")
    print(f"Trampas detectadas: {traps}")
    print(f"Pasos con colisión: {collision_steps}")
    print(f"Chunks nuevos: {chunks}")
    print(
        "LiDAR min/max: "
        f"{float(env.lidar_meters.min()):.2f} / "
        f"{float(env.lidar_meters.max()):.2f} m"
    )
    env.close()
    print("ENV SMOKE OK")


if __name__ == "__main__":
    main()
