"""Preview offscreen del abanico LiDAR translucido.

Genera una escena con obstaculos, lanza 72 rayos reales y dibuja el abanico
como mallas dinamicas. Soporta variantes geometricas para comparar el aspecto
con la imagen de referencia del usuario.

Uso: python test_fan_visual.py [pyramid|cone]
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pybullet as p

N_RAYS = 72
MAX_DIST = 6.0
ORIGIN_OFFSET = 0.30
FAN_HEIGHT = 1.1
SECTORS = 12


def write_fan_mesh(path: Path, dists: list[float], height: float, mode: str) -> None:
    """Malla de abanico en cuanas angulares.

    pyramid: cuna cerrada (apex comun + suelo/techo/paredes) - look 3D grueso.
    cone:    superficie conica apoyada en el anillo de obstaculos (mas plana).
    """
    n = len(dists)
    step = max(1, n // SECTORS)
    verts: list[tuple[float, float, float]] = []

    def add_vert(x: float, y: float, z: float) -> int:
        verts.append((x, y, z))
        return len(verts)  # indice obj (base 1)

    apex_bottom = add_vert(0.0, 0.0, 0.0)
    apex_top = add_vert(0.0, 0.0, height) if mode == "cone" else None

    faces: list[str] = []
    for s in range(SECTORS):
        i0 = (s * step) % n
        i1 = ((s + 1) * step) % n
        d = min(dists[i0:i1] if i1 > i0 else dists[i0:] + dists[:i1])
        a0 = 2.0 * math.pi * i0 / n
        a1 = 2.0 * math.pi * i1 / n
        b0 = add_vert(d * math.cos(a0), d * math.sin(a0), 0.0)
        t0 = add_vert(d * math.cos(a0), d * math.sin(a0), height)
        b1 = add_vert(d * math.cos(a1), d * math.sin(a1), 0.0)
        t1 = add_vert(d * math.cos(a1), d * math.sin(a1), height)
        if mode == "cone":
            faces.append(f"f {apex_top} {b0} {b1}")
            faces.append(f"f {apex_top} {b1} {b0}")
        else:
            faces.append(f"f {apex_bottom} {b0} {b1}")
            faces.append(f"f {apex_bottom} {t1} {t0}")
            faces.append(f"f {apex_bottom} {t0} {b0}")
            faces.append(f"f {apex_bottom} {b1} {t1}")
            faces.append(f"f {b0} {b1} {t1}")
            faces.append(f"f {b0} {t1} {t0}")

    lines = ["# lidar fan"] + [
        f"v {x:.4f} {y:.4f} {z:.4f}" for (x, y, z) in verts
    ] + faces
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def build_scene() -> None:
    p.setGravity(0.0, 0.0, -9.81)
    p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 0)
    p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)

    floor_col = p.createCollisionShape(p.GEOM_PLANE)
    floor_vis = p.createVisualShape(
        p.GEOM_BOX,
        halfExtents=[7.0, 7.0, 0.05],
        rgbaColor=[0.70, 0.70, 0.72, 1.0],
    )
    p.createMultiBody(
        baseMass=0, baseCollisionShapeIndex=floor_col,
        baseVisualShapeIndex=-1, basePosition=[0, 0, 0],
    )
    p.createMultiBody(
        baseMass=0, baseCollisionShapeIndex=-1,
        baseVisualShapeIndex=floor_vis, basePosition=[0, 0, -0.05],
    )

    obstacles = [
        ([-2.5, 1.8, 0.5], [0.6, 0.6, 0.5], [0.35, 0.35, 0.40]),
        ([1.5, 2.6, 0.4], [0.5, 0.5, 0.4], [0.60, 0.60, 0.62]),
        ([2.8, -1.2, 0.3], [0.5, 0.5, 0.3], [0.40, 0.40, 0.44]),
        ([-1.2, -2.4, 0.4], [0.5, 0.5, 0.4], [0.55, 0.45, 0.30]),
    ]
    for pos, half, color in obstacles:
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=half)
        vis = p.createVisualShape(
            p.GEOM_BOX, halfExtents=half, rgbaColor=color + [1.0]
        )
        p.createMultiBody(
            baseMass=0, baseCollisionShapeIndex=col,
            baseVisualShapeIndex=vis, basePosition=pos,
        )

    robot_col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.15, 0.15, 0.10])
    robot_vis = p.createVisualShape(
        p.GEOM_BOX, halfExtents=[0.15, 0.15, 0.10],
        rgbaColor=[0.75, 0.10, 0.10, 1.0],
    )
    p.createMultiBody(
        baseMass=1.0, baseCollisionShapeIndex=robot_col,
        baseVisualShapeIndex=robot_vis, basePosition=[0, 0, 0.15],
    )


def scan() -> list[float]:
    froms = []
    tos = []
    for i in range(N_RAYS):
        angle = 2.0 * math.pi * i / N_RAYS
        dx = math.cos(angle)
        dy = math.sin(angle)
        froms.append([dx * ORIGIN_OFFSET, dy * ORIGIN_OFFSET, 0.20])
        tos.append([dx * MAX_DIST, dy * MAX_DIST, 0.20])
    results = p.rayTestBatch(froms, tos)
    ray_len = MAX_DIST - ORIGIN_OFFSET
    return [ORIGIN_OFFSET + float(hit[2]) * ray_len for hit in results]


def capture(mode: str, dists: list[float], out_name: str) -> None:
    obj_path = Path(tempfile.gettempdir()) / f"lidar_fan_{mode}.obj"
    write_fan_mesh(obj_path, dists, FAN_HEIGHT, mode)
    shape = p.createVisualShape(
        p.GEOM_MESH,
        fileName=str(obj_path),
        meshScale=[1.0, 1.0, 1.0],
        rgbaColor=[0.20, 0.45, 1.00, 0.45],
    )
    body = p.createMultiBody(
        baseMass=0.0, baseCollisionShapeIndex=-1,
        baseVisualShapeIndex=shape, basePosition=[0, 0, 0],
        baseOrientation=[0, 0, 0, 1],
    )
    width, height = 900, 650
    proj = p.computeProjectionMatrixFOV(58.0, width / height, 0.1, 100.0)
    eye = [5.6, -5.6, 6.8]
    target = [0.0, 0.0, 0.2]
    view = p.computeViewMatrix(eye, target, [0.0, 0.0, 1.0])
    img = p.getCameraImage(
        width, height, viewMatrix=view, projectionMatrix=proj,
        renderer=p.ER_TINY_RENDERER,
    )
    raw = np.asarray(img[2], dtype=np.uint8).reshape(img[1], img[0], -1)
    rgb = raw[:, :, :3] if raw.shape[2] >= 3 else raw
    out = Path(__file__).resolve().parent / "models" / out_name
    try:
        from PIL import Image

        Image.fromarray(rgb).save(out)
    except ImportError:
        import imageio.v2 as imageio

        imageio.imwrite(out, rgb)
    p.removeBody(body)
    print("guardado:", out)


def main() -> None:
    modes = sys.argv[1:] or ["pyramid", "cone"]
    p.connect(p.DIRECT)
    build_scene()
    dists = scan()
    for mode in modes:
        capture(mode, dists, f"_fan_{mode}.png")
    p.disconnect()


if __name__ == "__main__":
    main()
