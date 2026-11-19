"""Reproduce la GUI exacta sin ventana.

Construye la misma escena (build_scene), el mismo cuerpo visual y el mismo
controlador que la GUI, y registra cada frenada, cada despegue y cada
contacto para ver por que WALL-E se para lejos de todo.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pybullet as p

import interactive_walle as iw

COMMANDS = ["avanza 5 metros", "gira 90 grados", "avanza 5 metros"]


def body_name(body_id: int) -> str:
    try:
        info = p.getBodyInfo(body_id)
        return info[0].decode("utf-8", "replace") or f"id{body_id}"
    except Exception:
        return f"id{body_id}"


def main() -> int:
    env = iw.WallEEnvV3(
        render_mode=None,
        show_proxy_visuals=False,
        stage=3,
        obstacle_count=6,
    )
    env.render = lambda: None
    iw.build_scene(env)
    iw.reset_env_home(env)

    textured = bool(iw.WALLE_USE_TEXTURE and iw.VISUAL_OBJ.exists())
    parts = [(str(iw.VISUAL_OBJ), (1.0, 1.0, 1.0), 0)] if textured else []
    visual = iw.WalleVisual(env, parts, textured=textured)
    print(f"cuerpo visual id={visual.body_id}", flush=True)

    logger = iw.FeedbackLogger(Path("feedback_probe"))
    reports = iw.TestReportWriter(Path("reports_probe"))
    controller = iw.WalleController(
        env, logger=logger, report_writer=reports
    )

    watched = {
        body: body_name(body)
        for body in (
            env.wall_ids
            + env.obstacle_ids
            + env.cylinder_ids
            + env.long_wall_ids
            + env.ramp_ids
            + env.l_wall_ids
        )
    }

    def traced_brake(reason: str, tentative_success: bool = False) -> None:
        exp = controller.exp
        pose = controller._pose()
        front = float(env.lidar_meters[env._front_indices].min())
        print(
            f"  >> FRENADA '{reason}' exito={tentative_success} "
            f"pasos={exp.steps if exp else -1} "
            f"pos=({pose.pos[0]:+.2f},{pose.pos[1]:+.2f}) "
            f"objetivo={exp.target_distance if exp else 0} "
            f"lidar_frontal={front:.2f}",
            flush=True,
        )
        controller._start_brake_original(reason, tentative_success)

    def traced_unstick(mode: str) -> None:
        pose = controller._pose()
        hits = []
        for body, name in watched.items():
            contacts = p.getContactPoints(bodyA=env.robot, bodyB=body)
            for c in contacts:
                hits.append(
                    f"{name} link={c[3]} "
                    f"p=({c[5][0]:+.2f},{c[5][1]:+.2f},{c[5][2]:+.2f}) "
                    f"fuerza={c[9]:.2f}"
                )
        print(
            f"  !! DESPEGUE modo={mode} pos="
            f"({pose.pos[0]:+.2f},{pose.pos[1]:+.2f}) contactos={len(hits)}",
            flush=True,
        )
        for hit in hits:
            print(f"       {hit}", flush=True)
        controller._start_unstick_original(mode)

    controller._start_brake_original = controller._start_brake  # type: ignore[attr-defined]
    controller._start_unstick_original = controller._start_unstick  # type: ignore[attr-defined]
    controller._start_brake = traced_brake  # type: ignore[assignment]
    controller._start_unstick = traced_unstick  # type: ignore[assignment]

    for command in COMMANDS:
        print(f"\n=== ORDEN: {command}", flush=True)
        for message in controller.handle_text(command):
            print(f"    [msg] {message}", flush=True)
        t0 = time.perf_counter()
        tick = 0
        for tick in range(12000):
            for message in controller.tick():
                print(f"    [msg] {message}", flush=True)
            visual.sync()
            if controller.mode == "idle" and tick > 5:
                break
        elapsed = time.perf_counter() - t0
        pose = controller._pose()
        print(
            f"=== FIN {elapsed:.1f}s ({tick} ticks, modo={controller.mode}) "
            f"pos=({pose.pos[0]:+.2f},{pose.pos[1]:+.2f}) "
            f"yaw={math.degrees(pose.yaw):+.1f}",
            flush=True,
        )

    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
