"""Que ve el LiDAR de los pies justo despues del reset en casa."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pybullet as p

import interactive_walle as iw

env = iw.WallEEnvV3(
    render_mode=None, show_proxy_visuals=False, stage=3, obstacle_count=6
)
env.render = lambda: None
iw.build_scene(env)
iw.reset_env_home(env)

pos, _q = p.getBasePositionAndOrientation(env.robot)
print(f"robot en {pos}")
print(f"enable_sensors={env._enable_sensors}")
print(f"lidar min={float(env.lidar_meters.min()):.3f} "
      f"max={float(env.lidar_meters.max()):.3f}")
print("anillo completo:")
print(np.round(env.lidar_meters, 2).tolist())
print(f"front_clearance(30)={env.front_clearance():.3f}")
print(f"front_clearance(60)={env.front_clearance(60.0):.3f}")

# Que cuerpo esta en el origen?
print("\ncuerpos cercanos al origen:")
for body in (env.obstacle_ids + env.cylinder_ids + env.long_wall_ids
             + env.ramp_ids + env.l_wall_ids):
    bpos, _ = p.getBasePositionAndOrientation(body)
    dist = float(np.hypot(bpos[0] - pos[0], bpos[1] - pos[1]))
    if dist < 3.0:
        print(f"  body={body} pos=({bpos[0]:+.2f},{bpos[1]:+.2f}) dist={dist:.2f}")

# Rayos crudos hacia el frente, sin excluir a nadie.
for name, parent in (("con exclusion", env.robot), ("sin exclusion", -1)):
    froms = [[pos[0], pos[1], pos[2] + 0.06]]
    tos = [[pos[0] + 6.0, pos[1], pos[2] + 0.06]]
    hits = p.rayTestBatch(froms, tos, parent, -1, 0)
    hit = hits[0]
    print(f"{name}: body={hit[0]} link={hit[1]} frac={hit[2]:.4f}")

env.close()
