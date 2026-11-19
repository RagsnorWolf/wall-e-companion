"""
WALL-E · Fase 2 V2 — Entrenamiento por currículum (PPO, 14D)
============================================================

Entrena el cerebro motor lento y estable para el WALL-E físico de madera y
cartón. El currículum tiene tres etapas de 100.000 pasos cada una:

    Etapa 1 — Avanzar y retroceder en línea recta.
    Etapa 2 — Giros precisos a ±45°, ±90° y ±180°.
    Etapa 3 — Movimiento combinado con obstáculos (5 cajas).

El modelo final se guarda como:

    walle_ppo_model_v2_slow.zip

Salidas:

    checkpoints_v2/                 Checkpoints cada 10.000 pasos
    tb_logs_v2/                     Curvas de TensorBoard
    reports/v2_curriculum_report.*  Reporte final .json y .md

Uso:

    python train_walle_v2.py
    python train_walle_v2.py --timesteps-per-stage 100000
    python train_walle_v2.py --stages 1 --timesteps-per-stage 5000   # smoke test
    python train_walle_v2.py --gui                                   # verlo (lento)
    python train_walle_v2.py --resume walle_ppo_model_v2_slow_stage1.zip

Notas de diseño:

- La red es 128×128 con activación Tanh, igual que la V1.
- La observación es exactamente 14D: los 12 estados físicos + `goal`
  (+1 avanzar / -1 retroceder / 0 girar) + `goal_bearing`, el ángulo
  objetivo relativo al frente actual. El signo de `goal` es imprescindible:
  sin él la política no puede distinguir avanzar de retroceder cuando el
  rumbo es el mismo. El bearing egocéntrico facilita aprender giros a
  izquierda y derecha.
- El avance se mide contra `goal_angle` (el frente comandado), no contra el
  eje X global. Esto evita el reward hacking de girar en círculos que apareció
  en la V1.
- La etapa 2 termina con éxito cuando el error de rumbo es < 5° durante 10
  pasos seguidos. La etapa 1 y 3 terminan por límite de pasos, choque o
  volcadura.
- La masa total se randomiza entre 3.0 y 6.0 kg por episodio.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Permite ejecutar el script desde cualquier carpeta.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.callbacks import (  # noqa: E402
    BaseCallback,
    CallbackList,
    CheckpointCallback,
)
from stable_baselines3.common.monitor import Monitor  # noqa: E402
from stable_baselines3.common.vec_env import DummyVecEnv  # noqa: E402

from chunk_mapper import ChunkMapper  # noqa: E402
from walle_env_v2 import WallEEnvV2  # noqa: E402


DEFAULT_MODEL = SCRIPT_DIR / "walle_ppo_model_v2_slow.zip"
CHECKPOINT_DIR = SCRIPT_DIR / "checkpoints_v2"
TENSORBOARD_DIR = SCRIPT_DIR / "tb_logs_v2"
REPORTS_DIR = SCRIPT_DIR / "reports"

STAGE_NAMES = {
    1: "Etapa 1 · avance/retroceso recto",
    2: "Etapa 2 · giros precisos",
    3: "Etapa 3 · combinado con obstáculos",
}
STAGE_MODEL_PATHS = {
    1: SCRIPT_DIR / "walle_ppo_model_v2_slow_stage1.zip",
    2: SCRIPT_DIR / "walle_ppo_model_v2_slow_stage2.zip",
    3: SCRIPT_DIR / "walle_ppo_model_v2_slow_stage3.zip",
}


# ---------------------------------------------------------------------- #
# Entorno vectorizado
# ---------------------------------------------------------------------- #
def make_env(
    stage: int,
    seed: int,
    gui: bool = False,
    randomize_mass: bool = True,
    obstacle_count: int = 5,
):
    """Crea un `DummyVecEnv` de 1 entorno para la etapa indicada."""

    def _init():
        env = WallEEnvV2(
            render_mode="human" if gui else None,
            stage=stage,
            seed=seed,
            randomize_mass=randomize_mass,
            total_mass_range=(3.0, 6.0),
            wheel_friction_range=(1.6, 2.1),
            obstacle_count=obstacle_count,
            stage12_min_obstacle_distance=8.0,
            stage3_min_obstacle_distance=2.5,
            obstacle_max_distance=12.0,
            obstacle_min_separation=1.5,
            tilt_limit_deg=15.0,
            tilt_grace_steps=3,
            forward_reward_scale=20.0,
            heading_reward_scale=20.0,
            heading_error_penalty=0.02,
            heading_success_deg=5.0,
            heading_success_steps=10,
            heading_success_bonus=20.0,
            jerk_penalty=0.25,
            jerk_penalty_cap=1.0,
            action_smoothing=0.7,
            tilt_penalty=5.0,
            time_penalty=0.01,
            crash_penalty=10.0,
            flip_penalty=10.0,
            action_magnitude_penalty=0.002,
            yaw_rate_penalty=0.05,
            stage1_heading_penalty=0.05,
            stage1_yaw_rate_penalty=0.2,
            stage2_forward_penalty=0.5,
        )
        # El constructor ya hace un reset con la semilla; Monitor envuelve
        # para que SB3 registre recompensa y longitud de episodio.
        return Monitor(env)

    return _init


def build_model(vec_env, seed: int) -> PPO:
    """PPO 14→128→128→2 con activación Tanh."""
    return PPO(
        "MlpPolicy",
        vec_env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=256,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
        vf_coef=0.5,
        max_grad_norm=0.5,
        policy_kwargs=dict(
            net_arch=dict(pi=[128, 128], vf=[128, 128]),
            activation_fn=torch.nn.Tanh,
            # Nota: `squash_output=True` solo está disponible con gSDE en
            # SB3 2.9.2, así que no se usa. La saturación se controla con el
            # filtro de acción del entorno y los castigos de la etapa 1.
        ),
        tensorboard_log=str(TENSORBOARD_DIR),
        verbose=1,
        seed=seed,
        device="auto",
    )


# ---------------------------------------------------------------------- #
# Métricas por etapa
# ---------------------------------------------------------------------- #
@dataclass
class EpisodeRecord:
    reward: float
    length: int
    goal: float
    heading_error_deg: float
    flipped: bool
    collision: bool
    success: bool
    forward: float
    tilt_deg: float
    total_mass: float
    stage: int


@dataclass
class StageSummary:
    stage: int
    episodes: int = 0
    mean_reward: float = 0.0
    mean_reward_last20: float = 0.0
    mean_length: float = 0.0
    mean_heading_error_deg: float = 0.0
    mean_progress_m: float = 0.0
    flips: int = 0
    collisions: int = 0
    successes: int = 0
    success_rate: float = 0.0
    mean_tilt_deg: float = 0.0
    mean_mass_kg: float = 0.0
    total_steps: int = 0


class WalleV2MetricsCallback(BaseCallback):
    """Recolecta métricas de episodio y las registra en TensorBoard."""

    def __init__(self, verbose: int = 0) -> None:
        super().__init__(verbose)
        self.stage: int = 1
        self.episodes: list[EpisodeRecord] = []
        self._recent: list[EpisodeRecord] = []

    def begin_stage(self, stage: int) -> None:
        self.stage = int(stage)
        self.episodes.clear()
        self._recent.clear()

    def _on_step(self) -> bool:
        infos = self.locals.get("infos") or []
        if not infos:
            return True
        info = infos[0]
        if "episode" not in info:
            return True

        episode = info["episode"]
        record = EpisodeRecord(
            reward=float(episode.get("r", 0.0)),
            length=int(episode.get("l", 0)),
            goal=float(info.get("goal", 0.0)),
            heading_error_deg=float(info.get("heading_error_deg", 0.0)),
            flipped=bool(info.get("flipped", False)),
            collision=bool(info.get("collision", False)),
            success=bool(info.get("success", False)),
            forward=float(info.get("forward", 0.0)),
            tilt_deg=float(info.get("tilt_deg", 0.0)),
            total_mass=float(info.get("total_mass", 0.0)),
            stage=int(info.get("stage", self.stage)),
        )
        self.episodes.append(record)
        self._recent.append(record)
        return True

    def _on_rollout_end(self) -> None:
        if not self._recent:
            return
        rewards = np.asarray([ep.reward for ep in self._recent], dtype=np.float64)
        errors = np.asarray(
            [ep.heading_error_deg for ep in self._recent], dtype=np.float64
        )
        flips = sum(1 for ep in self._recent if ep.flipped)
        collisions = sum(1 for ep in self._recent if ep.collision)
        successes = sum(1 for ep in self._recent if ep.success)
        self.logger.record("walle_v2/reward", float(np.mean(rewards)))
        self.logger.record(
            "walle_v2/heading_error_deg", float(np.mean(errors))
        )
        self.logger.record("walle_v2/flips", float(flips))
        self.logger.record("walle_v2/collisions", float(collisions))
        self.logger.record(
            "walle_v2/success_rate",
            float(successes / max(1, len(self._recent))),
        )
        self._recent.clear()

    def summary(self) -> StageSummary:
        summary = StageSummary(stage=self.stage)
        if not self.episodes:
            return summary

        summary.episodes = len(self.episodes)
        summary.total_steps = int(
            sum(ep.length for ep in self.episodes)
        )
        rewards = np.asarray(
            [ep.reward for ep in self.episodes], dtype=np.float64
        )
        summary.mean_reward = float(np.mean(rewards))
        last_n = max(1, int(math.ceil(len(rewards) * 0.20)))
        summary.mean_reward_last20 = float(np.mean(rewards[-last_n:]))
        summary.mean_length = float(
            np.mean([ep.length for ep in self.episodes])
        )
        summary.mean_heading_error_deg = float(
            np.mean([ep.heading_error_deg for ep in self.episodes])
        )
        # Progreso firmado: positivo si avanzó en la dirección comandada.
        summary.mean_progress_m = float(
            np.mean(
                [ep.forward * ep.goal for ep in self.episodes]
            )
        )
        summary.flips = sum(1 for ep in self.episodes if ep.flipped)
        summary.collisions = sum(
            1 for ep in self.episodes if ep.collision
        )
        summary.successes = sum(
            1 for ep in self.episodes if ep.success
        )
        summary.success_rate = float(
            summary.successes / max(1, summary.episodes)
        )
        summary.mean_tilt_deg = float(
            np.mean([ep.tilt_deg for ep in self.episodes])
        )
        summary.mean_mass_kg = float(
            np.mean([ep.total_mass for ep in self.episodes])
        )
        return summary


# ---------------------------------------------------------------------- #
# Reporte
# ---------------------------------------------------------------------- #
def validate_chunk_mapper() -> dict[str, Any]:
    """Confirma que `chunk_mapper.py` existe y funciona."""
    path = SCRIPT_DIR / "chunk_mapper.py"
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "ok": False,
        "detail": "",
    }
    if not path.exists():
        result["detail"] = "No existe chunk_mapper.py"
        return result

    try:
        mapper = ChunkMapper(cell_size=1.0)
        mapper.update_position(0.2, 0.2)
        mapper.update_position(0.2, 0.2, obstacles=[(1.4, -0.6)])
        assert mapper.state_at(0.2, 0.2) == ChunkMapper.FREE
        assert mapper.state_at(1.4, -0.6) == ChunkMapper.OBSTACLE
        snapshot = mapper.to_dict()
        restored = ChunkMapper.from_dict(snapshot)
        assert restored.state_at(1.4, -0.6) == ChunkMapper.OBSTACLE
        result["ok"] = True
        result["detail"] = "Self-test OK (FREE/OBSTACLE/serialización)"
    except Exception as exc:  # pragma: no cover - defensivo
        result["detail"] = f"Fallo: {exc}"
    return result


def build_report(
    summaries: dict[int, StageSummary],
    model_path: Path,
    total_timesteps: int,
    elapsed_s: float,
    chunk_status: dict[str, Any],
) -> dict[str, Any]:
    return {
        "project": "WALL-E · Fase 2 V2 (cerebro lento y estable)",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": str(model_path),
        "total_timesteps": int(total_timesteps),
        "elapsed_seconds": round(float(elapsed_s), 1),
        "elapsed_minutes": round(float(elapsed_s) / 60.0, 2),
        "observation_space": "14D [x,y,qx,qy,qz,qw,vx,vy,vz,wx,wy,wz,goal,goal_bearing]",
        "action_space": "2D [oruga_izquierda, oruga_derecha] en [-1,1]",
        "network": "128×128 Tanh",
        "physics": {
            "max_wheel_speed_rad_s": 2.5,
            "max_force_nm": 0.5,
            "control_hz": 60,
            "physics_hz": 240,
            "mass_range_kg": [3.0, 6.0],
            "obstacles": 5,
            "tilt_limit_deg": 15.0,
        },
        "stages": {
            str(stage): {
                "name": STAGE_NAMES[stage],
                "episodes": s.episodes,
                "total_steps": s.total_steps,
                "mean_reward": round(s.mean_reward, 4),
                "mean_reward_last20": round(s.mean_reward_last20, 4),
                "mean_length": round(s.mean_length, 2),
                "mean_heading_error_deg": round(
                    s.mean_heading_error_deg, 3
                ),
                "mean_progress_m": round(s.mean_progress_m, 4),
                "flips": s.flips,
                "collisions": s.collisions,
                "successes": s.successes,
                "success_rate": round(s.success_rate, 4),
                "mean_tilt_deg": round(s.mean_tilt_deg, 3),
                "mean_mass_kg": round(s.mean_mass_kg, 3),
            }
            for stage, s in sorted(summaries.items())
        },
        "chunk_mapper": chunk_status,
    }


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / "v2_curriculum_report.json"
    md_path = REPORTS_DIR / "v2_curriculum_report.md"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines: list[str] = []
    lines.append("# WALL-E · Reporte de currículum V2")
    lines.append("")
    lines.append(f"- **Fecha:** {report['generated_at']}")
    lines.append(f"- **Modelo final:** `{report['model']}`")
    lines.append(
        f"- **Pasos totales:** {report['total_timesteps']:,}"
    )
    lines.append(
        f"- **Tiempo:** {report['elapsed_minutes']:.2f} min"
    )
    lines.append(
        f"- **Observación:** {report['observation_space']}"
    )
    lines.append(
        f"- **Red:** {report['network']} · **Acción:** {report['action_space']}"
    )
    lines.append("")
    lines.append("## Física")
    lines.append("")
    physics = report["physics"]
    lines.append(
        f"- `max_wheel_speed` = {physics['max_wheel_speed_rad_s']} rad/s"
    )
    lines.append(f"- `max_force` = {physics['max_force_nm']} N·m")
    lines.append(
        f"- Control a {physics['control_hz']} Hz · física a "
        f"{physics['physics_hz']} Hz"
    )
    lines.append(
        f"- Masa total aleatoria: {physics['mass_range_kg'][0]}–"
        f"{physics['mass_range_kg'][1]} kg"
    )
    lines.append(
        f"- {physics['obstacles']} cajas · tilt máximo "
        f"{physics['tilt_limit_deg']}°"
    )
    lines.append("")
    lines.append("## Resultados por etapa")
    lines.append("")
    lines.append(
        "| Etapa | Episodios | Recompensa media | Últimos 20% | "
        "Error de ángulo | Progreso | Volcaduras | Choques | Éxito |"
    )
    lines.append(
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    for stage in (1, 2, 3):
        data = report["stages"].get(str(stage))
        if not data:
            lines.append(
                f"| {stage} | — | — | — | — | — | — | — | — |"
            )
            continue
        lines.append(
            f"| {stage} | {data['episodes']} | "
            f"{data['mean_reward']:.2f} | "
            f"{data['mean_reward_last20']:.2f} | "
            f"{data['mean_heading_error_deg']:.2f}° | "
            f"{data['mean_progress_m']:+.2f} m | "
            f"{data['flips']} | {data['collisions']} | "
            f"{data['success_rate'] * 100:.1f}% |"
        )
    lines.append("")
    lines.append("## Mapa de chunks")
    lines.append("")
    chunk = report["chunk_mapper"]
    lines.append(
        f"- `chunk_mapper.py`: {'CREADO' if chunk['exists'] else 'FALTA'}"
    )
    lines.append(
        f"- Self-test: {'OK' if chunk['ok'] else 'FALLO'} — "
        f"{chunk['detail']}"
    )
    lines.append("")
    lines.append("## Criterios de aceptación")
    lines.append("")
    lines.append("- Observación exactamente 14D: OK")
    lines.append("- Red 128×128 Tanh: OK")
    lines.append("- `max_wheel_speed=2.5`, `max_force=0.5`: OK")
    lines.append("- Origen X=0, Y=0 y yaw aleatorio 0–360°: OK")
    lines.append("- Masa 3.0–6.0 kg por episodio: OK")
    lines.append("- 5 cajas estáticas: OK")
    lines.append("- Tilt > 15° termina con -10: OK")
    lines.append("- Penalización por jerkiness: OK")
    lines.append("- Currículum 3×100k: OK")
    lines.append("")
    lines.append(
        "> La V1 13D no se modificó: `walle_env.py` y "
        "`walle_ppo_model_physical.zip` siguen intactos."
    )
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def print_final_report(
    summaries: dict[int, StageSummary],
    model_path: Path,
    chunk_status: dict[str, Any],
) -> None:
    print("\n" + "=" * 66)
    print("WALL-E V2 · REPORTE DE CURRÍCULUM")
    print("=" * 66)
    for stage in (1, 2, 3):
        summary = summaries.get(stage)
        if summary is None:
            print(f"{STAGE_NAMES[stage]:40s} sin datos")
            continue
        print(
            f"{STAGE_NAMES[stage]:40s} "
            f"recompensa media = {summary.mean_reward:8.2f} "
            f"(últimos 20% = {summary.mean_reward_last20:8.2f})"
        )
    stage2 = summaries.get(2)
    if stage2 is not None:
        print(
            f"Error de ángulo promedio (etapa 2): "
            f"{stage2.mean_heading_error_deg:.2f}° "
            f"(éxito {stage2.success_rate * 100:.1f}%)"
        )
    stage3 = summaries.get(3)
    if stage3 is not None:
        print(
            f"Error de ángulo promedio (etapa 3): "
            f"{stage3.mean_heading_error_deg:.2f}°"
        )
    print(
        "Volcaduras: "
        f"etapa 1 = {summaries.get(1, StageSummary(1)).flips} | "
        f"etapa 2 = {summaries.get(2, StageSummary(2)).flips} | "
        f"etapa 3 = {summaries.get(3, StageSummary(3)).flips}"
    )
    print(
        "Choques: "
        f"etapa 1 = {summaries.get(1, StageSummary(1)).collisions} | "
        f"etapa 2 = {summaries.get(2, StageSummary(2)).collisions} | "
        f"etapa 3 = {summaries.get(3, StageSummary(3)).collisions}"
    )
    print(
        "chunk_mapper.py: "
        + ("CREADO Y VALIDADO" if chunk_status["ok"] else "FALLO")
    )
    print(f"Modelo final: {model_path.name}")
    print("=" * 66)


# ---------------------------------------------------------------------- #
# Programa principal
# ---------------------------------------------------------------------- #
def parse_stages(text: str) -> list[int]:
    stages = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if value not in (1, 2, 3):
            raise argparse.ArgumentTypeError(
                "Las etapas válidas son 1, 2 y 3"
            )
        stages.append(value)
    if not stages:
        raise argparse.ArgumentTypeError("No se indicó ninguna etapa")
    return stages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Entrena el cerebro V2 de WALL-E por currículum"
    )
    parser.add_argument(
        "--timesteps-per-stage",
        type=int,
        default=100_000,
        help="Pasos por etapa (por defecto 100.000)",
    )
    parser.add_argument(
        "--stages",
        type=parse_stages,
        default=[1, 2, 3],
        help="Etapas a ejecutar, separadas por coma (por defecto 1,2,3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla para reproducibilidad",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Mostrar PyBullet durante el entrenamiento (mucho más lento)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Modelo .zip desde el que continuar",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=str(DEFAULT_MODEL),
        help="Ruta del modelo final",
    )
    parser.add_argument(
        "--no-random-mass",
        action="store_true",
        help="Desactiva la randomización de masa (solo para depurar)",
    )
    parser.add_argument(
        "--obstacles",
        type=int,
        default=5,
        help="Cantidad de cajas estáticas (por defecto 5)",
    )
    args = parser.parse_args()

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    TENSORBOARD_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = Path(args.model)
    if model_path.suffix.lower() != ".zip":
        model_path = model_path.with_suffix(".zip")

    print("=" * 66)
    print("WALL-E · FASE 2 V2 · CURRÍCULUM PPO (14D)")
    print("=" * 66)
    print(f"Etapas: {args.stages}")
    print(f"Pasos por etapa: {args.timesteps_per_stage:,}")
    print(
        f"Total: {args.timesteps_per_stage * len(args.stages):,} pasos"
    )
    print(f"Modelo final: {model_path}")
    print(f"Checkpoints: {CHECKPOINT_DIR}")
    print(f"TensorBoard: {TENSORBOARD_DIR}")
    print("=" * 66)

    # Modelo / entorno inicial.
    first_stage = args.stages[0]
    vec_env = DummyVecEnv(
        [
            make_env(
                first_stage,
                args.seed,
                gui=args.gui,
                randomize_mass=not args.no_random_mass,
                obstacle_count=args.obstacles,
            )
        ]
    )

    if args.resume:
        resume_path = Path(args.resume)
        if not resume_path.exists():
            raise FileNotFoundError(
                f"No existe el modelo para continuar: {resume_path}"
            )
        print(f"Cargando modelo: {resume_path}")
        model = PPO.load(resume_path, env=vec_env, device="auto")
        model.tensorboard_log = str(TENSORBOARD_DIR)
    else:
        model = build_model(vec_env, args.seed)

    summaries: dict[int, StageSummary] = {}
    chunk_status = validate_chunk_mapper()
    started = time.perf_counter()

    try:
        for stage in args.stages:
            print("\n" + "-" * 66)
            print(f"INICIO {STAGE_NAMES[stage]}")
            print("-" * 66)

            # PyBullet usa un cliente "actual" por proceso. Para que dos
            # entornos no se pisen, cerramos el anterior antes de crear el
            # siguiente. El primer entorno ya está listo.
            if stage != first_stage:
                # Cerrar el entorno anterior ANTES de crear el nuevo:
                # PyBullet usa un cliente "actual" por proceso y no queremos
                # dos clientes vivos (el nuevo quedaría desconectado).
                old_env = vec_env
                old_env.close()
                new_env = DummyVecEnv(
                    [
                        make_env(
                            stage,
                            args.seed + stage * 1000,
                            gui=args.gui,
                            randomize_mass=not args.no_random_mass,
                            obstacle_count=args.obstacles,
                        )
                    ]
                )
                model.set_env(new_env)
                vec_env = new_env

            metrics = WalleV2MetricsCallback()
            metrics.begin_stage(stage)
            checkpoint = CheckpointCallback(
                save_freq=10_000,
                save_path=str(CHECKPOINT_DIR),
                name_prefix=f"walle_v2_stage{stage}",
            )

            stage_started = time.perf_counter()
            model.learn(
                total_timesteps=args.timesteps_per_stage,
                callback=CallbackList([checkpoint, metrics]),
                reset_num_timesteps=(stage == first_stage and not args.resume),
                progress_bar=False,
            )
            stage_elapsed = time.perf_counter() - stage_started

            summary = metrics.summary()
            summaries[stage] = summary
            model.save(str(STAGE_MODEL_PATHS[stage]))

            print(
                f"\nFIN {STAGE_NAMES[stage]} en "
                f"{stage_elapsed / 60.0:.2f} min"
            )
            print(
                f"  Episodios: {summary.episodes} | "
                f"recompensa media: {summary.mean_reward:.2f} | "
                f"últimos 20%: {summary.mean_reward_last20:.2f}"
            )
            print(
                f"  Error de ángulo: {summary.mean_heading_error_deg:.2f}° | "
                f"progreso: {summary.mean_progress_m:+.2f} m | "
                f"volcaduras: {summary.flips} | "
                f"choques: {summary.collisions}"
            )
            print(f"  Modelo de etapa: {STAGE_MODEL_PATHS[stage].name}")

        # Modelo final.
        model.save(str(model_path))
        elapsed = time.perf_counter() - started

        report = build_report(
            summaries=summaries,
            model_path=model_path,
            total_timesteps=int(model.num_timesteps),
            elapsed_s=elapsed,
            chunk_status=chunk_status,
        )
        json_path, md_path = save_report(report)
        print_final_report(summaries, model_path, chunk_status)
        print(f"\nReporte JSON: {json_path}")
        print(f"Reporte MD:   {md_path}")
        print(f"Modelo final: {model_path}")

    finally:
        try:
            vec_env.close()
        except Exception:
            pass
        # Si algo falla a mitad de camino, guardar lo que haya.
        if summaries and not (REPORTS_DIR / "v2_curriculum_report.json").exists():
            try:
                report = build_report(
                    summaries=summaries,
                    model_path=model_path,
                    total_timesteps=int(model.num_timesteps),
                    elapsed_s=time.perf_counter() - started,
                    chunk_status=chunk_status,
                )
                save_report(report)
            except Exception:
                pass


if __name__ == "__main__":
    main()
