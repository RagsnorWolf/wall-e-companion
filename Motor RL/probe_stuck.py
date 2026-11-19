"""Que hay donde se traba: cuerpos, altura, inclinacion y contactos."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pybullet as p

import interactive_walle as iw

TARGET = (5.10, -2.40)

env = iw.WallEEnvV3(
    render_mode=None, show_proxy_visuals=False, stage=3, obstacle_count=6
)
env.render = lambda: None
iw.build_scene(env)
iw.reset_env_home(env)

print(f"robot en {p.getBasePositionAndOrientation(env.robot)[0]}")
print("\ncuerpos de la escena:")
groups = {
    "wall": env.wall_ids,
    "obstacle": env.obstacle_ids,
    "cylinder": env.cylinder_ids,
    "long_wall": env.long_wall_ids,
    "ramp": env.ramp_ids,
    "l_wall": env.l_wall_ids,
}
for name, ids in groups.items():
    for body in ids:
        bpos, bquat = p.getBasePositionAndOrientation(body)
        aabb = p.getAABB(body)
        dist = float(np.hypot(bpos[0] - TARGET[0], bpos[1] - TARGET[1]))
        if dist < 2.0:
            print(
                f"  {name:9s} id={body} pos=({bpos[0]:+.2f},{bpos[1]:+.2f},"
                f"{bpos[2]:+.2f}) dist={dist:.2f} "
                f"aabb_z=({aabb[0][2]:+.2f},{aabb[1][2]:+.2f}) "
                f"aabb_xy=({aabb[0][0]:+.2f},{aabb[0][1]:+.2f}).."
                f"({aabb[1][0]:+.2f},{aabb[1][1]:+.2f})"
            )

# Colocar el robot en el punto del atasco y ver que toca.
p.resetBasePositionAndOrientation(
    env.robot, [TARGET[0], TARGET[1], 0.15], [0, 0, 0, 1]
)
for _ in range(240):
    p.setJointMotorControl2(env.robot, 0, p.VELOCITY_CONTROL,
                            targetVelocity=0.0, force=1.6)
    p.setJointMotorControl2(env.robot, 1, p.VELOCITY_CONTROL,
                            targetVelocity=0.0, force=1.6)
    p.stepSimulation()

pos, quat = p.getBasePositionAndOrientation(env.robot)
roll, pitch, yaw = p.getEulerFromQuaternion(quat)
print(
    f"\ntras asentar: pos=({pos[0]:+.2f},{pos[1]:+.2f},{pos[2]:+.3f}) "
    f"roll={np.degrees(roll):+.1f} pitch={np.degrees(pitch):+.1f}"
)
print("contactos:")
for name, ids in groups.items():
    for body in ids:
        contacts = p.getContactPoints(bodyA=env.robot, bodyB=body)
        for c in contacts:
            if float(c[9]) > 0.02:
                print(
                    f"  {name} id={body} linkA={c[3]} linkB={c[4]} "
                    f"p=({c[5][0]:+.2f},{c[5][1]:+.2f},{c[5][2]:+.3f}) "
                    f"n=({c[7][0]:+.2f},{c[7][1]:+.2f},{c[7][2]:+.2f}) "
                    f"f={float(c[9]):.1f}"
                )

print("\nempujo 1.5 s hacia +X y mido:")
start = p.getBasePositionAndOrientation(env.robot)[0]
for _ in range(90):
    for j in (0, 1):
        p.setJointMotorControl2(env.robot, j, p.VELOCITY_CONTROL,
                                targetVelocity=5.0, force=1.6)
    p.stepSimulation()
end = p.getBasePositionAndOrientation(env.robot)[0]
print(f"  avance = {np.hypot(end[0]-start[0], end[1]-start[1]):.3f} m")

env.close()
