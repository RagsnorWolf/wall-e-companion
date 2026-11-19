"""Geometria de la rampa y que toca WALL-E cuando se traba cerca de ella."""
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

print("rampas:")
for body in env.ramp_ids:
    pos, quat = p.getBasePositionAndOrientation(body)
    aabb = p.getAABB(body)
    print(
        f"  id={body} pos=({pos[0]:+.2f},{pos[1]:+.2f},{pos[2]:+.3f}) "
        f"aabb=({aabb[0][0]:+.2f},{aabb[0][1]:+.2f},{aabb[0][2]:+.3f}).."
        f"({aabb[1][0]:+.2f},{aabb[1][1]:+.2f},{aabb[1][2]:+.3f})"
    )

# Colocar el robot en el punto del atasco y empujar hacia +X.
TARGET = (3.81, -2.38)
for yaw_deg in (-65.0, 0.0):
    p.resetBasePositionAndOrientation(
        env.robot,
        [TARGET[0], TARGET[1], 0.16],
        p.getQuaternionFromEuler([0.0, 0.0, np.radians(yaw_deg)]),
    )
    for _ in range(60):
        p.stepSimulation()
    start = p.getBasePositionAndOrientation(env.robot)[0]
    for _ in range(120):
        for j in (0, 1):
            p.setJointMotorControl2(
                env.robot, j, p.VELOCITY_CONTROL, targetVelocity=5.0, force=1.6
            )
        p.stepSimulation()
    end, quat = p.getBasePositionAndOrientation(env.robot)
    roll, pitch, _yaw = p.getEulerFromQuaternion(quat)
    print(
        f"\nyaw={yaw_deg:+.0f}: avance="
        f"{np.hypot(end[0]-start[0], end[1]-start[1]):.3f} m "
        f"pitch={np.degrees(pitch):+.1f} z={end[2]:+.3f}"
    )
    for body in env.ramp_ids + env.obstacle_ids + env.cylinder_ids:
        for c in p.getContactPoints(bodyA=env.robot, bodyB=body):
            if float(c[9]) > 0.02:
                print(
                    f"  contacto id={body} linkA={c[3]} linkB={c[4]} "
                    f"n=({c[7][0]:+.2f},{c[7][1]:+.2f},{c[7][2]:+.2f}) "
                    f"f={float(c[9]):.1f} dist={float(c[8]):.3f}"
                )

env.close()
