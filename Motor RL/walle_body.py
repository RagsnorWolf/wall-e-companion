"""
WALL-E · Autoconocimiento corporal (body schema)
=================================================

Este módulo le da al simulador una descripción explícita del cuerpo del
WALL-E físico de madera y cartón: rostro, chasis, manos/brazos, orugas,
vértices, caras, áreas, masas, precisión y hitbox de colisión.

La descripción es local al robot:

    +X = frente
    +Y = izquierda
    +Z = arriba
    (0, 0, 0) = centro del chasis
    (0, 0, -BASE_Z) = punto de contacto con el piso

El módulo no depende de PyBullet. Se puede usar desde el entorno RL, desde
el simulador interactivo o desde un script de exploración. Para pasar una
pieza al mundo se usan `world_center`, `world_vertices` o `awareness`.

Uso rápido:

    from walle_body import WallEBody

    body = WallEBody()
    print(body.summary())
    print(body.to_dict()["hitbox"])

    pose = body.awareness(
        base_position=(0.0, 0.0, 0.15),
        base_quaternion=(0.0, 0.0, 0.0, 1.0),
    )
    print(pose["parts"]["head"]["world_center"])
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable

# Altura del centro del chasis cuando el robot está apoyado en el piso.
# Es la misma constante que usa `walle_env_v2.WallEEnvV2.BASE_Z`.
BASE_Z = 0.15


# ---------------------------------------------------------------------- #
# Utilidades matemáticas
# ---------------------------------------------------------------------- #
def wrap_angle(angle: float) -> float:
    """Normaliza un ángulo a (-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def quat_from_yaw(yaw: float) -> tuple[float, float, float, float]:
    """Cuaternión (x, y, z, w) de una rotación pura alrededor de Z."""
    half = 0.5 * float(yaw)
    return (0.0, 0.0, math.sin(half), math.cos(half))


def quat_multiply(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_rotate(
    quat: tuple[float, float, float, float],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Rota un vector local por un cuaternión unitario."""
    qx, qy, qz, qw = quat
    vx, vy, vz = vector
    # v' = v + 2 * q_vec × (q_vec × v + qw * v)
    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)
    return (
        vx + qw * tx + qy * tz - qz * ty,
        vy + qw * ty + qz * tx - qx * tz,
        vz + qw * tz + qx * ty - qy * tx,
    )


def add(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(
    v: tuple[float, float, float], factor: float
) -> tuple[float, float, float]:
    return (v[0] * factor, v[1] * factor, v[2] * factor)


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


# ---------------------------------------------------------------------- #
# Piezas
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class BodyPart:
    """Una pieza rectangular del cuerpo, con vértices, caras y área."""

    name: str
    role: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]  # largo (X), ancho (Y), alto (Z)
    mass_kg: float
    color: tuple[float, float, float, float] = (0.85, 0.65, 0.20, 1.0)
    material: str = "madera/cartón"
    precision_m: float = 0.02
    notes: str = ""

    @property
    def half(self) -> tuple[float, float, float]:
        return (
            self.size[0] / 2.0,
            self.size[1] / 2.0,
            self.size[2] / 2.0,
        )

    def vertices(self) -> list[tuple[float, float, float]]:
        """8 vértices locales, en orden (---, --+, -+-, -++, +--, +-+, ++-, +++)."""
        hx, hy, hz = self.half
        cx, cy, cz = self.center
        result = []
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                for sz in (-1.0, 1.0):
                    result.append(
                        (cx + sx * hx, cy + sy * hy, cz + sz * hz)
                    )
        return result

    def faces(self) -> dict[str, list[int]]:
        """Caras como índices de los 8 vértices.

        Orden de vértices:
            0 (-,-,-)  1 (-,-,+)  2 (-,+,-)  3 (-,+,+)
            4 (+,-,-)  5 (+,-,+)  6 (+,+,-)  7 (+,+,+)
        """
        return {
            "back": [0, 1, 3, 2],
            "front": [4, 6, 7, 5],
            "right": [0, 4, 5, 1],
            "left": [2, 3, 7, 6],
            "bottom": [0, 2, 6, 4],
            "top": [1, 5, 7, 3],
        }

    def face_centers(self) -> dict[str, tuple[float, float, float]]:
        hx, hy, hz = self.half
        cx, cy, cz = self.center
        return {
            "front": (cx + hx, cy, cz),
            "back": (cx - hx, cy, cz),
            "left": (cx, cy + hy, cz),
            "right": (cx, cy - hy, cz),
            "top": (cx, cy, cz + hz),
            "bottom": (cx, cy, cz - hz),
        }

    def face_normals(self) -> dict[str, tuple[float, float, float]]:
        return {
            "front": (1.0, 0.0, 0.0),
            "back": (-1.0, 0.0, 0.0),
            "left": (0.0, 1.0, 0.0),
            "right": (0.0, -1.0, 0.0),
            "top": (0.0, 0.0, 1.0),
            "bottom": (0.0, 0.0, -1.0),
        }

    @property
    def surface_area_m2(self) -> float:
        lx, ly, lz = self.size
        return 2.0 * (lx * ly + lx * lz + ly * lz)

    @property
    def footprint_area_m2(self) -> float:
        return self.size[0] * self.size[1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "center": list(self.center),
            "size": list(self.size),
            "half_extents": list(self.half),
            "mass_kg": self.mass_kg,
            "material": self.material,
            "color": list(self.color),
            "precision_m": self.precision_m,
            "notes": self.notes,
            "vertices": [list(v) for v in self.vertices()],
            "faces": self.faces(),
            "face_centers": {
                k: list(v) for k, v in self.face_centers().items()
            },
            "face_normals": {
                k: list(v) for k, v in self.face_normals().items()
            },
            "surface_area_m2": round(self.surface_area_m2, 6),
            "footprint_area_m2": round(self.footprint_area_m2, 6),
        }


# ---------------------------------------------------------------------- #
# Cuerpo completo
# ---------------------------------------------------------------------- #
@dataclass
class WallEBody:
    """Esquema corporal del WALL-E físico (35×30×28 cm visuales)."""

    base_z: float = BASE_Z
    # Hitbox de colisión solicitada: 25–30 cm. Usamos 30×30×28 cm.
    hitbox_size: tuple[float, float, float] = (0.30, 0.30, 0.28)
    hitbox_center: tuple[float, float, float] = (0.0, 0.0, 0.01)
    # Radio de la esfera que contiene la hitbox (para chequeos rápidos).
    hitbox_radius: float = 0.25

    # Precisión declarada del robot y de sus sensores.
    position_precision_m: float = 0.02
    angle_precision_deg: float = 2.5
    sensor_range_m: float = 2.0
    sensor_half_angle_deg: float = 25.0
    sensor_num_rays: int = 5
    chunk_size_m: float = 1.0

    # Origen lógico y pose inicial (se completa al resetear el entorno).
    initial_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    initial_yaw_deg: float = 0.0

    parts: dict[str, BodyPart] = field(init=False)

    def __post_init__(self) -> None:
        self.parts = self._build_parts()

    # ------------------------------------------------------------------ #
    # Construcción
    # ------------------------------------------------------------------ #
    def _build_parts(self) -> dict[str, BodyPart]:
        return {
            # Chasis principal: 35 × 30 × 28 cm. Es la pieza visual.
            "chassis": BodyPart(
                name="chassis",
                role="cuerpo",
                center=(0.0, 0.0, 0.0),
                size=(0.35, 0.30, 0.28),
                mass_kg=3.50,
                color=(0.85, 0.65, 0.20, 1.0),
                notes="Caja de madera/cartón que contiene la electrónica.",
            ),
            # Cabeza: delantera y superior, con el rostro mirando a +X.
            "head": BodyPart(
                name="head",
                role="rostro",
                center=(0.10, 0.0, 0.19),
                size=(0.20, 0.18, 0.16),
                mass_kg=0.30,
                color=(0.95, 0.78, 0.30, 1.0),
                notes="Cabeza con la pantalla/ojos; mira hacia el frente (+X).",
            ),
            "face": BodyPart(
                name="face",
                role="rostro/pantalla",
                center=(0.205, 0.0, 0.19),
                size=(0.012, 0.15, 0.11),
                mass_kg=0.04,
                color=(0.05, 0.05, 0.06, 1.0),
                precision_m=0.005,
                notes="Pantalla frontal; los ojos se dibujan aquí.",
            ),
            "eye_left": BodyPart(
                name="eye_left",
                role="ojo izquierdo",
                center=(0.212, 0.045, 0.21),
                size=(0.008, 0.035, 0.045),
                mass_kg=0.005,
                color=(0.65, 0.85, 1.0, 1.0),
                precision_m=0.002,
            ),
            "eye_right": BodyPart(
                name="eye_right",
                role="ojo derecho",
                center=(0.212, -0.045, 0.21),
                size=(0.008, 0.035, 0.045),
                mass_kg=0.005,
                color=(0.65, 0.85, 1.0, 1.0),
                precision_m=0.002,
            ),
            # Brazos y manos a los costados. Sirven para cargar chunks.
            "arm_left": BodyPart(
                name="arm_left",
                role="brazo izquierdo",
                center=(0.04, 0.18, 0.06),
                size=(0.12, 0.05, 0.05),
                mass_kg=0.12,
                color=(0.80, 0.60, 0.20, 1.0),
                notes="Brazo articulado; se extiende hacia +X.",
            ),
            "arm_right": BodyPart(
                name="arm_right",
                role="brazo derecho",
                center=(0.04, -0.18, 0.06),
                size=(0.12, 0.05, 0.05),
                mass_kg=0.12,
                color=(0.80, 0.60, 0.20, 1.0),
            ),
            "hand_left": BodyPart(
                name="hand_left",
                role="mano izquierda",
                center=(0.13, 0.18, 0.04),
                size=(0.08, 0.06, 0.06),
                mass_kg=0.05,
                color=(0.30, 0.30, 0.32, 1.0),
                precision_m=0.01,
                notes="Pinza/agarre para chunks pequeños.",
            ),
            "hand_right": BodyPart(
                name="hand_right",
                role="mano derecha",
                center=(0.13, -0.18, 0.04),
                size=(0.08, 0.06, 0.06),
                mass_kg=0.05,
                color=(0.30, 0.30, 0.32, 1.0),
                precision_m=0.01,
            ),
            # Orugas/ruedas: cilindros de 9 cm de radio y 8 cm de ancho.
            # La caja envolvente de la oruga mide 35 × 8 × 18 cm.
            "tread_left": BodyPart(
                name="tread_left",
                role="oruga izquierda",
                center=(0.0, 0.20, -0.06),
                size=(0.35, 0.08, 0.18),
                mass_kg=0.35,
                color=(0.22, 0.22, 0.24, 1.0),
                precision_m=0.01,
                notes="Rueda/oruga izquierda; radio 9 cm, eje Y.",
            ),
            "tread_right": BodyPart(
                name="tread_right",
                role="oruga derecha",
                center=(0.0, -0.20, -0.06),
                size=(0.35, 0.08, 0.18),
                mass_kg=0.35,
                color=(0.22, 0.22, 0.24, 1.0),
                precision_m=0.01,
                notes="Rueda/oruga derecha; radio 9 cm, eje Y.",
            ),
        }

    # ------------------------------------------------------------------ #
    # Propiedades agregadas
    # ------------------------------------------------------------------ #
    @property
    def total_mass_kg(self) -> float:
        return sum(part.mass_kg for part in self.parts.values())

    @property
    def total_surface_area_m2(self) -> float:
        return sum(part.surface_area_m2 for part in self.parts.values())

    @property
    def footprint_area_m2(self) -> float:
        """Área de apoyo aproximada (chasis + orugas)."""
        chassis = self.parts["chassis"].footprint_area_m2
        treads = (
            self.parts["tread_left"].footprint_area_m2
            + self.parts["tread_right"].footprint_area_m2
        )
        return chassis + treads

    @property
    def hitbox_vertices(self) -> list[tuple[float, float, float]]:
        hx, hy, hz = (
            self.hitbox_size[0] / 2.0,
            self.hitbox_size[1] / 2.0,
            self.hitbox_size[2] / 2.0,
        )
        cx, cy, cz = self.hitbox_center
        return [
            (cx + sx * hx, cy + sy * hy, cz + sz * hz)
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
            for sz in (-1.0, 1.0)
        ]

    def part(self, name: str) -> BodyPart:
        if name not in self.parts:
            raise KeyError(
                f"Pieza desconocida: {name}. "
                f"Disponibles: {', '.join(sorted(self.parts))}"
            )
        return self.parts[name]

    def sensor_origin_local(self) -> tuple[float, float, float]:
        """Origen del sensor frontal: delante del rostro, a media altura."""
        return (0.23, 0.0, 0.10)

    def front_point_local(self) -> tuple[float, float, float]:
        """Punto más adelantado del cuerpo (útil para la hitbox)."""
        return (self.hitbox_center[0] + self.hitbox_size[0] / 2.0, 0.0, 0.0)

    # ------------------------------------------------------------------ #
    # Transformaciones al mundo
    # ------------------------------------------------------------------ #
    def world_center(
        self,
        part_name: str,
        base_position: Iterable[float],
        base_quaternion: Iterable[float],
    ) -> tuple[float, float, float]:
        part = self.part(part_name)
        quat = tuple(float(v) for v in base_quaternion)
        rotated = quat_rotate(quat, part.center)
        base = tuple(float(v) for v in base_position)
        return add(base, rotated)

    def world_vertices(
        self,
        part_name: str,
        base_position: Iterable[float],
        base_quaternion: Iterable[float],
    ) -> list[tuple[float, float, float]]:
        part = self.part(part_name)
        quat = tuple(float(v) for v in base_quaternion)
        base = tuple(float(v) for v in base_position)
        return [add(base, quat_rotate(quat, vertex)) for vertex in part.vertices()]

    def world_face_centers(
        self,
        part_name: str,
        base_position: Iterable[float],
        base_quaternion: Iterable[float],
    ) -> dict[str, tuple[float, float, float]]:
        part = self.part(part_name)
        quat = tuple(float(v) for v in base_quaternion)
        base = tuple(float(v) for v in base_position)
        return {
            face: add(base, quat_rotate(quat, center))
            for face, center in part.face_centers().items()
        }

    def world_hitbox_vertices(
        self,
        base_position: Iterable[float],
        base_quaternion: Iterable[float],
    ) -> list[tuple[float, float, float]]:
        quat = tuple(float(v) for v in base_quaternion)
        base = tuple(float(v) for v in base_position)
        return [
            add(base, quat_rotate(quat, vertex))
            for vertex in self.hitbox_vertices
        ]

    def world_sensor_origin(
        self,
        base_position: Iterable[float],
        base_quaternion: Iterable[float],
    ) -> tuple[float, float, float]:
        quat = tuple(float(v) for v in base_quaternion)
        base = tuple(float(v) for v in base_position)
        return add(base, quat_rotate(quat, self.sensor_origin_local()))

    # ------------------------------------------------------------------ #
    # Conocimiento corporal completo
    # ------------------------------------------------------------------ #
    def awareness(
        self,
        base_position: Iterable[float],
        base_quaternion: Iterable[float],
        initial_position: Iterable[float] | None = None,
        initial_yaw_deg: float | None = None,
    ) -> dict[str, Any]:
        """Devuelve el estado corporal en coordenadas del mundo.

        Incluye pose, piezas, vértices, caras, áreas, hitbox, sensor frontal,
        origen, precisión y pose inicial. Es lo que el simulador usa para
        "saber" dónde está cada parte de su cuerpo.
        """
        base_pos = tuple(float(v) for v in base_position)
        base_quat = tuple(float(v) for v in base_quaternion)
        yaw = float(math.atan2(
            2.0 * (base_quat[3] * base_quat[2] + base_quat[0] * base_quat[1]),
            1.0 - 2.0 * (base_quat[1] ** 2 + base_quat[2] ** 2),
        ))

        parts_world: dict[str, Any] = {}
        for name, part in self.parts.items():
            parts_world[name] = {
                "role": part.role,
                "local_center": list(part.center),
                "local_size": list(part.size),
                "world_center": list(
                    self.world_center(name, base_pos, base_quat)
                ),
                "world_vertices": [
                    list(v)
                    for v in self.world_vertices(name, base_pos, base_quat)
                ],
                "world_face_centers": {
                    face: list(center)
                    for face, center in self.world_face_centers(
                        name, base_pos, base_quat
                    ).items()
                },
                "surface_area_m2": round(part.surface_area_m2, 6),
                "footprint_area_m2": round(part.footprint_area_m2, 6),
                "mass_kg": part.mass_kg,
                "material": part.material,
                "precision_m": part.precision_m,
            }

        sensor_origin = self.world_sensor_origin(base_pos, base_quat)
        front_dir = quat_rotate(base_quat, (1.0, 0.0, 0.0))
        front_point = add(
            base_pos,
            quat_rotate(base_quat, self.front_point_local()),
        )

        return {
            "pose": {
                "base_position": list(base_pos),
                "base_quaternion": list(base_quat),
                "yaw_rad": yaw,
                "yaw_deg": math.degrees(yaw),
                "z_visible": base_pos[2] - self.base_z,
                "ground_contact": list(
                    add(
                        base_pos,
                        quat_rotate(base_quat, (0.0, 0.0, -self.base_z)),
                    )
                ),
            },
            "initial_pose": {
                "position": [
                    round(float(v), 6)
                    for v in (
                        initial_position
                        if initial_position is not None
                        else self.initial_position
                    )
                ],
                "yaw_deg": round(
                    float(
                        initial_yaw_deg
                        if initial_yaw_deg is not None
                        else self.initial_yaw_deg
                    ),
                    3,
                ),
            },
            "front": {
                "direction": list(front_dir),
                "point": list(front_point),
                "sensor_origin": list(sensor_origin),
                "sensor_range_m": self.sensor_range_m,
                "sensor_half_angle_deg": self.sensor_half_angle_deg,
                "sensor_num_rays": self.sensor_num_rays,
            },
            "parts": parts_world,
            "hitbox": {
                "size": list(self.hitbox_size),
                "center_local": list(self.hitbox_center),
                "center_world": list(
                    add(
                        base_pos,
                        quat_rotate(base_quat, self.hitbox_center),
                    )
                ),
                "vertices_world": [
                    list(v)
                    for v in self.world_hitbox_vertices(base_pos, base_quat)
                ],
                "radius_m": self.hitbox_radius,
            },
            "precision": {
                "position_m": self.position_precision_m,
                "angle_deg": self.angle_precision_deg,
                "sensor_range_m": self.sensor_range_m,
                "sensor_half_angle_deg": self.sensor_half_angle_deg,
                "chunk_size_m": self.chunk_size_m,
            },
            "areas": {
                "total_surface_m2": round(self.total_surface_area_m2, 6),
                "footprint_m2": round(self.footprint_area_m2, 6),
            },
            "mass_kg": {
                "total": round(self.total_mass_kg, 3),
                "by_part": {
                    name: part.mass_kg for name, part in self.parts.items()
                },
            },
        }

    # ------------------------------------------------------------------ #
    # Serialización
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": "WALL-E físico (madera/cartón)",
            "units": "metros, kilogramos, radianes",
            "local_frame": {
                "x": "frente",
                "y": "izquierda",
                "z": "arriba",
                "origin": "centro del chasis",
                "ground_contact_z": -self.base_z,
            },
            "visual_size_m": [0.35, 0.30, 0.28],
            "hitbox": {
                "size_m": list(self.hitbox_size),
                "center_local": list(self.hitbox_center),
                "radius_m": self.hitbox_radius,
                "vertices_local": [list(v) for v in self.hitbox_vertices],
            },
            "parts": {
                name: part.to_dict() for name, part in self.parts.items()
            },
            "total_mass_kg": round(self.total_mass_kg, 3),
            "total_surface_area_m2": round(self.total_surface_area_m2, 6),
            "footprint_area_m2": round(self.footprint_area_m2, 6),
            "precision": {
                "position_m": self.position_precision_m,
                "angle_deg": self.angle_precision_deg,
                "sensor_range_m": self.sensor_range_m,
                "sensor_half_angle_deg": self.sensor_half_angle_deg,
                "sensor_num_rays": self.sensor_num_rays,
                "chunk_size_m": self.chunk_size_m,
            },
            "sensor_origin_local": list(self.sensor_origin_local()),
            "initial_pose": {
                "position": list(self.initial_position),
                "yaw_deg": self.initial_yaw_deg,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def summary(self) -> str:
        lines = [
            "WALL-E · esquema corporal",
            f"  Masa total: {self.total_mass_kg:.2f} kg",
            f"  Tamaño visual: 35 × 30 × 28 cm",
            f"  Hitbox: {self.hitbox_size[0]*100:.0f} × "
            f"{self.hitbox_size[1]*100:.0f} × "
            f"{self.hitbox_size[2]*100:.0f} cm "
            f"(radio {self.hitbox_radius*100:.0f} cm)",
            f"  Área de apoyo: {self.footprint_area_m2:.4f} m²",
            f"  Superficie total: {self.total_surface_area_m2:.4f} m²",
            f"  Precisión: {self.position_precision_m*100:.1f} cm / "
            f"{self.angle_precision_deg:.1f}°",
            f"  Sensor frontal: {self.sensor_range_m:.1f} m, "
            f"±{self.sensor_half_angle_deg:.0f}°, "
            f"{self.sensor_num_rays} rayos",
            "  Piezas:",
        ]
        for name, part in self.parts.items():
            lines.append(
                f"    - {name:12s} {part.role:18s} "
                f"{part.size[0]*100:5.1f}×{part.size[1]*100:4.1f}×"
                f"{part.size[2]*100:4.1f} cm  "
                f"{part.mass_kg:5.2f} kg"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------- #
# Self-test
# ---------------------------------------------------------------------- #
def _self_test() -> None:
    body = WallEBody()

    # Todas las piezas deben tener 8 vértices y 6 caras.
    for name, part in body.parts.items():
        assert len(part.vertices()) == 8, name
        assert len(part.faces()) == 6, name
        assert part.surface_area_m2 > 0.0, name
        assert part.footprint_area_m2 > 0.0, name

    # La hitbox solicitada debe medir 25–30 cm en sus lados horizontales.
    assert 0.25 <= body.hitbox_size[0] <= 0.30
    assert 0.25 <= body.hitbox_size[1] <= 0.30
    assert len(body.hitbox_vertices) == 8

    # Transformación al mundo: sin rotación, el centro del chasis es la base.
    awareness = body.awareness(
        base_position=(0.0, 0.0, 0.15),
        base_quaternion=(0.0, 0.0, 0.0, 1.0),
    )
    chassis_center = awareness["parts"]["chassis"]["world_center"]
    assert abs(chassis_center[0]) < 1e-9
    assert abs(chassis_center[1]) < 1e-9
    assert abs(chassis_center[2] - 0.15) < 1e-9

    # Con yaw=90°, el frente (+X local) debe apuntar a +Y del mundo.
    awareness90 = body.awareness(
        base_position=(0.0, 0.0, 0.15),
        base_quaternion=quat_from_yaw(math.pi / 2.0),
    )
    front_dir = awareness90["front"]["direction"]
    assert abs(front_dir[0]) < 1e-6
    assert abs(front_dir[1] - 1.0) < 1e-6

    # El JSON debe ser serializable y contener las piezas clave.
    data = body.to_dict()
    json.dumps(data)
    for key in ("chassis", "head", "face", "hand_left", "tread_right"):
        assert key in data["parts"]

    print("walle_body OK")
    print(body.summary())


if __name__ == "__main__":
    _self_test()
