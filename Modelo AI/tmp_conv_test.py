import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from brain.agent import Agent

CASES = [
    "Hola",
    "Hoy tuve un día largo en el trabajo",
    "Estoy triste porque discutí con mi mamá",
    "Me gusta el café",
    "Aprobé el final de matemática",
    "Contame algo",
    "¿Qué hora es?",
    "¿Qué ves?",
    "Estoy harto de mi jefe",
    "¿Qué me recomendás para esta noche?",
]

db = Path("tmp_conv_memory.db")
if db.exists():
    db.unlink()
agent = Agent(memory_path=db, warmup=True, conversation_only=True, verbose=True)

if not agent.llm.health():
    print("[FALLA] Ollama no responde")
    raise SystemExit(1)

total = 0.0
for prompt in CASES:
    start = time.perf_counter()
    answer = agent.respond(prompt)
    elapsed = time.perf_counter() - start
    total += elapsed
    print(f"\nvos>   {prompt}")
    print(f"walle> {answer}")
    print(f"tiempo: {elapsed:.2f}s")

print(f"\npromedio: {total / len(CASES):.2f}s")
agent.close()
db.unlink(missing_ok=True)
