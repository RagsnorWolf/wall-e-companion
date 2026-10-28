"""Prueba de humo del cerebro, sin interacción manual.

    python smoke_test.py

Verifica: personalidad, tool calling, memoria y latencia.
"""

from __future__ import annotations

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
from brain.llm import OllamaError  # noqa: E402

CASES = [
    ("hola, ¿quién sos?", "personalidad"),
    ("avanzá un segundo", "tool mover"),
    ("acordate que me llamo Gonzalo", "tool recordar"),
    ("¿cómo me llamo?", "memoria"),
    ("¿estás conectado?", "tool estado_robot"),
]


def main() -> int:
    db = Path("smoke_memory.db")
    if db.exists():
        db.unlink()

    agent = Agent(memory_path=db, verbose=True)

    if not agent.llm.health():
        print("[FALLA] Ollama no responde")
        return 1

    models = agent.llm.models()
    if "walle" not in " ".join(models):
        print(f"[aviso] 'walle' no aparece en {models}")

    failures = 0
    total = 0.0

    for prompt, label in CASES:
        start = time.perf_counter()
        try:
            answer = agent.respond(prompt)
        except OllamaError as exc:
            print(f"[FALLA] {label}: {exc}")
            failures += 1
            continue
        elapsed = time.perf_counter() - start
        total += elapsed
        print(f"\n{label}")
        print(f"  vos>   {prompt}")
        print(f"  walle> {answer}")
        print(f"  tiempo: {elapsed:.2f}s")
        if not answer:
            failures += 1

    print(f"\nmemoria: {agent.memory.count()} recuerdos")
    print(f"promedio: {total / len(CASES):.2f}s")
    if agent.memory.count() == 0:
        print("[FALLA] no se guardó ningún recuerdo")
        failures += 1
    agent.close()

    print("\nOK" if failures == 0 else f"\n{failures} fallas")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
