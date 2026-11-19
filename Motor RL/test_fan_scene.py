"""Preview offscreen de la escena real V4 + abanico LiDAR (mismo codigo que la GUI)."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
import pybullet as p

from interactive_walle import WalleHud, build_scene
from walle_env_v3 import WallEEnvV3


def write_hud_fan(hud: WalleHud, pos, yaw) -> None:
    hud._update_lidar_fan(pos, yaw)


def capture(name: str, eye, target, width=900, height=650) -> None:
    proj = p.computeProjectionMatrixFOV(58.0, width / height, 0.1, 100.0)
    view = p.computeViewMatrix(eye, target, [0.0, 0.0, 1.0])
    img = p.getCameraImage(
        width, height, viewMatrix=view, projectionMatrix=proj,
        renderer=p.ER_TINY_RENDERER,
    )
    raw = np.asarray(img[2], dtype=np.uint8).reshape(img[1], img[0], -1)
    rgb = raw[:, :, :3]
    out = Path(__file__).resolve().parent / "models" / name
    try:
        from PIL import Image

        Image.fromarray(rgb).save(out)
    except ImportError:
        import imageio.v2 as imageio

        imageio.imwrite(out, rgb)
    print("guardado:", out)


def main() -> None:
    p.connect(p.DIRECT)
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
    build_scene(env)
    env.render = lambda: None
    env._scan_lidar()

    hud = WalleHud(env)
    pos, quat = p.getBasePositionAndOrientation(env.robot)
    yaw = float(p.getEulerFromQuaternion(quat)[2])
    write_hud_fan(hud, pos, yaw)

    print("obstacle_ids:", len(env.obstacle_ids))
    print("wall_ids:", len(getattr(env, "wall_ids", [])))
    print("lidar min/max:", round(float(np.min(env.lidar_meters)), 2),
          round(float(np.max(env.lidar_meters)), 2))

    # Vista tipo GUI (distancia 4, elevacion ~30).
    target = [0.0, 0.0, 0.28]
    eye_gui = [2.45, -2.45, 2.28]
    capture("_scene_gui_view.png", eye_gui, target)

    # Vista panoramica para evaluar el conjunto.
    eye_wide = [5.5, -5.5, 6.0]
    capture("_scene_wide_view.png", eye_wide, target)

    hud._remove_lidar_fan()
    env.close()


if __name__ == "__main__":
    main()
