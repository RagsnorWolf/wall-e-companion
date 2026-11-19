"""
WALL-E · Fase 2 — Cerebro Motor (entorno de simulación)

Entorno Gymnasium sobre PyBullet para entrenar el movimiento autónomo de
WALL-E con Reinforcement Learning (PPO).

Qué representa este entorno:
- Un plano infinito como suelo.
- Un "proxy físico" del robot: chasis rígido (caja) + dos ruedas/orugas
  articuladas (joints revolutos) que se controlan por velocidad.
- Acción continua de 2 dimensiones: velocidad de oruga izquierda y derecha.
- Observación (13 números): posición (x, y), orientación (quaternion),
  velocidades lineales/angulares de la base y el comando `goal`
  (+1 avanzar, -1 retroceder, 0 quedarse quieto).
- Recompensa condicionada por el comando y medida sobre el **frente del
  robot** (no sobre el eje X global), con penalización por choque o
  volcamiento y refuerzo de suavidad/ahorro para el robot físico.
- Arranques aleatorios en toda la arena (no solo en x=-18) y rumbo inicial
  aleatorio para que la política no sufra Out-of-Distribution al cambiar de
  posición ni después de un giro.

El objetivo es que PPO aprenda una política de conducción diferencial que
luego se pueda transferir (con calibración) al robot físico.

Uso rápido:
    python walle_env.py            # prueba aleatoria con GUI
    python walle_env.py --direct   # prueba aleatoria sin GUI
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


class WallEEnv(gym.Env):
    """Entorno de conducción diferencial para el proxy físico de WALL-E."""

    metadata = {"render_modes": ["human"], "render_fps": 60}

    # ------------------------------------------------------------------ #
    # Construcción del mundo
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        render_mode: str | None = None,
        max_episode_steps: int = 1000,
        max_wheel_speed: float = 10.0,
        # Torque máximo por oruga (N·m). Ajustado a 1.0 para suavizar aceleración.
        max_force: float = 1.0,
        forward_reward_scale: float = 20.0,
        time_penalty: float = 0.01,
        crash_penalty: float = 10.0,
        flip_penalty: float = 10.0,
        arena_half_size: float = 20.0,
        visual_mesh_path: str | None = None,
        visual_mesh_scale: float = 1.0,
        connect_options: str | None = None,
        show_proxy_visuals: bool = True,
        # --- Sim-to-real y condicionamiento por comando -------------------
        randomize_goal: bool = True,
        obs_noise_std: float = 0.0,
        action_rate_penalty: float = 0.0,
        action_magnitude_penalty: float = 0.0,
        randomize_reset: bool = False,
        # Rango de arranque aleatorio dentro del arena. `reset_margin` deja
        # ese margen respecto de las paredes para no nacer pegado a ellas.
        reset_margin: float = 2.0,
        reset_yaw_range_deg: float = 8.0,
        # Probabilidades de comando en orden [retroceder, quieto, avanzar].
        goal_probs: tuple[float, float, float] = (0.35, 0.30, 0.35),
        # Refuerzo del comando "quieto": multiplica la penalización por
        # deriva, castiga la velocidad residual de la base y penaliza
        # directamente las acciones no nulas.
        stop_drift_scale: float = 2.0,
        stop_velocity_penalty: float = 0.5,
        stop_action_penalty: float = 0.0,
        # Castigo al giro no comandado (yaw rate). Inspirado en el tutorial
        # de balance bot con PPO: evita que la política "haga trampa" girando
        # para acumular avance frontal.
        yaw_rate_penalty: float = 0.0,
        # Domain randomization opcional para sim-to-real: masa, fricción y
        # fuerza de los motores varían por episodio.
        randomize_physics: bool = False,
        base_mass_range: tuple[float, float] = (0.90, 1.10),
        wheel_mass_range: tuple[float, float] = (0.90, 1.10),
        wheel_friction_range: tuple[float, float] = (0.80, 1.20),
        motor_force_range: tuple[float, float] = (0.80, 1.20),
    ) -> None:
        super().__init__()

        self.render_mode = render_mode
        self.max_episode_steps = max_episode_steps
        self.max_wheel_speed = max_wheel_speed
        self.max_force = max_force
        self.nominal_max_force = max_force
        self.forward_reward_scale = forward_reward_scale
        self.time_penalty = time_penalty
        self.crash_penalty = crash_penalty
        self.flip_penalty = flip_penalty
        self.arena_half_size = arena_half_size
        self.randomize_goal = randomize_goal
        self.obs_noise_std = obs_noise_std
        self.action_rate_penalty = action_rate_penalty
        self.action_magnitude_penalty = action_magnitude_penalty
        self.randomize_reset = randomize_reset
        self.reset_margin = max(0.0, float(reset_margin))
        self.reset_yaw_range_deg = max(0.0, float(reset_yaw_range_deg))
        limit = max(0.0, self.arena_half_size - self.reset_margin)
        self.reset_x_range = (-limit, limit)
        self.reset_y_range = (-limit, limit)
        self.goal_probs = tuple(float(v) for v in goal_probs)
        self.stop_drift_scale = stop_drift_scale
        self.stop_velocity_penalty = stop_velocity_penalty
        self.stop_action_penalty = stop_action_penalty
        self.yaw_rate_penalty = yaw_rate_penalty
        self.randomize_physics = randomize_physics
        self.base_mass_range = tuple(float(v) for v in base_mass_range)
        self.wheel_mass_range = tuple(float(v) for v in wheel_mass_range)
        self.wheel_friction_range = tuple(float(v) for v in wheel_friction_range)
        self.motor_force_range = tuple(float(v) for v in motor_force_range)
        # La fuerza efectiva puede cambiar por episodio con domain randomization.
        self.current_max_force = max_force
        # Se desactiva en evaluación para tener observaciones limpias.
        self.training = True
        self.goal = 1.0
        # Rumbo de referencia para la recompensa de avance. Se fija al inicio
        # de cada episodio (o con `set_reference_yaw` al comenzar un movimiento
        # PPO después de un giro). Usar el rumbo de referencia evita que la
        # política "haga trampa" girando en círculos para acumular avance.
        self.reference_yaw = 0.0
        self.prev_action = np.zeros(2, dtype=np.float32)
        self.visual_mesh_path = (
            str(Path(visual_mesh_path).resolve()) if visual_mesh_path else None
        )
        self.visual_mesh_scale = visual_mesh_scale
        self.connect_options = connect_options
        self.show_proxy_visuals = show_proxy_visuals

        # Física: 240 Hz internos, 4 subpasos por step de control = 60 Hz.
        self.physics_hz = 240.0
        self.substeps = 4
        self.dt = self.substeps / self.physics_hz

        # Espacios Gymnasium
        self.action_space = gym.spaces.Box(
            low=-1.0, high=1.0, shape=(2,), dtype=np.float32
        )

        # x, y, qx, qy, qz, qw, vx, vy, vz, wx, wy, wz, goal
        # goal: +1 avanzar, -1 retroceder, 0 quedarse quieto.
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
            ],
            dtype=np.float32,
        )
        obs_high = np.array(
            [
                self.arena_half_size,
                self.arena_half_size,
                1.0,
                1.0,
                1.0,
                1.0,
                10.0,
                10.0,
                10.0,
                20.0,
                20.0,
                20.0,
                1.0,
            ],
            dtype=np.float32,
        )
        self.observation_space = gym.spaces.Box(
            low=obs_low, high=obs_high, dtype=np.float32
        )

        # Conexión PyBullet.
        # En GUI usamos --opengl2: el renderer OpenGL 3 por defecto se cuelga
        # al crear cuerpos con algunos drivers AMD (Radeon Vega). OpenGL 2
        # funciona de forma estable en esas máquinas. `connect_options`
        # permite agregar, por ejemplo, el color de fondo (cielo).
        if self.render_mode == "human":
            options = (
                self.connect_options
                if self.connect_options is not None
                else "--opengl2"
            )
            self.client_id = p.connect(p.GUI, options=options)
        else:
            self.client_id = p.connect(p.DIRECT)
        if self.client_id < 0:
            raise RuntimeError(
                "No se pudo conectar a PyBullet. "
                "Verificá que pybullet esté instalado correctamente."
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
            # Ojo: COV_ENABLE_SHADOWS puede colgar la GUI con algunos drivers
            # (probado con AMD Radeon Vega). No lo activamos.

        self._build_world()
        self._build_walle()

        self.start_pos = np.array(
            [-self.arena_half_size + 2.0, 0.0, 0.15], dtype=np.float64
        )
        self.start_orn = p.getQuaternionFromEuler([0.0, 0.0, 0.0])

        self.step_count = 0
        self.prev_pos = self.start_pos.copy()
        self.total_forward = 0.0

        self.reset()

    # ------------------------------------------------------------------ #
    # Mundo: suelo y paredes
    # ------------------------------------------------------------------ #
    def _build_world(self) -> None:
        # Plano infinito de PyBullet (pybullet_data/plane.urdf)
        self.plane = p.loadURDF("plane.urdf")
        p.changeDynamics(self.plane, -1, lateralFriction=1.0)

        # Paredes del arena (cajas estáticas). Limitan el entrenamiento y
        # permiten detectar choques.
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

        # Paredes en X = ±half y Y = ±half
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
    # Robot: chasis + dos orugas articuladas
    # ------------------------------------------------------------------ #
    def _build_walle(self) -> None:
        wheel_radius = 0.09
        wheel_width = 0.08
        wheel_mass = 0.45

        # Chasis (caja). halfExtents = medio tamaño en metros.
        # La base queda a solo 1 cm del piso: actúa como "patín" anti-volcado
        # y evita que el robot bascule sobre el único eje de ruedas.
        chassis_half = [0.25, 0.18, 0.14]  # 0.50 x 0.36 x 0.28 m
        base_collision = p.createCollisionShape(
            p.GEOM_BOX, halfExtents=chassis_half
        )

        if not self.show_proxy_visuals:
            # Proxy invisible de verdad: caja visual de 0.2 mm (alpha 0 en
            # OpenGL3 se pinta negra y -1 pinta la colisión con colores).
            base_visual = p.createVisualShape(
                p.GEOM_BOX,
                halfExtents=[0.0001, 0.0001, 0.0001],
                rgbaColor=[0.0, 0.0, 0.0, 0.0],
            )
        elif self.visual_mesh_path:
            # Apariencia opcional con el modelo de la Fase 1 (OBJ).
            base_visual = p.createVisualShape(
                p.GEOM_MESH,
                fileName=self.visual_mesh_path,
                meshScale=[
                    self.visual_mesh_scale,
                    self.visual_mesh_scale,
                    self.visual_mesh_scale,
                ],
                rgbaColor=[1.0, 1.0, 1.0, 1.0],
            )
        else:
            # Sin mesh: caja amarilla WALL-E.
            base_visual = p.createVisualShape(
                p.GEOM_BOX,
                halfExtents=chassis_half,
                rgbaColor=[0.85, 0.65, 0.20, 1.0],
            )

        # Ruedas/orugas: cilindros grises.
        # El cilindro de PyBullet está alineado con Z local. Lo rotamos 90°
        # alrededor de X mediante el frame del shape, dejando el frame del
        # link en identidad. Así el eje del joint [0, 1, 0] es Y global sin
        # ambigüedad (rueda que gira hacia adelante/atrás).
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
            basePosition=[0.0, 0.0, 0.15],
            baseOrientation=[0.0, 0.0, 0.0, 1.0],
            linkMasses=[wheel_mass, wheel_mass],
            linkCollisionShapeIndices=[wheel_collision, wheel_collision],
            linkVisualShapeIndices=[wheel_visual, wheel_visual],
            linkPositions=[
                [0.0, 0.22, -0.06],
                [0.0, -0.22, -0.06],
            ],
            linkOrientations=[identity_orn, identity_orn],
            linkInertialFramePositions=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            linkInertialFrameOrientations=[identity_orn, identity_orn],
            linkParentIndices=[0, 0],
            linkJointTypes=[p.JOINT_REVOLUTE, p.JOINT_REVOLUTE],
            linkJointAxis=[[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        )

        # Fricción: ruedas con buen agarre, chasis con poca fricción para que
        # no "arrastre" si roza el piso.
        for wheel_index in (0, 1):
            p.changeDynamics(
                self.robot,
                wheel_index,
                lateralFriction=1.8,
                spinningFriction=0.05,
                rollingFriction=0.001,
                restitution=0.0,
            )
        p.changeDynamics(
            self.robot,
            -1,
            lateralFriction=0.4,
            restitution=0.0,
        )

        # Valores nominales para domain randomization (se restauran en cada
        # reset cuando la aleatorización está desactivada).
        self.nominal_base_mass = 3.5
        self.nominal_wheel_mass = wheel_mass
        self.nominal_wheel_friction = 1.8
        self.nominal_base_friction = 0.4

    def _apply_physics_randomization(self) -> None:
        """Varía masa, fricción y fuerza por episodio (sim-to-real).

        Inspirado en la fase 2 del tutorial de balance bot: si la política
        solo ve un robot "perfecto", aprende a explotar detalles que en el
        hardware real no existen. Con parámetros ligeramente distintos por
        episodio, la política aprende a tolerar la variación.
        """
        if self.randomize_physics:
            rng = self.np_random
            base_mass = self.nominal_base_mass * float(
                rng.uniform(*self.base_mass_range)
            )
            wheel_mass = self.nominal_wheel_mass * float(
                rng.uniform(*self.wheel_mass_range)
            )
            wheel_friction = self.nominal_wheel_friction * float(
                rng.uniform(*self.wheel_friction_range)
            )
            self.current_max_force = self.nominal_max_force * float(
                rng.uniform(*self.motor_force_range)
            )
        else:
            base_mass = self.nominal_base_mass
            wheel_mass = self.nominal_wheel_mass
            wheel_friction = self.nominal_wheel_friction
            self.current_max_force = self.nominal_max_force

        p.changeDynamics(
            self.robot,
            -1,
            mass=base_mass,
            lateralFriction=self.nominal_base_friction,
        )
        for wheel_index in (0, 1):
            p.changeDynamics(
                self.robot,
                wheel_index,
                mass=wheel_mass,
                lateralFriction=wheel_friction,
            )

    # ------------------------------------------------------------------ #
    # Observación / estado
    # ------------------------------------------------------------------ #
    def _get_obs(self) -> np.ndarray:
        pos, quat = p.getBasePositionAndOrientation(self.robot)
        lin_vel, ang_vel = p.getBaseVelocity(self.robot)
        obs = np.concatenate(
            [
                np.asarray(pos[:2], dtype=np.float32),
                np.asarray(quat, dtype=np.float32),
                np.asarray(lin_vel, dtype=np.float32),
                np.asarray(ang_vel, dtype=np.float32),
                np.asarray([self.goal], dtype=np.float32),
            ]
        )
        # Ruido de sensores solo durante el entrenamiento (sim-to-real).
        if self.training and self.obs_noise_std > 0.0:
            noise = self.np_random.normal(
                0.0, self.obs_noise_std, size=obs.shape
            ).astype(np.float32)
            noise[-1] = 0.0  # la señal de comando no se corrompe
            obs = obs + noise
        return obs.astype(np.float32)

    def get_observation(self, goal: float | None = None) -> np.ndarray:
        """Observación de 13D para inferencia, sin ruido de sensores.

        Orden: x, y, qx, qy, qz, qw, vx, vy, vz, wx, wy, wz, goal.
        Si se pasa `goal`, actualiza el comando del entorno antes de leer.
        """
        if goal is not None:
            self.goal = float(np.clip(float(goal), -1.0, 1.0))
        was_training = self.training
        self.training = False
        try:
            return self._get_obs()
        finally:
            self.training = was_training

    def set_reference_yaw(self, yaw: float) -> None:
        """Fija el rumbo de referencia para la recompensa de avance.

        Se usa al comenzar un movimiento PPO después de un giro: así la
        recompensa mide el avance sobre el frente actual y no permite que la
        política gire en círculos para acumular `delta_forward`.
        """
        self.reference_yaw = float(yaw)

    def _is_flipped(self) -> bool:
        _, quat = p.getBasePositionAndOrientation(self.robot)
        matrix = p.getMatrixFromQuaternion(quat)
        # Tercera columna de la matriz de rotación = vector "up" del robot.
        up_z = matrix[8]
        return up_z < 0.5

    def _has_collision(self) -> bool:
        for wall_id in self.wall_ids:
            contacts = p.getContactPoints(bodyA=self.robot, bodyB=wall_id)
            if contacts:
                return True
        return False

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

        # Comando del episodio: avanzar (+1), retroceder (-1) o quieto (0).
        if "goal" in options:
            self.goal = float(np.clip(float(options["goal"]), -1.0, 1.0))
        elif self.randomize_goal:
            self.goal = float(
                self.np_random.choice(
                    [-1.0, 0.0, 1.0], p=list(self.goal_probs)
                )
            )
        else:
            self.goal = 1.0

        # Posición inicial: `start_pos` permite fijarla desde la evaluación
        # (p. ej. el centro del arena para tener espacio en ambos sentidos).
        if "start_pos" in options:
            start = np.asarray(options["start_pos"], dtype=np.float64).copy()
            if start.shape == (2,):
                start = np.array([start[0], start[1], 0.15])
            start_orn = self.start_orn
        else:
            start = np.asarray(self.start_pos, dtype=np.float64).copy()
            if self.randomize_reset:
                # OOD fix: arrancar en cualquier punto del arena, no solo
                # cerca de x=-18. Así la política ve todas las posiciones.
                x_low, x_high = self.reset_x_range
                y_low, y_high = self.reset_y_range
                start[0] = float(self.np_random.uniform(x_low, x_high))
                start[1] = float(self.np_random.uniform(y_low, y_high))
                yaw_limit = math.radians(self.reset_yaw_range_deg)
                yaw = float(
                    self.np_random.uniform(-yaw_limit, yaw_limit)
                )
                start_orn = p.getQuaternionFromEuler([0.0, 0.0, yaw])
            else:
                start_orn = self.start_orn

        # Rumbo inicial explícito (evaluación tras un giro o test OOD).
        if "start_yaw" in options:
            start_orn = p.getQuaternionFromEuler(
                [0.0, 0.0, float(options["start_yaw"])]
            )

        # La recompensa de avance se mide sobre este rumbo de referencia.
        self.reference_yaw = float(
            p.getEulerFromQuaternion(start_orn)[2]
        )

        p.resetBasePositionAndOrientation(
            self.robot, start.tolist(), start_orn
        )
        p.resetBaseVelocity(self.robot, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        self._apply_physics_randomization()
        for joint_index in (0, 1):
            p.resetJointState(self.robot, joint_index, targetValue=0.0)
            # Frenar los motores: si no, conservan la orden del episodio
            # anterior y el robot arranca moviéndose durante el asentamiento.
            p.setJointMotorControl2(
                self.robot,
                joint_index,
                p.VELOCITY_CONTROL,
                targetVelocity=0.0,
                force=self.current_max_force,
            )

        self.step_count = 0
        self.prev_pos = start.copy()
        self.prev_action = np.zeros(2, dtype=np.float32)
        self.total_forward = 0.0

        # Dejar que la física se asiente antes de observar.
        for _ in range(8):
            p.stepSimulation()

        obs = self._get_obs()
        info = {
            "x": float(start[0]),
            "y": float(start[1]),
            "yaw": float(p.getEulerFromQuaternion(start_orn)[2]),
            "goal": self.goal,
            "collision": False,
            "flipped": False,
            "step": 0,
        }
        return obs, info

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action = np.clip(
            np.asarray(action, dtype=np.float32), -1.0, 1.0
        )
        left_speed = float(action[0]) * self.max_wheel_speed
        right_speed = float(action[1]) * self.max_wheel_speed

        p.setJointMotorControl2(
            self.robot,
            0,
            p.VELOCITY_CONTROL,
            targetVelocity=left_speed,
            force=self.current_max_force,
        )
        p.setJointMotorControl2(
            self.robot,
            1,
            p.VELOCITY_CONTROL,
            targetVelocity=right_speed,
            force=self.current_max_force,
        )

        for _ in range(self.substeps):
            p.stepSimulation()

        if self.render_mode == "human":
            self.render()

        pos, quat = p.getBasePositionAndOrientation(self.robot)
        pos = np.asarray(pos, dtype=np.float64)
        yaw = float(p.getEulerFromQuaternion(quat)[2])
        # Proyección sobre el rumbo de referencia (fijado al inicio del
        # episodio o al comenzar el movimiento PPO), no sobre el yaw
        # instantáneo. Así girar en círculos no acumula recompensa.
        forward_x = math.cos(self.reference_yaw)
        forward_y = math.sin(self.reference_yaw)

        delta_x = float(pos[0] - self.prev_pos[0])
        delta_y = float(pos[1] - self.prev_pos[1])
        delta_forward = delta_x * forward_x + delta_y * forward_y
        self.prev_pos = pos.copy()
        self.total_forward += delta_forward
        self.step_count += 1

        # Recompensa condicionada por comando, medida sobre el frente del
        # robot: +1 avanza, -1 retrocede, 0 se queda quieto. Usar el frente
        # (y no X global) hace que la política siga siendo correcta después
        # de cualquier giro y con rumbo inicial aleatorio.
        reward = 0.0
        ang_vel = None
        if self.goal > 0.5:
            reward += delta_forward * self.forward_reward_scale
        elif self.goal < -0.5:
            reward -= delta_forward * self.forward_reward_scale
        else:
            # "Quieto": castigo fuerte por cualquier deriva (en cualquier
            # dirección) y por velocidad residual, para que no se arrastre.
            reward -= (
                math.hypot(delta_x, delta_y)
                * self.forward_reward_scale
                * self.stop_drift_scale
            )
            if self.stop_velocity_penalty > 0.0:
                lin_vel, ang_vel = p.getBaseVelocity(self.robot)
                motion_sq = float(np.dot(lin_vel, lin_vel)) + 0.5 * float(
                    np.dot(ang_vel, ang_vel)
                )
                reward -= self.stop_velocity_penalty * motion_sq

        # Castigo al giro no comandado (yaw rate). Sin este término, la
        # política puede "hacer trampa" rotando para acumular avance frontal
        # (reward hacking), y en el robot real eso gasta batería y desgasta
        # las orugas.
        if self.yaw_rate_penalty > 0.0:
            if ang_vel is None:
                _, ang_vel = p.getBaseVelocity(self.robot)
            reward -= self.yaw_rate_penalty * abs(float(ang_vel[2]))

        reward -= self.time_penalty

        # Sim-to-real: penalizar cambios bruscos de acción (suavidad de
        # motores) y acciones demasiado grandes (consumo de batería).
        if self.action_rate_penalty > 0.0:
            delta_action = action - self.prev_action
            reward -= self.action_rate_penalty * float(
                np.dot(delta_action, delta_action)
            )
        if self.action_magnitude_penalty > 0.0:
            reward -= self.action_magnitude_penalty * float(
                np.dot(action, action)
            )
        # "Quieto": castigar directamente cualquier acción no nula. Sin esto,
        # el PPO puede aprender a arrastrarse lentamente en vez de frenar.
        if self.goal == 0.0 and self.stop_action_penalty > 0.0:
            reward -= self.stop_action_penalty * float(np.dot(action, action))
        self.prev_action = action.copy()

        collided = self._has_collision()
        flipped = self._is_flipped()

        terminated = False
        if collided:
            # Penalización exacta de -10 y fin del episodio.
            reward = -self.crash_penalty
            terminated = True
        if flipped:
            reward = -self.flip_penalty
            terminated = True

        truncated = self.step_count >= self.max_episode_steps

        obs = self._get_obs()
        info = {
            "x": float(pos[0]),
            "y": float(pos[1]),
            "yaw": yaw,
            "delta_x": delta_x,
            "delta_y": delta_y,
            "delta_forward": delta_forward,
            "forward": self.total_forward,
            "goal": self.goal,
            "collision": bool(collided),
            "flipped": bool(flipped),
            "step": self.step_count,
        }
        return obs, float(reward), bool(terminated), bool(truncated), info

    def render(self) -> None:
        if self.render_mode != "human":
            return
        pos, _ = p.getBasePositionAndOrientation(self.robot)
        p.resetDebugVisualizerCamera(
            cameraDistance=3.5,
            cameraYaw=40.0,
            cameraPitch=-25.0,
            cameraTargetPosition=pos,
        )

    def close(self) -> None:
        if getattr(self, "client_id", -1) >= 0:
            try:
                p.disconnect(self.client_id)
            finally:
                self.client_id = -1

    def __del__(self) -> None:
        self.close()


# ---------------------------------------------------------------------- #
# Prueba manual del entorno (acciones aleatorias)
# ---------------------------------------------------------------------- #
def _random_demo(render_mode: str | None) -> None:
    default_mesh = Path(__file__).with_name("walle_visual.obj")
    visual_mesh = str(default_mesh) if default_mesh.exists() else None
    env = WallEEnv(render_mode=render_mode, visual_mesh_path=visual_mesh)
    obs, info = env.reset()
    print("Observación inicial:", np.round(obs, 3))
    print("Acción aleatoria cada 60 Hz. Ctrl+C para salir.")

    try:
        for step in range(5000):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if step % 60 == 0:
                print(
                    f"step={step:4d} x={info['x']:+.2f} y={info['y']:+.2f} "
                    f"reward={reward:+.2f} terminated={terminated} "
                    f"truncated={truncated}"
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
    parser = argparse.ArgumentParser(description="Prueba del entorno WALL-E")
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Sin GUI (más rápido, para depurar)",
    )
    args = parser.parse_args()
    _random_demo(None if args.direct else "human")
