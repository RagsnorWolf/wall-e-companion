"""Genera el Modelfile de Ollama a partir de prompts/system.md y crea el modelo.

Uso:
    python build_model.py                # genera Modelfile
    python build_model.py --create       # genera y corre `ollama create walle`
    python build_model.py --base qwen2.5:3b --name walle

Una sola fuente de verdad: prompts/system.md. Si editás la personalidad,
volvés a correr esto y el modelo queda actualizado.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SYSTEM_PROMPT = ROOT / "prompts" / "system.md"
MODELFILE = ROOT / "Modelfile"

HEADER = """# Generado por build_model.py — no editar a mano.
# Fuente: prompts/system.md

FROM {base}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 4096
PARAMETER num_predict 256
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"

SYSTEM \"\"\"
{system}
\"\"\"
"""


def build_modelfile(base: str) -> Path:
    if not SYSTEM_PROMPT.exists():
        sys.exit(f"No existe {SYSTEM_PROMPT}")
    system = SYSTEM_PROMPT.read_text(encoding="utf-8").strip()
    if '"""' in system:
        sys.exit('El system prompt no puede contener triple comilla (""")')
    MODELFILE.write_text(HEADER.format(base=base, system=system), encoding="utf-8")
    return MODELFILE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="qwen2.5:3b", help="modelo base de Ollama")
    parser.add_argument("--name", default="walle", help="nombre del modelo a crear")
    parser.add_argument("--create", action="store_true", help="correr ollama create")
    args = parser.parse_args()

    path = build_modelfile(args.base)
    print(f"[ok] Modelfile generado: {path}")

    if not args.create:
        print(f"[..] Ahora: ollama create {args.name} -f \"{path}\"")
        return

    if shutil.which("ollama") is None:
        sys.exit("[error] ollama no está en el PATH")

    print(f"[..] ollama create {args.name}")
    result = subprocess.run(
        ["ollama", "create", args.name, "-f", str(path)],
        text=True,
        capture_output=True,
    )
    print(result.stdout.strip() or result.stderr.strip())
    if result.returncode != 0:
        sys.exit(f"[error] ollama create falló ({result.returncode})")
    print(f"[ok] Modelo '{args.name}' listo. Probá: ollama run {args.name}")


if __name__ == "__main__":
    main()
