"""Test de avance manual: mide velocidad y tilt con distintas acciones."""

from __future__ import annotations

import numpy as np
import pybullet as p

from walle_env_v3 import WallEEnvV3


def run_action(action_value: float, steps: int = 120) -> None:
    env = WallEEnvV3(
        render_mode=None,
        stage=3,
        obstacle_count=6,
        show_proxy_visuals=False,
    )
    env.reset(
        seed=1,
        options={"start_pos": (0.0, 0.0, 0.15), "start_yaw": 0.0, "goal": 1.0},
    )
    env.set_reference_yaw(0.0)
    start, _ = p.getBasePositionAndOrientation(env.robot)
    max_tilt = 0.0
    for i in range(steps):
        obs, reward, terminated, truncated, info = env.step(
            np.array([action_value, action_value], dtype=np.float32)
        )
        max_tilt = max(max_tilt, float(info["tilt_deg"]))
        if terminated or truncated:
            print(f"  acción {action_value}: terminó en paso {i} ({info})")
            break
    end, _ = p.getBasePositionAndOrientation(env.robot)
    dist = float(np.hypot(end[0] - start[0], end[1] - start[1]))
    print(
        f"acción {action_value:.2f}: avance {dist:.3f} m en "
        f"{steps / 60.0:.1f} s -> {dist / (steps / 60.0):.3f} m/s, "
        f"tilt máx {max_tilt:.1f}°"
    )
    env.close()


def main() -> None:
    for action_value in (0.45, 0.70, 0.90, 1.00):
        run_action(action_value)


if __name__ == "__main__":
    main()
