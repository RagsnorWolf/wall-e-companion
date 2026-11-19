"""
WALL-E · Mapa de chunks (memoria espacial)

Divide el mundo en una grilla de celdas de 1×1 metro (configurable) y guarda
el estado de cada celda:

    0 = DESCONOCIDO
    1 = LIBRE
    2 = OBSTÁCULO

La clase está pensada para conectarse más adelante con la visión del robot:
`update_position(x, y, obstacles=...)` marca la celda actual como libre y las
celdas donde el sensor detectó obstáculos como ocupadas. Por ahora es la base
independiente, sin cámara ni LiDAR.

Uso:
    from chunk_mapper import ChunkMapper
    mapa = ChunkMapper(cell_size=1.0)
    mapa.update_position(0.0, 0.0)
    mapa.update_position(0.0, 0.0, obstacles=[(1.2, 0.3, 0.4)])
    print(mapa.state_at(0.2, 0.2))   # 1 (libre)
    print(mapa.state_at(1.2, 0.3))   # 2 (obstáculo)
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence


class ChunkMapper:
    """Grilla espacial de estados libre/obstáculo/desconocido."""

    UNKNOWN = 0
    FREE = 1
    OBSTACLE = 2

    def __init__(self, cell_size: float = 1.0) -> None:
        if cell_size <= 0.0:
            raise ValueError("cell_size debe ser mayor que cero")
        self.cell_size = float(cell_size)
        # Clave: (ix, iy). Valor: UNKNOWN/FREE/OBSTACLE.
        self.cells: dict[tuple[int, int], int] = {}

    # ------------------------------------------------------------------ #
    # Conversión mundo <-> celda
    # ------------------------------------------------------------------ #
    def world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        """Convierte coordenadas del mundo a índices de celda (1 m por celda)."""
        return (
            int(math.floor(float(x) / self.cell_size)),
            int(math.floor(float(y) / self.cell_size)),
        )

    def cell_to_world(self, ix: int, iy: int) -> tuple[float, float]:
        """Devuelve el centro de la celda en coordenadas del mundo."""
        return (
            (float(ix) + 0.5) * self.cell_size,
            (float(iy) + 0.5) * self.cell_size,
        )

    # ------------------------------------------------------------------ #
    # Marcado de celdas
    # ------------------------------------------------------------------ #
    def mark_free(self, x: float, y: float) -> tuple[int, int]:
        cell = self.world_to_cell(x, y)
        self.cells[cell] = self.FREE
        return cell

    def mark_obstacle(self, x: float, y: float) -> tuple[int, int]:
        cell = self.world_to_cell(x, y)
        self.cells[cell] = self.OBSTACLE
        return cell

    def mark_unknown(self, x: float, y: float) -> tuple[int, int]:
        cell = self.world_to_cell(x, y)
        self.cells.pop(cell, None)
        return cell

    def update_position(
        self,
        x: float,
        y: float,
        obstacles: Iterable[Sequence[float]] | None = None,
    ) -> None:
        """Actualiza el mapa con la posición actual y los obstáculos detectados.

        Parámetros:
            x, y: posición actual del robot en metros.
            obstacles: iterable de puntos detectados. Cada punto puede ser
                `(x, y)` o `(x, y, radio)`. Si tiene radio, se marcan todas
                las celdas dentro de ese radio (en metros).
        """
        self.mark_free(x, y)
        if obstacles is None:
            return

        for obstacle in obstacles:
            if len(obstacle) < 2:
                continue
            ox = float(obstacle[0])
            oy = float(obstacle[1])
            radius = float(obstacle[2]) if len(obstacle) >= 3 else 0.0
            if radius <= 0.0:
                self.mark_obstacle(ox, oy)
                continue

            # Marcar el cuadrado de celdas que cubre el círculo detectado.
            min_ix, min_iy = self.world_to_cell(ox - radius, oy - radius)
            max_ix, max_iy = self.world_to_cell(ox + radius, oy + radius)
            for ix in range(min_ix, max_ix + 1):
                for iy in range(min_iy, max_iy + 1):
                    cx, cy = self.cell_to_world(ix, iy)
                    if math.hypot(cx - ox, cy - oy) <= radius:
                        self.cells[(ix, iy)] = self.OBSTACLE

    # ------------------------------------------------------------------ #
    # Consultas
    # ------------------------------------------------------------------ #
    def state_at(self, x: float, y: float) -> int:
        """Estado de la celda que contiene (x, y)."""
        return self.cells.get(self.world_to_cell(x, y), self.UNKNOWN)

    def cell_state(self, ix: int, iy: int) -> int:
        return self.cells.get((int(ix), int(iy)), self.UNKNOWN)

    def is_free(self, x: float, y: float) -> bool:
        return self.state_at(x, y) == self.FREE

    def is_obstacle(self, x: float, y: float) -> bool:
        return self.state_at(x, y) == self.OBSTACLE

    def is_known(self, x: float, y: float) -> bool:
        return self.state_at(x, y) != self.UNKNOWN

    def cells_of(self, state: int) -> list[tuple[int, int]]:
        return [cell for cell, value in self.cells.items() if value == state]

    @property
    def free_cells(self) -> list[tuple[int, int]]:
        return self.cells_of(self.FREE)

    @property
    def obstacle_cells(self) -> list[tuple[int, int]]:
        return self.cells_of(self.OBSTACLE)

    def __len__(self) -> int:
        return len(self.cells)

    # ------------------------------------------------------------------ #
    # Serialización / reset
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        self.cells.clear()

    def to_dict(self) -> dict:
        return {
            "cell_size": self.cell_size,
            "cells": {
                f"{ix},{iy}": int(state)
                for (ix, iy), state in self.cells.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChunkMapper":
        mapper = cls(cell_size=float(data.get("cell_size", 1.0)))
        for key, state in data.get("cells", {}).items():
            ix_text, iy_text = key.split(",")
            mapper.cells[(int(ix_text), int(iy_text))] = int(state)
        return mapper

    # ------------------------------------------------------------------ #
    # Utilidades de depuración
    # ------------------------------------------------------------------ #
    def ascii_map(
        self,
        min_ix: int = -5,
        max_ix: int = 5,
        min_iy: int = -5,
        max_iy: int = 5,
    ) -> str:
        """Representación ASCII para depurar (Y hacia arriba)."""
        symbols = {self.UNKNOWN: "?", self.FREE: ".", self.OBSTACLE: "#"}
        lines = []
        for iy in range(max_iy, min_iy - 1, -1):
            row = "".join(
                symbols.get(self.cells.get((ix, iy), self.UNKNOWN), "?")
                for ix in range(min_ix, max_ix + 1)
            )
            lines.append(f"{iy:+3d} {row}")
        return "\n".join(lines)


# ---------------------------------------------------------------------- #
# Self-test
# ---------------------------------------------------------------------- #
def _self_test() -> None:
    mapper = ChunkMapper(cell_size=1.0)

    # La celda del origen debe empezar como desconocida.
    assert mapper.state_at(0.2, 0.2) == ChunkMapper.UNKNOWN

    # Marcar la celda actual como libre.
    mapper.update_position(0.2, 0.2)
    assert mapper.state_at(0.2, 0.2) == ChunkMapper.FREE

    # Marcar un obstáculo puntual.
    mapper.update_position(0.2, 0.2, obstacles=[(1.4, -0.6)])
    assert mapper.state_at(1.4, -0.6) == ChunkMapper.OBSTACLE

    # Marcar un obstáculo con radio: debe cubrir varias celdas.
    mapper.update_position(0.2, 0.2, obstacles=[(-2.0, 2.0, 1.2)])
    assert mapper.state_at(-2.0, 2.0) == ChunkMapper.OBSTACLE
    assert mapper.state_at(-1.2, 2.0) == ChunkMapper.OBSTACLE
    assert mapper.state_at(-2.8, 2.0) == ChunkMapper.OBSTACLE

    # Serialización ida y vuelta.
    snapshot = mapper.to_dict()
    restored = ChunkMapper.from_dict(snapshot)
    assert restored.state_at(1.4, -0.6) == ChunkMapper.OBSTACLE
    assert restored.state_at(0.2, 0.2) == ChunkMapper.FREE
    assert restored.cell_size == mapper.cell_size

    # Reset.
    mapper.reset()
    assert len(mapper) == 0
    assert mapper.state_at(0.2, 0.2) == ChunkMapper.UNKNOWN

    print("chunk_mapper OK")
    print(f"  Celdas libres: {len(restored.free_cells)}")
    print(f"  Celdas obstáculo: {len(restored.obstacle_cells)}")


if __name__ == "__main__":
    _self_test()
