"""Mide dónde se va el tiempo: carga, lectura del prompt y generación.

    python bench_model.py
    python bench_model.py --model qwen2.5:1.5b
"""

from __future__ import annotations

import argparse
import json
import urllib.request

HOST = "http://127.0.0.1:11434"


def call(model: str, prompt: str, num_predict: int = 40) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 2048, "num_predict": num_predict},
        "keep_alive": "30m",
    }
    req = urllib.request.Request(
        f"{HOST}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def ms(value: int | None) -> float:
    return (value or 0) / 1_000_000


def report(tag: str, data: dict) -> None:
    load = ms(data.get("load_duration"))
    prompt = data.get("prompt_eval_count", 0)
    prompt_ms = ms(data.get("prompt_eval_duration"))
    out = data.get("eval_count", 0)
    out_ms = ms(data.get("eval_duration"))
    print(f"\n[{tag}]")
    print(f"  carga del modelo : {load:8.0f} ms")
    print(f"  prompt           : {prompt:5d} tokens en {prompt_ms:8.0f} ms "
          f"({prompt / (prompt_ms / 1000) if prompt_ms else 0:.1f} tok/s)")
    print(f"  generación       : {out:5d} tokens en {out_ms:8.0f} ms "
          f"({out / (out_ms / 1000) if out_ms else 0:.1f} tok/s)")
    print(f"  total            : {ms(data.get('total_duration')):8.0f} ms")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="walle")
    args = parser.parse_args()

    print(f"modelo: {args.model}")
    report("primera llamada (carga)", call(args.model, "Hola, ¿quién sos?"))
    report("segunda llamada (caliente)", call(args.model, "Decime una frase corta."))
    report("prompt corto", call(args.model, "Hola"))


if __name__ == "__main__":
    main()
