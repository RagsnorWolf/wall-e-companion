"""Test end-to-end del modo PPO de la GUI, sin ventana.

Carga el checkpoint V4 más reciente (o el modelo final si existe) y ejecuta
la exploración autónoma exactamente como lo hace interactive_walle.py.
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
    for reply in controller.set_control_mode("ppo"):
        print("respuesta:", reply)
    if controller.model is None:
        print("ERROR: el modelo no se cargó")
        env.close()
        return
    print("modelo:", controller.model_path.name)
    print("recurrente:", controller._is_recurrent())

    start = controller._pose()
    steps = 0
    collisions = 0
    t0 = time.perf_counter()
    max_tilt = 0.0
    while steps < int(40 * CONTROL_HZ):
        controller.tick()
        steps += 1
        pose = controller._pose()
        max_tilt = max(max_tilt, np.degrees(np.arccos(np.clip(pose.up_z, -1.0, 1.0))))
        if steps % int(4 * CONTROL_HZ) == 0:
            print(
                f"t={steps / CONTROL_HZ:4.1f}s x={pose.pos[0]:+.2f} "
                f"y={pose.pos[1]:+.2f} yaw={np.degrees(pose.yaw):+6.1f}° "
                f"chunks={len(env.chunk_mapper.cells)} modo={controller.mode}"
            )
        if controller.mode in ("idle", "braking"):
            # El controlador se detuvo (colisión/volcado): reiniciar como la GUI.
            if controller.mode == "braking":
                collisions += 1
            break
    wall = time.perf_counter() - t0
    end = controller._pose()
    dist = float(np.hypot(end.pos[0] - start.pos[0], end.pos[1] - start.pos[1]))
    print(f"pasos: {steps} ({steps / CONTROL_HZ:.1f} s sim) en {wall:.2f} s reales")
    print(f"avance neto: {dist:.2f} m")
    print(f"chunks descubiertos: {len(env.chunk_mapper.cells)}")
    print(f"tilt máximo: {max_tilt:.1f}°")
    print(f"paradas/colisiones detectadas: {collisions}")
    print(f"LiDAR mínimo: {float(np.min(env.lidar_meters)):.2f} m")
    env.close()


if __name__ == "__main__":
    main()
