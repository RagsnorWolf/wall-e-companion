"""Test de la recuperación anti-atasco del modo PPO."""

from __future__ import annotations

import numpy as np

from interactive_walle import CONTROL_HZ, WalleController
from walle_env_v3 import WallEEnvV3


def main() -> None:
    env = WallEEnvV3(
        render_mode=None,
        show_proxy_visuals=False,
        stage=3,
        obstacle_count=6,
    )
    env.reset(
        seed=1,
        options={"start_pos": (0.0, 0.0, 0.15), "start_yaw": 0.0, "goal": 1.0},
    )
    env.set_reference_yaw(0.0)
    controller = WalleController(env)
    controller.set_control_mode("ppo")
    start = controller._pose()

    # Forzar la maniobra de escape como si hubiera colisión.
    controller._start_ppo_recovery("test")
    print("modo tras iniciar recuperación:", controller.mode)
    steps = 0
    while controller.mode == "ppo_recovering" and steps < int(5 * CONTROL_HZ):
        controller.tick()
        steps += 1
    end = controller._pose()
    print(f"recuperación: {steps} pasos ({steps / CONTROL_HZ:.2f} s)")
    print("modo final:", controller.mode)
    print(
        "retroceso: x {:+.3f} -> {:+.3f} (delta {:+.3f} m)".format(
            start.pos[0], end.pos[0], end.pos[0] - start.pos[0]
        )
    )
    print("nuevo goal_angle:", round(float(env.goal_angle), 3))
    print("LSTM reseteada:", controller._lstm_states is None)

    # Debe seguir explorando sin errores tras la recuperación.
    for _ in range(int(3 * CONTROL_HZ)):
        controller.tick()
    print("modo tras 3 s más:", controller.mode)
    print("posición:", np.round(controller._pose().pos[:2], 3))
    env.close()


if __name__ == "__main__":
    main()
