"""Como excluir el propio robot del rayTestBatch en esta build."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pybullet as p

import interactive_walle as iw

env = iw.WallEEnvV3(
    render_mode=None, show_proxy_visuals=False, stage=3, obstacle_count=6
)
env.render = lambda: None
iw.build_scene(env)
iw.reset_env_home(env)

pos, _q = p.getBasePositionAndOrientation(env.robot)
z = pos[2] + 0.06
froms = [[pos[0], pos[1], z]]
tos = [[pos[0] + 6.0, pos[1], z]]

print("robot id:", env.robot)
print("AABB:", p.getAABB(env.robot))

tries = {
    "posicional parent=robot": lambda: p.rayTestBatch(
        froms, tos, env.robot, -1, 0
    ),
    "kw parentObjectUniqueId": lambda: p.rayTestBatch(
        froms, tos, parentObjectUniqueId=env.robot,
        parentLinkIndex=-1, numThreads=0
    ),
    "kw numThreads solo": lambda: p.rayTestBatch(froms, tos, numThreads=0),
    "kw objectFilter sin robot": lambda: p.rayTestBatch(
        froms, tos, numThreads=0,
        objectFilter=[b for b in range(0, 40) if b != env.robot],
    ),
}
for name, call in tries.items():
    try:
        hits = call()
        hit = hits[0]
        print(f"{name}: body={hit[0]} link={hit[1]} frac={hit[2]:.4f}")
    except Exception as exc:
        print(f"{name}: ERROR {type(exc).__name__}: {exc}")

print("\ndoc:")
print(p.rayTestBatch.__doc__)

env.close()
