"""Que toca WALL-E en (5.03,-2.42) mirando a -Y, y que ve el LiDAR."""
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

groups = {
    "wall": env.wall_ids,
    "obstacle": env.obstacle_ids,
    "cylinder": env.cylinder_ids,
    "long_wall": env.long_wall_ids,
    "ramp": env.ramp_ids,
    "l_wall": env.l_wall_ids,
}

TARGET = (5.03, -2.42)
p.resetBasePositionAndOrientation(
    env.robot,
    [TARGET[0], TARGET[1], 0.16],
    p.getQuaternionFromEuler([0.0, 0.0, np.radians(-90.0)]),
)
for _ in range(120):
    p.stepSimulation()

pos, quat = p.getBasePositionAndOrientation(env.robot)
print(f"asentado en ({pos[0]:+.3f},{pos[1]:+.3f},{pos[2]:+.3f})")

print("\ncontactos:")
for name, ids in groups.items():
    for body in ids:
        for c in p.getContactPoints(bodyA=env.robot, bodyB=body):
            if float(c[9]) > 0.02:
                print(
                    f"  {name} id={body} linkA={c[3]} "
                    f"n=({c[7][0]:+.2f},{c[7][1]:+.2f},{c[7][2]:+.2f}) "
                    f"f={float(c[9]):.1f} dist={float(c[8]):.3f}"
                )

env._scan_lidar()
meters = np.asarray(env.lidar_meters)
print(f"\nlidar min={meters.min():.2f} frente={meters[0]:.2f}")
print("primeros 20 rayos (0 = rumbo, +izquierda):")
print(np.round(meters[:20], 2).tolist())
print(f"front_clearance(30)={env.front_clearance():.2f}")

print("\nempujo 1.5 s hacia -Y:")
start = p.getBasePositionAndOrientation(env.robot)[0]
for _ in range(90):
    for j in (0, 1):
        p.setJointMotorControl2(
            env.robot, j, p.VELOCITY_CONTROL, targetVelocity=5.0, force=1.6
        )
    p.stepSimulation()
end = p.getBasePositionAndOrientation(env.robot)[0]
print(f"  avance = {np.hypot(end[0]-start[0], end[1]-start[1]):.3f} m")

env.close()
