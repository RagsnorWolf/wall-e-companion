"""
WALL-E · Fase 2 — Conversión del modelo visual de la Fase 1 (GLB -> OBJ)
=======================================================================

PyBullet puede usar un OBJ como apariencia del proxy físico. Este script
convierte el GLB animado del cockpit a un OBJ estático, escala el modelo a
una altura realista (~0.5 m) y lo centra para que quede apoyado sobre las
orugas.

Importante: el OBJ NO conserva animaciones ni esqueleto; es solo la cáscara
visual. La física la sigue aportando el proxy (chasis + ruedas).

Uso:
    pip install trimesh
    python convert_model.py "..\\Pagina Web\\cockpit\\ui\\public\\models\\walle_animated.glb"
    python convert_model.py ruta\\al\\modelo.glb -o walle_visual.obj --height 0.5

Luego:
    python train_walle.py --visual-mesh walle_visual.obj --gui
    python evaluate_walle.py --visual-mesh walle_visual.obj
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import trimesh


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte el GLB de WALL-E a OBJ para PyBullet"
    )
    parser.add_argument("input", type=str, help="Archivo .glb de entrada")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="walle_visual.obj",
        help="Archivo .obj de salida (por defecto walle_visual.obj)",
    )
    parser.add_argument(
        "--height",
        type=float,
        default=0.5,
        help="Altura final en metros (por defecto 0.5)",
    )
    parser.add_argument(
        "--no-scale",
        action="store_true",
        help="No escalar el modelo",
    )
    parser.add_argument(
        "--no-center",
        action="store_true",
        help="No centrar el modelo en X/Y",
    )
    parser.add_argument(
        "--up-axis",
        choices=["y", "z"],
        default="y",
        help="Eje vertical del archivo: 'y' para glTF/GLB (por defecto), "
        "'z' si ya viene en Z-up",
    )
    parser.add_argument(
        "--yaw",
        type=float,
        default=0.0,
        help="Rotación extra sobre Z en grados (para orientar el frente)",
    )
    parser.add_argument(
        "--bottom-z",
        type=float,
        default=-0.15,
        help="Altura local del punto más bajo (por defecto -0.15)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {input_path}")

    print(f"Cargando: {input_path}")
    scene = trimesh.load(str(input_path), force="scene")

    if isinstance(scene, trimesh.Scene):
        mesh = scene.dump(concatenate=True)
    else:
        mesh = scene

    if not isinstance(mesh, trimesh.Trimesh):
        # Algunos GLB contienen solo puntos/líneas: forzamos triángulos.
        mesh = trimesh.Trimesh(
            vertices=mesh.vertices,
            faces=mesh.faces,
            process=False,
        )

    # glTF usa Y-up; PyBullet usa Z-up. Rotamos -90° o +90° sobre X para
    # que la altura quede en Z antes de escalar y centrar.
    if args.up_axis == "y":
        mesh.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi / 2.0, [1, 0, 0])
        )
        print("Rotado de Y-up (glTF) a Z-up (PyBullet)")

    if args.yaw:
        mesh.apply_transform(
            trimesh.transformations.rotation_matrix(
                math.radians(args.yaw), [0, 0, 1]
            )
        )
        print(f"Rotado {args.yaw:+.1f}° sobre Z")

    extents = mesh.extents
    print(
        f"Tamaño original: {extents[0]:.3f} x {extents[1]:.3f} x "
        f"{extents[2]:.3f} m | {len(mesh.vertices)} vértices, "
        f"{len(mesh.faces)} caras"
    )

    if not args.no_scale and extents[2] > 1e-6:
        factor = args.height / float(extents[2])
        mesh.apply_scale(factor)
        print(f"Escalado x{factor:.4f} -> altura {args.height:.2f} m")

    if not args.no_center:
        bounds = mesh.bounds
        center_x = (bounds[0][0] + bounds[1][0]) / 2.0
        center_y = (bounds[0][1] + bounds[1][1]) / 2.0
        bottom_z = bounds[0][2]
        mesh.apply_translation(
            [
                -center_x,
                -center_y,
                args.bottom_z - bottom_z,
            ]
        )
        print(
            f"Centrado en X/Y y apoyado en z={args.bottom_z:.2f} "
            "(coincide con la base de las orugas)"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(output_path), file_type="obj")
    print(f"\nExportado: {output_path.resolve()}")
    print(
        "PyBullet puede ignorar las texturas del MTL y mostrar el mesh en "
        "gris; la forma y la física funcionan igual."
    )


if __name__ == "__main__":
    main()
