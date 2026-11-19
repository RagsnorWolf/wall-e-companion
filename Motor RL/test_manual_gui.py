"""Test end-to-end del controlador manual de la GUI, sin ventana.

Simula exactamente lo que hace interactive_walle.py a 60 Hz:
comando de texto -> PID -> env.step. Mide tiempo y distancia reales.
"""

from __future__ import annotations

import time

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
    start = controller._pose()
    print(
        "inicio: x={:+.3f} y={:+.3f} yaw={:+.1f}°".format(
            start.pos[0], start.pos[1], np.degrees(start.yaw)
        )
    )
    for reply in controller.handle_text("avanza 1 metro"):
        print("respuesta:", reply)

    steps = 0
    t0 = time.perf_counter()
    min_up = 1.0
    while controller.mode == "moving" and steps < int(20 * CONTROL_HZ):
        controller.tick()
        steps += 1
        min_up = min(min_up, controller._pose().up_z)
    wall = time.perf_counter() - t0
    end = controller._pose()
    dist = float(np.hypot(end.pos[0] - start.pos[0], end.pos[1] - start.pos[1]))
    print("modo final:", controller.mode)
    print(f"pasos: {steps} -> tiempo sim {steps / CONTROL_HZ:.2f} s")
    print(f"tiempo real headless: {wall:.2f} s")
    print(f"avance real: {dist:.3f} m")
    print(f"error vs 1.000 m: {dist - 1.0:+.3f} m")
    print(f"up_z mínimo (1.0=vertical): {min_up:.4f}")
    print("colisiones:", controller.falls_detected, "caídas")

    # Giro de 90° para validar el PID de rumbo.
    start_yaw = controller._pose().yaw
    for reply in controller.handle_text("gira 90 grados a la izquierda"):
        print("respuesta:", reply)
    steps = 0
    min_up_turn = 1.0
    while controller.mode == "turning" and steps < int(20 * CONTROL_HZ):
        controller.tick()
        steps += 1
        min_up_turn = min(min_up_turn, controller._pose().up_z)
    end_yaw = controller._pose().yaw
    delta = np.degrees(np.arctan2(np.sin(end_yaw - start_yaw), np.cos(end_yaw - start_yaw)))
    print(f"giro: {delta:+.1f}° en {steps / CONTROL_HZ:.2f} s (objetivo +90°)")
    print(f"up_z mínimo en giro: {min_up_turn:.4f}")
    env.close()


if __name__ == "__main__":
    main()
