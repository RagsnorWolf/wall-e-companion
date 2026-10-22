#!/usr/bin/env python3
"""
Auto-commit simple para Wall-E Companion.
Guarda cambios cada N segundos automáticamente.
"""
import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

DEFAULT_INTERVAL = 30
IGNORE = {".git", "__pycache__", "*.pyc", ".venv", "venv", "env", "node_modules", ".next", "dist", "build", "*.log", ".pytest_cache", ".mypy_cache", ".ruff_cache", "*.tmp", "*.swp", "*.swo", ".DS_Store", "Thumbs.db"}

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(), logging.FileHandler("logs/auto_commit.log")])
logger = logging.getLogger(__name__)

class Handler(FileSystemEventHandler):
    def __init__(self, repo): self.repo, self.changed, self.last = repo, False, 0
    def on_any_event(self, e):
        if e.is_directory: return
        rel = Path(e.src_path).relative_to(self.repo)
        if any(rel.match(p) or any(par.match(p) for par in rel.parents) for p in IGNORE): return
        self.changed, self.last = True, time.time()

def git(cmd, cwd):
    try: return subprocess.run(["git"]+cmd, cwd=cwd, capture_output=True, text=True, timeout=30).returncode == 0
    except: return False

def commit(repo, msg):
    if not git(["add", "-A"], repo): return False
    if not git(["commit", "-m", msg], repo): return False
    logger.info(f"Committed: {msg}")
    return True

def push(repo, remote, branch): return git(["push", remote, branch], repo)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    ap.add_argument("--branch", default="main")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--push", action="store_true", default=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo/".git").exists(): logger.error("No es repo git"); sys.exit(1)
    (repo/"logs").mkdir(exist_ok=True)

    if args.once:
        msg = f"auto: manual ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        if commit(repo, msg) and args.push: push(repo, args.remote, args.branch)
        return

    h = Handler(repo)
    obs = Observer(); obs.schedule(h, str(repo), recursive=True); obs.start()
    signal.signal(signal.SIGINT, lambda s,f: (obs.stop(), sys.exit(0)))

    logger.info(f"Auto-commit cada {args.interval}s en {args.branch}")
    while True:
        time.sleep(args.interval)
        if not h.changed: continue
        if time.time() - h.last < args.interval/2: continue
        if not any((repo/".git").glob("*")): continue
        msg = f"auto: {len(list(repo.rglob('*')))} files ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        if commit(repo, msg):
            h.changed = False
            if args.push: push(repo, args.remote, args.branch)

if __name__ == "__main__": main()