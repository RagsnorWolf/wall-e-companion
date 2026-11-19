"""
WALL-E · Fase 2 V2 — Entorno lento y estable (14D)

Objetivo: entrenar un cerebro motor para el WALL-E físico de madera y cartón
(~4.4 kg, 35×30×28 cm, centro de gravedad alto). La prioridad es la estabilidad
y la suavidad, no la velocidad. Es un "tanque lento y seguro".

Diferencias principales con la V1 (`walle_env.py`):

- Observación de 14 dimensiones:
    [x, y, qx, qy, qz, qw, vx, vy, vz, wx, wy, wz,
     goal, goal_bearing]

  `goal` es +1 (avanzar), -1 (retroceder) o 0 (solo girar). Sin este signo
  la política no puede distinguir avanzar de retroceder, porque ambas
  situaciones comparten el mismo rumbo. `goal_bearing` es el ángulo objetivo
  relativo al frente actual: `wrap(goal_angle - yaw)` en [-π, π]. Es
  egocéntrico y evita que la red tenga que calcular la diferencia a mano.
  La recompensa de giro usa sin/cos del error de rumbo.
- Acción 2D: [oruga_izquierda, oruga_derecha] en [-1, 1].
- `max_wheel_speed = 5.0 rad/s` y `max_force = 1.6 N·m`. Con rueda de 0.09 m
  eso da 0.45 m/s de velocidad lineal y par suficiente para no patinar al
  empujar una caja: antes (2.5 rad/s y 0.5 N·m) el robot se arrastraba a
  0.05 m/s bajo carga y parecía que "se frenaba solo".
- El robot siempre arranca en el origen (x=0, y=0), con yaw aleatorio 0–360°.
  La base física queda a z=0.15 para no atravesar el piso; la Z visible es 0.00.
- Masa total aleatoria entre 3.0 y 6.0 kg por episodio.
- 5 cajas estáticas de distintos tamaños distribuidas por la arena.
- Castigo por inclinación (pitch/roll) y terminación si supera 15°.
- Castigo por brusquedad (jerkiness) entre acciones consecutivas.
- Castigo por colisión con paredes o cajas: -10 y fin del episodio.
- Recompensa de avance relativa al frente del robot.
- Recompensa por reducir el error de rumbo hacia `goal_angle`.
- Currículum de 3 etapas (avance/retroceso, giros, combinado).

La V1 no se toca: este archivo es independiente y se usa desde
`train_walle_v2.py` / `evaluate_walle_v2.py`.

Uso rápido:
    python walle_env_v2.py --direct
    python walle_env_v2.py --stage 3
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
import pybullet as p
import pybullet_data


def wrap_angle(angle: float) -> float:
    """Normaliza un ángulo a [-pi, pi]."""
    return (float(angle) + math.pi) % (2.0 * math.pi) - math.pi


class WallEEnvV2(gym.Env):
    """Entorno 14D para el cerebro motor lento y estable de WALL-E."""

    metadata = {"render_modes": ["human"], "render_fps": 60}

    STAGE_ADVANCE = 1
    STAGE_TURN = 2
    STAGE_COMBINED = 3

    # Altura de la base para que las ruedas apoyen sin atravesar el piso.
    BASE_Z = 0.15
    # Caja de colisión del robot físico (largo, ancho, alto).
    # El chasis visual mide 35×30×28 cm, pero el hitbox solicitado es de
    # 25–30 cm: usamos 30×30×28 cm y un radio envolvente de 25 cm.
    HITBOX_SIZE = (0.30, 0.30, 0.28)
    HITBOX_RADIUS = 0.25

    def __init__(
        self,
        render_mode: str | None = None,
        stage: int = 1,
        max_episode_steps: int | None = None,
        max_wheel_speed: float = 5.0,
        max_force: float = 1.6,
        # Destino opcional de las velocidades de oruga, en rad/s. Con un
        # adaptador de sim_link.py el simulador maneja el robot real.
        # None = sólo simulación.
        wheel_sink: Any = None,
        arena_half_size: float = 20.0,
        visual_mesh_path: str | None = None,
        show_proxy_visuals: bool = True,
        # --- Randomización de masa (madera/cartón) -----------------------
        randomize_mass: bool = True,
        total_mass_range: tuple[float, float] = (3.0, 6.0),
        wheel_mass: float = 0.45,
        wheel_friction_range: tuple[float, float] = (1.6, 2.1),
        # --- Obstáculos ---------------------------------------------------
        obstacle_count: int = 5,
        stage12_min_obstacle_distance: float = 8.0,
        stage3_min_obstacle_distance: float = 2.5,
        obstacle_max_distance: float = 12.0,
        obstacle_min_separation: float = 1.5,
        # --- Seguridad / estabilidad -------------------------------------
        tilt_limit_deg: float = 15.0,
        tilt_grace_steps: int = 3,
        # --- Recompensas --------------------------------------------------
        forward_reward_scale: float = 20.0,
        heading_reward_scale: float = 20.0,
        heading_error_penalty: float = 0.02,
        heading_success_deg: float = 5.0,
        heading_success_steps: int = 10,
        heading_success_bonus: float = 20.0,
        jerk_penalty: float = 0.25,
        jerk_penalty_cap: float = 1.0,
        action_smoothing: float = 0.7,
        tilt_penalty: float = 5.0,
        time_penalty: float = 0.01,
        crash_penalty: float = 10.0,
        flip_penalty: float = 10.0,
        action_magnitude_penalty: float = 0.002,
        yaw_rate_penalty: float = 0.05,
        stage1_heading_penalty: float = 0.05,
        stage1_yaw_rate_penalty: float = 0.2,
        stage2_forward_penalty: float = 0.5,
        seed: int | None = None,
        # Opciones de conexion para el renderer GUI (p. ej. color de fondo).
        connect_options: str | None = None,
        # Si es False, chocar NO termina el episodio: el robot debe aprender a
        # retroceder y salir del obstaculo. V4 (WallEEnvV3) lo desactiva.
        collision_terminates: bool = True,
    ) -> None:
        super().__init__()

        self.render_mode = render_mode
        self.max_wheel_speed = float(max_wheel_speed)
        self.wheel_sink = wheel_sink
        self.max_force = float(max_force)
        self.arena_half_size = float(arena_half_size)
        self.visual_mesh_path = (
            str(Path(visual_mesh_path).resolve()) if visual_mesh_path else None
        )
        self.show_proxy_visuals = bool(show_proxy_visuals)
        self.collision_terminates = bool(collision_terminates)

        self.randomize_mass = bool(randomize_mass)
        self.total_mass_range = tuple(float(v) for v in total_mass_range)
        self.wheel_mass = float(wheel_mass)
        self.wheel_friction_range = tuple(float(v) for v in wheel_friction_range)

        self.obstacle_count = max(0, int(obstacle_count))
        self.stage12_min_obstacle_distance = float(
            stage12_min_obstacle_distance
        )
        self.stage3_min_obstacle_distance = float(
            stage3_min_obstacle_distance
        )
        self.obstacle_max_distance = float(obstacle_max_distance)
        self.obstacle_min_separation = float(obstacle_min_separation)

        self.tilt_limit_deg = float(tilt_limit_deg)
        self.tilt_grace_steps = max(1, int(tilt_grace_steps))

        self.forward_reward_scale = float(forward_reward_scale)
        self.heading_reward_scale = float(heading_reward_scale)
        self.heading_error_penalty = float(heading_error_penalty)
        self.heading_success_deg = float(heading_success_deg)
        self.heading_success_steps = max(1, int(heading_success_steps))
        self.heading_success_bonus = float(heading_success_bonus)
        self.jerk_penalty = float(jerk_penalty)
        self.jerk_penalty_cap = float(jerk_penalty_cap)
        self.action_smoothing = float(
            np.clip(action_smoothing, 0.0, 0.95)
        )
        self.tilt_penalty = float(tilt_penalty)
        self.time_penalty = float(time_penalty)
        self.crash_penalty = float(crash_penalty)
        self.flip_penalty = float(flip_penalty)
        self.action_magnitude_penalty = float(action_magnitude_penalty)
        self.yaw_rate_penalty = float(yaw_rate_penalty)
        self.stage1_heading_penalty = float(stage1_heading_penalty)
        self.stage1_yaw_rate_penalty = float(stage1_yaw_rate_penalty)
        self.stage2_forward_penalty = float(stage2_forward_penalty)

        self._max_episode_steps_override = (
            int(max_episode_steps) if max_episode_steps is not None else None
        )
        self._init_rng = np.random.default_rng(seed)
        self.training = True

        # Estado del episodio.
        self.stage = int(stage)
        self.max_episode_steps = 1000
        self.goal = 1.0
        self.goal_angle = 0.0
        # Pose inicial real del episodio (para autoconocimiento y chunks).
        self.initial_position = np.array(
            [0.0, 0.0, 0.0], dtype=np.float64
        )
        self.initial_quaternion = np.array(
            [0.0, 0.0, 0.0, 1.0], dtype=np.float64
        )
        self.initial_yaw = 0.0
        self.prev_action = np.zeros(2, dtype=np.float32)
        self.prev_applied_action = np.zeros(2, dtype=np.float32)
        self.prev_heading_error = 0.0
        self.heading_success_counter = 0
        self.tilt_counter = 0
        self.step_count = 0
        self.prev_pos = np.zeros(3, dtype=np.float64)
        self.total_forward = 0.0
        self.total_forward_body = 0.0
        self.current_total_mass = 0.0
        self.obstacle_positions: list[tuple[float, float]] = []

        # Física: 240 Hz internos, 4 subpasos = 60 Hz de control.
        self.physics_hz = 240.0
        self.substeps = 4
        self.dt = self.substeps / self.physics_hz

        # Espacios Gymnasium.
        self.action_space = gym.spaces.Box(
            low=-1.0, high=1.0, shape=(2,), dtype=np.float32
        )

        obs_low = np.array(
            [
                -self.arena_half_size,
                -self.arena_half_size,
                -1.0,
                -1.0,
                -1.0,
                -1.0,
                -10.0,
                -10.0,
                -10.0,
                -20.0,
                -20.0,
                -20.0,
                -1.0,
                -math.pi,
            ],
            dtype=np.float32,
        )
        obs_high = -obs_low
        self.observation_space = gym.spaces.Box(
            low=obs_low, high=obs_high, dtype=np.float32
        )

        # Conexión PyBullet.
        if self.render_mode == "human":
            options = (
                connect_options if connect_options is not None else "--opengl2"
            )
            self.client_id = p.connect(p.GUI, options=options)
        else:
            self.client_id = p.connect(p.DIRECT)
        if self.client_id < 0:
            raise RuntimeError(
                "No se pudo conectar a PyBullet. Verificá la instalación."
            )

        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0.0, 0.0, -9.81)
        p.setTimeStep(1.0 / self.physics_hz)
        p.setPhysicsEngineParameter(
            numSolverIterations=20,
            numSubSteps=1,
            fixedTimeStep=1.0 / self.physics_hz,
            contactERP=0.2,
            frictionERP=0.2,
        )

        if self.render_mode == "human":
            p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)

        self._build_world()
        self._build_walle()
        self._build_obstacles()
        self.set_stage(self.stage)

        self.start_pos = np.array(
            [0.0, 0.0, self.BASE_Z], dtype=np.float64
        )
        self.start_orn = p.getQuaternionFromEuler([0.0, 0.0, 0.0])

        self.reset(seed=seed)

    # ------------------------------------------------------------------ #
    # Construcción del mundo
    # ------------------------------------------------------------------ #
    def _build_world(self) -> None:
        self.plane = p.loadURDF("plane.urdf")
        p.changeDynamics(self.plane, -1, lateralFriction=1.0)

        half = self.arena_half_size
        wall_half_height = 0.6
        wall_thickness = 0.25
        wall_color = [0.64, 0.64, 0.67, 1.0]
        self.wall_ids: list[int] = []

        def add_wall(half_extents: list[float], position: list[float]) -> None:
            collision = p.createCollisionShape(
                p.GEOM_BOX, halfExtents=half_extents
            )
            visual = p.createVisualShape(
                p.GEOM_BOX,
                halfExtents=half_extents,
                rgbaColor=wall_color,
            )
            wall_id = p.createMultiBody(
                baseMass=0.0,
                baseCollisionShapeIndex=collision,
                baseVisualShapeIndex=visual,
                basePosition=position,
            )
            self.wall_ids.append(wall_id)

        add_wall(
            [wall_thickness, half, wall_half_height],
            [half, 0.0, wall_half_height],
        )
        add_wall(
            [wall_thickness, half, wall_half_height],
            [-half, 0.0, wall_half_height],
        )
        add_wall(
            [half, wall_thickness, wall_half_height],
            [0.0, half, wall_half_height],
        )
        add_wall(
            [half, wall_thickness, wall_half_height],
            [0.0, -half, wall_half_height],
        )

    # ------------------------------------------------------------------ #
    # Robot: chasis + dos orugas
    # ------------------------------------------------------------------ #
    def _build_walle(self) -> None:
        wheel_radius = 0.09
        wheel_width = 0.08

        # Dimensiones del robot físico: 35 × 30 × 28 cm.
        chassis_half = [0.175, 0.15, 0.14]
        base_collision = p.createCollisionShape(
            p.GEOM_BOX, halfExtents=chassis_half
        )

        if not self.show_proxy_visuals:
            # Proxy invisible de verdad: una caja visual de 0.2 mm. Con
            # visualShapeIndex=-1 PyBullet dibuja la forma de colisión con
            # colores por defecto, y con alpha 0 OpenGL3 la pinta negra.
            base_visual = p.createVisualShape(
                p.GEOM_BOX,
                halfExtents=[0.0001, 0.0001, 0.0001],
                rgbaColor=[0.0, 0.0, 0.0, 0.0],
            )
        elif self.visual_mesh_path:
            base_visual = p.createVisualShape(
                p.GEOM_MESH,
                fileName=self.visual_mesh_path,
                meshScale=[1.0, 1.0, 1.0],
                rgbaColor=[1.0, 1.0, 1.0, 1.0],
            )
        else:
            base_visual = p.createVisualShape(
                p.GEOM_BOX,
                halfExtents=chassis_half,
                rgbaColor=[0.85, 0.65, 0.20, 1.0],
            )

        link_orn_shape = p.getQuaternionFromEuler([math.pi / 2.0, 0.0, 0.0])
        wheel_collision = p.createCollisionShape(
            p.GEOM_CYLINDER,
            radius=wheel_radius,
            height=wheel_width,
            collisionFrameOrientation=link_orn_shape,
        )
        if self.show_proxy_visuals:
            wheel_visual = p.createVisualShape(
                p.GEOM_CYLINDER,
                radius=wheel_radius,
                length=wheel_width,
                rgbaColor=[0.22, 0.22, 0.24, 1.0],
                visualFrameOrientation=link_orn_shape,
            )
        else:
            wheel_visual = p.createVisualShape(
                p.GEOM_BOX,
                halfExtents=[0.0001, 0.0001, 0.0001],
                rgbaColor=[0.0, 0.0, 0.0, 0.0],
            )

        identity_orn = [0.0, 0.0, 0.0, 1.0]
        self.robot = p.createMultiBody(
            baseMass=3.5,
            baseCollisionShapeIndex=base_collision,
            baseVisualShapeIndex=base_visual,
            basePosition=[0.0, 0.0, self.BASE_Z],
            baseOrientation=[0.0, 0.0, 0.0, 1.0],
            linkMasses=[self.wheel_mass, self.wheel_mass],
            linkCollisionShapeIndices=[wheel_collision, wheel_collision],
            linkVisualShapeIndices=[wheel_visual, wheel_visual],
            linkPositions=[
                [0.0, 0.20, -0.06],
                [0.0, -0.20, -0.06],
            ],
            linkOrientations=[identity_orn, identity_orn],
            linkInertialFramePositions=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            linkInertialFrameOrientations=[identity_orn, identity_orn],
            linkParentIndices=[0, 0],
            linkJointTypes=[p.JOINT_REVOLUTE, p.JOINT_REVOLUTE],
            linkJointAxis=[[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        )

        for wheel_index in (0, 1):
            p.changeDynamics(
                self.robot,
                wheel_index,
                lateralFriction=1.8,
                # Sin fricción de spinning: con 0.05 el motor de 0.5 N·m no
                # podía vencer la resistencia al giro en el lugar.
                spinningFriction=0.0,
                rollingFriction=0.001,
                restitution=0.0,
            )
        p.changeDynamics(
            self.robot,
            -1,
            lateralFriction=0.4,
            restitution=0.0,
        )

        self.nominal_base_mass = 3.5
        self.nominal_wheel_mass = self.wheel_mass
        self.nominal_wheel_friction = 1.8
        self.nominal_base_friction = 0.4

    # ------------------------------------------------------------------ #
    # Obstáculos
    # ------------------------------------------------------------------ #
    def _build_obstacles(self) -> None:
        self.obstacle_ids: list[int] = []
        self.obstacle_half_sizes: list[list[float]] = []
        self.obstacle_positions = []

        for index in range(self.obstacle_count):
            hx = float(self._init_rng.uniform(0.20, 0.60))
            hy = float(self._init_rng.uniform(0.20, 0.60))
            hz = float(self._init_rng.uniform(0.15, 0.60))
            half_extents = [hx, hy, hz]
            color = [
                float(self._init_rng.uniform(0.35, 0.85)),
                float(self._init_rng.uniform(0.30, 0.80)),
                float(self._init_rng.uniform(0.25, 0.75)),
                1.0,
            ]
            collision = p.createCollisionShape(
                p.GEOM_BOX, halfExtents=half_extents
            )
            visual = p.createVisualShape(
                p.GEOM_BOX, halfExtents=half_extents, rgbaColor=color
            )
            body = p.createMultiBody(
                baseMass=0.0,
                baseCollisionShapeIndex=collision,
                baseVisualShapeIndex=visual,
                basePosition=[0.0, 12.0 + index * 2.0, hz],
            )
            p.changeDynamics(
                body,
                -1,
                lateralFriction=0.9,
                restitution=0.0,
            )
            self.obstacle_ids.append(body)
            self.obstacle_half_sizes.append(half_extents)

    def _place_obstacles(self) -> None:
        """Reparte las 5 cajas lejos del robot y entre sí."""
        if not self.obstacle_ids:
            return

        min_distance = (
            self.stage12_min_obstacle_distance
            if self.stage in (self.STAGE_ADVANCE, self.STAGE_TURN)
            else self.stage3_min_obstacle_distance
        )
        max_distance = max(
            min_distance + 0.5,
            min(
                self.obstacle_max_distance,
                self.arena_half_size - 2.0,
            ),
        )

        positions: list[tuple[float, float]] = []
        for index, body in enumerate(self.obstacle_ids):
            chosen = None
            for _attempt in range(120):
                angle = float(self.np_random.uniform(0.0, 2.0 * math.pi))
                radius = float(
                    self.np_random.uniform(min_distance, max_distance)
                )
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                if all(
                    math.hypot(x - px, y - py)
                    >= self.obstacle_min_separation
                    for px, py in positions
                ):
                    chosen = (x, y)
                    break
            if chosen is None:
                chosen = (
                    float(self.np_random.uniform(-max_distance, max_distance)),
                    float(self.np_random.uniform(-max_distance, max_distance)),
                )
            positions.append(chosen)
            half_extents = self.obstacle_half_sizes[index]
            p.resetBasePositionAndOrientation(
                body,
                [chosen[0], chosen[1], half_extents[2]],
                [0.0, 0.0, 0.0, 1.0],
            )

        self.obstacle_positions = positions

    # ------------------------------------------------------------------ #
    # Randomización de masa
    # ------------------------------------------------------------------ #
    def _apply_mass_randomization(self) -> None:
        if self.randomize_mass:
            total_mass = float(
                self.np_random.uniform(*self.total_mass_range)
            )
            base_mass = max(1.5, total_mass - 2.0 * self.wheel_mass)
            self.current_total_mass = base_mass + 2.0 * self.wheel_mass
        else:
            base_mass = self.nominal_base_mass
            self.current_total_mass = (
                self.nominal_base_mass + 2.0 * self.wheel_mass
            )

        p.changeDynamics(self.robot, -1, mass=float(base_mass))

        friction = float(
            self.np_random.uniform(*self.wheel_friction_range)
        )
        for wheel_index in (0, 1):
            p.changeDynamics(
                self.robot,
                wheel_index,
                mass=self.wheel_mass,
                lateralFriction=friction,
            )

    # ------------------------------------------------------------------ #
    # Configuración de etapa
    # ------------------------------------------------------------------ #
    def set_stage(self, stage: int) -> None:
        stage = int(stage)
        if stage not in (
            self.STAGE_ADVANCE,
            self.STAGE_TURN,
            self.STAGE_COMBINED,
        ):
            raise ValueError(f"Etapa inválida: {stage}. Usá 1, 2 o 3.")
        self.stage = stage
        if self._max_episode_steps_override is not None:
            self.max_episode_steps = self._max_episode_steps_override
        else:
            self.max_episode_steps = {
                self.STAGE_ADVANCE: 600,
                # 180° a velocidad lenta puede tardar ~340 pasos; dejamos
                # margen para que la política no sea castigada por el reloj.
                self.STAGE_TURN: 600,
                self.STAGE_COMBINED: 1000,
            }[stage]

    # ------------------------------------------------------------------ #
    # Observación
    # ------------------------------------------------------------------ #
    def _get_obs(self) -> np.ndarray:
        pos, quat = p.getBasePositionAndOrientation(self.robot)
        lin_vel, ang_vel = p.getBaseVelocity(self.robot)
        yaw = float(p.getEulerFromQuaternion(quat)[2])
        # Ángulo objetivo relativo al frente actual (egocéntrico). Es mucho
        # más fácil de aprender que el ángulo global: la red no tiene que
        # combinar el cuaternión con el objetivo para calcular el error.
        goal_bearing = wrap_angle(float(self.goal_angle) - yaw)
        obs = np.concatenate(
            [
                np.asarray(pos[:2], dtype=np.float32),
                np.asarray(quat, dtype=np.float32),
                np.asarray(lin_vel, dtype=np.float32),
                np.asarray(ang_vel, dtype=np.float32),
                np.asarray(
                    [float(self.goal), goal_bearing],
                    dtype=np.float32,
                ),
            ]
        )
        return obs.astype(np.float32)

    def get_observation(
        self,
        goal: float | None = None,
        goal_angle: float | None = None,
        stage: int | None = None,
    ) -> np.ndarray:
        """Observación 14D para inferencia, sin ruido de sensores."""
        if stage is not None:
            self.set_stage(stage)
        if goal is not None:
            self.goal = float(np.clip(float(goal), -1.0, 1.0))
        if goal_angle is not None:
            self.goal_angle = wrap_angle(float(goal_angle))
        was_training = self.training
        self.training = False
        try:
            return self._get_obs()
        finally:
            self.training = was_training

    # ------------------------------------------------------------------ #
    # Colisiones / tilt
    # ------------------------------------------------------------------ #
    def _has_collision(self) -> bool:
        for body_id in self.wall_ids + self.obstacle_ids:
            if p.getContactPoints(bodyA=self.robot, bodyB=body_id):
                return True
        return False

    def _tilt_rad(self, quat: tuple[float, ...]) -> tuple[float, float, float]:
        roll, pitch, yaw = p.getEulerFromQuaternion(quat)
        return float(roll), float(pitch), float(yaw)

    # ------------------------------------------------------------------ #
    # API Gymnasium
    # ------------------------------------------------------------------ #
    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        options = options or {}
        self.set_stage(int(options.get("stage", self.stage)))

        # Yaw inicial: siempre aleatorio 0–360°, salvo que se fije para evaluar.
        if "start_yaw" in options:
            yaw = wrap_angle(float(options["start_yaw"]))
        else:
            yaw = float(self.np_random.uniform(0.0, 2.0 * math.pi))

        # Comando y ángulo objetivo según la etapa.
        if "goal" in options:
            self.goal = float(np.clip(float(options["goal"]), -1.0, 1.0))
        elif self.stage == self.STAGE_ADVANCE:
            self.goal = float(self.np_random.choice([-1.0, 1.0]))
        elif self.stage == self.STAGE_TURN:
            self.goal = 0.0
        else:
            self.goal = 1.0 if self.np_random.random() < 0.8 else -1.0

        if "goal_angle" in options:
            self.goal_angle = wrap_angle(float(options["goal_angle"]))
        elif self.stage == self.STAGE_ADVANCE:
            # Sin giro: el objetivo de rumbo es el rumbo inicial.
            self.goal_angle = yaw
        elif self.stage == self.STAGE_TURN:
            delta = float(
                self.np_random.choice(
                    [
                        -math.pi,
                        -math.pi / 2.0,
                        -math.pi / 4.0,
                        math.pi / 4.0,
                        math.pi / 2.0,
                        math.pi,
                    ]
                )
            )
            self.goal_angle = wrap_angle(yaw + delta)
        else:
            self.goal_angle = wrap_angle(
                yaw + float(self.np_random.uniform(-math.pi, math.pi))
            )

        # Obstáculos primero, para que el robot no aparezca dentro de una caja.
        self._place_obstacles()
        self._apply_mass_randomization()

        start_pos = [0.0, 0.0, self.BASE_Z]
        start_orn = p.getQuaternionFromEuler([0.0, 0.0, yaw])
        p.resetBasePositionAndOrientation(
            self.robot, start_pos, start_orn
        )
        p.resetBaseVelocity(
            self.robot, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        )
        for joint_index in (0, 1):
            p.resetJointState(self.robot, joint_index, targetValue=0.0)
            p.setJointMotorControl2(
                self.robot,
                joint_index,
                p.VELOCITY_CONTROL,
                targetVelocity=0.0,
                force=self.max_force,
            )

        self.step_count = 0
        self.prev_pos = np.array(start_pos, dtype=np.float64)
        self.prev_action = np.zeros(2, dtype=np.float32)
        self.prev_applied_action = np.zeros(2, dtype=np.float32)
        self.total_forward = 0.0
        self.total_forward_body = 0.0
        self.heading_success_counter = 0
        self.tilt_counter = 0
        self.prev_heading_error = abs(
            wrap_angle(self.goal_angle - yaw)
        )

        # Asentar la física antes de observar.
        for _ in range(8):
            p.stepSimulation()

        # Leer la pose real después de asentar: la precisión del origen es
        # importante para el robot físico y para el mapa de chunks.
        settled_pos, settled_quat = p.getBasePositionAndOrientation(self.robot)
        settled_roll, settled_pitch, settled_yaw = self._tilt_rad(settled_quat)
        self.prev_pos = np.asarray(settled_pos, dtype=np.float64)
        self.prev_heading_error = abs(
            wrap_angle(self.goal_angle - settled_yaw)
        )
        # Coordenada inicial que el robot debe conocer y recordar.
        self.initial_position = np.array(
            [
                float(settled_pos[0]),
                float(settled_pos[1]),
                float(settled_pos[2] - self.BASE_Z),
            ],
            dtype=np.float64,
        )
        self.initial_quaternion = np.asarray(
            settled_quat, dtype=np.float64
        )
        self.initial_yaw = float(settled_yaw)

        obs = self._get_obs()
        info = {
            "x": float(settled_pos[0]),
            "y": float(settled_pos[1]),
            "z": float(settled_pos[2] - self.BASE_Z),
            "z_physical": float(settled_pos[2]),
            "yaw": float(settled_yaw),
            "initial_x": float(self.initial_position[0]),
            "initial_y": float(self.initial_position[1]),
            "initial_z": float(self.initial_position[2]),
            "initial_yaw": float(self.initial_yaw),
            "initial_yaw_deg": math.degrees(self.initial_yaw),
            "pitch": float(settled_pitch),
            "roll": float(settled_roll),
            "goal": self.goal,
            "goal_angle": self.goal_angle,
            "goal_angle_deg": math.degrees(self.goal_angle),
            "heading_error_deg": math.degrees(self.prev_heading_error),
            "tilt_deg": math.degrees(
                max(abs(settled_pitch), abs(settled_roll))
            ),
            "total_mass": float(self.current_total_mass),
            "stage": self.stage,
            "collision": False,
            "flipped": False,
            "success": False,
            "step": 0,
            "forward": 0.0,
            "forward_body": 0.0,
            "delta_forward": 0.0,
            "hitbox": list(self.HITBOX_SIZE),
            "hitbox_radius": float(self.HITBOX_RADIUS),
        }
        return obs, info

    def get_pose(self) -> dict[str, float]:
        """Pose actual del robot, útil para el cuerpo y los sensores."""
        pos, quat = p.getBasePositionAndOrientation(self.robot)
        roll, pitch, yaw = self._tilt_rad(quat)
        return {
            "x": float(pos[0]),
            "y": float(pos[1]),
            "z": float(pos[2] - self.BASE_Z),
            "z_physical": float(pos[2]),
            "yaw": float(yaw),
            "roll": float(roll),
            "pitch": float(pitch),
            "quat": tuple(float(v) for v in quat),
            "initial_x": float(self.initial_position[0]),
            "initial_y": float(self.initial_position[1]),
            "initial_z": float(self.initial_position[2]),
            "initial_yaw": float(self.initial_yaw),
        }

    def reset_robot_only(
        self,
        x: float | None = None,
        y: float | None = None,
        yaw: float | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Reubica solo al robot, sin volver a sortear obstáculos ni masa.

        Sirve para recuperarse de una caída o un choque durante la
        exploración: el mapa de chunks y las cajas quedan intactos.
        """
        if x is None:
            x = float(self.initial_position[0])
        if y is None:
            y = float(self.initial_position[1])
        if yaw is None:
            yaw = float(self.initial_yaw)

        start_pos = [float(x), float(y), self.BASE_Z]
        start_orn = p.getQuaternionFromEuler([0.0, 0.0, float(yaw)])
        p.resetBasePositionAndOrientation(self.robot, start_pos, start_orn)
        p.resetBaseVelocity(
            self.robot, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        )
        for joint_index in (0, 1):
            p.resetJointState(self.robot, joint_index, targetValue=0.0)
            p.setJointMotorControl2(
                self.robot,
                joint_index,
                p.VELOCITY_CONTROL,
                targetVelocity=0.0,
                force=self.max_force,
            )

        self.step_count = 0
        self.prev_action = np.zeros(2, dtype=np.float32)
        self.prev_applied_action = np.zeros(2, dtype=np.float32)
        self.total_forward = 0.0
        self.total_forward_body = 0.0
        self.heading_success_counter = 0
        self.tilt_counter = 0

        for _ in range(8):
            p.stepSimulation()

        settled_pos, settled_quat = p.getBasePositionAndOrientation(
            self.robot
        )
        settled_roll, settled_pitch, settled_yaw = self._tilt_rad(
            settled_quat
        )
        self.prev_pos = np.asarray(settled_pos, dtype=np.float64)
        self.prev_heading_error = abs(
            wrap_angle(self.goal_angle - settled_yaw)
        )
        obs = self._get_obs()
        info = {
            "x": float(settled_pos[0]),
            "y": float(settled_pos[1]),
            "z": float(settled_pos[2] - self.BASE_Z),
            "z_physical": float(settled_pos[2]),
            "yaw": float(settled_yaw),
            "initial_x": float(self.initial_position[0]),
            "initial_y": float(self.initial_position[1]),
            "initial_z": float(self.initial_position[2]),
            "initial_yaw": float(self.initial_yaw),
            "initial_yaw_deg": math.degrees(self.initial_yaw),
            "pitch": float(settled_pitch),
            "roll": float(settled_roll),
            "tilt_deg": math.degrees(
                max(abs(settled_pitch), abs(settled_roll))
            ),
            "goal": self.goal,
            "goal_angle": self.goal_angle,
            "goal_angle_deg": math.degrees(self.goal_angle),
            "heading_error_deg": math.degrees(self.prev_heading_error),
            "total_mass": float(self.current_total_mass),
            "stage": self.stage,
            "collision": False,
            "flipped": False,
            "success": False,
            "step": 0,
            "forward": 0.0,
            "forward_body": 0.0,
            "delta_forward": 0.0,
            "hitbox": list(self.HITBOX_SIZE),
            "hitbox_radius": float(self.HITBOX_RADIUS),
            "recovered": True,
        }
        return obs, info

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        raw_action = np.clip(
            np.asarray(action, dtype=np.float32), -1.0, 1.0
        )
        # Filtro exponencial: el robot físico no puede cambiar la velocidad de
        # las orugas instantáneamente. Suaviza la acción y reduce el castigo
        # por jerkiness sin impedir que la política explore.
        applied_action = (
            self.action_smoothing * self.prev_applied_action
            + (1.0 - self.action_smoothing) * raw_action
        ).astype(np.float32)

        left_speed = float(applied_action[0]) * self.max_wheel_speed
        right_speed = float(applied_action[1]) * self.max_wheel_speed
        if self.wheel_sink is not None:
            # El adaptador no bloquea: anota la consigna y la manda su propio
            # hilo. Si el enlace falla, el simulador sigue vivo.
            try:
                self.wheel_sink.drive(left_speed, right_speed)
            except Exception as exc:  # noqa: BLE001 - el enlace nunca tumba el sim
                print(f"[wheel_sink] {exc}")
                self.wheel_sink = None
        p.setJointMotorControl2(
            self.robot,
            0,
            p.VELOCITY_CONTROL,
            targetVelocity=left_speed,
            force=self.max_force,
        )
        p.setJointMotorControl2(
            self.robot,
            1,
            p.VELOCITY_CONTROL,
            targetVelocity=right_speed,
            force=self.max_force,
        )

        for _ in range(self.substeps):
            p.stepSimulation()

        if self.render_mode == "human":
            self.render()

        pos, quat = p.getBasePositionAndOrientation(self.robot)
        pos = np.asarray(pos, dtype=np.float64)
        lin_vel, ang_vel = p.getBaseVelocity(self.robot)
        roll, pitch, yaw = self._tilt_rad(quat)

        delta_x = float(pos[0] - self.prev_pos[0])
        delta_y = float(pos[1] - self.prev_pos[1])
        # Avance relativo al frente COMANDADO (goal_angle), no al eje X global.
        # Usar el yaw instantáneo permitía reward hacking girando en círculos
        # (el robot acumulaba avance frontal mientras rotaba). El goal_angle es
        # la dirección que el robot debe mirar, así que sigue siendo relativo
        # al frente del robot y no al mundo.
        delta_forward = (
            delta_x * math.cos(self.goal_angle)
            + delta_y * math.sin(self.goal_angle)
        )
        # Métrica de diagnóstico: avance relativo al frente físico actual.
        delta_forward_body = (
            delta_x * math.cos(yaw) + delta_y * math.sin(yaw)
        )
        self.prev_pos = pos.copy()
        self.total_forward += delta_forward
        self.total_forward_body += delta_forward_body
        self.step_count += 1

        heading_error = abs(wrap_angle(self.goal_angle - yaw))
        heading_progress = self.prev_heading_error - heading_error

        reward = 0.0

        if self.stage == self.STAGE_ADVANCE:
            reward += (
                self.goal * delta_forward * self.forward_reward_scale
            )
            # Mantener el rumbo inicial: castigo suave por desviarse.
            reward -= self.stage1_heading_penalty * heading_error
            # En la etapa 1 no queremos que "gire en el lugar" para evitar
            # el avance: castigamos siempre la velocidad angular.
            reward -= self.stage1_yaw_rate_penalty * abs(float(ang_vel[2]))
        elif self.stage == self.STAGE_TURN:
            # Solo giro: premia reducir el error de rumbo y castiga trasladarse.
            reward += self.heading_reward_scale * heading_progress
            reward -= self.stage2_forward_penalty * math.hypot(
                delta_x, delta_y
            )
        else:
            # Combinado: avanzar/retroceder + orientarse + evitar obstáculos.
            reward += (
                self.goal * delta_forward * self.forward_reward_scale
            )
            reward += self.heading_reward_scale * heading_progress
            reward -= self.heading_error_penalty * heading_error

        # Castigo continuo por inclinación (antes de la terminación).
        reward -= self.tilt_penalty * (pitch * pitch + roll * roll)

        # Castigo por brusquedad (jerkiness): acciones suaves para el robot real.
        # El cap evita que una acción aleatoria al inicio domine la recompensa
        # y que la política colapse a "no hacer nada" para evitar el castigo.
        delta_action = applied_action - self.prev_applied_action
        jerk = float(np.dot(delta_action, delta_action))
        reward -= self.jerk_penalty * min(jerk, self.jerk_penalty_cap)

        reward -= self.time_penalty
        reward -= self.action_magnitude_penalty * float(
            np.dot(applied_action, applied_action)
        )

        # Amortiguar oscilación de rumbo cuando ya está casi alineado.
        # También en la etapa 2: así la política frena el giro al llegar al
        # objetivo en vez de oscilar alrededor del ángulo. En la etapa 1 ya
        # se castiga el yaw rate de forma continua, así que no se duplica.
        if (
            self.stage != self.STAGE_ADVANCE
            and heading_error < math.radians(10.0)
        ):
            reward -= self.yaw_rate_penalty * abs(float(ang_vel[2]))

        # Éxito de giro: error < 5° durante 10 pasos seguidos.
        success = False
        if (
            self.stage == self.STAGE_TURN
            and heading_error < math.radians(self.heading_success_deg)
        ):
            self.heading_success_counter += 1
        else:
            self.heading_success_counter = 0

        terminated = False
        if (
            self.stage == self.STAGE_TURN
            and self.heading_success_counter >= self.heading_success_steps
        ):
            reward += self.heading_success_bonus
            success = True
            terminated = True

        # Colisión con pared o caja: -10 y fin.
        collided = self._has_collision()
        if collided:
            reward = -self.crash_penalty
            if self.collision_terminates:
                terminated = True

        # Inclinación > 15° sostenida: -10 y fin.
        tilt_deg = math.degrees(max(abs(pitch), abs(roll)))
        if tilt_deg > self.tilt_limit_deg:
            self.tilt_counter += 1
        else:
            self.tilt_counter = 0

        flipped = False
        if self.tilt_counter >= self.tilt_grace_steps:
            reward = -self.flip_penalty
            terminated = True
            flipped = True

        truncated = self.step_count >= self.max_episode_steps

        self.prev_action = raw_action.copy()
        self.prev_applied_action = applied_action.copy()
        self.prev_heading_error = heading_error

        obs = self._get_obs()
        info = {
            "x": float(pos[0]),
            "y": float(pos[1]),
            "yaw": float(yaw),
            "pitch": float(pitch),
            "roll": float(roll),
            "tilt_deg": float(tilt_deg),
            "goal": self.goal,
            "goal_angle": self.goal_angle,
            "goal_angle_deg": math.degrees(self.goal_angle),
            "heading_error_deg": math.degrees(heading_error),
            "delta_forward": float(delta_forward),
            "delta_forward_body": float(delta_forward_body),
            "forward": float(self.total_forward),
            "forward_body": float(self.total_forward_body),
            "z": float(pos[2] - self.BASE_Z),
            "z_physical": float(pos[2]),
            "total_mass": float(self.current_total_mass),
            "hitbox": list(self.HITBOX_SIZE),
            "hitbox_radius": float(self.HITBOX_RADIUS),
            "action_raw": raw_action.tolist(),
            "action_applied": applied_action.tolist(),
            "stage": self.stage,
            "collision": bool(collided),
            "flipped": bool(flipped),
            "success": bool(success),
            "step": self.step_count,
        }
        return obs, float(reward), bool(terminated), bool(truncated), info

    # ------------------------------------------------------------------ #
    # Render / cierre
    # ------------------------------------------------------------------ #
    def render(self) -> None:
        if self.render_mode != "human":
            return
        pos, _ = p.getBasePositionAndOrientation(self.robot)
        p.resetDebugVisualizerCamera(
            cameraDistance=3.2,
            cameraYaw=40.0,
            cameraPitch=-25.0,
            cameraTargetPosition=pos,
        )

    def close(self) -> None:
        sink = getattr(self, "wheel_sink", None)
        if sink is not None:
            self.wheel_sink = None
            try:
                sink.close()
            except Exception:
                pass
        if getattr(self, "client_id", -1) >= 0:
            try:
                p.disconnect(self.client_id)
            except Exception:
                # Si el cliente ya estaba desconectado, no hay nada que hacer.
                pass
            finally:
                self.client_id = -1

    def __del__(self) -> None:
        self.close()


# ---------------------------------------------------------------------- #
# Prueba manual / smoke test
# ---------------------------------------------------------------------- #
def _random_demo(render_mode: str | None, stage: int) -> None:
    env = WallEEnvV2(render_mode=render_mode, stage=stage)
    obs, info = env.reset()
    print("Observación inicial (14D):", np.round(obs, 3), obs.shape)
    print(
        f"Etapa={stage} | masa={info['total_mass']:.2f} kg | "
        f"yaw={math.degrees(info['yaw']):+.1f}° | "
        f"goal_angle={info['goal_angle_deg']:+.1f}° | "
        f"episodio={env.max_episode_steps} pasos"
    )
    print("Acción aleatoria a 60 Hz. Ctrl+C para salir.")

    try:
        for step in range(5000):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if step % 60 == 0:
                print(
                    f"step={step:4d} x={info['x']:+.2f} "
                    f"y={info['y']:+.2f} "
                    f"tilt={info['tilt_deg']:.1f}° "
                    f"err={info['heading_error_deg']:.1f}° "
                    f"reward={reward:+.2f} "
                    f"term={terminated} trunc={truncated}"
                )
            if render_mode == "human":
                time.sleep(1.0 / 60.0)
            if terminated or truncated:
                print("Episodio terminado:", info)
                obs, info = env.reset()
    except KeyboardInterrupt:
        pass
    finally:
        env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prueba del entorno WALL-E V2")
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Sin GUI (más rápido, para depurar)",
    )
    parser.add_argument(
        "--stage",
        type=int,
        default=1,
        choices=(1, 2, 3),
        help="Etapa del currículum (1 avance, 2 giros, 3 combinado)",
    )
    args = parser.parse_args()
    _random_demo(
        None if args.direct else "human",
        stage=args.stage,
    )
