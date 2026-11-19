"""Test rapido de 10 s: abanico LiDAR azul + estetica mejorada V3.

Abre la ventana de PyBullet con el entorno V3, dibuja el scanner de
36 rayos azules (FOV 180 grados), el HUD "ESCANEANDO..." y la grilla de
chunks, mientras el robot avanza suavemente. Cierra solo a los 10 s.
"""

from __future__ import annotations

import time

import pybullet as p

from interactive_walle import build_scene, WalleHud
from walle_env_v3 import WallEEnvV3

DURACION_S = 10.0


def main() -> None:
    env = WallEEnvV3(
        render_mode="gui",
        stage=3,
        obstacle_count=6,
        max_episode_steps=100000,
        enable_sensors=True,
    )
    build_scene(env)
    hud = WalleHud(env)  # controller=None -> HUD "ESCANEANDO..."
    env.reset()
    p.resetDebugVisualizerCamera(
        cameraDistance=5.0,
        cameraYaw=45.0,
        cameraPitch=-25.0,
        cameraTargetPosition=[0.0, 0.0, 0.3],
    )
    print("[TEST] Escena V3 lista. Scanner LiDAR azul activo 10 segundos...")
    inicio = time.perf_counter()
    pasos = 0
    while time.perf_counter() - inicio < DURACION_S:
        # Avance suave para ver el abanico barriendo el escenario
        _obs, _r, terminado, truncado, _info = env.step([0.30, 0.30])
        hud.update()
        pasos += 1
        if terminado or truncado:
            env.reset()
    print(f"[TEST] Listo: {pasos} pasos en {DURACION_S:.0f} s. Cerrando.")
    env.close()


if __name__ == "__main__":
    main()
