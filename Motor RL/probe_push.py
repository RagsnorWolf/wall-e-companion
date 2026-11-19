"""Control: el mismo empujon en casa y en el punto del atasco."""
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


def push(x, y, yaw_deg, label):
    p.resetBasePositionAndOrientation(
        env.robot,
        [x, y, 0.16],
        p.getQuaternionFromEuler([0.0, 0.0, np.radians(yaw_deg)]),
    )
    for _ in range(90):
        p.stepSimulation()
    start = p.getBasePositionAndOrientation(env.robot)[0]
    for _ in range(90):
        for j in (0, 1):
            p.setJointMotorControl2(
                env.robot, j, p.VELOCITY_CONTROL,
                targetVelocity=5.0, force=1.6
            )
        p.stepSimulation()
    end, quat = p.getBasePositionAndOrientation(env.robot)
    roll, pitch, _y = p.getEulerFromQuaternion(quat)
    contacts = p.getContactPoints(bodyA=env.robot)
    real = [c for c in contacts if float(c[9]) > 0.02]
    print(
        f"{label:14s} start=({start[0]:+.2f},{start[1]:+.2f},{start[2]:+.3f}) "
        f"end=({end[0]:+.2f},{end[1]:+.2f}) "
        f"avance={np.hypot(end[0]-start[0], end[1]-start[1]):.3f} "
        f"pitch={np.degrees(pitch):+.1f} contactos={len(real)}"
    )
    for c in real:
        print(f"   bodyB={c[2]} linkB={c[4]} f={float(c[9]):.1f}")


push(0.0, 0.0, 0.0, "casa")
push(5.03, -2.42, -90.0, "atasco -90")
push(5.03, -2.42, 0.0, "atasco 0")
push(5.03, -1.80, -90.0, "libre -90")

env.close()
