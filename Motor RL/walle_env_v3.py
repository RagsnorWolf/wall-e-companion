"""
WALL-E · Fase 5 — Explorador Autónomo V5 (LiDAR 72 a ras de suelo, obs 58D)

Entorno Gymnasium + PyBullet de nivel industrial para exploración autónoma.

Características V5:
- LiDAR 2D virtual de 72 rayos (cada 5°, 360°) con rayTestBatch (rápido).
  El plano de escaneo va a la altura de los pies y los rayos nacen en el
  centro del robot: ve lo que está a punto de tocar.
- Observación de 58 dimensiones:
    [x, y, qx, qy, qz, qw, vx, vy, vz, wx, wy, wz,
     goal, goal_bearing,
     s0..s35,            <- 36 rayos frontales (180°) normalizados [0,1]
     claridad_frontal,   <- 1 - min(frontal)/alcance
     distancia_minima,   <- 1 - min(72)/alcance
     obst_sin, obst_cos, <- rumbo del obstáculo más cercano
     libre_sin, libre_cos, <- dirección del hueco más ancho (escape)
     contacto, atascado] <- banderas de resolución de problemas
- Obstáculos complejos: cajas de alturas variadas, cilindros (postes),
  rampas inclinadas y paredes en forma de "L" (callejones sin salida).
- Fricción variable: zona de césped (mu=2.0) y zona de baldosa (mu=0.5).
- ChunkMapper 1x1 m: 0=desconocido, 1=libre, 2=obstáculo.
- Chocar NO termina el episodio: se castiga el contacto y se premia salir.

Sistema de recompensas múltiple:
    +10 por descubrir un chunk nuevo.
    -5  por evento de colisión.
    -0.25 por paso en contacto con algo sólido.
    +3  por soltarse del obstáculo retrocediendo.
    +2  por ganar distancia libre cuando estaba pegado (<0.40 m).
    -0.30 por acercarse todavía más a algo que ya tenía encima.
    -5  por quedarse quieto más de 1 segundo.
    +2  por cada segundo de movimiento continuo.
    -15 por quedar atrapado (3+ obstáculos a menos de 30 cm).
"""

from __future__ import annotations

import math
from typing import Any, List, Tuple

import gymnasium as gym
import numpy as np
import pybullet as p

from chunk_mapper import ChunkMapper

# Importamos todo lo necesario desde V2 para reutilizar su infraestructura.
# No tocamos walle_env_v2.py: creamos un entorno independiente basado en él.
from walle_env_v2 import WallEEnvV2, wrap_angle  # noqa: F401


# --------------------------------------------------------------------- #
# Constantes V4
# --------------------------------------------------------------------- #
LIDAR_RAYS = 72                 # LiDAR 2D completo (360°, cada 5°)
SENSOR_COUNT = 36               # rayos frontales incluidos en la observación
LIDAR_MAX_DIST = 6.0            # alcance máximo en metros
# El plano de escaneo va a la altura de los pies: así el LiDAR ve lo que
# WALL-E está a punto de tocar (cajas bajas, rampas, bordes) y no pasa por
# encima de obstáculos pequeños.
SENSOR_HEIGHT = 0.06            # altura del LiDAR sobre la base
# Los rayos nacen en el centro del robot y se excluye el propio cuerpo con
# parentObjectUniqueId. Antes nacían a 30 cm: al tocar una pared el origen
# quedaba DENTRO del obstáculo y el sensor se quedaba ciego justo al chocar.
LIDAR_ORIGIN_OFFSET = 0.0       # desplazamiento radial (0 = centro exacto)
# Hilos del barrido de rayos. Medido en esta build (Nov 2026), 72 rayos:
#   nt=0 -> 0.13 ms, nt=2 -> 0.10 ms, nt=4 -> 0.11 ms (en régimen estable).
# El primer escaneo con nt>0 paga la creación del pool (~75 ms) y, dentro de
# SubprocVecEnv, el pool multihilo de pybullet provoca un access violation que
# mata al worker (EOFError en el padre). Con nt=0 no hay pool y es igual de
# rápido: se deja en 0.
LIDAR_THREADS = 0

# Recompensas V4 (sistema múltiple)
CHUNK_DISCOVERY_REWARD = 10.0   # por cada celda nueva descubierta
COLLISION_PENALTY = -5.0        # por evento de colisión
IDLE_PENALTY = -5.0             # por quedarse quieto más de 1 segundo
MOVE_STREAK_BONUS = 2.0         # por cada segundo de movimiento continuo
TRAP_PENALTY = -15.0            # atrapado: 3+ obstáculos a menos de 30 cm
EXPLORATION_BONUS = 0.3         # shaping adicional por explorar
OBSTACLE_AVOID_BONUS = 0.1      # shaping por mantener distancia
CLOSE_OBSTACLE_PENALTY = -1.0   # shaping si un sensor está casi tocando

# Umbrales de detección
TRAP_RADIUS = 0.30              # metros
TRAP_MIN_OBSTACLES = 3          # obstáculos cercanos para considerar trampa
TRAP_COOLDOWN_STEPS = 120       # 2 s de enfriamiento tras castigar
IDLE_STEPS_THRESHOLD = 60       # 1 s a 60 Hz
MOVE_STREAK_THRESHOLD = 60      # 1 s de movimiento continuo
MOVE_EPS_M = 0.002              # desplazamiento mínimo por paso para "moverse"

# --- Resolución de problemas (prioridad del cerebro) -------------------- #
# Chocar ya NO termina el episodio: el robot tiene que aprender a salir.
CONTACT_PENALTY = -0.25         # por paso en contacto con algo sólido
ESCAPE_BONUS = 3.0              # por soltarse de un obstáculo retrocediendo
CLEARANCE_REWARD = 2.0          # por ganar distancia libre cuando estaba pegado
APPROACH_PENALTY = -0.30        # por acercarse a <0.40 m teniendo el frente libre
NEAR_OBSTACLE_M = 0.40          # "pegado": por debajo de esto hay que maniobrar
FREE_RAY_M = 1.20               # rayo que cuenta como espacio libre transitable
STUCK_SPEED = 0.03              # m/s por debajo de esto el robot está atascado
STUCK_STEPS = 45                # 0.75 s sin moverse = bandera de atascado

# Umbral de contacto real. PyBullet mantiene en getContactPoints los pares de
# broadphase con normalForce=0 y sin penetración: contarlos como choque hacía
# que WALL-E se declarara bloqueado en mitad de la nada.
COLLISION_MIN_FORCE = 0.02      # N de fuerza normal mínima para contar
COLLISION_MIN_PENETRATION_M = 0.001  # 1 mm de penetración mínima

# Observación extendida: 14 base + 36 LiDAR + 8 de resolución de problemas.
OBS_EXTRAS = 8
OBS_DIM = 14 + SENSOR_COUNT + OBS_EXTRAS


class WallEEnvV3(WallEEnvV2):
    """Entorno V4: LiDAR 72 + obstáculos complejos + recompensas múltiples."""

    # ------------------------------------------------------------------ #
    # Constructor
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        render_mode: str | None = None,
        stage: int = 3,
        max_episode_steps: int | None = None,
        max_wheel_speed: float = 2.5,
        max_force: float = 0.5,
        arena_half_size: float = 12.0,
        visual_mesh_path: str | None = None,
        show_proxy_visuals: bool = True,
        randomize_mass: bool = True,
        total_mass_range: tuple[float, float] = (3.0, 6.0),
        wheel_mass: float = 0.45,
        wheel_friction_range: tuple[float, float] = (1.6, 2.1),
        obstacle_count: int = 6,
        stage3_min_obstacle_distance: float = 2.5,
        obstacle_max_distance: float = 10.0,
        obstacle_min_separation: float = 1.5,
        tilt_limit_deg: float = 15.0,
        tilt_grace_steps: int = 3,
        tilt_penalty: float = 1.0,
        flip_penalty: float = 10.0,
        crash_penalty: float = 10.0,
        time_penalty: float = 0.01,
        forward_reward_scale: float = 20.0,
        # V4-specific
        enable_sensors: bool = True,
        sensor_noise_std: float = 0.0,
        connect_options: str | None = None,
        # Resolución de problemas: chocar no termina el episodio.
        collision_terminates: bool = False,
        # Destino opcional de las velocidades de oruga (robot real).
        wheel_sink: Any = None,
    ) -> None:
        # ── Inicializar atributos V4 ANTES de super().__init__ (que llama a reset) ──
        self._enable_sensors = enable_sensors
        self._sensor_noise_std = sensor_noise_std
        self._collision_terminates = bool(collision_terminates)

        # LiDAR 2D de 72 rayos
        self.lidar_rays = LIDAR_RAYS
        self.lidar_max_dist = LIDAR_MAX_DIST
        self.lidar_meters = np.full(
            LIDAR_RAYS, LIDAR_MAX_DIST, dtype=np.float32
        )
        self.lidar_norm = np.ones(LIDAR_RAYS, dtype=np.float32)
        # Índices de los 36 rayos frontales (180°) para la observación.
        # Los rayos van de 0° a 355° en pasos de 5°; el frente del robot es
        # el rayo 0, así que el semicírculo frontal son 54..71 y 0..17.
        self._front_indices: List[int] = list(range(54, 72)) + list(
            range(0, 18)
        )

        # Chunk mapper
        self.chunk_mapper = ChunkMapper(cell_size=1.0)
        self._chunks_discovered_before_reset: int = 0

        # Estado interno de recompensas V4
        self._idle_steps = 0
        self._move_streak = 0
        self._idle_penalized = False
        self._trap_cooldown = 0
        self._last_pos: tuple[float, float] | None = None
        self._prev_collision = False

        # Estado de resolución de problemas
        self._contact_flag = False
        self._contact_points: list[tuple[float, float, float]] = []
        self._contact_normals: list[tuple[float, float, float]] = []
        self._was_in_contact = False
        self._escape_pending = 0
        self._escape_moved = 0.0
        self._contact_distance: float | None = None
        self._escaped_awarded = False
        self._stuck_steps = 0
        self._prev_nearest = LIDAR_MAX_DIST
        self._prev_front_min = LIDAR_MAX_DIST

        # Obstáculos extra V4 (se llenan en _build_obstacles)
        self.cylinder_ids: List[int] = []
        self.cylinder_radii: List[float] = []
        self.cylinder_positions: List[Tuple[float, float]] = []
        self.long_wall_ids: List[int] = []
        self.long_wall_positions: List[Tuple[float, float]] = []
        self.ramp_ids: List[int] = []
        self.ramp_positions: List[Tuple[float, float]] = []
        self.l_wall_ids: List[int] = []
        self.l_wall_positions: List[Tuple[float, float]] = []
        self.friction_zone_ids: List[int] = []

        super().__init__(
            render_mode=render_mode,
            stage=stage,
            max_episode_steps=max_episode_steps,
            max_wheel_speed=max_wheel_speed,
            max_force=max_force,
            arena_half_size=arena_half_size,
            visual_mesh_path=visual_mesh_path,
            show_proxy_visuals=show_proxy_visuals,
            randomize_mass=randomize_mass,
            total_mass_range=total_mass_range,
            wheel_mass=wheel_mass,
            wheel_friction_range=wheel_friction_range,
            obstacle_count=obstacle_count,
            stage12_min_obstacle_distance=8.0,
            stage3_min_obstacle_distance=stage3_min_obstacle_distance,
            obstacle_max_distance=obstacle_max_distance,
            obstacle_min_separation=obstacle_min_separation,
            tilt_limit_deg=tilt_limit_deg,
            tilt_grace_steps=tilt_grace_steps,
            tilt_penalty=tilt_penalty,
            flip_penalty=flip_penalty,
            crash_penalty=crash_penalty,
            time_penalty=time_penalty,
            forward_reward_scale=forward_reward_scale,
            connect_options=connect_options,
            collision_terminates=self._collision_terminates,
            wheel_sink=wheel_sink,
        )

        self.reference_yaw = 0.0

        # Espacio de observación V5 (58D = 14 base + 36 frontales + 8 extras).
        # Los tres bloques se declaran explícitamente: antes la lista de bounds
        # sólo cubría 14 + SENSOR_COUNT y el espacio quedaba en 50D mientras
        # _get_obs devolvía 58D, lo que rompía el LSTM de RecurrentPPO con
        # "shape [1, -1, 50] is invalid for input of size 58".
        base_low = [
            -self.arena_half_size,   # x
            -self.arena_half_size,   # y
            -1.0, -1.0, -1.0, -1.0,  # orientación (sin/cos)
            -10.0, -10.0, -10.0,     # velocidad lineal
            -20.0, -20.0, -20.0,     # velocidad angular
            -1.0,                    # heading normalizado
            -math.pi,                # error de rumbo
        ]
        sensor_low = [0.0] * SENSOR_COUNT
        # 50..57: claridad frontal, distancia mínima, seno y coseno del rumbo
        # al obstáculo, seno y coseno del hueco libre, contacto y atascado.
        extras_low = [0.0, 0.0, -1.0, -1.0, -1.0, -1.0, 0.0, 0.0]

        obs_low = np.array(
            base_low + sensor_low + extras_low, dtype=np.float32
        )
        obs_high = np.array(
            [
                self.arena_half_size,
                self.arena_half_size,
                1.0, 1.0, 1.0, 1.0,
                10.0, 10.0, 10.0,
                20.0, 20.0, 20.0,
                1.0,
                math.pi,
            ]
            + [1.0] * SENSOR_COUNT
            + [1.0] * OBS_EXTRAS,
            dtype=np.float32,
        )

        if obs_low.size != OBS_DIM:  # nunca debe dispararse: falla ruidoso
            raise RuntimeError(
                f"observation_space mal dimensionado: {obs_low.size} != {OBS_DIM}"
            )

        self.observation_space = gym.spaces.Box(
            low=obs_low, high=obs_high, dtype=np.float32
        )

    # ------------------------------------------------------------------ #
    # Construcción de obstáculos V4
    # ------------------------------------------------------------------ #
    def _build_obstacles(self) -> None:
        super()._build_obstacles()  # cajas de alturas variadas (V2)

        # Cilindros (postes)
        self.cylinder_ids = []
        self.cylinder_radii = []
        for i in range(max(2, self.obstacle_count // 2)):
            radius = float(self.np_random.uniform(0.15, 0.40))
            height = float(self.np_random.uniform(0.6, 2.0))
            collision = p.createCollisionShape(
                p.GEOM_CYLINDER, radius=radius, height=height
            )
            visual = p.createVisualShape(
                p.GEOM_CYLINDER,
                radius=radius,
                length=height,
                rgbaColor=[0.6, 0.6, 0.62, 1.0],
            )
            body = p.createMultiBody(
                baseMass=0.0,
                baseCollisionShapeIndex=collision,
                baseVisualShapeIndex=visual,
                basePosition=[0.0, 14.0 + i * 2.5, height / 2.0],
            )
            p.changeDynamics(body, -1, lateralFriction=0.9, restitution=0.0)
            self.cylinder_ids.append(body)
            self.cylinder_radii.append(radius)

        # Paredes largas que bordean la arena
        self._build_long_walls()
        # Rampas inclinadas
        self._build_ramps()
        # Paredes en forma de L (callejones sin salida)
        self._build_l_walls()
        # Zonas de fricción variable
        self._build_friction_zones()

        # Sombras en la GUI (entorno más realista)
        try:
            info = p.getConnectionInfo()
            if int(info.get("connectionMethod", -1)) == int(p.GUI):
                p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1)
        except Exception:
            pass

        # Estética neutral: blanco / gris claro / negro para que el
        # láser azul del LiDAR destaque sobre los obstáculos.
        neutral_palette = [
            (0.92, 0.92, 0.92, 1.0),  # blanco
            (0.60, 0.60, 0.62, 1.0),  # gris claro
            (0.10, 0.10, 0.12, 1.0),  # negro
        ]
        all_bodies = (
            self.obstacle_ids
            + self.cylinder_ids
            + self.long_wall_ids
            + self.ramp_ids
            + self.l_wall_ids
        )
        for index, body in enumerate(all_bodies):
            try:
                p.changeVisualShape(
                    body, -1, rgbaColor=list(neutral_palette[index % 3])
                )
            except Exception:
                pass

    def _build_long_walls(self) -> None:
        """Paredes largas que bordean el área de exploración."""
        half = self.arena_half_size
        length = 2.0 * half + 2.0
        half_len = length / 2.0
        wall_thickness = 0.3
        wall_half_height = 0.8
        wall_color = [0.30, 0.30, 0.33, 1.0]

        self.long_wall_positions = []
        for pos, half_extents in [
            ([half + wall_thickness, 0.0, wall_half_height],
             [wall_thickness, half_len, wall_half_height]),
            ([-half - wall_thickness, 0.0, wall_half_height],
             [wall_thickness, half_len, wall_half_height]),
            ([0.0, half + wall_thickness, wall_half_height],
             [half_len, wall_thickness, wall_half_height]),
            ([0.0, -half - wall_thickness, wall_half_height],
             [half_len, wall_thickness, wall_half_height]),
        ]:
            collision = p.createCollisionShape(
                p.GEOM_BOX, halfExtents=half_extents
            )
            visual = p.createVisualShape(
                p.GEOM_BOX, halfExtents=half_extents,
                rgbaColor=wall_color,
            )
            body = p.createMultiBody(
                baseMass=0.0,
                baseCollisionShapeIndex=collision,
                baseVisualShapeIndex=visual,
                basePosition=pos,
            )
            p.changeDynamics(body, -1, lateralFriction=0.9, restitution=0.0)
            self.long_wall_ids.append(body)
            self.long_wall_positions.append((pos[0], pos[1]))

    def _build_ramps(self) -> None:
        """Rampas inclinadas (pendientes) para física compleja.

        Antes eran cajas de 6 cm flotando a z=0.22 con 18°: el borde bajo
        quedaba a 12 cm del suelo y el alto a 0.56 m, así que para WALL-E
        (0.35 m de largo, ruedas de 9 cm) eran un escalón, no una rampa. Se
        subía de lado, patinaba y se quedaba clavado. Ahora el borde bajo
        queda enrasado con el suelo y la pendiente es de 10°.
        """
        self.ramp_ids = []
        self.ramp_positions = []
        half_len = 1.1
        thickness = 0.06
        specs = [
            (4.5, -3.5, math.radians(10.0)),
            (-4.0, 4.5, math.radians(-10.0)),
        ]
        for x, y, pitch in specs:
            half_extents = [half_len, 0.9, thickness]
            # Centro a media altura del plano inclinado, hundido medio grosor
            # para que la cara superior del borde bajo toque el suelo.
            z = half_len * abs(math.sin(pitch)) - thickness * 0.5
            collision = p.createCollisionShape(
                p.GEOM_BOX, halfExtents=half_extents
            )
            visual = p.createVisualShape(
                p.GEOM_BOX,
                halfExtents=half_extents,
                rgbaColor=[0.55, 0.55, 0.58, 1.0],
            )
            quat = p.getQuaternionFromEuler([0.0, pitch, 0.0])
            body = p.createMultiBody(
                baseMass=0.0,
                baseCollisionShapeIndex=collision,
                baseVisualShapeIndex=visual,
                basePosition=[x, y, z],
                baseOrientation=quat,
            )
            p.changeDynamics(body, -1, lateralFriction=1.0, restitution=0.0)
            self.ramp_ids.append(body)
            self.ramp_positions.append((x, y))

    def _build_l_walls(self) -> None:
        """Paredes en forma de L que crean callejones sin salida."""
        self.l_wall_ids = []
        self.l_wall_positions = []
        length = 2.2
        height = 0.9
        thickness = 0.15
        for cx, cy in [(4.0, 3.0), (-4.5, -3.5)]:
            # Pared A: a lo largo del eje X, centrada en (cx, cy)
            half_a = [length / 2.0, thickness / 2.0, height / 2.0]
            # Pared B: a lo largo del eje Y, arranca en el extremo de A
            half_b = [thickness / 2.0, length / 2.0, height / 2.0]
            pos_b = [cx + length / 2.0, cy + length / 2.0, height / 2.0]
            for half_extents, position in [
                (half_a, [cx, cy, height / 2.0]),
                (half_b, pos_b),
            ]:
                collision = p.createCollisionShape(
                    p.GEOM_BOX, halfExtents=half_extents
                )
                visual = p.createVisualShape(
                    p.GEOM_BOX,
                    halfExtents=half_extents,
                    rgbaColor=[0.35, 0.35, 0.38, 1.0],
                )
                body = p.createMultiBody(
                    baseMass=0.0,
                    baseCollisionShapeIndex=collision,
                    baseVisualShapeIndex=visual,
                    basePosition=position,
                )
                p.changeDynamics(
                    body, -1, lateralFriction=0.9, restitution=0.0
                )
                self.l_wall_ids.append(body)
                self.l_wall_positions.append((position[0], position[1]))

    def _build_friction_zones(self) -> None:
        """Zonas de fricción variable: césped (2.0) y baldosa (0.5).

        Solo existen como colisión: no llevan forma visual para que el suelo
        del estudio se vea uniforme, sin parches de color ni cajas negras.
        """
        self.friction_zone_ids = []
        zones = [
            # (posición, semiejes, fricción)
            ([3.5, 3.5, 0.006], [3.0, 3.0, 0.006], 2.0),   # césped
            ([-3.5, -3.5, 0.006], [3.0, 3.0, 0.006], 0.5),  # baldosa
        ]
        # PyBullet dibuja los cuerpos sin forma visual con colores por
        # defecto (amarillo/verde). Por eso cada zona lleva una losa visual
        # fina, del color del suelo y a ras del piso: invisible en la escena.
        zone_color = [0.26, 0.26, 0.28, 1.0]
        for position, half_extents, mu in zones:
            collision = p.createCollisionShape(
                p.GEOM_BOX, halfExtents=half_extents
            )
            visual = p.createVisualShape(
                p.GEOM_BOX,
                halfExtents=[half_extents[0], half_extents[1], 0.001],
                rgbaColor=zone_color,
                visualFramePosition=[0.0, 0.0, -0.005],
            )
            body = p.createMultiBody(
                baseMass=0.0,
                baseCollisionShapeIndex=collision,
                baseVisualShapeIndex=visual,
                basePosition=position,
            )
            p.changeDynamics(body, -1, lateralFriction=mu, restitution=0.0)
            self.friction_zone_ids.append(body)

    def _place_obstacles(self) -> None:
        """Coloca cajas y cilindros lejos del robot, con separación mínima."""
        super()._place_obstacles()  # coloca las cajas de V2

        # Coloca cilindros también lejos del robot
        min_dist = self.stage3_min_obstacle_distance
        max_dist = min(
            self.obstacle_max_distance,
            self.arena_half_size - 2.0,
        )
        positions: List[Tuple[float, float]] = list(self.obstacle_positions)

        for body, radius in zip(self.cylinder_ids, self.cylinder_radii):
            chosen = None
            for _attempt in range(120):
                angle = float(self.np_random.uniform(0.0, 2.0 * math.pi))
                r = float(self.np_random.uniform(min_dist, max_dist))
                x = r * math.cos(angle)
                y = r * math.sin(angle)
                ok = all(
                    math.hypot(x - px, y - py)
                    >= self.obstacle_min_separation + radius
                    for px, py in positions
                )
                if ok:
                    chosen = (x, y)
                    break
            if chosen is None:
                chosen = (
                    float(self.np_random.uniform(-max_dist, max_dist)),
                    float(self.np_random.uniform(-max_dist, max_dist)),
                )
            positions.append(chosen)
            p.resetBasePositionAndOrientation(
                body, [chosen[0], chosen[1], 0.0], [0.0, 0.0, 0.0, 1.0]
            )

        self.cylinder_positions = [
            tuple(p.getBasePositionAndOrientation(body)[0][:2])
            for body in self.cylinder_ids
        ]

    # ------------------------------------------------------------------ #
    # LiDAR 2D de 72 rayos (rayTestBatch: una sola llamada por paso)
    # ------------------------------------------------------------------ #
    def _scan_lidar(self) -> None:
        """Escanea 360° con 72 rayos y cachea distancias reales y normalizadas.

        El plano de escaneo va a la altura de los pies (SENSOR_HEIGHT) y los
        rayos salen del centro del robot, excluyendo su propio cuerpo con
        parentObjectUniqueId. Así el sensor sigue viendo el obstáculo incluso
        cuando el chasis ya lo está tocando.
        """
        pos, quat = p.getBasePositionAndOrientation(self.robot)
        yaw = float(p.getEulerFromQuaternion(quat)[2])
        z = pos[2] + SENSOR_HEIGHT

        froms = []
        tos = []
        for i in range(LIDAR_RAYS):
            angle = yaw + 2.0 * math.pi * i / LIDAR_RAYS
            dx = math.cos(angle)
            dy = math.sin(angle)
            froms.append(
                [
                    pos[0] + dx * LIDAR_ORIGIN_OFFSET,
                    pos[1] + dy * LIDAR_ORIGIN_OFFSET,
                    z,
                ]
            )
            tos.append(
                [
                    pos[0] + dx * LIDAR_MAX_DIST,
                    pos[1] + dy * LIDAR_MAX_DIST,
                    z,
                ]
            )

        # La exclusión del propio robot SOLO funciona por nombre en esta
        # build. Pasada por posición (from, to, parent, link, threads) el
        # parentObjectUniqueId se ignora y cada rayo impacta el chasis a
        # fracción 0: medio anillo de ceros, "obstáculo a 0.00 m" delante
        # siempre, y WALL-E frenando en mitad de la nada. Por nombre excluye
        # de verdad (body=-1, frac=1.0 = sin impacto).
        results = p.rayTestBatch(
            froms,
            tos,
            parentObjectUniqueId=self.robot,
            parentLinkIndex=-1,
            numThreads=LIDAR_THREADS,
        )
        meters = np.empty(LIDAR_RAYS, dtype=np.float32)
        ray_len = LIDAR_MAX_DIST - LIDAR_ORIGIN_OFFSET
        for i, hit in enumerate(results):
            frac = float(hit[2])
            # Cinturón y tirantes: si alguna build vuelve a ignorar la
            # exclusión, un impacto contra el propio cuerpo no es distancia.
            if int(hit[0]) == self.robot:
                meters[i] = LIDAR_MAX_DIST
                continue
            # La distancia real desde el centro del robot es offset + frac*ray_len.
            dist = LIDAR_ORIGIN_OFFSET + frac * ray_len
            if self._sensor_noise_std > 0.0:
                dist += float(
                    self.np_random.normal(0.0, self._sensor_noise_std)
                )
            meters[i] = min(max(dist, 0.0), LIDAR_MAX_DIST)

        self.lidar_meters = meters
        self.lidar_norm = np.clip(
            1.0 - meters / LIDAR_MAX_DIST, 0.0, 1.0
        ).astype(np.float32)

    # ------------------------------------------------------------------ #
    # Resolución de problemas: geometría útil para decidir
    # ------------------------------------------------------------------ #
    def _nearest_ray(self) -> tuple[int, float]:
        """Rayo (índice) y distancia del obstáculo más cercano de los 72."""
        if self.lidar_meters.size == 0:
            return 0, LIDAR_MAX_DIST
        index = int(np.argmin(self.lidar_meters))
        return index, float(self.lidar_meters[index])

    def _free_direction(self) -> tuple[float, float]:
        """Dirección (sin, cos) del hueco libre más ancho, relativa al frente.

        Recorre el anillo de rayos y busca la tirada contigua más larga de
        rayos con distancia > FREE_RAY_M. Devuelve el centro angular de ese
        hueco: es la ruta de escape natural cuando está pegado a algo.
        """
        n = int(self.lidar_meters.size)
        if n == 0:
            return 0.0, 0.0
        free = self.lidar_meters > FREE_RAY_M
        if not free.any():
            return 0.0, 0.0
        if free.all():
            return 0.0, 1.0
        # Empezar en un rayo bloqueado rompe la circularidad.
        start = int(np.argmin(free))
        best_len = 0
        best_start = 0
        run_len = 0
        run_start = 0
        for k in range(n):
            idx = (start + k) % n
            if free[idx]:
                if run_len == 0:
                    run_start = k
                run_len += 1
                if run_len > best_len:
                    best_len = run_len
                    best_start = run_start
            else:
                run_len = 0
        step = 2.0 * math.pi / n
        mid = best_start + (best_len - 1) * 0.5
        angle = ((start + mid) * step + math.pi) % (2.0 * math.pi) - math.pi
        return math.sin(angle), math.cos(angle)

    def _problem_obs(self) -> np.ndarray:
        """8 valores que describen el problema inmediato del robot."""
        meters = self.lidar_meters
        max_d = float(self.lidar_max_dist)
        front = meters[self._front_indices]
        front_min = float(front.min()) if front.size else max_d
        index, nearest = self._nearest_ray()
        step = 2.0 * math.pi / max(1, int(meters.size))
        bearing = index * step
        bearing = (bearing + math.pi) % (2.0 * math.pi) - math.pi
        free_sin, free_cos = self._free_direction()
        return np.array(
            [
                float(np.clip(1.0 - front_min / max_d, 0.0, 1.0)),
                float(np.clip(1.0 - nearest / max_d, 0.0, 1.0)),
                math.sin(bearing),
                math.cos(bearing),
                free_sin,
                free_cos,
                1.0 if self._contact_flag else 0.0,
                1.0 if self._stuck_steps >= STUCK_STEPS else 0.0,
            ],
            dtype=np.float32,
        )

    # ------------------------------------------------------------------ #
    # Observación 58D (14 base + 36 frontales + 8 de resolución)
    # ------------------------------------------------------------------ #
    def _get_obs(self) -> np.ndarray:
        base_obs = super()._get_obs()  # 14D de V2
        if self._enable_sensors:
            self._scan_lidar()
            front = self.lidar_norm[self._front_indices]
            extras = self._problem_obs()
        else:
            front = np.ones(SENSOR_COUNT, dtype=np.float32)
            extras = np.zeros(OBS_EXTRAS, dtype=np.float32)
        return np.concatenate(
            [
                base_obs,
                np.asarray(front, dtype=np.float32),
                np.asarray(extras, dtype=np.float32),
            ],
            dtype=np.float32,
        )

    # ------------------------------------------------------------------ #
    # Chunk mapper - optimizado para rendimiento
    # ------------------------------------------------------------------ #
    def _update_chunk_mapper(self) -> None:
        """Actualiza el mapa de chunks con la posición actual y obstáculos."""
        pos = self._pose().pos if hasattr(self, "_pose") else None
        if pos is None:
            pos, _ = p.getBasePositionAndOrientation(self.robot)
        # Marcar celda actual como libre
        self.chunk_mapper.update_position(float(pos[0]), float(pos[1]))

        # Marcar celdas ocupadas solo por obstáculos cercanos (dentro de 8m)
        # para reducir carga computacional
        bodies = (
            self.obstacle_ids
            + self.cylinder_ids
            + self.long_wall_ids
            + self.l_wall_ids
            + self.ramp_ids
        )
        cx, cy = pos[0], pos[1]
        cell_size = self.chunk_mapper.cell_size
        for body in bodies:
            bpos, _ = p.getBasePositionAndOrientation(body)
            # Solo procesar obstáculos cerca del robot (rendimiento)
            if math.hypot(bpos[0] - cx, bpos[1] - cy) > 8.0:
                continue
            if body in self.cylinder_ids:
                idx = self.cylinder_ids.index(body)
                radius = self.cylinder_radii[idx]
            else:
                radius = 0.45
            bx, by = bpos[0], bpos[1]
            min_ix = int(math.floor((bx - radius) / cell_size))
            max_ix = int(math.floor((bx + radius) / cell_size))
            min_iy = int(math.floor((by - radius) / cell_size))
            max_iy = int(math.floor((by + radius) / cell_size))
            for ix in range(min_ix, max_ix + 1):
                for iy in range(min_iy, max_iy + 1):
                    cx_cell, cy_cell = self.chunk_mapper.cell_to_world(ix, iy)
                    if math.hypot(cx_cell - bx, cy_cell - by) <= radius:
                        self.chunk_mapper.cells[
                            (ix, iy)
                        ] = self.chunk_mapper.OBSTACLE

    def _count_new_discovered(self) -> int:
        """Devuelve cuántas celdas han cambiado de estado desde el último conteo."""
        current = len(self.chunk_mapper.cells)
        new_count = current - self._chunks_discovered_before_reset
        self._chunks_discovered_before_reset = current
        return max(0, new_count)

    def set_reference_yaw(self, yaw: float) -> None:
        """Fija el rumbo de referencia para la recompensa de avance."""
        self.reference_yaw = float(yaw)

    # ------------------------------------------------------------------ #
    # Detección de colisiones con TODOS los obstáculos V4
    # ------------------------------------------------------------------ #
    def _has_collision(self) -> bool:
        bodies = (
            self.wall_ids
            + self.obstacle_ids
            + self.cylinder_ids
            + self.long_wall_ids
            + self.ramp_ids
            + self.l_wall_ids
        )
        points: list[tuple[float, float, float]] = []
        normals: list[tuple[float, float, float]] = []
        for body_id in bodies:
            contacts = p.getContactPoints(bodyA=self.robot, bodyB=body_id)
            for contact in contacts:
                # Un punto de contacto NO es un choque. PyBullet deja pares
                # "fantasma" en la lista con normalForce=0 y sin penetración:
                # son candidatos de colisión de broadphase, no contacto real.
                # Contarlos hacía que WALL-E se declarara chocado en mitad de
                # la nada, se despegara y abandonara la orden.
                force = float(contact[9])
                penetration = float(contact[8])
                if force < COLLISION_MIN_FORCE and penetration > -COLLISION_MIN_PENETRATION_M:
                    continue
                # contact[5] = punto de contacto en el mundo.
                # contact[7] = normal en el cuerpo B.
                point = contact[5]
                normal = contact[7]
                points.append((float(point[0]), float(point[1]), float(point[2])))
                normals.append(
                    (float(normal[0]), float(normal[1]), float(normal[2]))
                )
        self._contact_points = points
        self._contact_normals = normals
        self._contact_flag = bool(points)
        return self._contact_flag

    def front_clearance(self, half_angle_deg: float = 30.0) -> float:
        """Distancia (m) al obstáculo más cercano del cono frontal.

        El abanico completo de 72 rayos barre 360°; `_front_indices` cubre
        ±90°, demasiado ancho para decidir "tengo algo delante". Aquí se
        recorta el cono a `half_angle_deg` alrededor del frente real (rayo 0 =
        rumbo del robot), que es la medida que usa el controlador para
        acelerar, modular o rodear.

        Devuelve `LIDAR_MAX_DIST` si el cono está despejado.
        """
        n = int(self.lidar_meters.size)
        if n == 0:
            return float(LIDAR_MAX_DIST)
        span = max(1, int(round(n * half_angle_deg / 360.0)))
        indices = [k % n for k in range(-span, span + 1)]
        cone = self.lidar_meters[indices]
        if cone.size == 0:
            return float(LIDAR_MAX_DIST)
        return float(cone.min())

    def contact_info(self) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
        """Puntos y normales de contacto del último paso (para la GUI)."""
        return list(zip(self._contact_points, self._contact_normals))

    def _count_close_sectors(self, radius: float) -> int:
        """Cuenta cuántos lados distintos están bloqueados a menos de `radius`.

        Usa el LiDAR de 72 rayos ya escaneado: agrupa los rayos consecutivos
        que detectan un obstáculo cercano en sectores angulares. Un callejón
        sin salida típico bloquea 3 sectores (frente, izquierda, derecha).
        """
        close = [float(d) <= radius for d in self.lidar_meters]
        n = len(close)
        if n == 0 or not any(close):
            return 0
        if all(close):
            return 4  # rodeado por completo
        # Romper la circularidad buscando un rayo libre.
        start = close.index(False)
        sectors = 0
        previous = False
        for k in range(n):
            current = close[(start + k) % n]
            if current and not previous:
                sectors += 1
            previous = current
        return sectors

    # ------------------------------------------------------------------ #
    # Reset y step con recompensas múltiples V4
    # ------------------------------------------------------------------ #
    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        self.chunk_mapper = ChunkMapper(cell_size=1.0)
        self._chunks_discovered_before_reset = 0
        # Estado de recompensas V4
        self._idle_steps = 0
        self._move_streak = 0
        self._idle_penalized = False
        self._trap_cooldown = 0
        self._last_pos = None
        self._prev_collision = False
        # Estado de resolución de problemas
        self._contact_flag = False
        self._contact_points = []
        self._contact_normals = []
        self._was_in_contact = False
        self._escape_pending = 0
        self._escape_moved = 0.0
        self._contact_distance = None
        self._escaped_awarded = False
        self._stuck_steps = 0
        self._prev_nearest = LIDAR_MAX_DIST
        self._prev_front_min = LIDAR_MAX_DIST
        return super().reset(seed=seed, options=options)

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        obs, reward, terminated, truncated, info = super().step(action)
        self._update_chunk_mapper()

        # ── 1) +10 por descubrir chunks nuevos ──
        new_chunks = self._count_new_discovered()
        if new_chunks > 0:
            reward += CHUNK_DISCOVERY_REWARD * new_chunks
            reward += EXPLORATION_BONUS * new_chunks

        # ── 2) -5 por colisión (una vez por evento) ──
        collided = bool(info.get("collision"))
        if collided and not self._prev_collision:
            reward += COLLISION_PENALTY
        self._prev_collision = collided

        # ── 3) Movimiento continuo / quieto ──
        pos, _ = p.getBasePositionAndOrientation(self.robot)
        moved = 0.0
        if self._last_pos is not None:
            moved = math.hypot(
                pos[0] - self._last_pos[0], pos[1] - self._last_pos[1]
            )
        self._last_pos = (float(pos[0]), float(pos[1]))

        if moved > MOVE_EPS_M:
            self._idle_steps = 0
            self._idle_penalized = False
            self._stuck_steps = 0
            self._move_streak += 1
            if self._move_streak >= MOVE_STREAK_THRESHOLD:
                reward += MOVE_STREAK_BONUS
                self._move_streak = 0
        else:
            self._move_streak = 0
            self._idle_steps += 1
            self._stuck_steps += 1
            if (
                self._idle_steps >= IDLE_STEPS_THRESHOLD
                and not self._idle_penalized
            ):
                reward += IDLE_PENALTY
                self._idle_penalized = True

        # ── 4) -15 por quedar atrapado (3+ lados bloqueados a <30 cm) ──
        if self._trap_cooldown > 0:
            self._trap_cooldown -= 1
        else:
            sectors = self._count_close_sectors(TRAP_RADIUS)
            if sectors >= TRAP_MIN_OBSTACLES:
                reward += TRAP_PENALTY
                self._trap_cooldown = TRAP_COOLDOWN_STEPS
                info["trapped"] = True
                info["trap_sectors"] = sectors

        # ── 5) Shaping suave de proximidad con los sensores frontales ──
        # lidar_norm: 0 = libre (sin obstáculo), 1 = obstáculo encima.
        sensor_slice = obs[14 : 14 + SENSOR_COUNT]
        max_sensor = (
            float(np.max(sensor_slice)) if self._enable_sensors else 0.0
        )
        if max_sensor > 0.85:
            # Algún rayo frontal detecta algo a menos de ~0.9 m.
            reward += CLOSE_OBSTACLE_PENALTY
        elif max_sensor < 0.50:
            # Todo el frente está despejado a más de 3 m.
            reward += OBSTACLE_AVOID_BONUS

        # ── 6) Resolución de problemas: contacto, escape y distancia ──
        # Chocar ya no termina el episodio (collision_terminates=False): lo
        # que se premia es salir del atasco, no morir en él.
        contact = self._contact_flag
        nearest = (
            float(self.lidar_meters.min())
            if self._enable_sensors
            else LIDAR_MAX_DIST
        )
        front_min = (
            float(self.lidar_meters[self._front_indices].min())
            if self._enable_sensors
            else LIDAR_MAX_DIST
        )
        if contact:
            reward += CONTACT_PENALTY

        # Escapar: se recuerda la distancia al obstáculo en el momento del
        # contacto y se premia cuando el robot consigue 8 cm de holgura real.
        if contact:
            if not self._was_in_contact:
                self._contact_distance = nearest
                self._escaped_awarded = False
        elif (
            self._contact_distance is not None
            and not self._escaped_awarded
            and nearest > self._contact_distance + 0.08
        ):
            reward += ESCAPE_BONUS
            self._escaped_awarded = True
            self._contact_distance = None

        if self._enable_sensors:
            if self._prev_nearest < NEAR_OBSTACLE_M:
                if nearest > self._prev_nearest + 0.005:
                    # Ganó distancia libre estando pegado: buena maniobra.
                    reward += CLEARANCE_REWARD * min(
                        1.0, (nearest - self._prev_nearest) / 0.20
                    )
                elif nearest < self._prev_nearest - 0.005:
                    # Se acercó aún más a algo que ya tenía encima.
                    reward += APPROACH_PENALTY
            self._prev_nearest = nearest
            self._prev_front_min = front_min

        self._was_in_contact = contact

        info["chunks_discovered"] = new_chunks
        info["max_sensor"] = max_sensor
        info["sensor_readings"] = (
            sensor_slice.tolist() if self._enable_sensors else []
        )
        info["nearest_obstacle_m"] = nearest
        info["front_clearance_m"] = front_min
        info["contact"] = contact
        info["stuck"] = self._stuck_steps >= STUCK_STEPS
        info["free_direction"] = (
            self._free_direction() if self._enable_sensors else (0.0, 0.0)
        )
        return obs, float(reward), bool(terminated), bool(truncated), info

    def _pose(self):
        pos, quat = p.getBasePositionAndOrientation(self.robot)
        yaw = float(p.getEulerFromQuaternion(quat)[2])
        return type("Pose", (), {"pos": pos, "yaw": yaw})()


# ---------------------------------------------------------------------- #
# Prueba rápida
# ---------------------------------------------------------------------- #
def _quick_test(render_mode: str | None = None) -> None:
    env = WallEEnvV3(render_mode=render_mode, stage=3, obstacle_count=6)
    obs, info = env.reset()
    print("Observación inicial (58D):", np.round(obs, 3), "shape:", obs.shape)
    print("LiDAR 72:", np.round(env.lidar_meters[:8], 2), "...")
    print("Frontales 36:", np.round(obs[14:50], 3))
    print("Resolución:", np.round(obs[50:], 3))
    for _ in range(10):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
    env.close()


if __name__ == "__main__":
    _quick_test()
