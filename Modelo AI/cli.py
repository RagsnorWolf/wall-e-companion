"""CLI para probar el cerebro sin micrófono ni robot.

Uso:
    python cli.py
    python cli.py --model walle --verbose
    python cli.py --say       # habla con pyttsx3 si está instalado

Comandos:
    /estado     muestra el estado del cuerpo y la memoria
    /memoria    lista lo último que recordás
    /reflejo    arranca seguimiento de color (10s)
    /limpiar    borra el historial de la sesión en pantalla
    /salir      termina
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from brain.agent import Agent  # noqa: E402
from vision.reflex import ColorTracker, probe_color  # noqa: E402


def make_speaker(enabled: bool):
    if not enabled:
        return lambda text: None
    try:
        import pyttsx3
    except ImportError:
        print("[aviso] pyttsx3 no instalado: sigo en texto")
        return lambda text: None

    engine = pyttsx3.init()
    engine.setProperty("rate", 180)

    def speak(text: str) -> None:
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass

    return speak


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="walle")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--port", default=None)
    parser.add_argument("--autoconnect", action="store_true", help="probar todos los puertos")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--say", action="store_true")
    args = parser.parse_args()

    agent = Agent(
        model=args.model,
        camera_index=args.camera,
        port=args.port,
        autoconnect=args.autoconnect,
        speak=make_speaker(args.say),
        verbose=args.verbose,
    )

    if not agent.llm.health():
        print("[error] Ollama no responde en http://127.0.0.1:11434")
        print("        Abrí Ollama y probá de nuevo.")
        return

    status = agent.link.status()
    print(f"[ok] modelo={args.model}  cuerpo={status['mode']}  puerto={status['port']}")
    print("Escribí y enter. /salir para terminar.\n")

    try:
        while True:
            try:
                text = input("vos> ").strip()
            except EOFError:
                break
            if not text:
                continue

            if text in {"/salir", "/exit", "/quit"}:
                break
            if text == "/estado":
                print(agent.tools.estado_robot())
                continue
            if text == "/memoria":
                print(f"items: {agent.memory.count()}")
                continue
            if text == "/reflejo":
                tracker = ColorTracker(agent.link, agent.camera, color="rojo")
                print("[..] siguiendo rojo 10s")
                tracker.start()
                time.sleep(10)
                tracker.stop()
                print(f"[ok] último: {tracker.last}")
                continue
            if text == "/limpiar":
                print("\n" * 2)
                continue
            if text == "/ver":
                print(probe_color(agent.camera, "rojo"))
                continue

            started = time.perf_counter()
            reply = agent.respond(text)
            elapsed = time.perf_counter() - started
            print(f"walle> {reply}   [{elapsed:.1f}s]")
            agent.speak(reply)
    except KeyboardInterrupt:
        print("\n[..] cortando")
    finally:
        agent.close()


if __name__ == "__main__":
    main()
