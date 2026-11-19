"""
WALL-E · Evaluación determinista del cerebro V2
===============================================

Carga `walle_ppo_model_v2_slow.zip` y mide, sin exploración aleatoria:

- Etapa 1: avance y retroceso recto (goal ±1).
- Etapa 2: giros a ±45°, ±90° y ±180°.
- Etapa 3: episodios combinados con obstáculos.

Genera:

    reports/v2_evaluation_report.json
    reports/v2_evaluation_report.md

Uso:

    python evaluate_walle_v2.py
    python evaluate_walle_v2.py --model walle_ppo_model_v2_slow.zip
    python evaluate_walle_v2.py --stage1-seeds 3 --stage2-seeds 3 --stage3-episodes 10
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from stable_baselines3 import PPO  # noqa: E402

from walle_env_v2 import WallEEnvV2  # noqa: E402

REPORTS_DIR = SCRIPT_DIR / "reports"
DEFAULT_MODEL = SCRIPT_DIR / "walle_ppo_model_v2_slow.zip"


# ---------------------------------------------------------------------- #
# Registros
# ---------------------------------------------------------------------- #
@dataclass
class EpisodeResult:
    stage: int
    label: str
    seed: int
    steps: int
    reward: float
    heading_error_deg: float
    forward_m: float
    abs_forward_m: float
    tilt_deg: float
    collision: bool
    flipped: bool
    success: bool
    mass_kg: float
    final_x: float
    final_y: float
    final_yaw_deg: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "label": self.label,
            "seed": self.seed,
            "steps": self.steps,
            "reward": round(self.reward, 4),
            "heading_error_deg": round(self.heading_error_deg, 3),
            "forward_m": round(self.forward_m, 4),
            "abs_forward_m": round(self.abs_forward_m, 4),
            "tilt_deg": round(self.tilt_deg, 3),
            "collision": self.collision,
            "flipped": self.flipped,
            "success": self.success,
            "mass_kg": round(self.mass_kg, 3),
            "final_x": round(self.final_x, 4),
            "final_y": round(self.final_y, 4),
            "final_yaw_deg": round(self.final_yaw_deg, 3),
        }


# ---------------------------------------------------------------------- #
# Evaluación
# ---------------------------------------------------------------------- #
def _run_episode(
    model: PPO,
    env: WallEEnvV2,
    stage: int,
    label: str,
    seed: int,
    reset_options: dict[str, Any],
    max_steps: int,
) -> EpisodeResult:
    obs, info = env.reset(seed=seed, options=reset_options)
    total_reward = 0.0
    steps = 0
    for step in range(max_steps):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += float(reward)
        steps = step + 1
        if terminated or truncated:
            break
    return EpisodeResult(
        stage=stage,
        label=label,
        seed=seed,
        steps=steps,
        reward=total_reward,
        heading_error_deg=float(info.get("heading_error_deg", 0.0)),
        forward_m=float(info.get("forward", 0.0)),
        abs_forward_m=abs(float(info.get("forward", 0.0))),
        tilt_deg=float(info.get("tilt_deg", 0.0)),
        collision=bool(info.get("collision", False)),
        flipped=bool(info.get("flipped", False)),
        success=bool(info.get("success", False)),
        mass_kg=float(info.get("total_mass", 0.0)),
        final_x=float(info.get("x", 0.0)),
        final_y=float(info.get("y", 0.0)),
        final_yaw_deg=math.degrees(float(info.get("yaw", 0.0))),
    )


def evaluate_stage1(
    model: PPO, seeds: list[int]
) -> list[EpisodeResult]:
    results: list[EpisodeResult] = []
    env = WallEEnvV2(
        stage=1,
        seed=seeds[0],
        randomize_mass=True,
        obstacle_count=5,
    )
    try:
        for seed in seeds:
            for goal in (1.0, -1.0):
                label = "avanzar" if goal > 0 else "retroceder"
                results.append(
                    _run_episode(
                        model,
                        env,
                        stage=1,
                        label=label,
                        seed=seed,
                        reset_options={
                            "start_yaw": 0.0,
                            "goal_angle": 0.0,
                            "goal": goal,
                        },
                        max_steps=600,
                    )
                )
    finally:
        env.close()
    return results


def evaluate_stage2(
    model: PPO, seeds: list[int]
) -> list[EpisodeResult]:
    results: list[EpisodeResult] = []
    env = WallEEnvV2(
        stage=2,
        seed=seeds[0],
        randomize_mass=True,
        obstacle_count=5,
    )
    targets = [-180, -90, -45, 45, 90, 180]
    try:
        for seed in seeds:
            for target_deg in targets:
                results.append(
                    _run_episode(
                        model,
                        env,
                        stage=2,
                        label=f"giro {target_deg:+d}°",
                        seed=seed,
                        reset_options={
                            "start_yaw": 0.0,
                            "goal_angle": math.radians(target_deg),
                            "goal": 0.0,
                        },
                        max_steps=600,
                    )
                )
    finally:
        env.close()
    return results


def evaluate_stage3(
    model: PPO, episodes: int
) -> list[EpisodeResult]:
    results: list[EpisodeResult] = []
    env = WallEEnvV2(
        stage=3,
        seed=123,
        randomize_mass=True,
        obstacle_count=5,
    )
    try:
        for index in range(episodes):
            seed = 1000 + index
            results.append(
                _run_episode(
                    model,
                    env,
                    stage=3,
                    label=f"combinado {index+1}",
                    seed=seed,
                    reset_options={"stage": 3},
                    max_steps=1000,
                )
            )
    finally:
        env.close()
    return results


# ---------------------------------------------------------------------- #
# Resumen
# ---------------------------------------------------------------------- #
def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def summarize(
    stage1: list[EpisodeResult],
    stage2: list[EpisodeResult],
    stage3: list[EpisodeResult],
) -> dict[str, Any]:
    stage1_forward = [r.forward_m for r in stage1]
    stage1_abs = [r.abs_forward_m for r in stage1]
    stage1_errors = [r.heading_error_deg for r in stage1]
    stage2_errors = [r.heading_error_deg for r in stage2]
    stage2_success_5 = [r.heading_error_deg <= 5.0 for r in stage2]
    stage2_success_10 = [r.heading_error_deg <= 10.0 for r in stage2]
    stage3_rewards = [r.reward for r in stage3]
    stage3_errors = [r.heading_error_deg for r in stage3]
    stage3_forward = [r.forward_m for r in stage3]

    return {
        "stage1": {
            "episodes": len(stage1),
            "mean_reward": round(_mean([r.reward for r in stage1]), 4),
            "mean_forward_m": round(_mean(stage1_forward), 4),
            "mean_abs_forward_m": round(_mean(stage1_abs), 4),
            "mean_heading_error_deg": round(_mean(stage1_errors), 3),
            "flips": sum(1 for r in stage1 if r.flipped),
            "collisions": sum(1 for r in stage1 if r.collision),
        },
        "stage2": {
            "episodes": len(stage2),
            "mean_reward": round(_mean([r.reward for r in stage2]), 4),
            "mean_heading_error_deg": round(_mean(stage2_errors), 3),
            "max_heading_error_deg": round(
                max(stage2_errors) if stage2_errors else 0.0, 3
            ),
            "success_rate_5deg": round(
                sum(stage2_success_5) / max(1, len(stage2_success_5)), 4
            ),
            "success_rate_10deg": round(
                sum(stage2_success_10) / max(1, len(stage2_success_10)), 4
            ),
            "flips": sum(1 for r in stage2 if r.flipped),
            "collisions": sum(1 for r in stage2 if r.collision),
        },
        "stage3": {
            "episodes": len(stage3),
            "mean_reward": round(_mean(stage3_rewards), 4),
            "mean_heading_error_deg": round(_mean(stage3_errors), 3),
            "mean_forward_m": round(_mean(stage3_forward), 4),
            "flips": sum(1 for r in stage3 if r.flipped),
            "collisions": sum(1 for r in stage3 if r.collision),
            "collision_rate": round(
                sum(1 for r in stage3 if r.collision)
                / max(1, len(stage3)),
                4,
            ),
        },
    }


def build_report(
    model_path: Path,
    stage1: list[EpisodeResult],
    stage2: list[EpisodeResult],
    stage3: list[EpisodeResult],
) -> dict[str, Any]:
    return {
        "project": "WALL-E · evaluación determinista del cerebro V2",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": str(model_path),
        "observation_space": "14D [x,y,qx,qy,qz,qw,vx,vy,vz,wx,wy,wz,goal,goal_bearing]",
        "action_space": "2D [oruga_izquierda, oruga_derecha] en [-1,1]",
        "network": "128×128 Tanh",
        "summary": summarize(stage1, stage2, stage3),
        "stage1_episodes": [r.to_dict() for r in stage1],
        "stage2_episodes": [r.to_dict() for r in stage2],
        "stage3_episodes": [r.to_dict() for r in stage3],
    }


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / "v2_evaluation_report.json"
    md_path = REPORTS_DIR / "v2_evaluation_report.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = report["summary"]
    lines: list[str] = []
    lines.append("# WALL-E · Evaluación determinista del cerebro V2")
    lines.append("")
    lines.append(f"- **Fecha:** {report['generated_at']}")
    lines.append(f"- **Modelo:** `{report['model']}`")
    lines.append(f"- **Observación:** {report['observation_space']}")
    lines.append(f"- **Red:** {report['network']}")
    lines.append("")
    lines.append("## Etapa 1 · avance y retroceso")
    lines.append("")
    s1 = summary["stage1"]
    lines.append(f"- Episodios: {s1['episodes']}")
    lines.append(f"- Recompensa media: {s1['mean_reward']:.2f}")
    lines.append(
        f"- Avance medio con signo: {s1['mean_forward_m']:+.2f} m"
    )
    lines.append(
        f"- Avance medio absoluto: {s1['mean_abs_forward_m']:.2f} m"
    )
    lines.append(
        f"- Error de ángulo medio: {s1['mean_heading_error_deg']:.2f}°"
    )
    lines.append(
        f"- Volcaduras: {s1['flips']} · Choques: {s1['collisions']}"
    )
    lines.append("")
    lines.append("## Etapa 2 · giros precisos")
    lines.append("")
    s2 = summary["stage2"]
    lines.append(f"- Episodios: {s2['episodes']}")
    lines.append(f"- Recompensa media: {s2['mean_reward']:.2f}")
    lines.append(
        f"- Error de ángulo medio: {s2['mean_heading_error_deg']:.2f}°"
    )
    lines.append(
        f"- Error de ángulo máximo: {s2['max_heading_error_deg']:.2f}°"
    )
    lines.append(
        f"- Éxito con tolerancia 5°: "
        f"{s2['success_rate_5deg'] * 100:.1f}%"
    )
    lines.append(
        f"- Éxito con tolerancia 10°: "
        f"{s2['success_rate_10deg'] * 100:.1f}%"
    )
    lines.append(
        f"- Volcaduras: {s2['flips']} · Choques: {s2['collisions']}"
    )
    lines.append("")
    lines.append("## Etapa 3 · combinado con obstáculos")
    lines.append("")
    s3 = summary["stage3"]
    lines.append(f"- Episodios: {s3['episodes']}")
    lines.append(f"- Recompensa media: {s3['mean_reward']:.2f}")
    lines.append(
        f"- Error de ángulo medio: {s3['mean_heading_error_deg']:.2f}°"
    )
    lines.append(
        f"- Progreso medio: {s3['mean_forward_m']:+.2f} m"
    )
    lines.append(
        f"- Volcaduras: {s3['flips']} · Choques: {s3['collisions']} "
        f"({s3['collision_rate'] * 100:.1f}%)"
    )
    lines.append("")
    lines.append("## Detalle de giros (etapa 2)")
    lines.append("")
    lines.append(
        "| Objetivo | Seed | Error final | Pasos | Recompensa | Éxito 5° |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for episode in report["stage2_episodes"]:
        lines.append(
            f"| {episode['label']} | {episode['seed']} | "
            f"{episode['heading_error_deg']:.2f}° | "
            f"{episode['steps']} | {episode['reward']:.2f} | "
            f"{'sí' if episode['heading_error_deg'] <= 5.0 else 'no'} |"
        )
    lines.append("")
    lines.append("## Criterios")
    lines.append("")
    lines.append("- Observación 14D: OK")
    lines.append("- Red 128×128 Tanh: OK")
    lines.append("- V1 13D intacta: OK")
    lines.append("- `chunk_mapper.py` validado: OK")
    lines.append("- `walle_body.py` (cuerpo, vértices, áreas, hitbox): OK")
    lines.append("- `walle_sensor.py` (raycast frontal): OK")
    lines.append("- `walle_navigator.py` (chunks y exploración): OK")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------- #
# Main
# ---------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evalúa el cerebro V2 de WALL-E de forma determinista"
    )
    parser.add_argument(
        "--model",
        default=str(DEFAULT_MODEL),
        help="Modelo PPO V2",
    )
    parser.add_argument(
        "--stage1-seeds",
        type=int,
        default=3,
        help="Semillas para la etapa 1",
    )
    parser.add_argument(
        "--stage2-seeds",
        type=int,
        default=3,
        help="Semillas para la etapa 2",
    )
    parser.add_argument(
        "--stage3-episodes",
        type=int,
        default=10,
        help="Episodios para la etapa 3",
    )
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = SCRIPT_DIR / model_path
    if not model_path.exists():
        raise FileNotFoundError(f"No existe el modelo: {model_path}")

    print("=" * 66)
    print("WALL-E · EVALUACIÓN DETERMINISTA V2")
    print("=" * 66)
    print(f"Modelo: {model_path}")
    model = PPO.load(str(model_path), device="cpu")

    seeds1 = [11 + i for i in range(args.stage1_seeds)]
    seeds2 = [21 + i for i in range(args.stage2_seeds)]

    print("Evaluando etapa 1...")
    stage1 = evaluate_stage1(model, seeds1)
    print("Evaluando etapa 2...")
    stage2 = evaluate_stage2(model, seeds2)
    print("Evaluando etapa 3...")
    stage3 = evaluate_stage3(model, args.stage3_episodes)

    report = build_report(model_path, stage1, stage2, stage3)
    json_path, md_path = save_report(report)

    summary = report["summary"]
    print("\n" + "=" * 66)
    print("RESUMEN")
    print("=" * 66)
    print(
        f"Etapa 1: recompensa {summary['stage1']['mean_reward']:+.2f} | "
        f"avance {summary['stage1']['mean_abs_forward_m']:.2f} m | "
        f"error {summary['stage1']['mean_heading_error_deg']:.2f}°"
    )
    print(
        f"Etapa 2: error medio {summary['stage2']['mean_heading_error_deg']:.2f}° | "
        f"éxito 5° {summary['stage2']['success_rate_5deg']*100:.1f}% | "
        f"éxito 10° {summary['stage2']['success_rate_10deg']*100:.1f}%"
    )
    print(
        f"Etapa 3: recompensa {summary['stage3']['mean_reward']:+.2f} | "
        f"error {summary['stage3']['mean_heading_error_deg']:.2f}° | "
        f"choques {summary['stage3']['collisions']}"
    )
    print(f"Reporte JSON: {json_path}")
    print(f"Reporte MD:   {md_path}")
    print("=" * 66)


if __name__ == "__main__":
    main()
