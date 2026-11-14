import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from brain.agent import Agent

agent = Agent(warmup=False, conversation_only=True)
samples = [
    'WALL-E: "Como WALL-E, te escucho."',
    "Como WALL-E, te escucho.",
    "**Oh…** Te entiendo!!!",
    '"Te escucho."',
]
for raw in samples:
    print(f"{raw!r} -> {agent._clean(raw)!r}")
agent.memory.close()
