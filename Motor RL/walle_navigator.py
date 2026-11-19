"""
WALL-E · Navegador de chunks y exploración autónoma
===================================================

Combina tres piezas:

1. `ChunkMapper`  — memoria espacial de celdas de 1×1 m.
2. `FrontSensor`  — raycast frontal para saber qué hay enfrente.
3. El cerebro V2  — política PPO de 14D que conduce las orugas.

El navegador mantiene un mapa de chunks, elige la frontera desconocida más
cercana, le pasa al cerebro un `goal` (+1 avanzar) y un `goal_angle`
(absoluto) y marca los chunks como cargados cuando el robot llega.

La exploración es autónoma: el robot arranca en el origen, escanea, elige un
chunk desconocido, conduce hasta él, lo marca como cargado y repite. Si el
sensor detecta un obstáculo cercano, el controlador hace un giro de seguridad
antes de seguir.

Uso:

    from walle_navigator import ExplorationController

    controller = ExplorationController(env, model)
    report = controller.run(max_steps=3000)
    controller.save_report("reports/v2_exploration_report.json")

También se puede ejecutar como demo:

    python walle_navigator.py --model walle_ppo_model_v2_slow.zip --steps 3000
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from chunk_mapper import ChunkMapper
from walle_body import WallEBody
from walle_sensor import FrontScan, FrontSensor

SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = SCRIPT_DIR / "reports"


# ---------------------------------------------------------------------- #
# Objetivo de navegación
# ---------------------------------------------------------------------- #
@dataclass
class NavigationTarget:
    cell: tuple[int, int]
    position: tuple[float, float]
    distance_m: float
    reason: str = "frontier"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell": [int(self.cell[0]), int(self.cell[1])],
            "position": [round(self.position[0], 4), round(self.position[1], 4)],
            "distance_m": round(self.distance_m, 4),
            "reason": self.reason,
        }


# ---------------------------------------------------------------------- #
# Mapa + fronteras
# ---------------------------------------------------------------------- #
class ChunkNavigator:
    """Mapa de chunks con búsqueda de fronteras y objetivos."""

    NEIGHBORS_8 = [
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ]

    def __init__(
        self,
        cell_size: float = 1.0,
        arena_half_size: float = 10.0,
        robot_radius: float = 0.25,
        safety_distance_m: float = 0.45,
        reach_distance_m: float = 0.45,
    ) -> None:
        self.mapper = ChunkMapper(cell_size=cell_size)
        self.arena_half_size = float(arena_half_size)
        self.robot_radius = float(robot_radius)
        self.safety_distance_m = float(safety_distance_m)
        self.reach_distance_m = float(reach_distance_m)
        self.visited: set[tuple[int, int]] = set()
        self.loaded: set[tuple[int, int]] = set()
        self.target: NavigationTarget | None = None
        self.last_target_reason = ""

    # ------------------------------------------------------------------ #
    # Actualización
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        self.mapper.reset()
        self.visited.clear()
        self.loaded.clear()
        self.target = None
        self.last_target_reason = ""

    def update_from_scan(
        self,
        scan: FrontScan,
        x: float,
        y: float,
    ) -> None:
        """Marca la celda actual, los obstáculos y el camino libre."""
        self.mapper.update_position(x, y, obstacles=scan.obstacle_points)
        self.visited.add(self.mapper.world_to_cell(x, y))

        # Marcar como libres las celdas barridas por cada rayo hasta el
        # impacto. No sobrescribimos obstáculos ya conocidos.
        for ray in scan.rays:
            angle_rad = math.radians(ray.angle_deg)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            direction = (
                scan.forward[0] * cos_a - scan.forward[1] * sin_a,
                scan.forward[0] * sin_a + scan.forward[1] * cos_a,
            )
            max_distance = min(ray.distance_m, scan.range_m)
            d = 0.0
            while d <= max_distance:
                px = scan.origin[0] + direction[0] * d
                py = scan.origin[1] + direction[1] * d
                if self.mapper.state_at(px, py) != ChunkMapper.OBSTACLE:
                    self.mapper.mark_free(px, py)
                d += max(0.1, self.mapper.cell_size * 0.15)

    # ------------------------------------------------------------------ #
    # Fronteras y objetivos
    # ------------------------------------------------------------------ #
    def _inside_arena(self, cell: tuple[int, int]) -> bool:
        cx, cy = self.mapper.cell_to_world(*cell)
        return (
            abs(cx) <= self.arena_half_size
            and abs(cy) <= self.arena_half_size
        )

    def frontier_cells(self) -> set[tuple[int, int]]:
        """Celdas desconocidas adyacentes a alguna celda libre."""
        frontiers: set[tuple[int, int]] = set()
        for (ix, iy), state in self.mapper.cells.items():
            if state != ChunkMapper.FREE:
                continue
            for dx, dy in self.NEIGHBORS_8:
                neighbor = (ix + dx, iy + dy)
                if (
                    self.mapper.cell_state(*neighbor) == ChunkMapper.UNKNOWN
                    and self._inside_arena(neighbor)
                ):
                    frontiers.add(neighbor)
        return frontiers

    def choose_target(
        self,
        x: float,
        y: float,
        force: bool = False,
    ) -> NavigationTarget | None:
        """Elige la frontera alcanzable más cercana (BFS por celdas libres)."""
        if self.target is not None and not force:
            if (
                not self.is_target_reached(x, y)
                and not self.is_target_blocked()
            ):
                return self.target

        start = self.mapper.world_to_cell(x, y)
        # La celda actual es libre por definición.
        self.mapper.mark_free(x, y)
        frontiers = self.frontier_cells()
        if not frontiers:
            self.target = None
            self.last_target_reason = "sin fronteras"
            return None

        # BFS por celdas libres: la primera frontera encontrada es la más
        # cercana en pasos de 1 m.
        queue: deque[tuple[int, int]] = deque([start])
        seen = {start}
        best: tuple[int, int] | None = None
        while queue:
            cell = queue.popleft()
            if cell in frontiers and cell != start:
                best = cell
                break
            for dx, dy in self.NEIGHBORS_8:
                neighbor = (cell[0] + dx, cell[1] + dy)
                if neighbor in seen:
                    continue
                if self.mapper.cell_state(*neighbor) != ChunkMapper.FREE:
                    continue
                if not self._inside_arena(neighbor):
                    continue
                seen.add(neighbor)
                queue.append(neighbor)

        if best is None:
            # Fallback euclidiano: frontera más cercana aunque no haya un
            # camino de celdas libres continuo (p. ej. al inicio).
            candidates = list(frontiers)
            if candidates:
                best = min(
                    candidates,
                    key=lambda cell: self._cell_distance(cell, x, y),
                )

        if best is None:
            self.target = None
            self.last_target_reason = "sin fronteras alcanzables"
            return None

        target_pos = self.mapper.cell_to_world(*best)
        self.target = NavigationTarget(
            cell=best,
            position=target_pos,
            distance_m=math.hypot(target_pos[0] - x, target_pos[1] - y),
            reason="frontera",
        )
        self.last_target_reason = "frontera"
        return self.target

    def _cell_distance(
        self, cell: tuple[int, int], x: float, y: float
    ) -> float:
        cx, cy = self.mapper.cell_to_world(*cell)
        return math.hypot(cx - x, cy - y)

    def is_target_reached(self, x: float, y: float) -> bool:
        if self.target is None:
            return False
        return (
            math.hypot(
                self.target.position[0] - x,
                self.target.position[1] - y,
            )
            <= self.reach_distance_m
        )

    def is_target_blocked(self) -> bool:
        if self.target is None:
            return True
        return (
            self.mapper.cell_state(*self.target.cell)
            == ChunkMapper.OBSTACLE
        )

    def mark_loaded(self) -> None:
        if self.target is not None:
            self.loaded.add(self.target.cell)
            self.visited.add(self.target.cell)
            self.target = None

    def goal_command(
        self, x: float, y: float
    ) -> dict[str, float] | None:
        """Comando para el cerebro V2: avanzar hacia el objetivo."""
        if self.target is None:
            return None
        dx = self.target.position[0] - x
        dy = self.target.position[1] - y
        bearing = math.atan2(dy, dx)
        return {
            "goal": 1.0,
            "goal_angle": bearing,
            "distance_m": math.hypot(dx, dy),
            "bearing_rad": bearing,
            "bearing_deg": math.degrees(bearing),
        }

    # ------------------------------------------------------------------ #
    # Métricas
    # ------------------------------------------------------------------ #
    def known_cells(self) -> int:
        return sum(
            1 for cell in self.mapper.cells if self._inside_arena(cell)
        )

    def coverage(self) -> float:
        total = (2.0 * self.arena_half_size / self.mapper.cell_size) ** 2
        if total <= 0.0:
            return 0.0
        return min(1.0, self.known_cells() / total)

    def report(self) -> dict[str, Any]:
        frontiers = self.frontier_cells()
        return {
            "cell_size_m": self.mapper.cell_size,
            "arena_half_size_m": self.arena_half_size,
            "known_cells": self.known_cells(),
            "free_cells": len(self.mapper.free_cells),
            "obstacle_cells": len(self.mapper.obstacle_cells),
            "visited_cells": len(self.visited),
            "loaded_cells": len(self.loaded),
            "coverage": round(self.coverage(), 4),
            "frontier_cells": len(frontiers),
            "target": (
                self.target.to_dict() if self.target is not None else None
            ),
            "loaded_cell_list": [
                [int(c[0]), int(c[1])] for c in sorted(self.loaded)
            ],
            "ascii_map": self.mapper.ascii_map(
                min_ix=-int(self.arena_half_size),
                max_ix=int(self.arena_half_size),
                min_iy=-int(self.arena_half_size),
                max_iy=int(self.arena_half_size),
            ),
        }


# ---------------------------------------------------------------------- #
# Controlador de exploración con el cerebro V2
# ---------------------------------------------------------------------- #
class ExplorationController:
    """Conduce el WALL-E V2 por el arena cargando chunks desconocidos."""

    def __init__(
        self,
        env,
        model,
        body: WallEBody | None = None,
        sensor: FrontSensor | None = None,
        navigator: ChunkNavigator | None = None,
        stage: int = 3,
        safety_distance_m: float = 0.45,
        seed: int | None = None,
        verbose: bool = True,
    ) -> None:
        self.env = env
        self.model = model
        self.stage = int(stage)
        self.safety_distance_m = float(safety_distance_m)
        self.seed = seed
        self.verbose = verbose

        self.body = body or WallEBody(
            hitbox_size=tuple(env.HITBOX_SIZE),
            hitbox_radius=float(env.HITBOX_RADIUS),
        )
        self.sensor = sensor or FrontSensor(
            robot_id=env.robot,
            body=self.body,
            obstacle_ids=env.obstacle_ids,
            wall_ids=env.wall_ids,
            floor_id=getattr(env, "plane", None),
        )
        self.navigator = navigator or ChunkNavigator(
            cell_size=self.body.chunk_size_m,
            arena_half_size=env.arena_half_size,
            robot_radius=self.body.hitbox_radius,
            safety_distance_m=self.safety_distance_m,
        )

        self.last_scan: FrontScan | None = None
        self.last_info: dict[str, Any] | None = None
        self.last_action: np.ndarray | None = None
        self.stats: dict[str, Any] = {
            "steps": 0,
            "episodes": 0,
            "collisions": 0,
            "flips": 0,
            "recoveries": 0,
            "loaded_chunks": 0,
            "safety_turns": 0,
            "total_distance_m": 0.0,
            "started_at": None,
            "elapsed_s": 0.0,
        }
        self._start_time = 0.0
        self._last_position: tuple[float, float] | None = None

    # ------------------------------------------------------------------ #
    # Reset
    # ------------------------------------------------------------------ #
    def reset(self) -> dict[str, Any]:
        obs, info = self.env.reset(
            seed=self.seed, options={"stage": self.stage}
        )
        self.last_info = info
        self.last_scan = self.sensor.scan()
        self.navigator.reset()
        self.navigator.update_from_scan(
            self.last_scan, info["x"], info["y"]
        )
        self.navigator.choose_target(info["x"], info["y"], force=True)
        self.body.initial_position = (
            float(info["initial_x"]),
            float(info["initial_y"]),
            float(info["initial_z"]),
        )
        self.body.initial_yaw_deg = float(info["initial_yaw_deg"])
        self.stats["episodes"] += 1
        self.stats["started_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
        self._start_time = time.perf_counter()
        self._last_position = (float(info["x"]), float(info["y"]))
        if self.verbose:
            print(
                f"[exploración] reset: pos=({info['x']:+.2f},"
                f"{info['y']:+.2f}) yaw={info['initial_yaw_deg']:+.1f}° "
                f"objetivo={self.navigator.target}"
            )
        return info

    # ------------------------------------------------------------------ #
    # Un paso
    # ------------------------------------------------------------------ #
    def step(self) -> dict[str, Any] | None:
        if self.last_info is None:
            self.reset()
        assert self.last_info is not None
        x = float(self.last_info["x"])
        y = float(self.last_info["y"])

        scan = self.sensor.scan()
        self.last_scan = scan
        self.navigator.update_from_scan(scan, x, y)

        # Si no hay objetivo, o ya llegó, o se volvió obstáculo: elegir otro.
        if (
            self.navigator.target is None
            or self.navigator.is_target_reached(x, y)
            or self.navigator.is_target_blocked()
        ):
            if (
                self.navigator.target is not None
                and self.navigator.is_target_reached(x, y)
            ):
                self.navigator.mark_loaded()
                self.stats["loaded_chunks"] = len(self.navigator.loaded)
            self.navigator.choose_target(x, y, force=True)

        command = self.navigator.goal_command(x, y)
        if command is None:
            return None

        # Giro grueso: si el objetivo queda muy de costado o atrás, girar en
        # el lugar por el camino corto antes de dejar conducir al cerebro.
        # El cerebro V2 sigue encargándose del avance y del ajuste fino.
        action_override: np.ndarray | None = None
        pose = self.env.get_pose()
        bearing_error = math.atan2(
            math.sin(command["goal_angle"] - pose["yaw"]),
            math.cos(command["goal_angle"] - pose["yaw"]),
        )
        if (
            abs(bearing_error) > math.radians(50.0)
            and scan.front_distance_m >= self.safety_distance_m
        ):
            if bearing_error > 0.0:
                action_override = np.array([-1.0, 1.0], dtype=np.float32)
            else:
                action_override = np.array([1.0, -1.0], dtype=np.float32)
            self.stats["coarse_turns"] = (
                self.stats.get("coarse_turns", 0) + 1
            )

        # Seguridad: si hay una pared/caja muy cerca, girar antes de seguir.
        if scan.front_distance_m < self.safety_distance_m:
            # Si el objetivo está justo delante y bloqueado, descartarlo.
            if (
                command["distance_m"] < 1.2
                and scan.front_distance_m < self.safety_distance_m * 0.8
            ):
                self.navigator.choose_target(x, y, force=True)
                command = self.navigator.goal_command(x, y)
                if command is None:
                    return None
            if scan.front_distance_m < self.safety_distance_m:
                if scan.left_distance_m >= scan.right_distance_m:
                    action_override = np.array([-0.8, 0.8], dtype=np.float32)
                else:
                    action_override = np.array([0.8, -0.8], dtype=np.float32)
                self.stats["safety_turns"] += 1

        # Observación 14D con el objetivo de navegación.
        obs = self.env.get_observation(
            goal=command["goal"],
            goal_angle=command["goal_angle"],
            stage=self.stage,
        )
        if action_override is None:
            action, _ = self.model.predict(obs, deterministic=True)
            action = np.asarray(action, dtype=np.float32)
        else:
            action = action_override
        self.last_action = action

        obs, reward, terminated, truncated, info = self.env.step(action)
        self.last_info = info
        self.stats["steps"] += 1

        if self._last_position is not None:
            self.stats["total_distance_m"] += math.hypot(
                info["x"] - self._last_position[0],
                info["y"] - self._last_position[1],
            )
        self._last_position = (float(info["x"]), float(info["y"]))

        # Recuperación: choque, volcadura o límite de tiempo.
        if terminated or truncated:
            if info.get("collision"):
                self.stats["collisions"] += 1
            if info.get("flipped"):
                self.stats["flips"] += 1
            if terminated or truncated:
                self.stats["recoveries"] += 1
                self.env.reset_robot_only()
                self.last_info = self.env.get_pose()
                self._last_position = (
                    float(self.last_info["x"]),
                    float(self.last_info["y"]),
                )
                self.navigator.choose_target(
                    self.last_info["x"], self.last_info["y"], force=True
                )
        return info

    # ------------------------------------------------------------------ #
    # Bucle completo
    # ------------------------------------------------------------------ #
    def run(self, max_steps: int = 3000, target_coverage: float = 0.90) -> dict[str, Any]:
        self.reset()
        for step in range(max_steps):
            info = self.step()
            if info is None:
                if self.verbose:
                    print(
                        "[exploración] no quedan fronteras; "
                        "exploración completa."
                    )
                break
            if self.verbose and (step + 1) % 120 == 0:
                self.sensor.draw_debug(self.last_scan)
                print(
                    f"[exploración] paso {step+1:4d} | "
                    f"pos=({info['x']:+.2f},{info['y']:+.2f}) | "
                    f"frente={self.last_scan.front_distance_m:.2f} m | "
                    f"chunks={len(self.navigator.loaded)} | "
                    f"cobertura={self.navigator.coverage()*100:.1f}% | "
                    f"choques={self.stats['collisions']} | "
                    f"volcaduras={self.stats['flips']}"
                )
            if self.navigator.coverage() >= target_coverage:
                if self.verbose:
                    print(
                        f"[exploración] cobertura objetivo alcanzada: "
                        f"{self.navigator.coverage()*100:.1f}%"
                    )
                break

        self.stats["elapsed_s"] = round(
            time.perf_counter() - self._start_time, 2
        )
        self.stats["loaded_chunks"] = len(self.navigator.loaded)
        return self.report()

    # ------------------------------------------------------------------ #
    # Reporte
    # ------------------------------------------------------------------ #
    def report(self) -> dict[str, Any]:
        awareness = self.sensor.body_awareness(
            base_position=(
                self.last_info["x"],
                self.last_info["y"],
                self.last_info["z"] + self.body.base_z,
            )
            if self.last_info is not None
            else None,
            base_quaternion=(
                self.env.get_pose()["quat"]
                if self.last_info is not None
                else None
            ),
            initial_position=self.body.initial_position,
            initial_yaw_deg=self.body.initial_yaw_deg,
        )
        return {
            "project": "WALL-E · exploración autónoma de chunks",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "stage": self.stage,
            "model": getattr(self.model, "_walle_model_path", None),
            "body": awareness,
            "map": self.navigator.report(),
            "stats": dict(self.stats),
            "last_scan": (
                self.last_scan.to_dict()
                if self.last_scan is not None
                else None
            ),
            "final_pose": self.last_info,
        }

    def save_report(
        self,
        json_path: str | Path = REPORTS_DIR / "v2_exploration_report.json",
        md_path: str | Path | None = None,
    ) -> tuple[Path, Path]:
        report = self.report()
        json_path = Path(json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if md_path is None:
            md_path = json_path.with_suffix(".md")
        md_path = Path(md_path)

        lines: list[str] = []
        lines.append("# WALL-E · Reporte de exploración y chunks")
        lines.append("")
        lines.append(f"- **Fecha:** {report['generated_at']}")
        lines.append(f"- **Etapa:** {report['stage']}")
        lines.append("")
        lines.append("## Cuerpo")
        lines.append("")
        body = report["body"]
        lines.append(
            f"- **Masa total:** {body['mass_kg']['total']} kg"
        )
        lines.append(
            f"- **Hitbox:** {body['hitbox']['size']} m "
            f"(radio {body['hitbox']['radius_m']} m)"
        )
        lines.append(
            f"- **Área de apoyo:** {body['areas']['footprint_m2']} m²"
        )
        lines.append(
            f"- **Precisión:** {body['precision']['position_m']} m / "
            f"{body['precision']['angle_deg']}°"
        )
        lines.append(
            f"- **Sensor frontal:** {body['front']['sensor_range_m']} m, "
            f"±{body['front']['sensor_half_angle_deg']}°, "
            f"{body['front']['sensor_num_rays']} rayos"
        )
        lines.append(
            f"- **Pose inicial:** {body['initial_pose']['position']} m, "
            f"yaw {body['initial_pose']['yaw_deg']}°"
        )
        lines.append("")
        lines.append("### Piezas")
        lines.append("")
        lines.append("| Pieza | Rol | Tamaño (cm) | Masa (kg) |")
        lines.append("| --- | --- | --- | ---: |")
        for name, part in body["parts"].items():
            size = part["local_size"]
            lines.append(
                f"| {name} | {part['role']} | "
                f"{size[0]*100:.1f} × {size[1]*100:.1f} × "
                f"{size[2]*100:.1f} | {part['mass_kg']:.2f} |"
            )
        lines.append("")
        lines.append("## Mapa de chunks")
        lines.append("")
        map_data = report["map"]
        lines.append(f"- **Celdas conocidas:** {map_data['known_cells']}")
        lines.append(f"- **Celdas libres:** {map_data['free_cells']}")
        lines.append(f"- **Celdas obstáculo:** {map_data['obstacle_cells']}")
        lines.append(f"- **Celdas visitadas:** {map_data['visited_cells']}")
        lines.append(f"- **Chunks cargados:** {map_data['loaded_cells']}")
        lines.append(
            f"- **Cobertura:** {map_data['coverage']*100:.1f}%"
        )
        lines.append(
            f"- **Fronteras pendientes:** {map_data['frontier_cells']}"
        )
        lines.append("")
        lines.append("```")
        lines.append(map_data["ascii_map"])
        lines.append("```")
        lines.append("")
        lines.append("## Estadísticas de exploración")
        lines.append("")
        for key, value in report["stats"].items():
            lines.append(f"- **{key}:** {value}")
        lines.append("")
        lines.append("## Última lectura del sensor")
        lines.append("")
        scan = report["last_scan"]
        if scan:
            lines.append(
                f"- **Frente:** {scan['front_distance_m']} m"
            )
            lines.append(
                f"- **Izquierda:** {scan['left_distance_m']} m"
            )
            lines.append(
                f"- **Derecha:** {scan['right_distance_m']} m"
            )
            lines.append(
                f"- **Camino libre:** {scan['path_clear']}"
            )
        lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")
        return json_path, md_path


# ---------------------------------------------------------------------- #
# Demo / CLI
# ---------------------------------------------------------------------- #
def _demo(args: argparse.Namespace) -> None:
    from stable_baselines3 import PPO

    from walle_env_v2 import WallEEnvV2

    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = SCRIPT_DIR / model_path
    if not model_path.exists():
        raise FileNotFoundError(f"No existe el modelo: {model_path}")

    env = WallEEnvV2(
        render_mode="human" if args.gui else None,
        stage=args.stage,
        seed=args.seed,
        randomize_mass=True,
        obstacle_count=args.obstacles,
        arena_half_size=args.arena_half_size,
        stage12_min_obstacle_distance=min(8.0, args.arena_half_size - 1.0),
        stage3_min_obstacle_distance=min(2.5, args.arena_half_size - 1.0),
        obstacle_max_distance=max(2.0, args.arena_half_size - 1.0),
        obstacle_min_separation=1.5,
    )
    model = PPO.load(str(model_path), device="cpu")
    model._walle_model_path = str(model_path)  # type: ignore[attr-defined]

    controller = ExplorationController(
        env=env,
        model=model,
        stage=args.stage,
        safety_distance_m=args.safety_distance,
        seed=args.seed,
        verbose=True,
    )
    try:
        report = controller.run(
            max_steps=args.steps,
            target_coverage=args.target_coverage,
        )
        json_path, md_path = controller.save_report(
            json_path=REPORTS_DIR / "v2_exploration_report.json",
        )
        print("\n" + "=" * 66)
        print("WALL-E · EXPLORACIÓN TERMINADA")
        print("=" * 66)
        print(f"Chunks cargados: {report['map']['loaded_cells']}")
        print(f"Cobertura: {report['map']['coverage']*100:.1f}%")
        print(f"Choques: {report['stats']['collisions']}")
        print(f"Volcaduras: {report['stats']['flips']}")
        print(f"Reporte JSON: {json_path}")
        print(f"Reporte MD:   {md_path}")
        print("=" * 66)
    finally:
        env.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exploración autónoma de chunks con el cerebro V2"
    )
    parser.add_argument(
        "--model",
        default="walle_ppo_model_v2_slow.zip",
        help="Modelo PPO V2",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=3000,
        help="Máximo de pasos de simulación",
    )
    parser.add_argument(
        "--stage",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="Etapa del cerebro V2",
    )
    parser.add_argument(
        "--obstacles",
        type=int,
        default=5,
        help="Cantidad de cajas",
    )
    parser.add_argument(
        "--arena-half-size",
        type=float,
        default=6.0,
        help="Mitad del lado del arena en metros (6 = 12×12 m)",
    )
    parser.add_argument(
        "--safety-distance",
        type=float,
        default=0.45,
        help="Distancia de seguridad frontal (m)",
    )
    parser.add_argument(
        "--target-coverage",
        type=float,
        default=0.90,
        help="Cobertura objetivo (0–1)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Mostrar la ventana de PyBullet",
    )
    args = parser.parse_args()
    _demo(args)


# ---------------------------------------------------------------------- #
# Self-test sin PyBullet
# ---------------------------------------------------------------------- #
def _self_test() -> None:
    navigator = ChunkNavigator(cell_size=1.0, arena_half_size=5.0)
    # Marcar un pasillo libre de 3 celdas y un obstáculo.
    for ix in range(0, 4):
        navigator.mapper.mark_free(ix + 0.5, 0.5)
    navigator.mapper.mark_obstacle(2.5, 1.5)
    navigator.visited.add((0, 0))
    frontiers = navigator.frontier_cells()
    assert (4, 0) in frontiers or (3, 1) in frontiers

    target = navigator.choose_target(0.5, 0.5, force=True)
    assert target is not None
    assert target.cell in frontiers
    command = navigator.goal_command(0.5, 0.5)
    assert command is not None
    assert "goal_angle" in command

    navigator.mark_loaded()
    assert len(navigator.loaded) == 1
    assert navigator.target is None

    report = navigator.report()
    assert report["known_cells"] >= 4
    assert report["coverage"] > 0.0
    assert "ascii_map" in report

    print("walle_navigator OK")
    print(f"  Celdas conocidas: {report['known_cells']}")
    print(f"  Fronteras: {report['frontier_cells']}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        _self_test()
    else:
        main()
