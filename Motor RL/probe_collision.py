"""Diagnostico: por que WALL-E frena lejos de todo.

Avanza en linea recta y cada 10 pasos imprime:
  - si _has_collision() dice que si
  - contra que cuerpo choca y a que distancia esta el punto de contacto
  - las 6 distancias LiDAR frontales
  - la posicion del robot
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pybullet as p

from walle_env_v3 import WallEEnvV3

env = WallEEnvV3(render_mode=None, show_proxy_visuals=False, stage=3, obstacle_count=6)
obs, _info = env.reset()

names: dict[int, str] = {}
for body in (
    env.wall_ids
    + env.obstacle_ids
    + env.cylinder_ids
    + env.long_wall_ids
    + env.ramp_ids
    + env.l_wall_ids
):
    try:
        info = p.getBodyInfo(body)
        names[body] = info[0].decode("utf-8", "replace")
    except Exception:
        names[body] = "?"

print("cuerpos vigilados:", len(names))
print("robot id:", env.robot, "plane:", env.plane)
print("robot en lista?", env.robot in names)
print()

for step in range(400):
    env.step([0.45, 0.45])
    if step % 10 != 0:
        continue
    pos, _orn = p.getBasePositionAndOrientation(env.robot)
    hit = env._has_collision()
    front = env.lidar_meters[env._front_indices]
    near = float(front.min()) if front.size else -1.0
    line = (
        f"t={step:3d} pos=({pos[0]:+.2f},{pos[1]:+.2f}) "
        f"col={int(hit)} front_min={near:.2f} "
        f"front={[round(float(x), 2) for x in front[:6]]}"
    )
    print(line, flush=True)
    if hit:
        for body in names:
            contacts = p.getContactPoints(bodyA=env.robot, bodyB=body)
            for c in contacts:
                link = c[3]
                point = c[5]
                dist = math.dist((pos[0], pos[1], pos[2]), point)
                normal = c[7]
                force = c[9]
                print(
                    f"    CHOQUE con {names[body]}(id={body}) link={link} "
                    f"punto=({point[0]:+.2f},{point[1]:+.2f},{point[2]:+.2f}) "
                    f"dist={dist:.2f} normal=({normal[0]:+.2f},{normal[1]:+.2f},"
                    f"{normal[2]:+.2f}) fuerza={force:.1f}",
                    flush=True,
                )
        print(flush=True)

env.close()
