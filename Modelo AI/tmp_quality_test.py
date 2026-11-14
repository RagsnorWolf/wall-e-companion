import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from brain.agent import Agent

db = Path("tmp_quality_test.db")
if db.exists():
    db.unlink()
agent = Agent(memory_path=db, warmup=False, conversation_only=True)

cases = [
    "Hola",
    "Hoy tuve un día largo en el trabajo",
    "Estoy triste porque mi mamá está enferma",
    "Me gusta el café",
    "¿Qué hora es?",
    "Aprobé el final de matemática",
    "Estoy harto de mi jefe",
    "¿Qué ves?",
    "Contame algo",
]

for text in cases:
    a = agent._analyze(text)
    print(f"{text!r}\n  -> {a}\n  ctx: {agent._context(text)}")
    print(f"  fallback: {agent._reflective_fallback(text, a)}")

print("\nclean:")
for raw in [
    'WALL-E: "Como WALL-E, te escucho."',
    "**Oh…** Te entiendo!!!",
    "Te entiendo.",
]:
    print(f"  {raw!r} -> {agent._clean(raw)!r}")

print("\ngeneric:")
for raw in ["Te entiendo.", "Qué lindo.", "Me alegra un montón.", "El café tiene algo lindo, despierta la casa."]:
    print(f"  {raw!r} -> {agent._is_generic(raw, agent._analyze('Me gusta el café'))}")

agent.memory.close()
db.unlink(missing_ok=True)
