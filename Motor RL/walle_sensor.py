"""
WALL-E · Sensor frontal por raycast
===================================

Le da al robot la capacidad de "ver" qué tiene enfrente antes de moverse.
Usa `pybullet.rayTest` desde el origen del sensor frontal definido en
`walle_body.WallEBody` (delante del rostro, a media altura) y devuelve:

- distancia libre en el centro, izquierda y derecha;
- puntos de impacto en coordenadas del mundo;
- tipo de objeto golpeado (pared, caja, piso, desconocido);
- puntos con radio para alimentar `ChunkMapper.update_position`.

El sensor es deliberadamente simple y determinista: no es una cámara, es un
"bigote" de 5 rayos que cubre ±25°. Suficiente para no chocar y para mapear
chunks de 1×1 m.

Uso:

    from walle_sensor import FrontSensor

    sensor = FrontSensor(
        robot_id=env.robot,
        body=body,
        obstacle_ids=env.obstacle_ids,
        wall_ids=env.wall_ids,
    )
    scan = sensor.scan()
    print(scan.front_distance, scan.obstacle_points)
    sensor.draw_debug(scan)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

import pybullet as p

from walle_body import WallEBody, quat_rotate


# ---------------------------------------------------------------------- #
# Lecturas
# ---------------------------------------------------------------------- #
@dataclass
class RayHit:
    angle_deg: float
    distance_m: float
    hit: bool
    object_id: int = -1
    link_index: int = -1
    position: tuple[float, float, float] | None = None
    normal: tuple[float, float, float] | None = None
    object_type: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "angle_deg": round(self.angle_deg, 3),
            "distance_m": round(self.distance_m, 4),
            "hit": self.hit,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "position": (
                [round(v, 4) for v in self.position]
                if self.position is not None
                else None
            ),
            "normal": (
                [round(v, 4) for v in self.normal]
                if self.normal is not None
                else None
            ),
        }


@dataclass
class FrontScan:
    timestamp_s: float
    origin: tuple[float, float, float]
    forward: tuple[float, float, float]
    range_m: float
    rays: list[RayHit] = field(default_factory=list)
    front_distance_m: float = math.inf
    left_distance_m: float = math.inf
    right_distance_m: float = math.inf
    min_distance_m: float = math.inf
    obstacle_points: list[tuple[float, float, float]] = field(
        default_factory=list
    )

    @property
    def path_clear(self) -> bool:
        return self.front_distance_m > 0.45

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_s": round(self.timestamp_s, 4),
            "origin": [round(v, 4) for v in self.origin],
            "forward": [round(v, 4) for v in self.forward],
            "range_m": round(self.range_m, 4),
            "front_distance_m": (
                round(self.front_distance_m, 4)
                if math.isfinite(self.front_distance_m)
                else None
            ),
            "left_distance_m": (
                round(self.left_distance_m, 4)
                if math.isfinite(self.left_distance_m)
                else None
            ),
            "right_distance_m": (
                round(self.right_distance_m, 4)
                if math.isfinite(self.right_distance_m)
                else None
            ),
            "min_distance_m": (
                round(self.min_distance_m, 4)
                if math.isfinite(self.min_distance_m)
                else None
            ),
            "path_clear": self.path_clear,
            "rays": [ray.to_dict() for ray in self.rays],
            "obstacle_points": [
                [round(v, 4) for v in point]
                for point in self.obstacle_points
            ],
        }


# ---------------------------------------------------------------------- #
# Sensor
# ---------------------------------------------------------------------- #
class FrontSensor:
    """Raycast frontal de 5 rayos (±25°) a la altura del rostro."""

    def __init__(
        self,
        robot_id: int,
        body: WallEBody,
        obstacle_ids: Iterable[int] = (),
        wall_ids: Iterable[int] = (),
        range_m: float | None = None,
        num_rays: int | None = None,
        half_angle_deg: float | None = None,
        obstacle_radius_m: float = 0.25,
        floor_id: int | None = None,
    ) -> None:
        self.robot_id = int(robot_id)
        self.body = body
        self.obstacle_ids = set(int(v) for v in obstacle_ids)
        self.wall_ids = set(int(v) for v in wall_ids)
        self.range_m = float(
            body.sensor_range_m if range_m is None else range_m
        )
        self.num_rays = int(
            body.sensor_num_rays if num_rays is None else num_rays
        )
        self.half_angle_deg = float(
            body.sensor_half_angle_deg
            if half_angle_deg is None
            else half_angle_deg
        )
        self.obstacle_radius_m = float(obstacle_radius_m)
        self.floor_id = floor_id
        if self.num_rays < 1:
            raise ValueError("num_rays debe ser >= 1")
        if self.range_m <= 0.0:
            raise ValueError("range_m debe ser > 0")
        self._last_scan: FrontScan | None = None

    # ------------------------------------------------------------------ #
    # Escaneo
    # ------------------------------------------------------------------ #
    def scan(
        self,
        base_position: Iterable[float] | None = None,
        base_quaternion: Iterable[float] | None = None,
    ) -> FrontScan:
        if base_position is None or base_quaternion is None:
            pos, quat = p.getBasePositionAndOrientation(self.robot_id)
            base_position = pos
            base_quaternion = quat

        base_pos = tuple(float(v) for v in base_position)
        base_quat = tuple(float(v) for v in base_quaternion)
        origin = self.body.world_sensor_origin(base_pos, base_quat)
        forward = quat_rotate(base_quat, (1.0, 0.0, 0.0))

        # Ángulos de -half a +half. Positivo = izquierda (+Y local).
        if self.num_rays == 1:
            angles = [0.0]
        else:
            step = (2.0 * self.half_angle_deg) / (self.num_rays - 1)
            angles = [
                -self.half_angle_deg + i * step
                for i in range(self.num_rays)
            ]

        rays: list[RayHit] = []
        obstacle_points: list[tuple[float, float, float]] = []
        front_distances: list[float] = []
        left_distances: list[float] = []
        right_distances: list[float] = []

        for angle_deg in angles:
            angle_rad = math.radians(angle_deg)
            # Rotar el vector forward alrededor de Z.
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            direction = (
                forward[0] * cos_a - forward[1] * sin_a,
                forward[0] * sin_a + forward[1] * cos_a,
                forward[2],
            )
            end = (
                origin[0] + direction[0] * self.range_m,
                origin[1] + direction[1] * self.range_m,
                origin[2] + direction[2] * self.range_m,
            )

            hit = p.rayTest(origin, end)[0]
            object_id, link_index, hit_fraction, hit_position, hit_normal = hit
            hit_bool = object_id >= 0
            distance = (
                float(hit_fraction) * self.range_m
                if hit_bool
                else self.range_m
            )
            object_type = self._classify(object_id)

            ray = RayHit(
                angle_deg=angle_deg,
                distance_m=distance,
                hit=hit_bool,
                object_id=int(object_id),
                link_index=int(link_index),
                position=(
                    tuple(float(v) for v in hit_position)
                    if hit_bool
                    else None
                ),
                normal=(
                    tuple(float(v) for v in hit_normal)
                    if hit_bool
                    else None
                ),
                object_type=object_type,
            )
            rays.append(ray)

            if hit_bool and object_type in ("obstacle", "wall"):
                if ray.position is not None:
                    obstacle_points.append(
                        (
                            ray.position[0],
                            ray.position[1],
                            self.obstacle_radius_m,
                        )
                    )
                if abs(angle_deg) <= 8.0:
                    front_distances.append(distance)
                if angle_deg > 0.0:
                    left_distances.append(distance)
                elif angle_deg < 0.0:
                    right_distances.append(distance)

        # Si ningún rayo central golpeó, la distancia frontal es el rango.
        front_distance = (
            min(front_distances) if front_distances else self.range_m
        )
        left_distance = (
            min(left_distances) if left_distances else self.range_m
        )
        right_distance = (
            min(right_distances) if right_distances else self.range_m
        )
        min_distance = min(ray.distance_m for ray in rays)

        scan = FrontScan(
            timestamp_s=time.perf_counter(),
            origin=origin,
            forward=forward,
            range_m=self.range_m,
            rays=rays,
            front_distance_m=front_distance,
            left_distance_m=left_distance,
            right_distance_m=right_distance,
            min_distance_m=min_distance,
            obstacle_points=obstacle_points,
        )
        self._last_scan = scan
        return scan

    def _classify(self, object_id: int) -> str:
        if object_id < 0:
            return "none"
        if object_id == self.robot_id:
            return "robot"
        if object_id in self.obstacle_ids:
            return "obstacle"
        if object_id in self.wall_ids:
            return "wall"
        if self.floor_id is not None and object_id == self.floor_id:
            return "floor"
        return "unknown"

    # ------------------------------------------------------------------ #
    # Utilidades
    # ------------------------------------------------------------------ #
    @property
    def last_scan(self) -> FrontScan | None:
        return self._last_scan

    def is_path_clear(
        self,
        scan: FrontScan | None = None,
        safety_distance_m: float = 0.45,
    ) -> bool:
        scan = scan or self._last_scan
        if scan is None:
            return True
        return scan.front_distance_m > safety_distance_m

    def draw_debug(
        self,
        scan: FrontScan | None = None,
        life_time_s: float = 0.15,
    ) -> None:
        """Dibuja los rayos en la GUI de PyBullet (verde libre, rojo choque)."""
        scan = scan or self._last_scan
        if scan is None:
            return
        for ray in scan.rays:
            angle_rad = math.radians(ray.angle_deg)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            direction = (
                scan.forward[0] * cos_a - scan.forward[1] * sin_a,
                scan.forward[0] * sin_a + scan.forward[1] * cos_a,
                scan.forward[2],
            )
            end = (
                scan.origin[0] + direction[0] * ray.distance_m,
                scan.origin[1] + direction[1] * ray.distance_m,
                scan.origin[2] + direction[2] * ray.distance_m,
            )
            color = [1.0, 0.2, 0.2] if ray.hit else [0.2, 1.0, 0.3]
            p.addUserDebugLine(
                scan.origin,
                end,
                lineColorRGB=color,
                lineWidth=1.5,
                lifeTime=life_time_s,
            )
            if ray.hit and ray.position is not None:
                p.addUserDebugPoints(
                    [ray.position],
                    pointColorsRGB=[color],
                    pointSize=4.0,
                    lifeTime=life_time_s,
                )

    def body_awareness(
        self,
        base_position: Iterable[float] | None = None,
        base_quaternion: Iterable[float] | None = None,
        initial_position: Iterable[float] | None = None,
        initial_yaw_deg: float | None = None,
    ) -> dict[str, Any]:
        """Une el esquema corporal con la última lectura del sensor."""
        if base_position is None or base_quaternion is None:
            pos, quat = p.getBasePositionAndOrientation(self.robot_id)
            base_position = pos
            base_quaternion = quat
        data = self.body.awareness(
            base_position,
            base_quaternion,
            initial_position=initial_position,
            initial_yaw_deg=initial_yaw_deg,
        )
        scan = self._last_scan or self.scan(
            base_position, base_quaternion
        )
        data["sensor"] = scan.to_dict()
        data["front_clear"] = scan.path_clear
        data["hitbox"]["radius_m"] = self.body.hitbox_radius
        return data


# ---------------------------------------------------------------------- #
# Self-test con un mundo mínimo
# ---------------------------------------------------------------------- #
def _self_test() -> None:
    import pybullet_data

    client = p.connect(p.DIRECT)
    try:
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0.0, 0.0, -9.81)
        plane = p.loadURDF("plane.urdf")
        body = WallEBody()

        # Robot simple: caja de 35×30×28 cm a 15 cm del piso.
        collision = p.createCollisionShape(
            p.GEOM_BOX, halfExtents=[0.175, 0.15, 0.14]
        )
        robot = p.createMultiBody(
            baseMass=4.0,
            baseCollisionShapeIndex=collision,
            basePosition=[0.0, 0.0, 0.15],
        )
        # Caja obstáculo a 1.0 m al frente.
        box_collision = p.createCollisionShape(
            p.GEOM_BOX, halfExtents=[0.2, 0.2, 0.2]
        )
        box = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=box_collision,
            basePosition=[1.0, 0.0, 0.2],
        )
        for _ in range(10):
            p.stepSimulation()

        sensor = FrontSensor(
            robot_id=robot,
            body=body,
            obstacle_ids=[box],
            wall_ids=[],
            floor_id=plane,
        )
        scan = sensor.scan()
        print(
            f"scan: front={scan.front_distance_m:.3f} m "
            f"left={scan.left_distance_m:.3f} m "
            f"right={scan.right_distance_m:.3f} m "
            f"rays={len(scan.rays)}"
        )
        assert scan.front_distance_m < 1.1
        assert scan.front_distance_m > 0.5
        assert len(scan.rays) == body.sensor_num_rays
        assert scan.obstacle_points

        awareness = sensor.body_awareness()
        assert "chassis" in awareness["parts"]
        assert "sensor" in awareness
        print("walle_sensor OK")
    finally:
        p.disconnect(client)


if __name__ == "__main__":
    _self_test()
