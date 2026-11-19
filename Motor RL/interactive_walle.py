"""
WALL-E · Fase 3 — Simulación interactiva, chat y RLHF
=====================================================

Modo manual (PID): WALL-E queda quieto hasta que recibe una orden por el
chat. Las órdenes de avance/retroceso usan el controlador de posición y las
de giro el PID de rumbo. El botón «Modo: Manual (PID)» de la cabecera cambia
al cerebro PPO entrenado (`walle_ppo_model_physical.zip`): desde ese momento
los avances/retrocesos los conduce la red neuronal de 13 entradas, mientras
que los giros siguen resolviéndose con el PID porque el cerebro no tiene
comando de ángulo.

Después de cada orden se puede calificar el resultado:

- "Lo hizo bien"  -> guarda una Experiencia Exitosa (CSV + JSONL).
- "No lo hizo bien" -> guarda un Fallo, vuelve a la pose anterior y avisa en
  consola que hay que ajustar los pesos en el próximo entrenamiento.

Uso:
    python interactive_walle.py
    python interactive_walle.py --mode ppo
    python interactive_walle.py --direct --command "avanza 2 metros"
    python interactive_walle.py --direct --command "gira 90 grados a la derecha"
    python interactive_walle.py --direct --mode ppo --command "avanza 2 metros"
    python interactive_walle.py --direct --command "avanza 20 metros" --command "detente"

También se puede escribir «modo ppo» o «modo manual» en el chat.

La cámara sigue a WALL-E; en la ventana de PyBullet se puede orbitar con el
mouse y acercar/alejar con la rueda.

Nota sobre OpenGL2 y texturas:
    El driver AMD de esta PC solo funciona con el renderer OpenGL2. Ese
    renderer muestra las texturas PNG en escala de grises y no respeta el
    color del MTL. Para que WALL-E se vea como el personaje de la Fase 1,
    este script lee material_0.png, muestrea sus colores por UV y genera una
    versión posterizada con 16 colores sólidos (piezas OBJ). El OBJ/MTL/PNG
    originales se conservan para otros renderers.
"""

from __future__ import annotations

import argparse
import colorsys
import csv
import json
import math
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pybullet as p

try:
    import tkinter as tk
    from tkinter import font as tkfont
except ImportError:  # pragma: no cover - solo afecta al modo GUI
    tk = None
    tkfont = None

from walle_env import WallEEnv
try:
    from walle_env_v3 import WallEEnvV3
except Exception:  # pragma: no cover - V3 opcional
    WallEEnvV3 = None  # type: ignore

# --------------------------------------------------------------------------- #
# Rutas y constantes
# --------------------------------------------------------------------------- #
SCRIPT_DIR = Path(__file__).resolve().parent
VISUAL_OBJ = SCRIPT_DIR / "walle_visual.obj"
MATERIAL_MTL = SCRIPT_DIR / "material.mtl"
TEXTURE_PNG = SCRIPT_DIR / "material_0.png"
COLOR_PARTS_DIR = SCRIPT_DIR / "walle_color_parts"
FEEDBACK_DIR = SCRIPT_DIR / "feedback_walle"
REPORTS_DIR = SCRIPT_DIR / "reports"
ICON_PNG = SCRIPT_DIR / "walle_icon.png"
PPO_MODEL = SCRIPT_DIR / "walle_ppo_model_physical.zip"

CONTROL_HZ = 60.0
# Altura del centro del chasis cuando el robot está apoyado en el suelo.
# El "origen" visible (X=0, Y=0, Z=0) es el punto de contacto con el piso.
HOME_BASE_Z = 0.15
FALL_UP_THRESHOLD = 0.50       # up_z por debajo de esto = caída/volcado
FALL_RECOVERED_UP = 0.85       # up_z para considerar que se enderezó
RECOVERY_MAX_STEPS = 240       # 4 s a 60 Hz antes de rendirse
RECOVERY_SETTLE_STEPS = 30     # 0.5 s de asentamiento tras enderezarse
SELF_RIGHT_TORQUE = 35.0       # N·m aplicados para enderezar el chasis
HUD_UPDATE_TICKS = 12           # ~3 Hz a 22 FPS: la nube de puntos persiste 0.7 s, sin parpadeo y sin cargar el renderer
# Abanico LiDAR V4: rayos FINOS y densos que salen de WALL-E y terminan en el
# punto de impacto real de cada rayo del escaneo (como la imagen de referencia).
# No hay cunas ni relleno solido: cada rayo es una cinta de ~1.6 cm de grosor
# con seccion en cruz, mas una marca azul en el punto de impacto. Todo el
# abanico es UNA sola malla que se regenera cada pocos ticks.
LIDAR_FAN_ARC_DEG = 180.0        # abanico frontal (WALL-E mira al frente)
LIDAR_FAN_LINE_WIDTH = 1.0       # grosor de cada rayo en la ventana
LIDAR_FAN_COLOR = [0.30, 0.55, 0.82]   # azul acero suave, no electrico
LIDAR_FAN_UPDATE_TICKS = 3       # 20 Hz a 60 FPS: abanico fluido y barato
# El abanico se dibuja a ras de suelo (a los pies de WALL-E): asi se ve
# exactamente donde esta chocando y que hueco tiene para escapar.
LIDAR_FAN_HEIGHT = 0.03
CONTACT_MARKER_COLOR = [0.95, 0.42, 0.18]   # naranja de impacto
CONTACT_MARKER_WIDTH = 2.6
# Textura real del OBJ en OpenGL3. Si se pone False, se usan las 16 piezas
# de color generadas desde la textura (fallback para OpenGL2).
WALLE_USE_TEXTURE = True
SKY_COLOR = (0.14, 0.14, 0.16)      # fondo de estudio, gris muy oscuro
GROUND_COLOR = (0.26, 0.26, 0.28, 1.0)   # suelo grafito mate
WALL_COLOR = (0.64, 0.64, 0.67, 1.0)     # paredes gris claro mate
GRID_COLOR_MINOR = (0.30, 0.30, 0.33)
GRID_COLOR_MAJOR = (0.46, 0.46, 0.50)

# Texto 3D flotante sobre el robot (telemetria). Apagado por defecto: el
# viewport queda limpio, como en Isaac Sim. La telemetria sigue en la GUI.
SHOW_DEBUG_HUD = False

# Camara inicial: WALL-E como protagonista, vista ligeramente elevada.
CAMERA_DISTANCE = 2.05
CAMERA_YAW = 42.0
CAMERA_PITCH = -30.0
CAMERA_TARGET_Z = 0.26
# Tercera persona: el objetivo sigue a WALL-E (respeta zoom y orbita).
# Ponlo en False para dejar la camara completamente libre.
CAMERA_FOLLOW = True

# --- PID manual suave ------------------------------------------------------ #
# El centro de gravedad del proxy es alto y las orugas tienen mucha
# autoridad: una acción de 0.90 gira a más de 90°/s y puede volcar el chasis
# en la GUI. Los topes y ganancias de abajo mantienen los giros lentos y las
# correcciones de rumbo pequeñas, con rampas por paso para no dar tirones.
MOVE_MAX_ACTION = 1.00
MOVE_GAIN = 1.15
MOVE_MIN_ACTION = 0.08
MOVE_STOP_M = 0.050
MOVE_TOLERANCE_M = 0.150
# Kp reducido a la mitad para evitar sobre-corrección (tirones).
MOVE_YAW_GAIN = 0.400
# Autoridad de giro durante la marcha. Con 0.10 WALL-E no podía separarse de
# una pared que rozaba de frente: el diferencial máximo no vencía el empuje y
# se quedaba clavado empujando. 0.22 gira sin volcar (el centro de gravedad
# aguanta hasta ~0.30 con la fuerza de motor actual).
MOVE_YAW_LIMIT = 0.22
# Zona muerta de 0.5 grados: no corregir micro-errores (evita temblor).
MOVE_YAW_DEADZONE_RAD = math.radians(0.5)
# Rampa de aceleración y suavizado de la corrección de rumbo (unidades de
# acción por tick de 60 Hz). Evitan cambios bruscos de torque.
MOVE_ACCEL_STEP = 0.025
MOVE_CORRECTION_SLEW = 0.008
# El cerebro PPO no modula la velocidad cerca del objetivo: frena antes
# para compensar la inercia del robot y no pasarse de largo.
PPO_STOP_MARGIN = 0.08

TURN_MAX_ACTION = 0.65
# Kp reducido a la mitad para giros suaves sin oscilación.
TURN_GAIN = 0.450
TURN_MIN_ACTION = 0.07
# La acción mínima solo se aplica con errores grandes; cerca del objetivo
# el PID puede usar acciones más pequeñas y frenar sin sacudidas.
TURN_MIN_ERROR_RAD = math.radians(6.0)
# Zona muerta de 0.5 grados: dentro de ella no se aplica corrección.
TURN_DEADZONE_RAD = math.radians(0.5)
TURN_ACCEL_STEP = 0.025
TURN_TOLERANCE_RAD = 0.030
TURN_TOLERANCE_DEG = 2.5

BRAKE_TICKS = 24
COMMAND_TIMEOUT_S = 90.0

# --- Recuperación manual de choques ------------------------------------- #
# Antes, tocar una pared durante "avanza" o "retrocede" abortaba la orden y
# WALL-E se quedaba plantado sin saber qué hacer. Ahora despega, gira hacia el
# hueco que ve el LiDAR y retoma la orden donde estaba.
UNSTICK_MAX_ATTEMPTS = 3      # intentos por orden antes de rendirse
UNSTICK_MAX_CYCLES = 6        # maniobras totales por orden (corta el bucle)
UNSTICK_BACK_S = 0.55         # segundos retrocediendo para separarse
UNSTICK_TURN_S = 0.65         # (heredado) referencia de la fase de giro
UNSTICK_TURN_MAX_S = 8.00     # tope de tiempo del giro del despegue
UNSTICK_TURN_DEG = 50.0       # grados de giro antes de reintentar la marcha
UNSTICK_BACK_ACTION = 0.55    # acción de oruga al separarse
UNSTICK_TURN_ACTION = 0.70    # acción de oruga al girar
UNSTICK_STILL_CONTACT_EXTRA_S = 0.40  # prórroga si sigue tocando

# --- Esquiva de obstáculos con el LiDAR de los pies --------------------- #
# El abanico vive a 0.06 m del suelo y mira en el plano de la marcha: es la
# medida real de "cuánto tengo delante". Con eso WALL-E decide sin tocar:
#   libre   -> acelera
#   cerca   -> modula la velocidad por la distancia
#   pegado  -> rodea (gira al hueco, avanza, vuelve al rumbo del objetivo)
SAFE_GO_M = 0.60             # por encima: vía libre, acción completa
SAFE_SLOW_M = 0.28           # por debajo: se detiene y rodea
AVOID_MAX_DETOURS = 14       # desvíos por orden antes de darse por vencido
AVOID_TURN_S = 0.50          # (heredado) referencia de la fase de giro
AVOID_TURN_MAX_S = 8.00      # tope de tiempo del giro del rodeo
AVOID_TURN_DEG = 45.0        # giro objetivo del rodeo, medido en el rumbo
AVOID_TURN_ACTION = 0.70     # acción de oruga durante el giro del rodeo
AVOID_FORWARD_S = 1.10       # segundos avanzando por el hueco
AVOID_FORWARD_ACTION = 0.70  # acción de oruga durante el avance del rodeo
AVOID_REAIM_RAD = math.radians(10.0)   # error de rumbo que obliga a reorientar
AVOID_REAIM_MAX_S = 1.60     # tope de tiempo del reenfoque
AVOID_STALL_M = 0.02         # avance mínimo por rodeo para no repetir en falso
AVOID_SAME_SPOT_M = 0.15     # rodeo que arranca aquí = el lado no sirve
AVOID_BACK_S = 0.55          # retroceso corto antes de girar el rodeo
AVOID_BACK_ACTION = 0.55     # acción de oruga al retroceder en el rodeo
STALL_WINDOW_S = 1.00        # sin avanzar este tiempo = camino cerrado
STALL_MIN_MOVE_M = 0.03      # menos de 3 cm cuenta como no avanzar
# Desplazamiento lateral del punto de mira. Perseguir el rumbo original a
# secas devolvía al robot contra el mismo muro: no se rodea nada sin salirse
# de la recta. El rodeo suma este desvío y el PID apunta ahí.
AVOID_OFFSET_STEP = 0.55     # metros de desvío que añade cada rodeo
AVOID_OFFSET_MAX = 2.20      # tope de desvío (lo suficiente para doblar un muro)
AVOID_OFFSET_SLEW = 0.02     # suavizado del desvío (m por tick de 60 Hz)
AVOID_OFFSET_DECAY = 0.004   # retorno a la línea original (m por tick)
AVOID_LOOKAHEAD_M = 1.20     # mira al frente para no cortar la esquina
AVOID_COOLDOWN_S = 1.20      # mínimo entre desvíos (da tiempo a que actúe)

COLOR_PART_VERSION = 3
COLOR_PART_CLUSTERS = 16

CSV_FIELDS = [
    "fecha",
    "resultado",
    "exito",
    "recompensa",
    "comando",
    "tipo",
    "objetivo_distancia_m",
    "objetivo_angulo_deg",
    "inicio_x",
    "inicio_y",
    "inicio_z",
    "inicio_yaw_deg",
    "fin_x",
    "fin_y",
    "fin_z",
    "fin_yaw_deg",
    "distancia_real_m",
    "angulo_real_deg",
    "error_distancia_m",
    "error_angulo_deg",
    "error_lateral_m",
    "pasos",
    "duracion_s",
    "colision",
    "volcado",
    "motivo",
    "accion_media_izq",
    "accion_media_der",
    "acciones_json",
    "estado_inicial_json",
    "estado_final_json",
    "modelo",
    "caidas",
    "recuperaciones",
    "fallos_recuperacion",
    "calificacion",
]


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def wrap_angle(angle: float) -> float:
    """Normaliza un ángulo a (-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def slew_toward(current: float, target: float, max_delta: float) -> float:
    """Mueve `current` hacia `target` como máximo `max_delta` por paso."""
    return current + clamp(target - current, -max_delta, max_delta)


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    return strip_accents(text).lower().strip()


def _zero_float(value: float, digits: int = 4) -> float:
    """Redondea y normaliza -0.0 a 0.0 para reportes legibles."""
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0.0 else rounded


def _round_opt(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else _zero_float(value, digits)


def _display_path(path: Path) -> str:
    """Ruta corta si está dentro del proyecto, ruta completa si no."""
    try:
        return str(path.resolve().relative_to(SCRIPT_DIR))
    except ValueError:
        return str(path.resolve())


def reset_env_home(env: WallEEnv) -> None:
    """Reinicia el simulador en el origen mirando hacia +X (yaw 0).

    Se usa solo en el simulador interactivo. El reset de entrenamiento
    (`WallEEnv.reset()` sin opciones) conserva su comportamiento.
    """
    env.reset(
        options={
            "start_pos": (0.0, 0.0, HOME_BASE_Z),
            "start_yaw": 0.0,
            "goal": 1.0,
        }
    )
    # La recompensa de avance también debe medirse sobre +X.
    env.set_reference_yaw(0.0)


# --------------------------------------------------------------------------- #
# Datos
# --------------------------------------------------------------------------- #
@dataclass
class Pose:
    pos: tuple[float, float, float]
    quat: tuple[float, float, float, float]
    yaw: float
    roll: float = 0.0
    pitch: float = 0.0

    @classmethod
    def from_robot(cls, robot_id: int) -> "Pose":
        pos, quat = p.getBasePositionAndOrientation(robot_id)
        roll, pitch, yaw = p.getEulerFromQuaternion(quat)
        return cls(
            pos=tuple(float(v) for v in pos),
            quat=tuple(float(v) for v in quat),
            yaw=float(yaw),
            roll=float(roll),
            pitch=float(pitch),
        )

    @property
    def up_z(self) -> float:
        """Componente Z del vector "up" del robot en el mundo.

        +1 = perfectamente derecho, 0 = de costado, -1 = invertido.
        """
        qx, qy, _qz, _qw = self.quat
        return 1.0 - 2.0 * (qx * qx + qy * qy)

    @property
    def display_pos(self) -> tuple[float, float, float]:
        """Posición visible: Z=0 cuando el chasis está apoyado en el suelo."""
        return (
            self.pos[0],
            self.pos[1],
            self.pos[2] - HOME_BASE_Z,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "pos": [round(v, 5) for v in self.pos],
            "pos_visible": [round(v, 5) for v in self.display_pos],
            "quat": [round(v, 6) for v in self.quat],
            "yaw_deg": round(math.degrees(self.yaw), 3),
            "pitch_deg": round(math.degrees(self.pitch), 3),
            "roll_deg": round(math.degrees(self.roll), 3),
            "up_z": round(self.up_z, 4),
        }


@dataclass
class ParsedCommand:
    kind: str
    distance: float | None = None       # metros, con signo (+ adelante)
    angle_deg: float | None = None      # grados, con signo (+ izquierda)
    raw: str = ""
    note: str = ""


@dataclass
class Experience:
    command: str
    kind: str
    start_pose: Pose
    target_distance: float | None = None
    target_angle_deg: float | None = None
    end_pose: Pose | None = None
    actions: list[tuple[float, float]] = field(default_factory=list)
    collision: bool = False
    flipped: bool = False
    reason: str = ""
    steps: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    lateral_error_m: float = 0.0
    model: str = "manual (sin PPO)"
    falls: int = 0
    recoveries: int = 0
    recovery_failures: int = 0
    success: bool | None = None
    rating: str | None = None
    report_paths: tuple[Path, Path] | None = None

    def distance_actual(self) -> float | None:
        """Distancia recorrida con signo, proyectada sobre el rumbo inicial."""
        if self.kind != "move" or self.end_pose is None:
            return None
        dx = self.end_pose.pos[0] - self.start_pose.pos[0]
        dy = self.end_pose.pos[1] - self.start_pose.pos[1]
        heading_x = math.cos(self.start_pose.yaw)
        heading_y = math.sin(self.start_pose.yaw)
        return float(dx * heading_x + dy * heading_y)

    def angle_actual_deg(self) -> float | None:
        if self.kind != "turn" or self.end_pose is None:
            return None
        return math.degrees(
            wrap_angle(self.end_pose.yaw - self.start_pose.yaw)
        )

    def error_distance_m(self) -> float | None:
        actual = self.distance_actual()
        if actual is None or self.target_distance is None:
            return None
        return actual - self.target_distance

    def error_angle_deg(self) -> float | None:
        actual = self.angle_actual_deg()
        if actual is None or self.target_angle_deg is None:
            return None
        return math.degrees(
            wrap_angle(math.radians(actual - self.target_angle_deg))
        )

    def duration_s(self) -> float:
        return self.steps / CONTROL_HZ

    def to_record(self, success: bool) -> dict[str, Any]:
        end = self.end_pose or self.start_pose
        actual_distance = self.distance_actual()
        actual_angle = self.angle_actual_deg()
        error_distance = self.error_distance_m()
        error_angle = self.error_angle_deg()
        if self.actions:
            mean_left = float(np.mean([a[0] for a in self.actions]))
            mean_right = float(np.mean([a[1] for a in self.actions]))
        else:
            mean_left = 0.0
            mean_right = 0.0
        actions_json = [
            [round(float(a), 4), round(float(b), 4)]
            for a, b in self.actions
        ]
        return {
            "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
            "resultado": "Experiencia Exitosa" if success else "Fallo",
            "exito": bool(success),
            "recompensa": 1.0 if success else -1.0,
            "comando": self.command,
            "tipo": self.kind,
            "objetivo_distancia_m": _round_opt(self.target_distance),
            "objetivo_angulo_deg": _round_opt(self.target_angle_deg),
            "inicio_x": round(self.start_pose.pos[0], 4),
            "inicio_y": round(self.start_pose.pos[1], 4),
            "inicio_z": round(self.start_pose.pos[2], 4),
            "inicio_yaw_deg": round(math.degrees(self.start_pose.yaw), 3),
            "fin_x": round(end.pos[0], 4),
            "fin_y": round(end.pos[1], 4),
            "fin_z": round(end.pos[2], 4),
            "fin_yaw_deg": round(math.degrees(end.yaw), 3),
            "distancia_real_m": _round_opt(actual_distance),
            "angulo_real_deg": _round_opt(actual_angle, 2),
            "error_distancia_m": _round_opt(error_distance),
            "error_angulo_deg": _round_opt(error_angle, 2),
            "error_lateral_m": round(self.lateral_error_m, 4),
            "pasos": self.steps,
            "duracion_s": round(self.duration_s(), 3),
            "colision": bool(self.collision),
            "volcado": bool(self.flipped),
            "motivo": self.reason,
            "accion_media_izq": round(mean_left, 4),
            "accion_media_der": round(mean_right, 4),
            "acciones_json": json.dumps(actions_json, ensure_ascii=False),
            "estado_inicial_json": json.dumps(
                self.start_pose.as_dict(), ensure_ascii=False
            ),
            "estado_final_json": json.dumps(end.as_dict(), ensure_ascii=False),
            "modelo": self.model,
            "caidas": self.falls,
            "recuperaciones": self.recoveries,
            "fallos_recuperacion": self.recovery_failures,
            "calificacion": self.rating or "",
        }


# --------------------------------------------------------------------------- #
# Feedback RLHF
# --------------------------------------------------------------------------- #
class FeedbackLogger:
    """Guarda experiencias exitosas/fallidas en CSV y JSONL."""

    def __init__(self, directory: Path | str = FEEDBACK_DIR) -> None:
        self.directory = Path(directory)
        self.csv_path = self.directory / "experiencias_walle.csv"
        self.jsonl_path = self.directory / "experiencias_walle.jsonl"

    def save(self, exp: Experience, success: bool) -> tuple[Path, Path]:
        self.directory.mkdir(parents=True, exist_ok=True)
        record = exp.to_record(success)
        write_header = (
            not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        )
        with self.csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=CSV_FIELDS, extrasaction="ignore"
            )
            if write_header:
                writer.writeheader()
            writer.writerow(record)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.csv_path, self.jsonl_path


# --------------------------------------------------------------------------- #
# Reportes automáticos de pruebas
# --------------------------------------------------------------------------- #
class TestReportWriter:
    """Genera un .md y un .json por cada orden ejecutada."""

    def __init__(self, directory: Path | str = REPORTS_DIR) -> None:
        self.directory = Path(directory)

    @staticmethod
    def _slug(text: str) -> str:
        normalized = normalize_text(text)
        slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
        return (slug or "comando")[:48]

    @staticmethod
    def _pose_dict(pose: Pose) -> dict[str, Any]:
        x, y, z = pose.display_pos
        return {
            "x_m": _zero_float(x, 4),
            "y_m": _zero_float(y, 4),
            "z_m": _zero_float(z, 4),
            "yaw_deg": _zero_float(math.degrees(pose.yaw), 2),
            "pitch_deg": _zero_float(math.degrees(pose.pitch), 2),
            "roll_deg": _zero_float(math.degrees(pose.roll), 2),
            "up_z": _zero_float(pose.up_z, 4),
        }

    def _payload(
        self,
        exp: Experience,
        automatic_success: bool | None,
        rating: str | None,
    ) -> dict[str, Any]:
        end = exp.end_pose or exp.start_pose
        distance = exp.distance_actual()
        angle = exp.angle_actual_deg()
        actions = exp.actions
        mean_left = (
            float(np.mean([a[0] for a in actions])) if actions else 0.0
        )
        mean_right = (
            float(np.mean([a[1] for a in actions])) if actions else 0.0
        )
        return {
            "reporte": "WALL-E · Reporte de prueba",
            "version": 1,
            "timestamp": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "orden_recibida": exp.command,
            "tipo": exp.kind,
            "modelo": exp.model,
            "resultado_automatico": automatic_success,
            "calificacion_humana": rating or exp.rating or "",
            "posicion_inicial": self._pose_dict(exp.start_pose),
            "posicion_final": self._pose_dict(end),
            "objetivo_distancia_m": _round_opt(exp.target_distance),
            "objetivo_angulo_deg": _round_opt(exp.target_angle_deg),
            "distancia_recorrida_m": _round_opt(distance),
            "angulo_girado_deg": _round_opt(angle, 2),
            "error_distancia_m": _round_opt(exp.error_distance_m()),
            "error_angulo_deg": _round_opt(exp.error_angle_deg(), 2),
            "error_lateral_m": round(exp.lateral_error_m, 4),
            "caidas_detectadas": exp.falls,
            "caidas_recuperadas": exp.recoveries,
            "fallos_recuperacion": exp.recovery_failures,
            "tiempo_total_s": round(exp.duration_s(), 3),
            "pasos": exp.steps,
            "colision": bool(exp.collision),
            "volcado": bool(exp.flipped),
            "motivo": exp.reason,
            "acciones": {
                "cantidad": len(actions),
                "media_izquierda": round(mean_left, 4),
                "media_derecha": round(mean_right, 4),
            },
        }

    @staticmethod
    def _markdown(data: dict[str, Any]) -> str:
        def value(key: str) -> str:
            raw = data.get(key)
            if raw is None or raw == "":
                return "—"
            return str(raw)

        success = data.get("resultado_automatico")
        if success is True:
            result = "✅ Éxito"
        elif success is False:
            result = "❌ Fallo"
        else:
            result = "—"

        start = data["posicion_inicial"]
        end = data["posicion_final"]

        return f"""# WALL-E · Reporte de prueba

**Timestamp:** {data["timestamp"]}  
**Orden recibida:** `{data["orden_recibida"]}`  
**Tipo:** {data["tipo"]}  
**Modelo:** {data["modelo"]}  
**Resultado automático:** {result}  
**Calificación humana:** {value("calificacion_humana")}

## Posición

| Momento | X (m) | Y (m) | Z (m) | Yaw (°) | Pitch (°) | Roll (°) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Inicial | {start["x_m"]:+.2f} | {start["y_m"]:+.2f} | {start["z_m"]:+.2f} | {start["yaw_deg"]:+.1f} | {start["pitch_deg"]:+.1f} | {start["roll_deg"]:+.1f} |
| Final | {end["x_m"]:+.2f} | {end["y_m"]:+.2f} | {end["z_m"]:+.2f} | {end["yaw_deg"]:+.1f} | {end["pitch_deg"]:+.1f} | {end["roll_deg"]:+.1f} |

## Movimiento

| Métrica | Valor |
| --- | ---: |
| Distancia recorrida | {value("distancia_recorrida_m")} m |
| Ángulo girado | {value("angulo_girado_deg")} ° |
| Objetivo de distancia | {value("objetivo_distancia_m")} m |
| Objetivo de ángulo | {value("objetivo_angulo_deg")} ° |
| Error de distancia | {value("error_distancia_m")} m |
| Error de ángulo | {value("error_angulo_deg")} ° |
| Error lateral | {value("error_lateral_m")} m |

## Caídas y recuperación

| Métrica | Valor |
| --- | ---: |
| Caídas detectadas | {data["caidas_detectadas"]} |
| Recuperaciones exitosas | {data["caidas_recuperadas"]} |
| Fallos de recuperación | {data["fallos_recuperacion"]} |

## Condiciones de la prueba

| Métrica | Valor |
| --- | ---: |
| Tiempo total | {data["tiempo_total_s"]} s |
| Pasos de simulación | {data["pasos"]} |
| Colisión | {"Sí" if data["colision"] else "No"} |
| Volcado | {"Sí" if data["volcado"] else "No"} |
| Motivo | {data["motivo"] or "—"} |
| Acción media izquierda | {data["acciones"]["media_izquierda"]} |
| Acción media derecha | {data["acciones"]["media_derecha"]} |

---

Generado automáticamente por `interactive_walle.py`.
"""

    def write(
        self,
        exp: Experience,
        automatic_success: bool | None,
        rating: str | None = None,
    ) -> tuple[Path, Path]:
        self.directory.mkdir(parents=True, exist_ok=True)

        if exp.report_paths is not None:
            md_path, json_path = exp.report_paths
        else:
            stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
            base = f"test_{stamp}_{self._slug(exp.command)}"
            md_path = self.directory / f"{base}.md"
            json_path = self.directory / f"{base}.json"
            suffix = 2
            while md_path.exists() or json_path.exists():
                md_path = self.directory / f"{base}_{suffix}.md"
                json_path = self.directory / f"{base}_{suffix}.json"
                suffix += 1

        data = self._payload(exp, automatic_success, rating)
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(self._markdown(data), encoding="utf-8")
        exp.report_paths = (md_path, json_path)
        return md_path, json_path

    @staticmethod
    def summary(exp: Experience, success: bool) -> str:
        actual = exp.distance_actual()
        angle = exp.angle_actual_deg()
        if exp.kind == "move" and actual is not None:
            verb = "Avanzó" if (exp.target_distance or 0.0) >= 0 else "Retrocedió"
            movement = f"{verb} {abs(actual):.2f} m"
        elif exp.kind == "turn" and angle is not None:
            movement = f"Giró {abs(angle):.0f}°"
        else:
            movement = "Terminó la orden"

        if exp.falls:
            falls = f"{exp.falls} caídas"
            if exp.recoveries:
                falls += f" ({exp.recoveries} recuperadas)"
        else:
            falls = "0 caídas"

        path = (
            _display_path(exp.report_paths[0])
            if exp.report_paths is not None
            else "reports/"
        )
        prefix = "Test completado" if success else "Test finalizado con fallo"
        return f"{prefix}: {movement}. {falls}. Reporte guardado en {path}."


# --------------------------------------------------------------------------- #
# Parser de español (sin dependencias externas)
# --------------------------------------------------------------------------- #
_NUMBER_WORDS: dict[str, float] = {
    "cero": 0,
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
    "cien": 100,
    "ciento": 100,
}

_STOP_RE = re.compile(
    r"\b(detente|detener|detenerse|parar|parate|alto|frena|frenar|stop)\b"
)
_MOVE_RE = re.compile(
    r"\b(avanza|avanzar|avanz[aá]|adelante|avancemos|camina|andar|anda|"
    r"muevete|movete)\b"
)
_BACK_RE = re.compile(
    r"\b(retrocede|retroceder|retroceda|atras|reversa|retroceso)\b"
)
_TURN_RE = re.compile(r"\b(gira|girar|gir[aá]|girate|girarse|turn)\b")
_LEFT_WORDS = (
    "izquierda",
    "izq",
    "izquierdo",
    "antihorario",
    "contra reloj",
    "contrarreloj",
)
_RIGHT_WORDS = (
    "derecha",
    "der",
    "derecho",
    "horario",
    "sentido horario",
)


def _find_word_position(text: str, words: tuple[str, ...]) -> int:
    positions = [text.find(word) for word in words if word in text]
    return min(positions) if positions else -1


def _direction_sign(text: str) -> tuple[int | None, str]:
    left_pos = _find_word_position(text, _LEFT_WORDS)
    right_pos = _find_word_position(text, _RIGHT_WORDS)
    if left_pos >= 0 and (right_pos < 0 or left_pos < right_pos):
        return 1, "izquierda"
    if right_pos >= 0:
        return -1, "derecha"
    return None, ""


def _word_number(text: str) -> float | None:
    total = 0.0
    found = False
    for token in re.findall(r"[a-z]+", text):
        if token in _NUMBER_WORDS:
            total += _NUMBER_WORDS[token]
            found = True
        elif token in {"medio", "media"}:
            total += 0.5
            found = True
    return total if found else None


def _extract_number(text: str) -> tuple[float | None, bool]:
    """Devuelve (valor absoluto, era_negativo)."""
    match = re.search(r"(-\s*)?(\d+(?:[.,]\d+)?)", text)
    if match:
        value = float(match.group(2).replace(",", "."))
        return abs(value), bool(match.group(1))
    if re.search(r"\b(metro|metros|cm|centimetros|centimetro|mm|milimetros|"
                 r"km|kilometros|kilometro|grado|grados|vuelta|vueltas|"
                 r"radianes|radian)\b", text):
        value = _word_number(text)
        if value is not None:
            return abs(value), False
    return None, False


def _distance_scale(text: str) -> float:
    if re.search(r"\b(cm|centimetros?)\b", text):
        return 0.01
    if re.search(r"\b(mm|milimetros?)\b", text):
        return 0.001
    if re.search(r"\b(km|kilometros?)\b", text):
        return 1000.0
    return 1.0


def _extract_distance(text: str) -> float | None:
    if "medio metro" in text or "media metro" in text:
        return 0.5 * _distance_scale(text)
    value, negative = _extract_number(text)
    if value is None:
        if "medio" in text:
            value = 0.5
        else:
            return None
    if "medio" in text and "medio metro" not in text and value >= 1.0:
        value += 0.5
    signed = -value if negative else value
    return signed * _distance_scale(text)


def _extract_turn_angle(text: str) -> tuple[float, str]:
    if "media vuelta" in text:
        return 180.0, "media vuelta"
    if "medio giro" in text:
        return 180.0, "medio giro"
    if "cuarto de vuelta" in text:
        return 90.0, "cuarto de vuelta"
    if "vuelta completa" in text:
        return 360.0, "vuelta completa"
    value, _negative = _extract_number(text)
    if value is None:
        return 90.0, "90° por defecto"
    if "vuelta" in text:
        return value * 360.0, ""
    if "radian" in text:
        return math.degrees(value), ""
    return value, ""


def parse_command(text: str) -> ParsedCommand:
    raw = text.strip()
    norm = normalize_text(raw)
    if not norm:
        return ParsedCommand("unknown", raw=raw)

    if any(
        word in norm
        for word in ("ayuda", "help", "comandos", "que podes hacer",
                     "qué podés hacer", "instrucciones")
    ):
        return ParsedCommand("help", raw=raw)

    if any(
        word in norm
        for word in ("reinicia", "reiniciar", "reset", "volve al inicio",
                     "vuelve al inicio", "posicion inicial", "posición inicial")
    ):
        return ParsedCommand("reset", raw=raw)

    if (
        "estado" in norm
        or "donde estas" in norm
        or "dónde estás" in norm
        or "posicion" in norm
        or "posición" in norm
    ):
        return ParsedCommand("status", raw=raw)

    if re.fullmatch(r"(para|pará)[.! ]*", norm):
        return ParsedCommand("stop", raw=raw)
    if _STOP_RE.search(norm):
        return ParsedCommand("stop", raw=raw)

    if re.search(r"\b(gracias|thanks)\b", norm):
        return ParsedCommand("thanks", raw=raw)

    is_move = bool(_MOVE_RE.search(norm))
    is_back = bool(_BACK_RE.search(norm))
    is_turn = bool(_TURN_RE.search(norm))
    direction, side = _direction_sign(norm)

    if is_move or is_back:
        distance = _extract_distance(norm)
        if distance is None:
            distance = 1.0
        distance = abs(distance)
        if is_back:
            distance = -distance
        return ParsedCommand("move", distance=distance, raw=raw)

    if is_turn or direction is not None:
        angle, angle_note = _extract_turn_angle(norm)
        _value, negative = _extract_number(norm)
        if direction is None:
            if negative:
                direction = 1
                note = "ángulo negativo"
            else:
                direction = -1
                note = "por defecto a la derecha"
        else:
            note = f"a la {side}"
        if angle_note:
            note = f"{note} ({angle_note})"
        signed_angle = abs(angle) * direction
        return ParsedCommand("turn", angle_deg=signed_angle, raw=raw, note=note)

    if re.search(r"\b(hola|buenas|hey|que tal)\b", norm):
        return ParsedCommand("greet", raw=raw)

    return ParsedCommand("unknown", raw=raw)


HELP_TEXT = (
    "Podés hablarme así:\n"
    "• «avanza 2 metros» (si no decís distancia, avanzo 1 m)\n"
    "• «retrocede 50 cm»\n"
    "• «gira 90 grados a la derecha» / «gira a la izquierda» "
    "(90° por defecto)\n"
    "• «detente» para frenar en seco\n"
    "• «estado», «reinicia» o «ayuda»\n"
    "Después de cada orden, calificá con «Lo hizo bien» o "
    "«No lo hizo bien»."
)

class WalleController:
    """Controlador de WALL-E: PID manual y, opcionalmente, cerebro PPO."""

    def __init__(
        self,
        env: WallEEnv,
        logger: FeedbackLogger | None = None,
        model_path: Path | str | None = None,
        control_mode: str = "manual",
        report_writer: TestReportWriter | None = None,
    ) -> None:
        self.env = env
        self.logger = logger or FeedbackLogger()
        self.reports = report_writer or TestReportWriter()
        self.home_pose = Pose.from_robot(env.robot)

        self.mode = "idle"  # idle | moving | turning | ppo_moving | braking | recovering
        self.exp: Experience | None = None
        self.last_experience: Experience | None = None
        self.last_experience_rated = False

        self._brake_left = 0
        self._brake_reason = ""
        self._brake_tentative = False
        self._timeout_steps = int(COMMAND_TIMEOUT_S * CONTROL_HZ)

        # --- Suavizado del PID manual ------------------------------------- #
        # Última acción aplicada, para rampar aceleración y correcciones.
        self._move_base_action = 0.0
        self._move_correction = 0.0
        self._turn_correction = 0.0

        # --- Caídas y auto-recuperación ---------------------------------- #
        self.falls_detected = 0
        self._mode_before_fall = "idle"
        self._fall_pose = self.home_pose
        self._last_stable_pose = self.home_pose
        self._recovery_steps = 0
        self._recovery_failures = 0
        self._recovery_cycles = 0
        self._recovery_torque_sign = 1.0
        self._settle_left = 0
        self._mode_after_settle = "idle"

        # --- Cerebro PPO -------------------------------------------------- #
        self.model_path = Path(model_path) if model_path else None
        self.control_mode = "manual"  # manual | ppo
        self.model = None
        # --- Rodeo de obstáculos (LiDAR de los pies) ----------------------- #
        # Fase interna del rodeo: "" | "turn" | "forward" | "reaim". Se usa
        # dentro de mode == "moving" para no tocar la lista de modos activos.
        self._avoid_phase = ""
        self._avoid_left = 0
        self._avoid_attempts = 0
        self._avoid_sign = 1.0
        self._avoid_entry_remaining = 0.0
        self._avoid_gained = 0.0
        self._avoid_start_pos = (0.0, 0.0, 0.0)
        self._avoid_last_start: tuple[float, float] = (1e9, 1e9)
        self._avoid_turn_start_yaw = 0.0
        self._avoid_turn_target = math.radians(AVOID_TURN_DEG)
        # Desvío lateral del punto de mira (m): el rodeo lo incrementa y el
        # PID lo persigue. Sin esto el robot vuelve al muro en cada intento.
        self._avoid_offset = 0.0
        self._avoid_offset_target = 0.0
        self._avoid_cooldown = 0
        self._avoid_back_extensions = 0
        # Detector de atasco de giro: pivote que deja de girar.
        self._turn_stall_yaw = 0.0
        self._turn_stall_ticks = 0
        # Detector de atasco: si no avanza, hay que rodear aunque el cono
        # frontal diga que está libre.
        self._stall_pos: tuple[float, float] = (0.0, 0.0)
        self._stall_ticks = 0
        # Etiqueta se asignará al cargar el modelo según el entorno
        self.ppo_label = "PPO"
        self.manual_label = "manual (PID)"
        # Recuperación anti-atasco del modo PPO.
        self._ppo_recover_left = 0
        self._ppo_recover_sign = 1.0
        self._ppo_watch_pos: tuple[float, float] | None = None
        self._ppo_watch_yaw = 0.0
        self._ppo_watch_steps = 0
        self._ppo_goal = 1.0
        self._brain_error = ""

        # --- Recuperación manual de choques ------------------------------- #
        self._unstick_phase = ""      # "" | "back" | "turn"
        self._unstick_left = 0
        self._unstick_attempts = 0
        self._unstick_sign = 1.0
        self._unstick_drive = -1.0    # sentido de la maniobra de despegue
        self._unstick_resume = "moving"
        self._unstick_back_extensions = 0
        self._unstick_turn_start_yaw = 0.0

        if control_mode == "ppo":
            # No forzamos el modo si el cerebro no carga: el llamador recibe
            # el mensaje de set_control_mode() y puede seguir en manual.
            self.set_control_mode("ppo")

    # ------------------------------------------------------------------ #
    # Cerebro PPO
    # ------------------------------------------------------------------ #
    def load_brain(self) -> tuple[bool, str]:
        """Carga la política PPO/RecurrentPPO. Acepta 13D (V1) o 58D (V5)."""
        if self.model is not None:
            return True, f"Cerebro PPO listo: {self.model_path.name}."
        if not self.model_path.exists():
            self._brain_error = f"No encuentro el modelo {self.model_path}."
            return False, self._brain_error
        model = None
        errors = []
        # V4: RecurrentPPO (LSTM) de sb3-contrib
        try:
            from sb3_contrib import RecurrentPPO

            model = RecurrentPPO.load(str(self.model_path), device="cpu")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"RecurrentPPO: {exc}")
        # V1/V3: PPO clásico
        if model is None:
            try:
                from stable_baselines3 import PPO

                model = PPO.load(str(self.model_path), device="cpu")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"PPO: {exc}")
        if model is None:
            self._brain_error = (
                "No pude cargar el cerebro PPO ("
                + " | ".join(errors)
                + "). Revisá stable-baselines3, sb3-contrib y torch en el .venv."
            )
            return False, self._brain_error

        obs_shape = getattr(model.observation_space, "shape", None)
        if obs_shape not in ((13,), (19,), (50,), (58,)):
            self._brain_error = (
                f"El modelo {self.model_path.name} espera observación "
                f"{obs_shape}, pero el entorno actual usa {self.env.observation_space.shape}."
            )
            return False, self._brain_error

        self.model = model
        # Estado LSTM para RecurrentPPO (V4). Para PPO clásico no se usa.
        self._lstm_states = None
        self._episode_start = np.ones((1,), dtype=bool)
        self._brain_error = ""
        kind = "RecurrentPPO (LSTM)" if self._is_recurrent() else "PPO"
        return True, (
            f"Cerebro {kind} cargado: {self.model_path.name} "
            f"(observación {obs_shape[0]}D, acción 2D)."
        )

    def _is_recurrent(self) -> bool:
        """True si el modelo cargado es RecurrentPPO (con LSTM)."""
        if self.model is None:
            return False
        try:
            from sb3_contrib import RecurrentPPO

            return isinstance(self.model, RecurrentPPO)
        except Exception:  # noqa: BLE001
            return False

    def _reset_lstm(self) -> None:
        """Reinicia la memoria LSTM al comenzar un episodio nuevo."""
        self._lstm_states = None
        self._episode_start = np.ones((1,), dtype=bool)

    def set_control_mode(self, mode: str) -> list[str]:
        """Cambia entre control manual (PID) y cerebro PPO."""
        mode = normalize_text(mode)
        if mode not in {"manual", "ppo"}:
            return ["Modo desconocido. Usá «manual» o «ppo»."]

        message = ""
        partial_note = ""
        if mode == "ppo":
            # Seleccionar el modelo correcto según el entorno (V5=58D, V4=50D,
            # V1=13D). Se prefiere el modelo V5 de resolución de problemas.
            if hasattr(self.env, "lidar_meters"):
                models_dir = Path(SCRIPT_DIR) / "models"
                v5_model = models_dir / "walle_ppo_model_v5_recovery.zip"
                v4_model = models_dir / "walle_ppo_model_v4_lidar.zip"
                expected = int(self.env.observation_space.shape[0])
                chosen = None
                if v5_model.exists() and expected == 58:
                    chosen = v5_model
                elif v4_model.exists() and expected == 50:
                    chosen = v4_model
                if chosen is not None:
                    self.model_path = chosen
                    self.model = None  # forzar recarga del nuevo modelo
                else:
                    # Entrenamiento en curso: usar el checkpoint más reciente.
                    ckpt_dir = models_dir / "checkpoints"
                    checkpoints = (
                        sorted(
                            ckpt_dir.glob("walle_v5_*_steps.zip"),
                            key=lambda path: path.stat().st_mtime,
                            reverse=True,
                        )
                        if ckpt_dir.exists()
                        else []
                    )
                    if checkpoints:
                        self.model_path = checkpoints[0]
                        self.model = None
                        partial_note = (
                            "Modelo V5 parcial cargado (entrenamiento en "
                            f"curso): {checkpoints[0].name}."
                        )
                    else:
                        return [
                            "El modelo V5 (walle_ppo_model_v5_recovery.zip) "
                            "todavía no existe y el entorno ahora usa 58D.",
                            "Lanza train_walle_v5.py o sigo en modo manual (PID).",
                        ]
            else:
                # Entorno V1: usar el modelo físico de 13D
                v1_model = PPO_MODEL
                if v1_model.exists():
                    self.model_path = v1_model
                    self.model = None  # forzar recarga
                else:
                    return [
                        "No encuentro el modelo V1 físico. "
                        "Sigo en modo manual (PID).",
                    ]

            ok, message = self.load_brain()
            if not ok:
                return [message, "Sigo en modo manual (PID)."]

            # Actualizar etiqueta con el nombre del modelo cargado
            self.ppo_label = f"PPO ({self.model_path.name})"

        if mode == self.control_mode:
            label = "PPO" if mode == "ppo" else "manual (PID)"
            return [f"Ya estoy en modo {label}.", *([message] if message else [])]

        interrupted = self._interrupt_active()
        if interrupted:
            # Un paso con acción cero deja los motores en reposo antes de
            # cambiar de controlador.
            self._step([0.0, 0.0])

        self.control_mode = mode
        if mode == "ppo":
            # Iniciar exploración autónoma automáticamente en V3/V4
            if hasattr(self.env, "lidar_meters") or hasattr(
                self.env, "chunk_mapper"
            ):
                header = [m for m in (partial_note, message) if m]
                return header + self._start_autonomous_exploration()
            return [
                message,
                "Modo PPO activado: las órdenes de avance/retroceso las "
                "conduce el cerebro. Los giros siguen usando el PID de rumbo.",
            ]
        return [
            "Modo manual (PID) activado: las órdenes usan el controlador "
            "de posición y rumbo."
        ]

    def _start_autonomous_exploration(self) -> list[str]:
        """Inicia la exploración autónoma: el robot avanza solo usando PPO
        y el LiDAR para esquivar obstáculos."""
        self._interrupt_active()
        self._recovery_failures = 0
        self._recovery_cycles = 0
        # Obtener pose actual como punto de partida
        start_pose = self._pose()
        self.mode = "ppo_moving"
        self._ppo_goal = 1.0
        self.env.set_reference_yaw(start_pose.yaw)
        # No usar Experience: el modo autónomo se maneja directamente en _tick_ppo_move
        self.exp = None
        # Reiniciar la memoria LSTM al comenzar un episodio de exploración.
        self._reset_lstm()
        self._ppo_watch_pos = (start_pose.pos[0], start_pose.pos[1])
        self._ppo_watch_yaw = start_pose.yaw
        self._ppo_watch_steps = 0
        self.last_experience = None
        self.last_experience_rated = False
        return [
            "🤖 Exploración autónoma activada: WALL-E avanza solo usando PPO y LiDAR 72.",
            "Escribí «detente» para parar la exploración.",
        ]

    def _mode_label(self) -> str:
        return "PPO" if self.control_mode == "ppo" else "manual (PID)"

    # ------------------------------------------------------------------ #
    # Estado y física
    # ------------------------------------------------------------------ #
    def _pose(self) -> Pose:
        return Pose.from_robot(self.env.robot)

    def _step(self, action: list[float] | tuple[float, float]):
        obs, reward, terminated, truncated, info = self.env.step(
            np.asarray(action, dtype=np.float32)
        )
        if self.exp is not None:
            self.exp.steps += 1
            # Los ticks de recuperación (despegue y rodeo) no consumen el
            # presupuesto de la orden: antes se sumaba el peor caso por
            # adelantado (8 s por rodeo) y con cuatro maniobras la orden moría
            # por "tiempo agotado" estando a medio metro de la meta.
            if self._avoid_phase or self._unstick_phase:
                self._timeout_steps += 1
            self.exp.actions.append((float(action[0]), float(action[1])))
            self.exp.collision = self.exp.collision or bool(
                info.get("collision")
            )
            self.exp.flipped = self.exp.flipped or bool(info.get("flipped"))
        pose = self._pose()
        if pose.up_z >= FALL_RECOVERED_UP:
            self._last_stable_pose = pose
        return info, terminated, truncated

    # ------------------------------------------------------------------ #
    # Caídas y auto-recuperación
    # ------------------------------------------------------------------ #
    def _check_fall(self) -> str | None:
        """Detecta volcado por el vector Up y arranca la recuperación."""
        if self.mode == "recovering":
            return None
        pose = self._pose()
        if pose.up_z >= FALL_UP_THRESHOLD:
            return None

        self.falls_detected += 1
        if self.exp is not None:
            self.exp.falls += 1
        self._mode_before_fall = self.mode
        self._fall_pose = self._last_stable_pose
        self._recovery_steps = 0
        self._recovery_torque_sign = 1.0
        self.mode = "recovering"
        print(
            f"[WALL-E] ¡Me caí! up_z={pose.up_z:+.2f}. "
            "Iniciando secuencia de recuperación.",
            flush=True,
        )
        return "¡Me caí! Iniciando secuencia de recuperación..."

    def _apply_self_right_torque(self, pose: Pose) -> None:
        """Aplica un torque en el eje que lleva el vector Up hacia +Z."""
        matrix = p.getMatrixFromQuaternion(pose.quat)
        up = np.array(
            [matrix[2], matrix[5], matrix[8]], dtype=np.float64
        )
        axis = np.cross(up, np.array([0.0, 0.0, 1.0]))
        norm = float(np.linalg.norm(axis))
        if norm < 1e-5:
            # Totalmente invertido: usar el eje X local como bisagra.
            axis = np.array(
                [matrix[0], matrix[3], matrix[6]], dtype=np.float64
            )
            norm = float(np.linalg.norm(axis))
        if norm < 1e-5:
            return
        axis /= norm
        torque = axis * SELF_RIGHT_TORQUE * self._recovery_torque_sign
        p.applyExternalTorque(
            self.env.robot,
            -1,
            torqueObj=torque.tolist(),
            flags=p.WORLD_FRAME,
        )

    def _finish_recovery(self) -> list[str]:
        resumed = self._mode_before_fall
        if resumed in {"recovering", "settling"}:
            resumed = self._mode_after_settle
        self._mode_after_settle = resumed
        self._settle_left = RECOVERY_SETTLE_STEPS
        self.mode = "settling"
        # Frenar el impulso angular del torque para que no vuelva a volcar.
        p.resetBaseVelocity(
            self.env.robot, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        )
        if self.exp is not None:
            self.exp.recoveries += 1
        print(
            f"[WALL-E] Recuperado (up_z={self._pose().up_z:+.2f}). "
            f"Estabilizando {RECOVERY_SETTLE_STEPS} pasos.",
            flush=True,
        )
        return ["¡Recuperado! Estabilizando antes de continuar..."]

    def _tick_settle(self) -> list[str]:
        self._step([0.0, 0.0])
        fall = self._check_fall()
        if fall:
            return [fall]
        self._settle_left -= 1
        if self._settle_left > 0:
            return []
        self.mode = self._mode_after_settle
        if self.mode == "idle":
            return ["Estabilizado. Quedo a la espera de órdenes."]
        return ["Estabilizado. Continúo con la orden."]

    def _abort_recovery(self) -> list[str]:
        self._restore_pose(self._fall_pose)
        self._recovery_failures += 1
        if self.exp is not None:
            self.exp.recovery_failures += 1

        if self._recovery_failures >= 2:
            print(
                "[WALL-E] No pude levantarme tras dos intentos. "
                "Registro el fallo y cierro la orden.",
                flush=True,
            )
            self._start_brake("caída no recuperada", tentative_success=False)
            return [
                "No pude levantarme. Reseteé la pose y registro el fallo "
                "en el reporte."
            ]

        self.mode = (
            self._mode_before_fall
            if self._mode_before_fall not in {"recovering", "settling"}
            else self._mode_after_settle
        )
        print(
            "[WALL-E] Recuperación agotada. Volví a la última pose estable "
            f"(x={self._fall_pose.pos[0]:+.2f}, y={self._fall_pose.pos[1]:+.2f}).",
            flush=True,
        )
        return [
            "No pude levantarme solo. Volví a la última pose estable y "
            "continúo con la orden."
        ]

    def _tick_recover(self) -> list[str]:
        self._recovery_steps += 1
        pose = self._pose()
        if pose.up_z >= FALL_RECOVERED_UP:
            return self._finish_recovery()
        if self._recovery_steps > RECOVERY_MAX_STEPS:
            return self._abort_recovery()

        # Si se trabó, alternar el sentido del torque y mecer las orugas.
        if self._recovery_steps % 120 == 0:
            self._recovery_torque_sign *= -1.0
        self._apply_self_right_torque(pose)
        wheel = 0.0
        if self._recovery_steps > 150:
            wheel = 0.45 if (self._recovery_steps // 30) % 2 == 0 else -0.45
        self._step([wheel, wheel])

        if self._pose().up_z >= FALL_RECOVERED_UP:
            return self._finish_recovery()
        return []

    def _reset_slew(self) -> None:
        """Reinicia las rampas del PID manual."""
        self._move_base_action = 0.0
        self._move_correction = 0.0
        self._turn_correction = 0.0

    def reset_home(self) -> list[str]:
        """Vuelve al origen (X=0, Y=0), mirando hacia +X y quieto."""
        self.mode = "idle"
        self.exp = None
        self._brake_left = 0
        self._brake_reason = ""
        self._brake_tentative = False
        self._recovery_steps = 0
        self._recovery_failures = 0
        self._recovery_cycles = 0
        self._settle_left = 0
        self._reset_slew()
        reset_env_home(self.env)
        self.home_pose = Pose.from_robot(self.env.robot)
        self._fall_pose = self.home_pose
        self._last_stable_pose = self.home_pose
        self.last_experience = None
        self.last_experience_rated = False
        return ["Listo: volví al origen mirando hacia +X (yaw 0°)."]

    def _restore_pose(self, pose: Pose) -> None:
        p.resetBasePositionAndOrientation(
            self.env.robot, list(pose.pos), list(pose.quat)
        )
        p.resetBaseVelocity(
            self.env.robot, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        )
        for joint_index in (0, 1):
            p.resetJointState(self.env.robot, joint_index, 0.0)
            p.setJointMotorControl2(
                self.env.robot,
                joint_index,
                p.VELOCITY_CONTROL,
                targetVelocity=0.0,
                force=self.env.max_force,
            )
        self.env.prev_pos = np.asarray(pose.pos, dtype=np.float64).copy()
        self.env.step_count = 0
        self._reset_slew()
        for _ in range(12):
            p.stepSimulation()

    # ------------------------------------------------------------------ #
    # Entrada de chat
    # ------------------------------------------------------------------ #
    def handle_text(self, text: str) -> list[str]:
        normalized = normalize_text(text)
        if normalized in {"modo ppo", "activar ppo", "cerebro ppo", "usar ppo"}:
            return self.set_control_mode("ppo")
        if normalized in {
            "modo manual",
            "activar manual",
            "control manual",
            "usar manual",
        }:
            return self.set_control_mode("manual")
        parsed = parse_command(text)
        if parsed.kind == "help":
            return [HELP_TEXT]
        if parsed.kind == "reset":
            return self.reset_home()
        if parsed.kind == "status":
            return [self.status_line()]
        if parsed.kind == "stop":
            return self._handle_stop()
        if parsed.kind == "thanks":
            return ["De nada. ¿Otra orden?"]
        if parsed.kind == "greet":
            return [
                "¡Hola! Soy WALL-E. Escribí una orden o pedí «ayuda». "
                "Estoy quieto hasta que me digas qué hacer."
            ]
        if parsed.kind == "move":
            if self.control_mode == "ppo":
                return self._start_ppo_move(parsed)
            return self._start_move(parsed)
        if parsed.kind == "turn":
            return self._start_turn(parsed)
        return [
            "No entendí esa orden. Probá con «avanza 1 metro», "
            "«gira 90 grados a la izquierda», «retrocede 50 cm» o "
            "«detente»."
        ]

    # ------------------------------------------------------------------ #
    # Inicio de órdenes
    # ------------------------------------------------------------------ #
    def _interrupt_active(self) -> str | None:
        if self.mode == "idle":
            return None
        self.mode = "idle"
        self.exp = None
        self._brake_left = 0
        self._reset_slew()
        return "Interrumpí la orden anterior."

    def _start_move(self, parsed: ParsedCommand) -> list[str]:
        messages: list[str] = []
        prefix = self._interrupt_active()
        if prefix:
            messages.append(prefix)
        self._reset_slew()
        self._recovery_failures = 0
        self._recovery_cycles = 0
        self._unstick_attempts = 0
        self._unstick_phase = ""
        self._unstick_left = 0
        self._avoid_phase = ""
        self._avoid_left = 0
        self._avoid_attempts = 0
        self._avoid_gained = 0.0
        self._avoid_start_pos = (0.0, 0.0, 0.0)
        self._avoid_last_start = (1e9, 1e9)
        self._avoid_turn_start_yaw = 0.0
        self._avoid_turn_target = math.radians(AVOID_TURN_DEG)
        self._avoid_offset = 0.0
        self._avoid_offset_target = 0.0
        self._avoid_cooldown = 0
        self._avoid_back_extensions = 0
        self._stall_ticks = 0
        self._stall_pos = (0.0, 0.0)
        distance = float(parsed.distance or 0.0)
        self.exp = Experience(
            command=parsed.raw,
            kind="move",
            start_pose=self._pose(),
            target_distance=distance,
            model=self.manual_label,
        )
        self.mode = "moving"
        self.last_experience = None
        self.last_experience_rated = False
        verb = "avanzo" if distance >= 0 else "retrocedo"
        messages.append(f"Entendido: {verb} {abs(distance):.2f} m.")
        return messages

    def _start_ppo_move(self, parsed: ParsedCommand) -> list[str]:
        messages: list[str] = []
        prefix = self._interrupt_active()
        if prefix:
            messages.append(prefix)
        self._reset_slew()

        ok, message = self.load_brain()
        if not ok:
            messages.append(message)
            messages.append("Uso el controlador manual (PID) para esta orden.")
            return messages + self._start_move(parsed)

        distance = float(parsed.distance or 0.0)
        self.exp = Experience(
            command=parsed.raw,
            kind="move",
            start_pose=self._pose(),
            target_distance=distance,
            model=self.ppo_label,
        )
        self.mode = "ppo_moving"
        self._ppo_goal = 1.0 if distance >= 0 else -1.0
        # La recompensa de avance debe medirse sobre el frente actual, no
        # sobre el rumbo del último reset (puede haber un giro en medio).
        self.env.set_reference_yaw(self.exp.start_pose.yaw)
        self._recovery_failures = 0
        self._recovery_cycles = 0
        self.last_experience = None
        self.last_experience_rated = False
        verb = "avanzo" if distance >= 0 else "retrocedo"
        messages.append(
            f"Entendido: {verb} {abs(distance):.2f} m con el cerebro PPO."
        )
        return messages

    def _start_turn(self, parsed: ParsedCommand) -> list[str]:
        messages: list[str] = []
        prefix = self._interrupt_active()
        if prefix:
            messages.append(prefix)
        self._reset_slew()
        self._recovery_failures = 0
        self._recovery_cycles = 0
        self._unstick_attempts = 0
        self._unstick_phase = ""
        self._unstick_left = 0
        self._turn_stall_yaw = self._pose().yaw
        self._turn_stall_ticks = 0
        angle = float(parsed.angle_deg or 0.0)
        self.exp = Experience(
            command=parsed.raw,
            kind="turn",
            start_pose=self._pose(),
            target_angle_deg=angle,
            model=self.manual_label,
        )
        self.mode = "turning"
        self.last_experience = None
        self.last_experience_rated = False
        side = "izquierda" if angle >= 0 else "derecha"
        note = f" ({parsed.note})" if parsed.note else ""
        messages.append(
            f"Entendido: giro {abs(angle):.0f}° a la {side}{note}."
        )
        if self.control_mode == "ppo":
            messages.append(
                "El cerebro PPO no tiene comando de ángulo: el giro lo "
                "resuelve el PID de rumbo."
            )
        return messages

    def _handle_stop(self) -> list[str]:
        if self.mode in {
            "moving",
            "ppo_moving",
            "turning",
            "recovering",
            "unsticking",
            "settling",
        }:
            self._start_brake("detenido por el usuario", tentative_success=False)
            return [
                "Frenando. La orden anterior quedó interrumpida; cuando "
                "termine el frenado podés calificarla."
            ]
        if self.mode == "braking":
            return ["Ya estoy frenando."]
        return ["Ya estoy detenido."]

    # ------------------------------------------------------------------ #
    # Bucle de control (60 Hz)
    # ------------------------------------------------------------------ #
    def tick(self) -> list[str]:
        if self.mode == "recovering":
            return self._tick_recover()
        if self.mode == "unsticking":
            return self._tick_unstick()
        if self.mode == "settling":
            return self._tick_settle()
        if self.mode == "ppo_recovering":
            return self._tick_ppo_recover()

        if self.mode == "idle":
            self._step([0.0, 0.0])
            fall = self._check_fall()
            return [fall] if fall else []

        # El modo ppo_moving no requiere self.exp (exploración autónoma continua)
        if self.exp is None and self.mode != "ppo_moving":
            self.mode = "idle"
            return []

        if self.mode == "moving":
            return self._tick_move()
        if self.mode == "ppo_moving":
            return self._tick_ppo_move()
        if self.mode == "turning":
            return self._tick_turn()
        if self.mode == "braking":
            self._step([0.0, 0.0])
            fall = self._check_fall()
            if fall:
                return [fall]
            self._brake_left -= 1
            if self._brake_left <= 0:
                return self._finish_after_brake()
        return []

    def _tick_move(self) -> list[str]:
        exp = self.exp
        assert exp is not None
        target = float(exp.target_distance or 0.0)
        if abs(target) < 1e-6:
            self._start_brake("objetivo alcanzado", tentative_success=True)
            return []

        # Un rodeo en curso manda sobre el PID de marcha.
        if self._avoid_phase:
            return self._tick_avoid()

        pose = self._pose()
        direction = 1.0 if target >= 0 else -1.0
        heading_x = math.cos(exp.start_pose.yaw)
        heading_y = math.sin(exp.start_pose.yaw)
        lateral_x = -heading_y
        lateral_y = heading_x
        dx = pose.pos[0] - exp.start_pose.pos[0]
        dy = pose.pos[1] - exp.start_pose.pos[1]
        along = (dx * heading_x + dy * heading_y) * direction
        remaining = abs(target) - along
        exp.lateral_error_m = float(dx * lateral_x + dy * lateral_y)

        if exp.steps >= self._timeout_steps:
            self._start_brake("tiempo agotado", tentative_success=False)
            return []
        if remaining <= MOVE_STOP_M:
            self._start_brake("objetivo alcanzado", tentative_success=True)
            return []

        # Punto de mira: sobre la línea del objetivo, desplazado lateralmente
        # por lo que hayan acumulado los rodeos. Perseguir el rumbo original
        # a secas hacía que el PID devolviera al robot contra el mismo muro
        # una y otra vez: no existe forma de rodear un obstáculo sin salirse
        # de la recta.
        clearance = self._front_clearance()
        if self._avoid_cooldown > 0:
            self._avoid_cooldown -= 1
        # Si el chasis esta tocando algo, el frente NO esta despejado por mucho
        # que el abanico de los pies pase por debajo: una rampa baja o el borde
        # de una caja dejan los rayos limpios y el robot se quedaba empujando
        # sin enterarse. Ese "frente libre" falso era el que impedia rodear.
        touching = self._touching()
        if touching and clearance > SAFE_SLOW_M:
            clearance = 0.0
        # Con el frente despejado y sin rodeo en curso, el desvío vuelve poco a
        # poco a la línea original: el robot no se queda caminando en paralelo
        # para siempre después de esquivar una caja. Nunca mientras toca algo:
        # ahí el desvío es justo lo que lo está sacando del atasco.
        if (
            self._avoid_phase == ""
            and not touching
            and clearance > SAFE_GO_M
            and self._avoid_offset_target != 0.0
        ):
            self._avoid_offset_target = slew_toward(
                self._avoid_offset_target, 0.0, AVOID_OFFSET_DECAY
            )
        self._avoid_offset = slew_toward(
            self._avoid_offset, self._avoid_offset_target, AVOID_OFFSET_SLEW
        )
        lateral = self._avoid_offset
        look = max(remaining, 0.0) + AVOID_LOOKAHEAD_M
        aim_x = (
            exp.start_pose.pos[0]
            + heading_x * (along + look)
            + lateral_x * lateral
        )
        aim_y = (
            exp.start_pose.pos[1]
            + heading_y * (along + look)
            + lateral_y * lateral
        )
        goal_yaw = math.atan2(aim_y - pose.pos[1], aim_x - pose.pos[0])
        if direction < 0.0:
            goal_yaw = wrap_angle(goal_yaw + math.pi)
        yaw_error = wrap_angle(goal_yaw - pose.yaw)
        # Zona muerta: ignorar micro-errores de rumbo (< 0.5°) para no temblar.
        if abs(yaw_error) < MOVE_YAW_DEADZONE_RAD:
            yaw_error = 0.0

        if direction > 0.0:
            # Se rodea ANTES de tocar: el abanico de los pies ya ve el muro a
            # 0.28 m y no hace falta estamparse para enterarse. El desvio se
            # aplica al punto de mira y el PID rodea solo: no hay guion ciego
            # de retroceder-girar-avanzar que dejaba al robot cruzado.
            if clearance <= SAFE_SLOW_M and self._avoid_attempts < 3:
                self._start_avoid(clearance)
                if self._avoid_phase:
                    return self._tick_avoid()
            # Detector de atasco: si en un segundo no avanzo ni 3 cm, el
            # camino esta cerrado aunque el cono frontal diga otra cosa (una
            # caja justo al borde del cono, un rincon, dos obstaculos en V).
            # Solo cuenta lejos del objetivo: cerca de la meta el robot frena
            # a proposito y eso no es un atasco.
            if (
                remaining > 0.50
                and self._stall_ticks >= int(STALL_WINDOW_S * CONTROL_HZ)
            ):
                self._reset_stall(pose.pos)
                # Primero se desplaza el punto de mira (barato y suave). Si
                # tras varios desvios sigue clavado, hace falta maniobra
                # fisica: retroceso + pivote. El desvio ya esta aplicado, asi
                # que al retomar la orden apunta al lado libre.
                if self._avoid_attempts < 3:
                    self._start_avoid(clearance)
                else:
                    self._start_unstick("moving")
                if self._avoid_phase:
                    return self._tick_avoid()
                return []

        target_base = clamp(
            MOVE_GAIN * max(remaining, 0.0) + 0.05,
            MOVE_MIN_ACTION,
            MOVE_MAX_ACTION,
        )
        # Modulación por distancia libre: entre SAFE_SLOW_M y SAFE_GO_M el
        # robot pasa de paso corto a fondo. Da tiempo a maniobrar sin que se
        # quede plantado en mitad del pasillo. NO se aplica mientras el chasis
        # toca algo: ahí hace falta par de sobra para pivotar y salir, y con
        # el paso corto WALL-E se quedaba empujando la rampa sin girar.
        if direction > 0.0 and clearance < SAFE_GO_M and not touching:
            span = max(SAFE_GO_M - SAFE_SLOW_M, 1e-3)
            scale = clamp((clearance - SAFE_SLOW_M) / span, 0.0, 1.0)
            target_base = max(
                target_base * (0.35 + 0.65 * scale), MOVE_MIN_ACTION
            )
        # Rampa de aceleración: sin escalones bruscos de torque.
        self._move_base_action = slew_toward(
            self._move_base_action, target_base, MOVE_ACCEL_STEP
        )
        target_correction = clamp(
            MOVE_YAW_GAIN * yaw_error,
            -MOVE_YAW_LIMIT,
            MOVE_YAW_LIMIT,
        )
        # Suavizado de la corrección de rumbo: evita latigazos laterales.
        self._move_correction = slew_toward(
            self._move_correction, target_correction, MOVE_CORRECTION_SLEW
        )
        base = self._move_base_action
        correction = self._move_correction
        left = clamp(direction * base - correction, -1.0, 1.0)
        right = clamp(direction * base + correction, -1.0, 1.0)
        info, _terminated, _truncated = self._step([left, right])
        self._track_stall(pose)

        fall = self._check_fall()
        if fall:
            return [fall]
        if info.get("flipped"):
            self._start_brake("volcado", tentative_success=False)
        # Un contacto NO lanza el despegue por si solo: despegarse en cada
        # tick de roce lateral era lo que dejaba a WALL-E vibrando contra una
        # rampa sin avanzar nunca. El detector de atasco (1 s sin 3 cm) es el
        # que decide, y el desvio del punto de mira se encarga del resto.
        return []

    # ------------------------------------------------------------------ #
    # Esquiva de obstáculos con el LiDAR de los pies
    # ------------------------------------------------------------------ #
    def _reset_stall(self, pos: tuple[float, float, float]) -> None:
        """Reinicia el detector de atasco desde la posición actual."""
        self._stall_pos = (float(pos[0]), float(pos[1]))
        self._stall_ticks = 0

    def _track_stall(self, pose: Pose) -> None:
        """Cuenta ticks sin avanzar al menos STALL_MIN_MOVE_M."""
        moved = math.dist(
            (self._stall_pos[0], self._stall_pos[1]),
            (pose.pos[0], pose.pos[1]),
        )
        if moved >= STALL_MIN_MOVE_M:
            self._stall_pos = (float(pose.pos[0]), float(pose.pos[1]))
            self._stall_ticks = 0
            return
        self._stall_ticks += 1

    def _blocking_contact(self, direction: float) -> bool:
        """True si el contacto se opone de verdad a la marcha pedida.

        Tocar una caja con el costado mientras se avanza NO bloquea el avance.
        Antes cualquier contacto lanzaba el despegue: WALL-E se separaba de un
        roce lateral, perdía el rumbo y se quedaba plantado con el frente
        despejado. Sólo cuenta el contacto cuya normal apunta en contra del
        movimiento (el obstáculo está delante).
        """
        try:
            contacts = self.env.contact_info()  # type: ignore[attr-defined]
        except Exception:
            return True  # sin datos: se asume bloqueado (conservador)
        if not contacts:
            return True
        # No se consulta el LiDAR aqui: un contacto con la normal en contra de
        # la marcha ES un bloqueo, aunque el abanico de los pies no vea nada
        # (la rampa baja deja pasar los rayos por debajo y el robot se quedaba
        # empujandola para siempre). El roce lateral da normal perpendicular
        # (dot ~ 0) y no dispara.
        pose = self._pose()
        fwd_x = math.cos(pose.yaw) * direction
        fwd_y = math.sin(pose.yaw) * direction
        for _point, normal in contacts:
            # contactNormalOnB apunta del obstáculo hacia el robot: la marcha
            # bloqueada es la que va en contra de esa normal.
            dot = fwd_x * float(normal[0]) + fwd_y * float(normal[1])
            if dot < -0.35:
                return True
        return False

    def _best_side_gap(self) -> float | None:
        """Ángulo (rad, +izquierda) del hueco lateral más ancho.

        Busca sólo entre 25° y 100° a cada lado del rumbo. `_free_direction()`
        del entorno devuelve el hueco más ancho del anillo completo, que con
        una pared de frente suele estar DETRÁS: girar 120° metía al robot en
        una excursión de cinco metros para volver a la misma recta. Para
        rodear hace falta el mejor hueco lateral, no el mejor absoluto.
        """
        try:
            meters = np.asarray(self.env.lidar_meters, dtype=np.float32)
        except Exception:
            return None
        n = int(meters.size)
        if n == 0:
            return None
        step = 2.0 * math.pi / n
        half_window = max(1, int(round(math.radians(15.0) / step)))
        best_score = -1.0
        best_angle = None
        for k in range(n // 2):
            rel = k * step
            if rel < math.radians(25.0) or rel > math.radians(100.0):
                continue
            for sign in (1.0, -1.0):
                idx = k if sign > 0.0 else (n - k) % n
                score = 0.0
                for w in range(-half_window, half_window + 1):
                    score += float(meters[(idx + w) % n])
                if score > best_score:
                    best_score = score
                    best_angle = sign * rel
        if best_angle is None:
            return None
        return float(best_angle)

    def _front_clearance(self) -> float:
        """Distancia (m) al obstáculo más cercano del cono frontal.

        Usa `front_clearance()` del entorno V3 (cono de ±30° sobre el rumbo
        actual). Con el entorno V1/V2, que no tiene LiDAR, devuelve infinito:
        el controlador se comporta como antes y sólo reacciona al contacto.
        """
        try:
            getter = getattr(self.env, "front_clearance", None)
            if callable(getter):
                return float(getter())
        except Exception:
            pass
        return float("inf")

    def _touching(self) -> bool:
        """True si el chasis toca algo ahora mismo (contactos ya filtrados)."""
        try:
            return bool(self.env.contact_info())  # type: ignore[attr-defined]
        except Exception:
            return False

    def _contact_side(self) -> float:
        """Lado donde está el obstáculo pegado: +1 izquierda, -1 derecha, 0."""
        try:
            contacts = self.env.contact_info()  # type: ignore[attr-defined]
        except Exception:
            return 0.0
        if not contacts:
            return 0.0
        pose = self._pose()
        lateral_x = -math.sin(pose.yaw)
        lateral_y = math.cos(pose.yaw)
        side = 0.0
        for _point, normal in contacts:
            # La normal apunta del obstáculo hacia el robot: su proyección
            # lateral dice de qué lado está la pared.
            side += float(normal[0]) * lateral_x + float(normal[1]) * lateral_y
        if side > 0.05:
            return 1.0
        if side < -0.05:
            return -1.0
        return 0.0

    def _start_avoid(self, clearance: float) -> None:
        """Aparta el punto de mira del obstáculo y deja que el PID rodee.

        Antes esto era un guion ciego de tres fases (retroceder, girar 90°,
        avanzar 1.1 s) que no miraba dónde quedaba el robot al terminar: con
        una rampa al costado lo dejaba cruzado contra ella, sin salida. Ahora
        el rodeo es un desplazamiento lateral acumulativo del objetivo y el
        PID de marcha hace el trabajo, corrigiendo cada tick con el LiDAR.
        """
        exp = self.exp
        if self._avoid_cooldown > 0:
            return
        if self._avoid_attempts >= AVOID_MAX_DETOURS:
            self._start_brake("camino bloqueado", tentative_success=False)
            return
        self._avoid_attempts += 1
        self._avoid_cooldown = int(AVOID_COOLDOWN_S * CONTROL_HZ)
        self._avoid_entry_remaining = (
            float(exp.target_distance or 0.0) if exp is not None else 0.0
        )

        # Sentido del desvío: primero el contacto real (la pared que se está
        # tocando), después el hueco lateral más ancho del LiDAR, y si no hay
        # datos, se alterna. Con un desvío ya acumulado NO se cambia de lado:
        # el robot ya está comprometido con rodear por ahí y alternar lo dejaba
        # oscilando seis centímetros entre dos posiciones.
        sign = 0.0
        side = self._contact_side()
        if side != 0.0:
            sign = -side  # se aparta hacia el lado contrario a la pared
        else:
            gap = self._best_side_gap()
            if gap is not None and abs(math.degrees(gap)) > 20.0:
                sign = 1.0 if gap >= 0.0 else -1.0
        if sign == 0.0:
            sign = self._avoid_sign if self._avoid_sign != 0.0 else 1.0
        if (
            self._avoid_offset_target != 0.0
            and sign != 0.0
            and math.copysign(1.0, sign) != math.copysign(
                1.0, self._avoid_offset_target
            )
        ):
            sign = math.copysign(1.0, self._avoid_offset_target)
        self._avoid_sign = sign

        self._avoid_offset_target = clamp(
            self._avoid_offset_target + sign * AVOID_OFFSET_STEP,
            -AVOID_OFFSET_MAX,
            AVOID_OFFSET_MAX,
        )
        self._reset_slew()
        self._reset_stall(self._pose().pos)

        # Si está trabado de frente, un retroceso corto antes de reanudar. Si
        # sólo roza de costado, retroceder es perder el tiempo y el rumbo.
        if self._blocking_contact(1.0):
            self._avoid_phase = "back"
            self._avoid_left = int(AVOID_BACK_S * CONTROL_HZ)
        print(
            f"[WALL-E] Obstáculo a {clearance:.2f} m: rodeo "
            f"{'izquierda' if sign > 0.0 else 'derecha'} "
            f"(intento {self._avoid_attempts}/{AVOID_MAX_DETOURS}, "
            f"desvío {self._avoid_offset_target:+.2f} m).",
            flush=True,
        )

    def _tick_avoid(self) -> list[str]:
        """Un tick del retroceso del rodeo. Devuelve los mensajes de la orden."""
        if self._avoid_phase == "back":
            self._step([-AVOID_BACK_ACTION, -AVOID_BACK_ACTION])
            self._avoid_left -= 1
            if self._avoid_left > 0:
                return []
            # Si sigue trabado, se alarga el retroceso en vez de girar contra
            # la pared: girar clavado sólo gasta presupuesto.
            if self._still_in_contact() and self._avoid_back_extensions < 2:
                self._avoid_back_extensions += 1
                self._avoid_left = int(
                    UNSTICK_STILL_CONTACT_EXTRA_S * CONTROL_HZ
                )
                return []
            self._avoid_phase = ""
            self._avoid_left = 0
            self._reset_slew()
            return []
        self._avoid_phase = ""
        return []

    def _tick_ppo_move(self) -> list[str]:
        """Conduce la exploración autónoma con la política PPO (sin parar por distancia)."""
        if self.model is None:
            self._start_brake("cerebro PPO no disponible", tentative_success=False)
            return []

        pose = self._pose()
        yaw = pose.yaw

        # Obtener observación (58D en V5: 14 base + 36 LiDAR + 8 resolución)
        observation = self.env.get_observation(self._ppo_goal)
        if self._is_recurrent():
            # RecurrentPPO: mantener el estado oculto LSTM entre pasos.
            action, self._lstm_states = self.model.predict(
                observation,
                state=self._lstm_states,
                episode_start=self._episode_start,
                deterministic=True,
            )
            self._episode_start = np.zeros((1,), dtype=bool)
        else:
            action, _state = self.model.predict(observation, deterministic=True)
        action = np.clip(
            np.asarray(action, dtype=np.float32).reshape(-1), -1.0, 1.0
        )
        if action.shape != (2,):
            self._start_brake("acción PPO inválida", tentative_success=False)
            return []

        # El cerebro decide la velocidad directa (el modelo aprende a esquivar
        # usando el LiDAR de 72 rayos; no hay corrección de rumbo externa).
        left = clamp(float(action[0]), -1.0, 1.0)
        right = clamp(float(action[1]), -1.0, 1.0)

        info, terminated, truncated = self._step([left, right])
        fall = self._check_fall()
        if fall:
            return [fall]
        if info.get("collision"):
            # Al chocar: retroceder girando y elegir un rumbo nuevo. Un
            # checkpoint temprano tiende a empujar la pared si solo se
            # reinicia la LSTM sin maniobra de escape.
            self._start_ppo_recovery("colisión")
            return []
        elif info.get("flipped"):
            self._start_brake("volcado", tentative_success=False)
        elif terminated:
            self._start_brake("episodio terminado", tentative_success=False)
        elif truncated:
            # Exploración continua: reiniciar SOLO el contador de episodio.
            # Si no, truncated quedaría en True en cada paso y la LSTM se
            # resetearía sin parar (el robot se quedaba congelado). No se
            # llama a env.reset() para no teletransportar ni reubicar nada.
            self.env.step_count = 0

        # Watchdog anti-atasco: si en 3 s no se trasladó ni giró, escapar.
        pose = self._pose()
        if self._ppo_watch_pos is None:
            self._ppo_watch_pos = (pose.pos[0], pose.pos[1])
            self._ppo_watch_yaw = pose.yaw
        self._ppo_watch_steps += 1
        if self._ppo_watch_steps >= int(3.0 * CONTROL_HZ):
            moved = math.hypot(
                pose.pos[0] - self._ppo_watch_pos[0],
                pose.pos[1] - self._ppo_watch_pos[1],
            )
            turned = abs(wrap_angle(pose.yaw - self._ppo_watch_yaw))
            if moved < 0.03 and turned < math.radians(10.0):
                self._start_ppo_recovery("atascado")
                return []
            self._ppo_watch_pos = (pose.pos[0], pose.pos[1])
            self._ppo_watch_yaw = pose.yaw
            self._ppo_watch_steps = 0
        return []

    def _start_ppo_recovery(self, reason: str) -> None:
        """Maniobra de escape: retrocede y gira hacia el hueco más amplio.

        La dirección ya no es aleatoria: sale de `_free_direction()` del
        entorno, que devuelve el centro del sector libre más ancho visto por
        el LiDAR. Así WALL-E se aparta hacia donde hay sitio de verdad.
        """
        self.mode = "ppo_recovering"
        self._ppo_recover_left = int(1.3 * CONTROL_HZ)
        free_sin, free_cos = 0.0, 0.0
        if hasattr(self.env, "_free_direction"):
            try:
                free_sin, free_cos = self.env._free_direction()
            except Exception:
                free_sin, free_cos = 0.0, 0.0
        if abs(free_sin) + abs(free_cos) > 0.10:
            # sin > 0 = hueco a la izquierda del frente del robot.
            self._ppo_recover_sign = 1.0 if free_sin > 0.0 else -1.0
        else:
            self._ppo_recover_sign = -self._ppo_recover_sign
        self._reset_lstm()
        print(
            f"[PPO] Recuperación por {reason}: retroceso y giro "
            f"{'izquierda' if self._ppo_recover_sign > 0 else 'derecha'}.",
            flush=True,
        )

    def _tick_ppo_recover(self) -> list[str]:
        sign = self._ppo_recover_sign
        # Retroceso con giro diferencial para despegarse del obstáculo.
        self._step([-0.45 + 0.20 * sign, -0.45 - 0.20 * sign])
        self._ppo_recover_left -= 1
        # Si sigue tocando algo, se alarga la maniobra en vez de rendirse.
        if self._ppo_recover_left <= 0 and self._still_in_contact():
            self._ppo_recover_left = int(0.6 * CONTROL_HZ)
        if self._ppo_recover_left <= 0:
            pose = self._pose()
            # Nuevo rumbo de exploración, como en el reset de entrenamiento.
            self.env.goal_angle = wrap_angle(
                pose.yaw + float(np.random.uniform(-math.pi, math.pi))
            )
            self.mode = "ppo_moving"
            self._reset_lstm()
            self._ppo_watch_pos = (pose.pos[0], pose.pos[1])
            self._ppo_watch_yaw = pose.yaw
            self._ppo_watch_steps = 0
        return []

    def _still_in_contact(self) -> bool:
        """True si el proxy sigue tocando un obstáculo o una pared."""
        try:
            if hasattr(self.env, "_has_collision"):
                return bool(self.env._has_collision())
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------ #
    # Recuperación manual de choques (avanza / retrocede / gira)
    # ------------------------------------------------------------------ #
    def _start_unstick(self, resume_mode: str) -> None:
        """Maniobra de despegue cuando el chasis toca algo.

        Secuencia: separarse en sentido contrario al avance bloqueado y girar
        hacia el sector libre más ancho del LiDAR. Después se retoma la orden
        original desde la posición nueva. Si se agotan los intentos, se frena y
        se reporta el choque como antes.
        """
        exp = self.exp
        if self._unstick_attempts >= UNSTICK_MAX_ATTEMPTS:
            # Sin despegues disponibles: se intenta un rodeo antes de rendirse.
            # Frenar en seco en mitad del pasillo era justo el síntoma.
            clearance = self._front_clearance()
            if (
                clearance <= SAFE_GO_M
                and self._avoid_attempts < AVOID_MAX_DETOURS
            ):
                self._start_avoid(clearance)
                return
            if clearance > SAFE_GO_M:
                # Frente despejado: lo que se toca es de costado y no impide
                # avanzar. Frenar aqui era el "se queda plantado en mitad de
                # la nada" que reporto killywilly. Se reanuda la orden; si
                # vuelve a atascarse, el detector de atasco lo trata.
                self._unstick_attempts = 0
                self.mode = self._unstick_resume
                self._unstick_phase = ""
                self._reset_slew()
                self._reset_stall(self._pose().pos)
                return
            self._start_brake("camino bloqueado", tentative_success=False)
            return

        self._unstick_attempts += 1
        self._recovery_cycles += 1
        if self._recovery_cycles > UNSTICK_MAX_CYCLES:
            # Presupuesto de maniobras agotado: mejor frenar y decirlo que
            # quedarse vibrando contra el mismo obstaculo para siempre.
            self._start_brake("camino bloqueado", tentative_success=False)
            return
        self._unstick_resume = resume_mode
        self.mode = "unsticking"

        # Sentido del despegue: lo contrario de la marcha que se bloqueó.
        drive = -1.0
        if exp is not None and exp.kind == "move":
            drive = -1.0 if float(exp.target_distance or 0.0) >= 0.0 else 1.0
        self._unstick_drive = drive

        # El despegue tambien desplaza el punto de mira: despegarse y volver a
        # apuntar a la misma recta era chocar otra vez contra lo mismo. Se
        # aparta hacia el lado contrario al contacto.
        side = self._contact_side()
        if side == 0.0:
            gap = self._best_side_gap()
            if gap is not None and abs(math.degrees(gap)) > 20.0:
                side = -1.0 if gap >= 0.0 else 1.0
        if side != 0.0:
            self._avoid_offset_target = clamp(
                self._avoid_offset_target - side * AVOID_OFFSET_STEP,
                -AVOID_OFFSET_MAX,
                AVOID_OFFSET_MAX,
            )

        # Giro hacia el hueco lateral real que ve el LiDAR (si lo expone).
        # Si ya hay un desvio comprometido, se gira HACIA ESE LADO: girar al
        # lado contrario dejaba el cuerpo mirando al muro mientras el punto de
        # mira apuntaba al otro, y el PID gastaba el presupuesto en corregir.
        sign = self._unstick_sign
        if self._avoid_offset_target != 0.0:
            sign = math.copysign(1.0, self._avoid_offset_target)
        else:
            gap = self._best_side_gap()
            if gap is not None and abs(math.degrees(gap)) > 20.0:
                sign = 1.0 if gap >= 0.0 else -1.0
            elif hasattr(self.env, "_free_direction"):
                try:
                    free_sin, _free_cos = self.env._free_direction()
                except Exception:
                    free_sin = 0.0
                if abs(free_sin) > 0.10:
                    sign = 1.0 if free_sin > 0.0 else -1.0
                else:
                    sign = -self._unstick_sign
        self._unstick_sign = sign

        self._unstick_phase = "back"
        self._unstick_left = int(UNSTICK_BACK_S * CONTROL_HZ)
        self._unstick_back_extensions = 0
        self._unstick_turn_start_yaw = self._pose().yaw
        # El tiempo de la maniobra no debe comerse el presupuesto de la orden.
        self._timeout_steps += int(
            (UNSTICK_BACK_S + UNSTICK_TURN_S) * CONTROL_HZ
        )
        self._reset_slew()
        print(
            f"[WALL-E] Choque detectado: despego hacia "
            f"{'atrás' if drive < 0 else 'adelante'} y giro a la "
            f"{'izquierda' if sign > 0 else 'derecha'} "
            f"(intento {self._unstick_attempts}/{UNSTICK_MAX_ATTEMPTS}).",
            flush=True,
        )

    def _tick_unstick(self) -> list[str]:
        if self.mode != "unsticking":
            return []
        fall = self._check_fall()
        if fall:
            return [fall]

        if self._unstick_phase == "back":
            drive = self._unstick_drive
            sign = self._unstick_sign
            self._step(
                [
                    clamp(drive * UNSTICK_BACK_ACTION + 0.20 * sign, -1.0, 1.0),
                    clamp(drive * UNSTICK_BACK_ACTION - 0.20 * sign, -1.0, 1.0),
                ]
            )
            self._unstick_left -= 1
            if self._unstick_left > 0:
                return []
            # Si sigue pegado, se alarga el retroceso en vez de girar contra
            # la pared: girar estando clavado sólo gasta el presupuesto.
            if self._still_in_contact() and self._unstick_back_extensions < 2:
                self._unstick_back_extensions += 1
                self._unstick_left = int(
                    UNSTICK_STILL_CONTACT_EXTRA_S * CONTROL_HZ
                )
                return []
            self._unstick_phase = "turn"
            self._unstick_left = int(UNSTICK_TURN_MAX_S * CONTROL_HZ)
            self._unstick_turn_start_yaw = self._pose().yaw
            return []

        if self._unstick_phase == "turn":
            sign = self._unstick_sign
            self._step(
                [-UNSTICK_TURN_ACTION * sign, UNSTICK_TURN_ACTION * sign]
            )
            self._unstick_left -= 1
            # El giro se mide en grados: a 0.55 de acción son ~10°/s, así que
            # 0.65 s giraban 6° y el despegue repetía el mismo choque.
            pose = self._pose()
            turned = (
                wrap_angle(pose.yaw - self._unstick_turn_start_yaw) * sign
            )
            if turned < math.radians(UNSTICK_TURN_DEG):
                if self._unstick_left > 0:
                    return []
            # Si sigue tocando, se alarga el giro en vez de rendirse.
            if self._unstick_left <= 0 and self._still_in_contact():
                self._unstick_left = int(
                    UNSTICK_STILL_CONTACT_EXTRA_S * CONTROL_HZ
                )
            if self._unstick_left > 0 and turned < math.radians(
                UNSTICK_TURN_DEG
            ):
                return []
            return self._resume_after_unstick()

        return self._resume_after_unstick()

    def _resume_after_unstick(self) -> list[str]:
        """Reancla la orden en la pose actual y vuelve al modo que tocaba."""
        exp = self.exp
        self._unstick_phase = ""
        self._unstick_left = 0
        self._reset_slew()
        if exp is None:
            self.mode = "idle"
            return []

        pose = self._pose()
        message = ""
        if exp.kind == "move" and exp.target_distance is not None:
            target = float(exp.target_distance)
            direction = 1.0 if target >= 0.0 else -1.0
            heading_x = math.cos(exp.start_pose.yaw)
            heading_y = math.sin(exp.start_pose.yaw)
            dx = pose.pos[0] - exp.start_pose.pos[0]
            dy = pose.pos[1] - exp.start_pose.pos[1]
            along = (dx * heading_x + dy * heading_y) * direction
            remaining = max(abs(target) - along, 0.0)
            # NO se reancla la orden: el rumbo y el origen del objetivo son
            # los de la orden original. Reanclar al rumbo que dejó el despegue
            # hacía que WALL-E se fuera caminando torcido y agotara el tiempo
            # lejos de la meta. Sólo se pide recuperar el rumbo.
            self._move_base_action = 0.0
            self._move_correction = 0.0
            verb = "avanzar" if direction > 0.0 else "retroceder"
            message = (
                f"Me despegué. Retomo la orden: me queda {verb} "
                f"{remaining:.2f} m."
            )
        elif exp.kind == "turn" and exp.target_angle_deg is not None:
            # El giro se reancla desde el rumbo actual.
            exp.start_pose = pose
            self._turn_correction = 0.0
            message = "Me despegué. Retomo el giro desde este rumbo."

        self.mode = self._unstick_resume
        return [message] if message else []

    def _tick_turn(self) -> list[str]:
        exp = self.exp
        assert exp is not None
        pose = self._pose()
        target_yaw = exp.start_pose.yaw + math.radians(
            float(exp.target_angle_deg or 0.0)
        )
        error = wrap_angle(target_yaw - pose.yaw)

        if exp.steps >= self._timeout_steps:
            self._start_brake("tiempo agotado", tentative_success=False)
            return []
        if abs(error) <= TURN_TOLERANCE_RAD:
            self._start_brake("objetivo alcanzado", tentative_success=True)
            return []
        # Zona muerta: dentro de 0.5° no corregir (evita oscilación/temblor).
        if abs(error) < TURN_DEADZONE_RAD:
            target_correction = 0.0
        else:
            target_correction = clamp(
                TURN_GAIN * error, -TURN_MAX_ACTION, TURN_MAX_ACTION
            )
            if (
                abs(error) > TURN_MIN_ERROR_RAD
                and abs(target_correction) < TURN_MIN_ACTION
            ):
                target_correction = math.copysign(TURN_MIN_ACTION, error)
        # Rampa de giro: la corrección crece y decrece de forma gradual.
        self._turn_correction = slew_toward(
            self._turn_correction, target_correction, TURN_ACCEL_STEP
        )
        correction = self._turn_correction
        left = clamp(-correction, -1.0, 1.0)
        right = clamp(correction, -1.0, 1.0)
        info, _terminated, _truncated = self._step([left, right])

        fall = self._check_fall()
        if fall:
            return [fall]
        if info.get("flipped"):
            self._start_brake("volcado", tentative_success=False)
            return []
        # Un giro es un pivote: rozar una pared mientras se gira no impide
        # girar. Antes cualquier contacto lanzaba el despegue y la orden de 90
        # grados se quedaba en 15 dando tumbos. Solo se despega si el rumbo
        # deja de avanzar de verdad.
        if abs(wrap_angle(pose.yaw - self._turn_stall_yaw)) > math.radians(2.0):
            self._turn_stall_yaw = pose.yaw
            self._turn_stall_ticks = 0
        else:
            self._turn_stall_ticks += 1
            if self._turn_stall_ticks >= int(1.5 * CONTROL_HZ):
                self._turn_stall_ticks = 0
                self._start_unstick("turning")
        return []

    # ------------------------------------------------------------------ #
    # Frenado y resultado
    # ------------------------------------------------------------------ #
    def _start_brake(self, reason: str, tentative_success: bool) -> None:
        if self.mode == "braking":
            return
        self.mode = "braking"
        self._brake_left = BRAKE_TICKS
        self._brake_reason = reason
        self._brake_tentative = tentative_success

    def _finish_after_brake(self) -> list[str]:
        exp = self.exp
        if exp is None:
            self.mode = "idle"
            return []

        exp.end_pose = self._pose()
        exp.finished_at = time.time()
        success = False
        if self._brake_tentative:
            if exp.kind == "move":
                error = exp.error_distance_m()
                success = error is not None and abs(error) <= MOVE_TOLERANCE_M
            elif exp.kind == "turn":
                error = exp.error_angle_deg()
                success = error is not None and abs(error) <= TURN_TOLERANCE_DEG

        if self._brake_reason == "objetivo alcanzado":
            exp.reason = "objetivo alcanzado" if success else "fuera de tolerancia"
        else:
            exp.reason = self._brake_reason

        self.last_experience = exp
        self.last_experience_rated = False
        self.mode = "idle"
        self.exp = None
        self._brake_left = 0
        self._reset_slew()
        exp.success = success
        message = self._result_message(exp, success)
        print(f"[WALL-E] {message}", flush=True)
        messages = [message]
        report_message = self._write_report(exp, success)
        if report_message:
            messages.append(report_message)
        return messages

    def _write_report(
        self,
        exp: Experience,
        automatic_success: bool | None,
        rating: str | None = None,
    ) -> str:
        try:
            md_path, json_path = self.reports.write(
                exp, automatic_success, rating
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[REPORT] ERROR al guardar el reporte: {exc}", flush=True)
            return f"No pude guardar el reporte: {exc}"
        print(
            f"[REPORT] {md_path} | {json_path}",
            flush=True,
        )
        return TestReportWriter.summary(exp, bool(automatic_success))

    def _result_message(self, exp: Experience, success: bool) -> str:
        if exp.kind == "move":
            target = float(exp.target_distance or 0.0)
            actual = exp.distance_actual() or 0.0
            verb = "avancé" if target >= 0 else "retrocedí"
            if success:
                error_cm = abs(actual - target) * 100.0
                return (
                    f"Listo: {verb} {abs(actual):.2f} m "
                    f"(objetivo {abs(target):.2f} m, error "
                    f"{error_cm:.0f} cm). Calificá el resultado con los botones."
                )
            if exp.reason == "colisión":
                return (
                    f"Me choqué contra la pared después de {abs(actual):.2f} m. "
                    "No completé la orden. Calificá el resultado con los botones."
                )
            if exp.reason == "volcado":
                return (
                    "Me volqué. No completé la orden. Calificá el resultado "
                    "con los botones."
                )
            if exp.reason == "detenido por el usuario":
                return (
                    f"Me detuve a los {abs(actual):.2f} m. La orden quedó "
                    "interrumpida. Calificá el resultado con los botones."
                )
            return (
                f"No completé la orden ({exp.reason}). Recorrí "
                f"{abs(actual):.2f} m. Calificá el resultado con los botones."
            )

        target = float(exp.target_angle_deg or 0.0)
        actual = exp.angle_actual_deg() or 0.0
        side = "izquierda" if target >= 0 else "derecha"
        if success:
            error_deg = abs(actual - target)
            return (
                f"Listo: giré {abs(actual):.0f}° a la {side} "
                f"(objetivo {abs(target):.0f}°, error {error_deg:.1f}°). "
                "Calificá el resultado con los botones."
            )
        if exp.reason == "colisión":
            return (
                f"Choqué mientras giraba ({abs(actual):.0f}°). No completé "
                "la orden. Calificá el resultado con los botones."
            )
        if exp.reason == "volcado":
            return (
                "Me volqué mientras giraba. No completé la orden. Calificá "
                "el resultado con los botones."
            )
        if exp.reason == "detenido por el usuario":
            return (
                f"Me detuve después de girar {abs(actual):.0f}°. La orden "
                "quedó interrumpida. Calificá el resultado con los botones."
            )
        return (
            f"No completé el giro ({exp.reason}). Giré {abs(actual):.0f}°. "
            "Calificá el resultado con los botones."
        )

    # ------------------------------------------------------------------ #
    # Feedback RLHF
    # ------------------------------------------------------------------ #
    def rate(self, success: bool) -> list[str]:
        active = self.exp is not None and self.mode in {
            "moving",
            "ppo_moving",
            "turning",
            "braking",
            "recovering",
            "unsticking",
            "settling",
        }
        if active:
            exp = self.exp
            assert exp is not None
            exp.end_pose = self._pose()
            exp.finished_at = time.time()
            exp.reason = (
                "aprobado por el usuario"
                if success
                else "rechazado por el usuario"
            )
            self._step([0.0, 0.0])
            self.mode = "idle"
            self.exp = None
            self._brake_left = 0
            self.last_experience = exp
            self.last_experience_rated = True
        else:
            exp = self.last_experience
            if exp is None:
                return [
                    "Todavía no hay una orden ejecutada para calificar. "
                    "Primero pedime que avance, gire o retroceda."
                ]
            if self.last_experience_rated:
                return [
                    "Ya califiqué la última orden. Enviá una nueva orden "
                    "para seguir."
                ]
            if exp.end_pose is None:
                exp.end_pose = self._pose()
                exp.finished_at = time.time()
            self.last_experience_rated = True

        label = "Experiencia Exitosa" if success else "Fallo"
        saved_word = "guardada" if success else "guardado"
        exp.rating = "Lo hizo bien" if success else "No lo hizo bien"
        paths: tuple[Path, Path] | None = None
        log_error: str | None = None
        try:
            paths = self.logger.save(exp, success)
        except Exception as exc:  # noqa: BLE001
            log_error = str(exc)

        messages: list[str] = []
        if paths is not None:
            messages.append(
                f"{label} {saved_word} en {_display_path(paths[0])} "
                f"y {_display_path(paths[1])}."
            )
            print(
                f"\n[RLHF] {label} {saved_word}: {paths[0]} | {paths[1]}",
                flush=True,
            )
        else:
            messages.append(
                f"No pude guardar el archivo de feedback: {log_error}"
            )
            print(f"[RLHF] ERROR al guardar feedback: {log_error}", flush=True)

        automatic = exp.success if exp.success is not None else success
        report_message = self._write_report(exp, automatic, exp.rating)
        if report_message:
            messages.append(report_message)

        if success:
            messages.append("¡Gracias! Esto sirve para el aprendizaje continuo.")
        else:
            messages.append(
                "Voy a volver a la posición anterior para que puedas "
                "reintentar la orden."
            )
            print(
                "[RLHF] ADVERTENCIA: fallo registrado. En el próximo "
                "entrenamiento ajustá los pesos de la política para reducir "
                f"este error (comando: {exp.command!r}, motivo: {exp.reason}).",
                flush=True,
            )
            self._restore_pose(exp.start_pose)
            self.mode = "idle"
            self.exp = None
            self._brake_left = 0
        return messages

    # ------------------------------------------------------------------ #
    # Estado legible
    # ------------------------------------------------------------------ #
    def _remaining_move_m(self) -> float | None:
        if self.exp is None or self.exp.kind != "move":
            return None
        exp = self.exp
        target = float(exp.target_distance or 0.0)
        direction = 1.0 if target >= 0 else -1.0
        pose = self._pose()
        heading_x = math.cos(exp.start_pose.yaw)
        heading_y = math.sin(exp.start_pose.yaw)
        dx = pose.pos[0] - exp.start_pose.pos[0]
        dy = pose.pos[1] - exp.start_pose.pos[1]
        along = (dx * heading_x + dy * heading_y) * direction
        return max(0.0, abs(target) - along)

    def _remaining_turn_deg(self) -> float | None:
        if self.exp is None or self.exp.kind != "turn":
            return None
        exp = self.exp
        target_yaw = exp.start_pose.yaw + math.radians(
            float(exp.target_angle_deg or 0.0)
        )
        error = wrap_angle(target_yaw - self._pose().yaw)
        return abs(math.degrees(error))

    def status_line(self) -> str:
        pose = self._pose()
        base = (
            f"x={pose.pos[0]:+.2f} m · y={pose.pos[1]:+.2f} m · "
            f"giro={math.degrees(pose.yaw):+.0f}°"
        )
        if self.mode == "moving" and self.exp is not None:
            remaining = self._remaining_move_m()
            direction = "Avanzando" if (self.exp.target_distance or 0) >= 0 else "Retrocediendo"
            if remaining is not None:
                return f"Manual · {direction} · faltan {remaining:.2f} m · {base}"
        if self.mode == "ppo_moving" and self.exp is not None:
            remaining = self._remaining_move_m()
            direction = "Avanzando" if (self.exp.target_distance or 0) >= 0 else "Retrocediendo"
            if remaining is not None:
                return f"PPO · {direction} · faltan {remaining:.2f} m · {base}"
        if self.mode == "turning" and self.exp is not None:
            remaining = self._remaining_turn_deg()
            if remaining is not None:
                return f"Manual · Girando · faltan {remaining:.0f}° · {base}"
        if self.mode == "recovering":
            return f"Recuperándome · up.z={pose.up_z:+.2f} · {base}"
        if self.mode == "settling":
            return f"Estabilizando · up.z={pose.up_z:+.2f} · {base}"
        if self.mode == "braking":
            return f"Frenando · {base}"
        return f"Quieto · modo {self._mode_label()} · {base}"

    def initial_position_message(self) -> str:
        x, y, z = self._pose().display_pos
        return (
            f"Posición inicial: X={_zero_float(x, 2):.2f}, "
            f"Y={_zero_float(y, 2):.2f}, Z={_zero_float(z, 2):.2f}. "
            "Eje X rojo = adelante; eje Y verde = izquierda; Z+ = arriba."
        )

# --------------------------------------------------------------------------- #
# Apariencia: textura -> piezas de color, suelo y cielo
# --------------------------------------------------------------------------- #
def verify_asset_files() -> None:
    missing = [
        path.name
        for path in (VISUAL_OBJ, MATERIAL_MTL, TEXTURE_PNG)
        if not path.exists()
    ]
    if missing:
        print(
            "[WALL-E] Aviso: faltan archivos del modelo visual: "
            + ", ".join(missing),
            flush=True,
        )
        return
    try:
        mtl = MATERIAL_MTL.read_text(encoding="utf-8", errors="replace")
        if "map_Kd" in mtl:
            print(
                f"[WALL-E] Material/Textura verificados: {MATERIAL_MTL.name} "
                f"-> {TEXTURE_PNG.name}",
                flush=True,
            )
    except OSError:
        pass


def _file_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def ensure_colored_parts() -> list[tuple[str, tuple[float, float, float], int]]:
    """Convierte la textura UV en 16 piezas OBJ de colores sólidos.

    OpenGL2 (el renderer estable de esta PC) ignora el color de las texturas.
    Para conservar el aspecto del WALL-E azul, se muestrea material_0.png por
    cada cara usando sus coordenadas UV y se agrupan las caras en 16 colores.
    Las piezas se cachean en walle_color_parts/ para no regenerarlas siempre.
    """
    if not VISUAL_OBJ.exists() or not TEXTURE_PNG.exists():
        return []

    try:
        import trimesh
        from PIL import Image
    except ImportError as exc:
        print(
            "[WALL-E] No se pudieron generar las piezas de color "
            f"({exc}). Se usará el proxy visual simple.",
            flush=True,
        )
        return []

    COLOR_PARTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = COLOR_PARTS_DIR / "manifest.json"
    source_obj = _file_signature(VISUAL_OBJ)
    source_png = _file_signature(TEXTURE_PNG)

    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            valid = (
                manifest.get("version") == COLOR_PART_VERSION
                and manifest.get("clusters") == COLOR_PART_CLUSTERS
                and manifest.get("source_obj") == source_obj
                and manifest.get("source_png") == source_png
            )
            if valid:
                parts: list[tuple[str, tuple[float, float, float], int]] = []
                for item in manifest.get("parts", []):
                    part_path = COLOR_PARTS_DIR / item["file"]
                    if not part_path.exists():
                        valid = False
                        break
                    parts.append(
                        (
                            str(part_path),
                            tuple(float(c) for c in item["color"]),
                            int(item.get("faces", 0)),
                        )
                    )
                if valid and parts:
                    print(
                        f"[WALL-E] Piezas de color en caché: {len(parts)}.",
                        flush=True,
                    )
                    return parts
        except Exception:
            pass

    try:
        mesh = trimesh.load(str(VISUAL_OBJ), force="mesh")
        image = Image.open(TEXTURE_PNG).convert("RGB")
        uv = np.asarray(mesh.visual.uv, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)
        vertices = np.asarray(mesh.vertices, dtype=np.float64)

        face_uv = uv[faces].mean(axis=1)
        u = np.mod(face_uv[:, 0], 1.0)
        v = np.mod(face_uv[:, 1], 1.0)
        xs = np.clip(
            (u * (image.width - 1)).astype(np.int64), 0, image.width - 1
        )
        ys = np.clip(
            ((1.0 - v) * (image.height - 1)).astype(np.int64),
            0,
            image.height - 1,
        )
        colors = (
            np.asarray(image, dtype=np.float32)[ys, xs] / 255.0
        )

        k = COLOR_PART_CLUSTERS
        rng = np.random.default_rng(0)
        centers = colors[rng.choice(len(colors), k, replace=False)].copy()
        labels = np.zeros(len(colors), dtype=np.int64)
        for _ in range(30):
            distances = (
                (colors[:, None, :] - centers[None, :, :]) ** 2
            ).sum(axis=2)
            labels = distances.argmin(axis=1)
            new_centers = centers.copy()
            for index in range(k):
                mask = labels == index
                if mask.any():
                    new_centers[index] = colors[mask].mean(axis=0)
            if np.allclose(new_centers, centers, atol=1e-5):
                centers = new_centers
                break
            centers = new_centers

        palette: list[tuple[float, float, float]] = []
        for color in centers:
            h, s, value = colorsys.rgb_to_hsv(*color)
            if s > 0.10 and value > 0.20:
                s = min(1.0, s * 1.25 + 0.06)
                value = min(1.0, value * 1.06)
            palette.append(colorsys.hsv_to_rgb(h, s, value))

        distances = (
            (colors[:, None, :] - centers[None, :, :]) ** 2
        ).sum(axis=2)
        labels = distances.argmin(axis=1)

        new_parts: list[dict[str, Any]] = []
        written_names: set[str] = set()
        for index in range(k):
            mask = labels == index
            if not mask.any():
                continue
            sub_faces = faces[mask]
            used = np.unique(sub_faces)
            remap = -np.ones(len(vertices), dtype=np.int64)
            remap[used] = np.arange(len(used))
            part_vertices = vertices[used]
            part_faces = remap[sub_faces]
            part_name = f"part_{index:02d}.obj"
            part_path = COLOR_PARTS_DIR / part_name
            with part_path.open("w", encoding="utf-8") as fh:
                for vtx in part_vertices:
                    fh.write(
                        f"v {vtx[0]:.6f} {vtx[1]:.6f} {vtx[2]:.6f}\n"
                    )
                for face in part_faces:
                    fh.write(
                        f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n"
                    )
            written_names.add(part_name)
            new_parts.append(
                {
                    "file": part_name,
                    "color": [round(float(c), 6) for c in palette[index]],
                    "faces": int(mask.sum()),
                }
            )

        for stale in COLOR_PARTS_DIR.glob("part_*.obj"):
            if stale.name not in written_names:
                try:
                    stale.unlink()
                except OSError:
                    pass

        manifest = {
            "version": COLOR_PART_VERSION,
            "clusters": COLOR_PART_CLUSTERS,
            "source_obj": source_obj,
            "source_png": source_png,
            "parts": new_parts,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result = [
            (
                str(COLOR_PARTS_DIR / item["file"]),
                tuple(float(c) for c in item["color"]),
                int(item["faces"]),
            )
            for item in new_parts
        ]
        print(
            f"[WALL-E] Modelo de color generado desde la textura: "
            f"{len(result)} piezas, {sum(p[2] for p in result)} caras.",
            flush=True,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        print(
            f"[WALL-E] No pude generar el modelo de color ({exc}). "
            "Se usará el proxy visual simple.",
            flush=True,
        )
        return []


def build_connect_options(gl3: bool = True) -> str:
    renderer = "--opengl3" if gl3 else "--opengl2"
    return (
        f"{renderer} --width=1000 --height=700 "
        f"--background_color_red={SKY_COLOR[0]:.3f} "
        f"--background_color_green={SKY_COLOR[1]:.3f} "
        f"--background_color_blue={SKY_COLOR[2]:.3f}"
    )


def build_scene(env: WallEEnv) -> None:
    """Estudio minimalista: suelo grafito, cuadricula sutil y paredes mate.

    Estetica tipo Isaac Sim / MuJoCo: fondo oscuro, geometria neutra y sin
    ejes ni carteles que ensucien el viewport.
    """
    arena = int(env.arena_half_size)

    # Aspecto profesional: sin panel de texto default ni ejes de depuracion.
    # COV_ENABLE_RGB_AXES no existe en todas las builds de PyBullet, por eso
    # se resuelve con getattr y se ignora si no esta disponible.
    debug_flags = [
        (getattr(p, "COV_ENABLE_RGB_AXES", None), 0),
        # Las sombras de esta build arrastran su propio panel de depuración en
        # los bordes de la ventana: se dejan apagadas para conservar el
        # viewport limpio, que es la prioridad estética.
        (p.COV_ENABLE_SHADOWS, 0),
        (p.COV_ENABLE_GUI, 0),
        (p.COV_ENABLE_GUI, 0),
    ]
    for flag, value in debug_flags:
        if flag is None:
            continue
        try:
            p.configureDebugVisualizer(flag, value)
        except Exception:
            pass

    # El plano original de pybullet_data tiene una textura checker que en
    # OpenGL2 se ve gris. Lo reemplazamos por una caja visual de estudio y un
    # plano de colision infinito en el mismo lugar.
    try:
        p.removeBody(env.plane)
    except Exception:
        pass
    ground_collision = p.createCollisionShape(p.GEOM_PLANE)
    ground_visual = p.createVisualShape(
        p.GEOM_BOX,
        # El suelo visual cubre solo la arena: mas alla de las paredes el
        # fondo oscuro continua y no aparece un plano infinito iluminado.
        halfExtents=[float(arena), float(arena), 0.01],
        rgbaColor=list(GROUND_COLOR),
        visualFramePosition=[0.0, 0.0, -0.01],
    )
    env.plane = p.createMultiBody(
        baseMass=0,
        baseCollisionShapeIndex=ground_collision,
        baseVisualShapeIndex=ground_visual,
        basePosition=[0.0, 0.0, 0.0],
    )
    p.changeDynamics(env.plane, -1, lateralFriction=1.0)

    # Cuadricula de 1 m; cada 5 m una linea algo mas marcada.
    for index in range(-arena, arena + 1):
        major = index % 5 == 0
        color = GRID_COLOR_MAJOR if major else GRID_COLOR_MINOR
        width = 1.4 if major else 1.0
        p.addUserDebugLine(
            [float(index), -float(arena), 0.006],
            [float(index), float(arena), 0.006],
            lineColorRGB=list(color),
            lineWidth=width,
        )
        p.addUserDebugLine(
            [-float(arena), float(index), 0.006],
            [float(arena), float(index), 0.006],
            lineColorRGB=list(color),
            lineWidth=width,
        )

    # Paleta neutra para todo lo que no es el robot: blanco mate, gris medio
    # y grafito. Las zonas de friccion se excluyen (quedan solo fisicas).
    neutral = [
        (0.88, 0.88, 0.89, 1.0),
        (0.66, 0.66, 0.69, 1.0),
        (0.42, 0.42, 0.45, 1.0),
    ]
    skip = {int(env.robot), int(env.plane)}
    skip.update(int(b) for b in getattr(env, "friction_zone_ids", []))
    palette_index = 0
    for body in range(p.getNumBodies()):
        if body in skip:
            continue
        try:
            p.changeVisualShape(
                body, -1, rgbaColor=list(neutral[palette_index % 3])
            )
            palette_index += 1
        except Exception:
            pass

    # Paredes perimetrales en gris claro mate (nada de cian translucido).
    for wall_id in getattr(env, "wall_ids", []):
        try:
            p.changeVisualShape(wall_id, -1, rgbaColor=list(WALL_COLOR))
        except Exception:
            pass


class WalleVisual:
    """Cuerpo visual de WALL-E que sigue al proxy físico.

    Con `textured=True` se carga el OBJ original con su MTL/PNG: en OpenGL3
    PyBullet aplica la textura real (antes en OpenGL2 se veía en grises).
    Con `textured=False` se usan las 16 piezas de color derivadas de la
    textura, que es el fallback barato para OpenGL2.
    """

    def __init__(
        self,
        env: WallEEnv,
        parts: list[tuple[str, tuple[float, float, float], int]],
        textured: bool = False,
    ) -> None:
        self.env = env
        self.parts = parts
        self.textured = bool(textured)
        self.body_id: int | None = None
        self._build()

    def _build(self) -> None:
        if not self.parts:
            return
        visual_ids: list[int] = []
        if self.textured:
            # Una sola malla con material y textura. rgbaColor blanco = sin
            # tinte: los colores salen del PNG.
            visual_ids.append(
                p.createVisualShape(
                    p.GEOM_MESH,
                    fileName=str(VISUAL_OBJ),
                    meshScale=[1.0, 1.0, 1.0],
                    rgbaColor=[1.0, 1.0, 1.0, 1.0],
                )
            )
        else:
            for path, color, _faces in self.parts:
                visual_ids.append(
                    p.createVisualShape(
                        p.GEOM_MESH,
                        fileName=path,
                        meshScale=[1.0, 1.0, 1.0],
                        rgbaColor=[color[0], color[1], color[2], 1.0],
                    )
                )
        count = len(visual_ids)
        self.body_id = p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=-1,
            baseVisualShapeIndex=-1,
            basePosition=[0.0, 0.0, 0.15],
            # Rotar 180° alrededor de Z para que el frente del modelo visual
            # coincida con la dirección de movimiento del proxy físico (+X).
            baseOrientation=p.getQuaternionFromEuler([0.0, 0.0, math.pi]),
            linkMasses=[0.0] * count,
            linkCollisionShapeIndices=[-1] * count,
            linkVisualShapeIndices=visual_ids,
            linkPositions=[[0.0, 0.0, 0.0]] * count,
            linkOrientations=[[0.0, 0.0, 0.0, 1.0]] * count,
            linkInertialFramePositions=[[0.0, 0.0, 0.0]] * count,
            linkInertialFrameOrientations=[[0.0, 0.0, 0.0, 1.0]] * count,
            linkParentIndices=[0] * count,
            linkJointTypes=[p.JOINT_FIXED] * count,
            linkJointAxis=[[0.0, 0.0, 1.0]] * count,
        )
        self.sync()

    def sync(self) -> None:
        if self.body_id is None:
            return
        pos, quat = p.getBasePositionAndOrientation(self.env.robot)
        # El OBJ original mira hacia -X y está derecho con Z arriba.
        # Un giro de 180° alrededor de Z lo alinea con el frente físico (+X)
        # sin invertir la vertical. (Un giro en Y lo dejaría boca abajo.)
        rot_180 = p.getQuaternionFromEuler([0.0, 0.0, math.pi])
        _, corrected_quat = p.multiplyTransforms(
            [0.0, 0.0, 0.0], quat, [0.0, 0.0, 0.0], rot_180
        )
        p.resetBasePositionAndOrientation(self.body_id, pos, corrected_quat)

    def reset_camera(self) -> None:
        """Vuelve a la vista de estudio (distancia, órbita y objetivo)."""
        pos, _quat = p.getBasePositionAndOrientation(self.env.robot)
        p.resetDebugVisualizerCamera(
            cameraDistance=CAMERA_DISTANCE,
            cameraYaw=CAMERA_YAW,
            cameraPitch=CAMERA_PITCH,
            cameraTargetPosition=[pos[0], pos[1], CAMERA_TARGET_Z],
        )

    def follow_camera(self) -> None:
        # getDebugVisualizerCamera devuelve 12 valores en esta build:
        # 8=yaw, 9=pitch, 10=distancia, 11=target.
        camera = p.getDebugVisualizerCamera()
        distance = float(camera[10])
        yaw = float(camera[8])
        pitch = float(camera[9])
        pos, _quat = p.getBasePositionAndOrientation(self.env.robot)
        p.resetDebugVisualizerCamera(
            cameraDistance=distance,
            cameraYaw=yaw,
            cameraPitch=pitch,
            cameraTargetPosition=[pos[0], pos[1], CAMERA_TARGET_Z],
        )


class WalleHud:
    """HUD flotante sobre WALL-E dentro de la ventana de PyBullet."""

    def __init__(self, env: WallEEnv, controller=None) -> None:
        self.env = env
        self.controller = controller
        self._ids: list[int] = []
        # Rayos del abanico LiDAR: IDs de lineas persistentes (se actualizan
        # con replaceItemUniqueId, sin recrear geometria).
        self._fan_lines: list[int] = []
        self._fan_key: tuple[float, float, float] | None = None
        self._contact_lines: list[int] = []
        self._chunk_draw_counter = 0

    def _remove_lidar_fan(self) -> None:
        """Apaga los rayos del abanico (quedan ocultos, sin recrear nada)."""
        for item in self._fan_lines:
            try:
                p.addUserDebugLine(
                    [0.0, 0.0, -50.0],
                    [0.0, 0.0, -50.0],
                    [0.0, 0.0, 0.0],
                    lineWidth=1.0,
                    lifeTime=0.0,
                    replaceItemUniqueId=item,
                )
            except Exception:
                pass
        self._fan_key = None

    def _update_lidar_fan(self, pos, yaw) -> None:
        """Abanico LiDAR: rayos finos y densos hasta el punto de impacto real.

        Cada rayo con impacto va desde el centro de WALL-E hasta el punto que
        detecto el escaneo. Los rayos sin impacto se colapsan en un punto (no
        se dibujan), asi que el abanico no forma un circulo en el vacio: se
        apoya en paredes y obstaculos. Solo se pinta el arco frontal
        (LIDAR_FAN_ARC_DEG) porque WALL-E mira al frente.

        Se usan 36 lineas de debug persistentes que se actualizan con
        replaceItemUniqueId: no se crean/borran items ni mallas por frame, que
        es lo que hundia los FPS del renderer OpenGL2.
        """
        lidar = getattr(self.env, "lidar_meters", None)
        if lidar is None or len(lidar) == 0:
            self._remove_lidar_fan()
            return
        count = len(lidar)
        max_dist = float(getattr(self.env, "lidar_max_dist", 6.0))
        # A ras de suelo: el abanico se apoya en los pies de WALL-E.
        sensor_z = float(pos[2]) - HOME_BASE_Z + LIDAR_FAN_HEIGHT
        bx = float(pos[0])
        by = float(pos[1])
        # Si el robot no se movio ni giro, el escaneo es identico: no se
        # reescriben las lineas.
        key = (round(bx, 2), round(by, 2), round(yaw, 2))
        if key == self._fan_key and self._fan_lines:
            return
        self._fan_key = key

        half_arc = math.radians(LIDAR_FAN_ARC_DEG) * 0.5
        step = 2.0 * math.pi / count
        hidden = [bx, by, -50.0]

        def make_ray(rel: float, dist: float | None):
            """Segmento (inicio, fin) de un rayo; None = sin impacto."""
            if dist is None:
                return (hidden, hidden)
            ang = yaw + rel
            d = max(0.05, min(dist, max_dist))
            return (
                [bx, by, sensor_z],
                [bx + math.cos(ang) * d, by + math.sin(ang) * d, sensor_z],
            )

        # Muestras reales del escaneo dentro del arco frontal.
        samples: list[tuple[float, float | None]] = []
        for i in range(count):
            dist = float(lidar[i])
            rel = (i * step + math.pi) % (2.0 * math.pi) - math.pi
            if abs(rel) > half_arc:
                continue  # fuera del arco frontal
            samples.append(
                (rel, None if dist >= max_dist - 0.05 else dist)
            )

        # Se interpola un rayo extra entre cada par de muestras: el abanico
        # pasa de 5 a 2.5 grados de separacion y se ve denso, no como lineas
        # sueltas. La interpolacion es lineal porque la escena es plana.
        segments: list[tuple[list[float], list[float]]] = []
        for index, (rel, dist) in enumerate(samples):
            segments.append(make_ray(rel, dist))
            if index + 1 < len(samples):
                rel_next, dist_next = samples[index + 1]
                if dist is not None and dist_next is not None:
                    segments.append(
                        make_ray(
                            (rel + rel_next) * 0.5,
                            (dist + dist_next) * 0.5,
                        )
                    )

        color = LIDAR_FAN_COLOR
        for index, (start, end) in enumerate(segments):
            if index < len(self._fan_lines):
                try:
                    p.addUserDebugLine(
                        start,
                        end,
                        color,
                        lineWidth=LIDAR_FAN_LINE_WIDTH,
                        lifeTime=0.0,
                        replaceItemUniqueId=self._fan_lines[index],
                    )
                except Exception:
                    pass
            else:
                try:
                    item = p.addUserDebugLine(
                        start,
                        end,
                        color,
                        lineWidth=LIDAR_FAN_LINE_WIDTH,
                        lifeTime=0.0,
                    )
                    self._fan_lines.append(item)
                except Exception:
                    pass

    def _update_contact_markers(self, pos) -> None:
        """Marca en naranja el punto exacto donde WALL-E está chocando.

        Sale del centro del robot y termina en el punto de contacto real que
        reporta el motor de física. Así se ve de un vistazo dónde y contra qué
        está empujando, que es lo que necesita para decidir cómo salir.
        """
        contacts = []
        if hasattr(self.env, "contact_info"):
            try:
                contacts = self.env.contact_info()
            except Exception:
                contacts = []
        z = float(pos[2]) - HOME_BASE_Z + LIDAR_FAN_HEIGHT + 0.02
        origin = [float(pos[0]), float(pos[1]), z]
        hidden = [0.0, 0.0, -50.0]
        for index, item in enumerate(self._contact_lines):
            try:
                if index < len(contacts):
                    point, _normal = contacts[index]
                    p.addUserDebugLine(
                        origin,
                        [point[0], point[1], z],
                        CONTACT_MARKER_COLOR,
                        lineWidth=CONTACT_MARKER_WIDTH,
                        lifeTime=0.0,
                        replaceItemUniqueId=item,
                    )
                else:
                    p.addUserDebugLine(
                        hidden,
                        hidden,
                        [0.0, 0.0, 0.0],
                        lineWidth=1.0,
                        lifeTime=0.0,
                        replaceItemUniqueId=item,
                    )
            except Exception:
                pass
        for point, _normal in contacts[len(self._contact_lines) :]:
            try:
                new_item = p.addUserDebugLine(
                    origin,
                    [point[0], point[1], z],
                    CONTACT_MARKER_COLOR,
                    lineWidth=CONTACT_MARKER_WIDTH,
                    lifeTime=0.0,
                )
                self._contact_lines.append(new_item)
            except Exception:
                pass

    def update_fan(self) -> None:
        """Refresca el abanico LiDAR y las marcas de contacto (20 Hz)."""
        try:
            pos, quat = p.getBasePositionAndOrientation(self.env.robot)
            _roll, _pitch, yaw = p.getEulerFromQuaternion(quat)
            self._update_lidar_fan(pos, yaw)
            self._update_contact_markers(pos)
        except Exception:
            pass

    def clear(self) -> None:
        for item in self._ids:
            try:
                p.removeUserDebugItem(item)
            except Exception:
                pass
        self._ids = []

    def update(self) -> None:
        self.clear()
        pos, quat = p.getBasePositionAndOrientation(self.env.robot)
        lin_vel, _ang_vel = p.getBaseVelocity(self.env.robot)
        roll, pitch, yaw = p.getEulerFromQuaternion(quat)
        x, y, z = pos[0], pos[1], pos[2] - HOME_BASE_Z
        speed = math.sqrt(sum(float(v) * float(v) for v in lin_vel))
        up_z = 1.0 - 2.0 * (quat[0] ** 2 + quat[1] ** 2)

        lines = [
            (
                f"X={x:+.2f} m   Y={y:+.2f} m   Z={z:+.2f} m",
                [1.0, 1.0, 1.0],
            ),
            (
                f"Yaw={math.degrees(yaw):+.1f}°   "
                f"Pitch={math.degrees(pitch):+.1f}°   "
                f"Roll={math.degrees(roll):+.1f}°",
                [1.0, 0.85, 0.25],
            ),
            (
                f"Vel lineal={speed:.2f} m/s   "
                f"(vx={lin_vel[0]:+.2f}, vy={lin_vel[1]:+.2f})   "
                f"Up.z={up_z:+.2f}",
                [0.35, 0.95, 1.0],
            ),
            (
                "Origen (0,0,0) · X rojo = adelante · Y verde = izquierda",
                [0.75, 0.95, 0.55],
            ),
        ]
        if SHOW_DEBUG_HUD:
            for index, (text, color) in enumerate(lines):
                item = p.addUserDebugText(
                    text,
                    [pos[0], pos[1], pos[2] + 0.62 - index * 0.075],
                    textColorRGB=color,
                    textSize=0.95,
                    lifeTime=0.0,
                )
                self._ids.append(item)

        # ── Dibujar sensores y chunks si es entorno V3/V4 ──────────────
        if hasattr(self.env, "chunk_mapper"):
            self._draw_v3_visuals(pos, quat, yaw)

    def _draw_v3_visuals(self, pos, quat, yaw) -> None:
        """Visuales V4: HUD + abanico LiDAR translucido + chunks.

        El abanico es una malla unica regenerada por sector angular (velas azules
        que se apoyan en el obstaculo mas cercano), como la imagen de referencia.
        No usa cientos de addUserDebugLine/remove por frame: eso hundia la GUI.
        """
        # ── HUD de estado: "MODO AUTONOMO" / "ESCANEANDO..." ──
        if SHOW_DEBUG_HUD:
            controller = getattr(self, "controller", None)
            autonomous = (
                controller is not None
                and getattr(controller, "mode", "") == "ppo_moving"
            )
            hud_text = "MODO AUTONOMO" if autonomous else "ESCANEANDO..."
            hud_color = [0.0, 1.0, 0.0] if autonomous else [1.0, 0.8, 0.0]
            try:
                item = p.addUserDebugText(
                    hud_text,
                    [pos[0] - 4.0, pos[1] + 4.0, pos[2] + 2.2],
                    textColorRGB=hud_color,
                    textSize=1.6,
                    lifeTime=0.0,
                )
                self._ids.append(item)
            except Exception:
                pass

        # ── Abanico LiDAR: rayos finos (se refresca aparte a 20 Hz) ──
        # Se dibuja en el bucle principal con LIDAR_FAN_UPDATE_TICKS para que
        # siga al robot con fluidez sin depender del ritmo del texto del HUD.

        # ── Chunks 3x3 como puntos (1 sola llamada) cada 4ª actualización ──
        self._chunk_draw_counter = (
            getattr(self, "_chunk_draw_counter", 0) + 1
        )
        if self._chunk_draw_counter % 4 != 0:
            return
        cell_size = self.env.chunk_mapper.cell_size
        cx = int(math.floor(pos[0] / cell_size))
        cy = int(math.floor(pos[1] / cell_size))
        radius_cells = 1
        points = []
        colors = []
        for ix in range(cx - radius_cells, cx + radius_cells + 1):
            for iy in range(cy - radius_cells, cy + radius_cells + 1):
                state = self.env.chunk_mapper.cell_state(ix, iy)
                if state == 0:
                    color = [0.42, 0.42, 0.48]
                elif state == 1:
                    color = [0.30, 0.62, 0.38]
                else:
                    color = [0.62, 0.30, 0.30]
                wx_cell, wy_cell = self.env.chunk_mapper.cell_to_world(ix, iy)
                points.append([wx_cell, wy_cell, 0.03])
                colors.append(color)
        try:
            p.addUserDebugPoints(
                points, colors, pointSize=4.0, lifeTime=2.5
            )
        except Exception:
            pass

# --------------------------------------------------------------------------- #
# Interfaz Tkinter: chat + botones de feedback
# --------------------------------------------------------------------------- #
UI_FONT = "Segoe UI"

UI_BG = "#17130c"
UI_PANEL = "#241c11"
UI_PANEL_2 = "#2f2414"
UI_BORDER = "#5a4527"
UI_TEXT = "#f6efe0"
UI_MUTED = "#b7a98e"
UI_ACCENT = "#f2b705"
UI_USER = "#9ed8ff"
UI_WALLE = "#ffe08a"
UI_OK = "#2f9e44"
UI_OK_ACTIVE = "#40c057"
UI_BAD = "#c92a2a"
UI_BAD_ACTIVE = "#e03131"


class InteractiveWalleApp:
    """Ventana de chat que avanza la simulación desde el hilo de Tk."""

    TICK_INTERVAL_S = 1.0 / CONTROL_HZ

    def __init__(
        self,
        env: WallEEnv,
        controller: WalleController,
        visual: WalleVisual,
        hud: WalleHud | None = None,
    ) -> None:
        if tk is None or tkfont is None:
            raise RuntimeError("Tkinter no está disponible en este Python.")

        self.env = env
        self.controller = controller
        self.visual = visual
        self.hud = hud
        self._closed = False
        self._after_id: str | None = None
        self._ticks = 0
        self._camera_primed = False
        self._last_status = ""
        self._next_tick = time.perf_counter()
        self._fps_t0 = time.perf_counter()
        self._fps_ticks = 0
        self._fps_value = 0.0
        self._last_wall_tick = time.perf_counter()
        self._sim_steps_total = 0
        self._sim_accum = 0.0
        self._sim_elapsed_total = 0.0

        self.root = tk.Tk()
        self.root.title("WALL-E · Hablar con WALL-E")
        self.root.configure(bg=UI_BG)
        self.root.minsize(540, 640)

        width, height = 620, 800
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, screen_w - width - 24)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        # La ventana de PyBullet se abre centrada y puede tapar el chat.
        # Mantenemos el chat encima para que siempre se pueda leer/escribir.
        self.root.attributes("-topmost", True)
        self.root.lift()

        try:
            if ICON_PNG.exists():
                self._icon = tk.PhotoImage(file=str(ICON_PNG))
                self.root.iconphoto(True, self._icon)
        except Exception:
            self._icon = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", lambda _event: self._stop())

        self._append(
            "WALL-E",
            "¡Hola! Soy WALL-E. Escribí una orden o pedí «ayuda». "
            "Estoy quieto hasta que me digas qué hacer.",
            "walle",
        )
        self._append(
            "Sistema",
            "Probá: «avanza 2 metros», «gira 90 grados a la izquierda», "
            "«retrocede 50 cm» o «detente».",
            "system",
        )
        self._append(
            "Sistema",
            self.controller.initial_position_message(),
            "system",
        )
        self._refresh_status(force=True)
        self._update_feedback_buttons()
        self._refresh_mode_ui()
        self.root.after(300, self._focus_entry)
        self._schedule_tick()

    # ------------------------------------------------------------------ #
    # Construcción de la ventana
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(3, weight=1)

        # Cabecera ------------------------------------------------------- #
        header = tk.Frame(self.root, bg=UI_BG, padx=18, pady=14)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = tk.Label(
            header,
            text="WALL-E",
            bg=UI_BG,
            fg=UI_ACCENT,
            font=(UI_FONT, 24, "bold"),
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w")
        self.subtitle = tk.Label(
            header,
            text="Asistente de movimiento · Modo manual (PID)",
            bg=UI_BG,
            fg=UI_MUTED,
            font=(UI_FONT, 9),
            anchor="w",
        )
        self.subtitle.grid(row=1, column=0, sticky="w", pady=(0, 0))

        badge = tk.Label(
            header,
            text="● SIMULACIÓN",
            bg=UI_PANEL_2,
            fg="#8ee6a0",
            font=(UI_FONT, 8, "bold"),
            padx=10,
            pady=4,
        )
        badge.grid(row=0, column=1, sticky="e")

        self.mode_button = tk.Button(
            header,
            text="Modo: Manual (PID)",
            command=self._toggle_mode,
            bg=UI_PANEL_2,
            fg=UI_ACCENT,
            activebackground="#4a3820",
            activeforeground="#ffd43b",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=3,
            font=(UI_FONT, 8, "bold"),
            cursor="hand2",
        )
        self.mode_button.grid(row=1, column=1, sticky="e", pady=(4, 0))

        # Barra de estado ------------------------------------------------ #
        status_frame = tk.Frame(
            self.root, bg=UI_PANEL, padx=18, pady=7, highlightthickness=1,
            highlightbackground=UI_BORDER,
        )
        status_frame.grid(row=1, column=0, sticky="ew", padx=12)
        status_frame.grid_columnconfigure(1, weight=1)
        tk.Label(
            status_frame,
            text="ESTADO",
            bg=UI_PANEL,
            fg=UI_MUTED,
            font=(UI_FONT, 7, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.status_var = tk.StringVar(value="Quieto")
        self.status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            bg=UI_PANEL,
            fg=UI_TEXT,
            font=("Consolas", 9),
            anchor="w",
        )
        self.status_label.grid(row=0, column=1, sticky="ew")

        # Historial de chat ---------------------------------------------- #
        chat_frame = tk.Frame(
            self.root, bg=UI_PANEL, padx=1, pady=1,
            highlightthickness=1, highlightbackground=UI_BORDER,
        )
        chat_frame.grid(
            row=3, column=0, sticky="nsew", padx=12, pady=(12, 8)
        )
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self.chat = tk.Text(
            chat_frame,
            wrap="word",
            state="disabled",
            bg="#120e08",
            fg=UI_TEXT,
            insertbackground=UI_ACCENT,
            selectbackground="#4a3a20",
            relief="flat",
            bd=0,
            padx=14,
            pady=12,
            spacing1=2,
            spacing3=2,
            font=(UI_FONT, 10),
            cursor="arrow",
        )
        self.chat.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(
            chat_frame,
            orient="vertical",
            command=self.chat.yview,
            bg=UI_PANEL_2,
            troughcolor=UI_BG,
            activebackground=UI_BORDER,
            relief="flat",
            bd=0,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scrollbar.set)

        self.chat.tag_configure(
            "meta", foreground=UI_MUTED, font=(UI_FONT, 8, "bold")
        )
        self.chat.tag_configure(
            "user", foreground=UI_USER, font=(UI_FONT, 10)
        )
        self.chat.tag_configure(
            "walle", foreground=UI_WALLE, font=(UI_FONT, 10)
        )
        self.chat.tag_configure(
            "system", foreground=UI_MUTED, font=(UI_FONT, 9, "italic")
        )
        self.chat.tag_configure(
            "success", foreground="#8ee6a0", font=(UI_FONT, 10, "bold")
        )
        self.chat.tag_configure(
            "error", foreground="#ff9a9a", font=(UI_FONT, 10)
        )

        # Entrada de texto ---------------------------------------------- #
        input_frame = tk.Frame(self.root, bg=UI_BG, padx=12)
        input_frame.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry = tk.Entry(
            input_frame,
            bg="#332818",
            fg=UI_TEXT,
            insertbackground=UI_ACCENT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=UI_BORDER,
            highlightcolor=UI_ACCENT,
            font=(UI_FONT, 11),
        )
        self.entry.grid(row=0, column=0, sticky="ew", ipady=10, padx=(0, 8))
        self.entry.bind("<Return>", self._on_entry_return)

        self.send_button = tk.Button(
            input_frame,
            text="Enviar",
            command=self._send,
            bg=UI_ACCENT,
            fg="#241a08",
            activebackground="#ffd43b",
            activeforeground="#241a08",
            disabledforeground="#8c7b58",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=20,
            font=(UI_FONT, 10, "bold"),
            cursor="hand2",
        )
        self.send_button.grid(row=0, column=1, sticky="ns", padx=(0, 8))

        self.stop_button = tk.Button(
            input_frame,
            text="Detener",
            command=self._stop,
            bg=UI_PANEL_2,
            fg="#ffb4a2",
            activebackground="#4a3820",
            activeforeground="#ffd0c6",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            font=(UI_FONT, 10, "bold"),
            cursor="hand2",
        )
        self.stop_button.grid(row=0, column=2, sticky="ns")

        # Feedback ------------------------------------------------------- #
        feedback = tk.Frame(self.root, bg=UI_BG, padx=12)
        feedback.grid(row=5, column=0, sticky="ew", pady=(0, 6))
        feedback.grid_columnconfigure(0, weight=1)
        feedback.grid_columnconfigure(1, weight=1)

        tk.Label(
            feedback,
            text="¿Cómo lo hizo WALL-E?",
            bg=UI_BG,
            fg=UI_MUTED,
            font=(UI_FONT, 9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.good_button = tk.Button(
            feedback,
            text="Lo hizo bien",
            command=lambda: self._rate(True),
            bg=UI_OK,
            fg="#ffffff",
            activebackground=UI_OK_ACTIVE,
            activeforeground="#ffffff",
            disabledforeground="#9bb7a0",
            relief="flat",
            bd=0,
            highlightthickness=0,
            pady=12,
            font=(UI_FONT, 11, "bold"),
            cursor="hand2",
        )
        self.good_button.grid(row=1, column=0, sticky="ew", padx=(0, 5))

        self.bad_button = tk.Button(
            feedback,
            text="No lo hizo bien",
            command=lambda: self._rate(False),
            bg=UI_BAD,
            fg="#ffffff",
            activebackground=UI_BAD_ACTIVE,
            activeforeground="#ffffff",
            disabledforeground="#c4a3a3",
            relief="flat",
            bd=0,
            highlightthickness=0,
            pady=12,
            font=(UI_FONT, 11, "bold"),
            cursor="hand2",
        )
        self.bad_button.grid(row=1, column=1, sticky="ew", padx=(5, 0))

        # Pie ------------------------------------------------------------ #
        tk.Label(
            self.root,
            text="Enter para enviar · Esc para detener · "
            "Cámara: clic izquierdo para rotar · rueda para zoom · "
            "Ctrl + clic para mover · Cerrá esta ventana para salir",
            bg=UI_BG,
            fg="#7d715e",
            font=(UI_FONT, 8),
        ).grid(row=6, column=0, pady=(0, 10))

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #
    def _append(self, prefix: str, text: str, tag: str) -> None:
        self.chat.configure(state="normal")
        if self.chat.index("end-1c") != "1.0":
            self.chat.insert("end", "\n")
        self.chat.insert("end", f"{prefix}  ", ("meta",))
        self.chat.insert("end", f"{text}\n", (tag,))
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _append_replies(
        self, messages: list[str], success: bool | None = None
    ) -> None:
        for message in messages:
            if success is True:
                tag = "success"
            elif success is False:
                tag = "error"
            elif message.startswith("Listo"):
                tag = "success"
            else:
                tag = "walle"
            self._append("WALL-E", message, tag)

    def _on_entry_return(self, _event: tk.Event) -> str:
        self._send()
        return "break"

    def _send(self) -> None:
        text = self.entry.get().strip()
        if not text or self._closed:
            return
        self.entry.delete(0, "end")
        self._append("Vos", text, "user")
        try:
            replies = self.controller.handle_text(text)
        except Exception as exc:  # noqa: BLE001
            self._append("Sistema", f"Error al procesar la orden: {exc}", "error")
            return
        self._append_replies(replies)
        try:
            if parse_command(text).kind == "reset":
                self._reset_camera()
        except Exception:
            pass
        self._refresh_status(force=True)
        self._update_feedback_buttons()
        self._refresh_mode_ui()
        self._focus_entry()

    def _reset_camera(self) -> None:
        """Devuelve la cámara a la vista inicial sobre el origen."""
        p.resetDebugVisualizerCamera(
            cameraDistance=CAMERA_DISTANCE,
            cameraYaw=CAMERA_YAW,
            cameraPitch=CAMERA_PITCH,
            cameraTargetPosition=[0.0, 0.0, CAMERA_TARGET_Z],
        )

    def _stop(self) -> None:
        if self._closed:
            return
        try:
            replies = self.controller.handle_text("detente")
        except Exception as exc:  # noqa: BLE001
            self._append("Sistema", f"No pude detener la simulación: {exc}", "error")
            return
        self._append_replies(replies)
        self._refresh_status(force=True)
        self._update_feedback_buttons()

    def _toggle_mode(self) -> None:
        """Alterna Manual (PID) <-> PPO desde el botón de la cabecera."""
        if self._closed:
            return
        target = "ppo" if self.controller.control_mode == "manual" else "manual"
        try:
            replies = self.controller.set_control_mode(target)
        except Exception as exc:  # noqa: BLE001
            self._append("Sistema", f"No pude cambiar de modo: {exc}", "error")
            return
        self._append_replies(replies)
        self._refresh_mode_ui()
        self._refresh_status(force=True)
        self._update_feedback_buttons()
        self._focus_entry()

    def _refresh_mode_ui(self) -> None:
        ppo = self.controller.control_mode == "ppo"
        self.mode_button.configure(
            text="Modo: PPO" if ppo else "Modo: Manual (PID)",
            fg="#8ee6a0" if ppo else UI_ACCENT,
        )
        self.subtitle.configure(
            text=(
                "Asistente de movimiento · Modo PPO (cerebro físico)"
                if ppo
                else "Asistente de movimiento · Modo manual (PID)"
            )
        )

    def _focus_entry(self) -> None:
        try:
            self.entry.focus_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ #
    # Feedback
    # ------------------------------------------------------------------ #
    def _rate(self, success: bool) -> None:
        if self._closed:
            return
        try:
            replies = self.controller.rate(success)
        except Exception as exc:  # noqa: BLE001
            self._append("Sistema", f"No pude guardar el feedback: {exc}", "error")
            return
        self._append_replies(replies, success=success)
        if self.visual is not None:
            try:
                self.visual.sync()
            except Exception:
                pass
        self._refresh_status(force=True)
        self._update_feedback_buttons()
        self._focus_entry()

    def _update_feedback_buttons(self) -> None:
        controller = self.controller
        active = controller.exp is not None and controller.mode != "idle"
        pending = (
            controller.last_experience is not None
            and not controller.last_experience_rated
        )
        state = tk.NORMAL if (active or pending) else tk.DISABLED
        for button in (self.good_button, self.bad_button):
            if str(button.cget("state")) != state:
                button.configure(state=state)
        self.stop_button.configure(
            state=tk.NORMAL if active else tk.DISABLED
        )

    # ------------------------------------------------------------------ #
    # Bucle de simulación
    # ------------------------------------------------------------------ #
    def _schedule_tick(self) -> None:
        if self._closed:
            return
        self._next_tick += self.TICK_INTERVAL_S
        now = time.perf_counter()
        delay = self._next_tick - now
        # Si el bucle se atrasó más de 3 ticks (p. ej. al cerrar un diálogo o
        # tras una pausa larga), resincronizamos en vez de encadenar ticks
        # inmediatos: así evitamos la "espiral de retraso" que causaba tirones.
        if delay < -3.0 * self.TICK_INTERVAL_S:
            self._next_tick = now + self.TICK_INTERVAL_S
            delay = self.TICK_INTERVAL_S
        elif delay < 0.0:
            self._next_tick = now
            delay = 0.0
        self._after_id = self.root.after(max(1, int(delay * 1000)), self._tick)

    def _tick(self) -> None:
        if self._closed:
            return
        now = time.perf_counter()
        elapsed = now - self._last_wall_tick
        self._last_wall_tick = now
        # La ventana puede renderizar a 20-35 FPS, pero la simulación debe
        # avanzar a 60 Hz. Acumulamos el tiempo real y ejecutamos los pasos
        # enteros que correspondan (máx. 6 para no bloquear la GUI). Sin un
        # mínimo forzado: redondear cada tick por separado dejaba la sim en
        # ~50 Hz porque los ticks rápidos sobre-simulaban y los lentos no.
        self._sim_accum += elapsed
        self._sim_elapsed_total += elapsed
        if self._sim_accum > 0.25:
            self._sim_accum = 0.25
        sim_steps = int(self._sim_accum / self.TICK_INTERVAL_S)
        sim_steps = min(6, sim_steps)
        self._sim_accum -= sim_steps * self.TICK_INTERVAL_S
        self._sim_steps_total += sim_steps
        messages: list[str] = []
        try:
            for _ in range(sim_steps):
                batch = self.controller.tick()
                if batch:
                    messages.extend(batch)
        except Exception as exc:  # noqa: BLE001
            self._after_id = None
            self._append(
                "Sistema",
                f"La simulación se detuvo: {exc}. Cerrá y volvé a abrir.",
                "error",
            )
            self.status_var.set("Simulación detenida")
            self._update_feedback_buttons()
            return

        if self.visual is not None:
            try:
                self.visual.sync()
                # La cámara de estudio se aplica en cuanto la ventana existe:
                # si se pide antes de que el cliente GUI esté vivo, PyBullet
                # la ignora y queda la vista por defecto (muy alejada). Se
                # reaplica durante el primer segundo y luego se suelta el
                # control al usuario.
                if not self._camera_primed:
                    self.visual.reset_camera()
                    if self._ticks == 10:
                        # En esta build, activar las sombras vuelve a mostrar
                        # el panel de depuración; se apaga con la ventana ya
                        # creada para que no queden restos en los bordes.
                        try:
                            p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)
                        except Exception:
                            pass
                    if self._ticks > 60:
                        self._camera_primed = True
                        cam = p.getDebugVisualizerCamera()
                        print(
                            "[WALL-E] Cámara fijada: dist="
                            f"{cam[10]:.2f} yaw={cam[8]:.1f} "
                            f"pitch={cam[9]:.1f}.",
                            flush=True,
                        )
                # Tercera persona: el objetivo sigue a WALL-E sin tocar el
                # zoom ni la órbita que haya elegido el usuario.
                elif CAMERA_FOLLOW and self._ticks % 6 == 0:
                    self.visual.follow_camera()
            except Exception:
                pass

        if self.hud is not None and self._ticks % LIDAR_FAN_UPDATE_TICKS == 0:
            self.hud.update_fan()

        if self.hud is not None and self._ticks % HUD_UPDATE_TICKS == 0:
            try:
                self.hud.update()
            except Exception:
                pass

        if messages:
            self._append_replies(messages)

        self._ticks += 1
        self._fps_ticks += 1
        if self._fps_ticks >= 60:
            now = time.perf_counter()
            elapsed = now - self._fps_t0
            if elapsed > 0.0:
                self._fps_value = self._fps_ticks / elapsed
                avg_steps = self._sim_steps_total / self._fps_ticks
                avg_elapsed = 1000.0 * self._sim_elapsed_total / self._fps_ticks
                print(
                    f"[GUI] {self._fps_value:.1f} FPS "
                    f"(tick medio {1000.0 * elapsed / self._fps_ticks:.1f} ms, "
                    f"dt sim {avg_elapsed:.1f} ms, "
                    f"{avg_steps:.1f} pasos físicos/tick, "
                    f"sim {self._fps_value * avg_steps:.0f} Hz)",
                    flush=True,
                )
            self._fps_t0 = now
            self._fps_ticks = 0
            self._sim_steps_total = 0
            self._sim_elapsed_total = 0.0
        if self._ticks % 6 == 0:
            self._refresh_status()
            self._update_feedback_buttons()
            self._refresh_mode_ui()
        self._schedule_tick()

    def _refresh_status(self, force: bool = False) -> None:
        try:
            text = self.controller.status_line()
        except Exception:
            return
        if self._fps_value > 0.0:
            text = f"{text} · GUI {self._fps_value:.0f} FPS"
        if force or text != self._last_status:
            self._last_status = text
            self.status_var.set(text)

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        self.root.mainloop()

    def _on_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self.hud is not None:
            try:
                self.hud._remove_lidar_fan()
            except Exception:
                pass
        try:
            self.env.close()
        except Exception:
            pass
        if self.hud is not None:
            try:
                self.hud.clear()
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# --------------------------------------------------------------------------- #
# Modos de ejecución
# --------------------------------------------------------------------------- #
def _make_logger(feedback_dir: str | None) -> FeedbackLogger:
    if feedback_dir:
        return FeedbackLogger(Path(feedback_dir).expanduser())
    return FeedbackLogger()


def _make_report_writer(reports_dir: str | None) -> TestReportWriter:
    if reports_dir:
        return TestReportWriter(Path(reports_dir).expanduser())
    return TestReportWriter()


CEREBRO_DIR_DEFAULT = (
    Path.home() / "OneDrive" / "Escritorio" / "Cerebro Wall-E" / "cerebro"
)


def open_robot_link(args: argparse.Namespace):
    """Adaptador hacia el robot real, o None si no se pidió --robot.

    El simulador sigue siendo el cerebro: las velocidades de oruga que calcula
    el controlador salen por WiFi al ESP32. Si el enlace no existe, el
    simulador corre igual.
    """
    if not getattr(args, "robot", None) and not getattr(args, "robot_dry", False):
        return None

    cerebro = Path(os.environ.get("WALLE_CEREBRO_DIR", str(CEREBRO_DIR_DEFAULT)))
    module = cerebro / "sim_link.py"
    if not module.exists():
        print(
            f"[ROBOT] No encuentro {module}. Sigo sólo en simulación.",
            flush=True,
        )
        return None

    if str(cerebro) not in sys.path:
        sys.path.insert(0, str(cerebro))
    try:
        from sim_link import open_wheel_link
    except Exception as exc:  # noqa: BLE001 - el enlace nunca impide arrancar
        print(f"[ROBOT] No pude cargar sim_link: {exc}", flush=True)
        return None

    dry = bool(getattr(args, "robot_dry", False))
    try:
        link = open_wheel_link(
            None if dry else args.robot,
            port=int(getattr(args, "robot_port", 4210)),
            dry_run=dry,
            logger=lambda message: print(f"[ROBOT] {message}", flush=True),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ROBOT] Enlace no disponible: {exc}", flush=True)
        return None

    destino = "sin hardware (dry-run)" if dry else args.robot
    print(f"[ROBOT] Orugas conectadas -> {destino}", flush=True)
    return link


def run_gui(args: argparse.Namespace) -> int:
    if tk is None:
        print(
            "[WALL-E] Tkinter no está disponible. Usá --direct o instalá "
            "Python con soporte para Tk.",
            flush=True,
        )
        return 2

    verify_asset_files()
    _t0 = time.perf_counter()

    def _stage(label: str, start: float) -> float:
        """Marca de tiempo de arranque: dice dónde se van los segundos."""
        now = time.perf_counter()
        print(f"[TIME] {label}: {now - start:.2f}s", flush=True)
        return now

    textured = bool(WALLE_USE_TEXTURE and VISUAL_OBJ.exists())
    if textured:
        # Una sola malla con su material y su PNG: la textura real del
        # personaje. Es también la opción más barata (1 visual en vez de 16).
        parts: list[tuple[str, tuple[float, float, float], int]] = [
            (str(VISUAL_OBJ), (1.0, 1.0, 1.0), 0)
        ]
    else:
        parts = ensure_colored_parts()
        if not parts:
            print(
                "[WALL-E] Sin piezas de color: se verá el proxy simple.",
                flush=True,
            )

    renderer_name = "OpenGL3" if args.opengl3 else "OpenGL2 (fallback)"
    print(f"[WALL-E] Conectando la simulación ({renderer_name})...", flush=True)
    robot_link = open_robot_link(args)
    if args.env == "v3" and WallEEnvV3 is not None:
        env = WallEEnvV3(
            render_mode="human",
            show_proxy_visuals=False,
            stage=3,
            obstacle_count=6,
            connect_options=build_connect_options(gl3=args.opengl3),
            wheel_sink=robot_link,
        )
        env_type = "v3"
    else:
        if robot_link is not None:
            print(
                "[ROBOT] --robot necesita --env v3: enlace de orugas ignorado.",
                flush=True,
            )
            robot_link.close()
            robot_link = None
        env = WallEEnv(
            render_mode="human",
            connect_options=build_connect_options(gl3=args.opengl3),
            show_proxy_visuals=False,
        )
        env_type = "v1"
    # WallEEnv.step llama a render() en modo human, lo que reinicia la
    # cámara en cada paso. Lo desactivamos para que el usuario tenga control
    # total de la cámara con el ratón (orbitar, zoom, paneo).
    env.render = lambda: None
    _t0 = _stage("entorno creado", _t0)

    try:
        build_scene(env)
        _t0 = _stage("escena construida", _t0)
        reset_env_home(env)
        _t0 = _stage("robot en origen", _t0)
        initial = Pose.from_robot(env.robot)
        initial_x, initial_y, initial_z = initial.display_pos
        print(
            f"[WALL-E] Posición inicial: X={_zero_float(initial_x, 2):.2f}, "
            f"Y={_zero_float(initial_y, 2):.2f}, "
            f"Z={_zero_float(initial_z, 2):.2f}, "
            f"Yaw={math.degrees(initial.yaw):+.1f}° (mirando hacia +X).",
            flush=True,
        )
        print(
            "[WALL-E] Vista de estudio: sin ejes ni panel de depuración.",
            flush=True,
        )
        textured = bool(WALLE_USE_TEXTURE and VISUAL_OBJ.exists())
        visual = WalleVisual(env, parts, textured=textured)
        _t0 = _stage("malla del robot creada", _t0)
        if textured:
            print(
                f"[WALL-E] Textura aplicada: {VISUAL_OBJ.name} + "
                f"{MATERIAL_MTL.name} + {TEXTURE_PNG.name} (OpenGL3).",
                flush=True,
            )
        hud = WalleHud(env)
        hud.update()

        # Configurar cámara inicial UNA SOLA VEZ: vista panorámica agradable
        # sobre WALL-E. Después, el usuario controla la cámara libremente con
        # el ratón (clic izquierdo = orbitar, rueda = zoom, Ctrl+clic = paneo).
        p.resetDebugVisualizerCamera(
            cameraDistance=CAMERA_DISTANCE,
            cameraYaw=CAMERA_YAW,
            cameraPitch=CAMERA_PITCH,
            cameraTargetPosition=[0.0, 0.0, CAMERA_TARGET_Z],
        )

        logger = _make_logger(args.feedback_dir)
        reports = _make_report_writer(args.reports_dir)
        controller = WalleController(
            env,
            logger,
            model_path=args.model,
            control_mode="manual",
            report_writer=reports,
        )
        # Darle al HUD acceso al controlador para el texto "MODO AUTONOMO".
        hud.controller = controller
        if args.mode == "ppo":
            for message in controller.set_control_mode("ppo"):
                print(f"[WALL-E] {message}", flush=True)
        print(
            f"[WALL-E] Feedback RLHF: {logger.directory.resolve()}",
            flush=True,
        )
        print(
            f"[WALL-E] Reportes de prueba: {reports.directory.resolve()}",
            flush=True,
        )
        print(
            f"[WALL-E] Modo inicial: {controller.control_mode} "
            f"({controller._mode_label()}).",
            flush=True,
        )
        print(
            "[WALL-E] Ventana de chat lista. La simulación espera órdenes.",
            flush=True,
        )
        app = InteractiveWalleApp(env, controller, visual, hud)
        _t0 = _stage("ventana de chat lista", _t0)
        app.run()
    finally:
        try:
            env.close()
        except Exception:
            pass
    return 0


def run_headless(args: argparse.Namespace) -> int:
    commands = args.command or []
    env = WallEEnv(render_mode=None, show_proxy_visuals=False)
    reset_env_home(env)
    initial = Pose.from_robot(env.robot)
    initial_x, initial_y, initial_z = initial.display_pos
    controller = WalleController(
        env,
        _make_logger(args.feedback_dir),
        model_path=args.model,
        control_mode="manual",
        report_writer=_make_report_writer(args.reports_dir),
    )

    print("[WALL-E] Modo directo (sin GUI).", flush=True)
    print(
        f"[WALL-E] Posición inicial: X={_zero_float(initial_x, 2):.2f}, "
        f"Y={_zero_float(initial_y, 2):.2f}, "
        f"Z={_zero_float(initial_z, 2):.2f}, "
        f"Yaw={math.degrees(initial.yaw):+.1f}° (mirando hacia +X).",
        flush=True,
    )
    if args.mode == "ppo":
        for message in controller.set_control_mode("ppo"):
            print(f"[WALL-E] {message}", flush=True)
    if not commands:
        print(HELP_TEXT, flush=True)
        print(f"Estado: {controller.status_line()}", flush=True)
        env.close()
        return 0

    max_ticks = int((COMMAND_TIMEOUT_S + 15.0) * CONTROL_HZ)
    try:
        for index, command in enumerate(commands, start=1):
            print(f"\n[Comando {index}] {command}", flush=True)
            for message in controller.handle_text(command):
                print(f"  WALL-E: {message}", flush=True)

            ticks = 0
            while controller.mode != "idle":
                for message in controller.tick():
                    print(f"  WALL-E: {message}", flush=True)
                ticks += 1
                if ticks > max_ticks:
                    print("  [WALL-E] Guard de seguridad: demasiados pasos.", flush=True)
                    controller.mode = "idle"
                    controller.exp = None
                    break

            exp = controller.last_experience
            if exp is not None and exp.end_pose is not None:
                actual = exp.distance_actual()
                angle = exp.angle_actual_deg()
                if actual is not None:
                    print(
                        f"  Resultado: {actual:+.3f} m | error "
                        f"{(exp.error_distance_m() or 0.0):+.3f} m | "
                        f"{exp.reason}",
                        flush=True,
                    )
                if angle is not None:
                    print(
                        f"  Resultado: {angle:+.2f}° | error "
                        f"{(exp.error_angle_deg() or 0.0):+.2f}° | "
                        f"{exp.reason}",
                        flush=True,
                    )

            if args.feedback != "none":
                success = args.feedback == "good"
                for message in controller.rate(success):
                    print(f"  RLHF: {message}", flush=True)

        print(f"\nEstado final: {controller.status_line()}", flush=True)
    finally:
        env.close()
    return 0


def _raise_process_priority() -> None:
    """Sube la prioridad del simulador para que no se congele.

    Si otro proceso (por ejemplo un entrenamiento de PyBullet) satura la CPU,
    la creación de la ventana OpenGL se queda esperando y el chat marca "no
    responde". Con prioridad HIGH el simulador siempre gana la CPU.
    """
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # 0x00000080 = HIGH_PRIORITY_CLASS
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00000080)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WALL-E Fase 3: chat en español, simulación manual y RLHF."
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Sin ventana de PyBullet ni Tkinter (para pruebas)",
    )
    parser.add_argument(
        "--command",
        action="append",
        default=None,
        help="Orden a ejecutar en modo directo (se puede repetir)",
    )
    parser.add_argument(
        "--feedback",
        choices=("none", "good", "bad"),
        default="none",
        help="Calificación automática en modo directo (para probar el RLHF)",
    )
    parser.add_argument(
        "--feedback-dir",
        default=None,
        help="Carpeta alternativa para CSV/JSONL de feedback",
    )
    parser.add_argument(
        "--reports-dir",
        default=None,
        help="Carpeta alternativa para los reportes .md/.json (por defecto: reports/)",
    )
    parser.add_argument(
        "--mode",
        choices=("manual", "ppo"),
        default="manual",
        help="Controlador inicial: PID manual o cerebro PPO (por defecto: manual)",
    )
    parser.add_argument(
        "--model",
        default=str(PPO_MODEL),
        help="Ruta del modelo PPO para --mode ppo (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--opengl2",
        dest="opengl3",
        action="store_false",
        default=True,
        help="Usar el fallback OpenGL2 (por defecto: OpenGL3)",
    )
    parser.add_argument(
        "--env",
        choices=("v1", "v3"),
        default="v1",
        help="Entorno de simulación: v1 (estándar) o v3 (explorador con sensores y chunks)",
    )
    parser.add_argument(
        "--robot",
        default=None,
        metavar="IP",
        help="Mandar las orugas a un robot real via el ESP32 (ej: 192.168.1.50)",
    )
    parser.add_argument(
        "--robot-port",
        type=int,
        default=4210,
        help="Puerto UDP del ESP32 (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--robot-dry",
        action="store_true",
        help="Probar el enlace de orugas sin hardware: guarda el historial",
    )
    args = parser.parse_args(argv)

    if args.feedback != "none" and not args.direct:
        parser.error("--feedback solo se puede usar junto con --direct")

    if args.direct:
        return run_headless(args)
    _raise_process_priority()
    return run_gui(args)


if __name__ == "__main__":
    raise SystemExit(main())


