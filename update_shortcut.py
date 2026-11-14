#!/usr/bin/env python3
"""Update desktop shortcut to point to .exe when ready"""

import os
import sys
from pathlib import Path

try:
    import winshell
    from win32com.client import Dispatch
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "winshell", "pywin32"])
    import winshell
    from win32com.client import Dispatch

PROJECT_DIR = Path(r"E:\Proyecto Wall E\Software de Wall-E")
EXE_PATH = PROJECT_DIR / "dist" / "Wall-E-Companion.exe"
SHORTCUT_NAME = "Wall-E Companion"
DESKTOP = Path(winshell.desktop())
SHORTCUT_PATH = DESKTOP / f"{SHORTCUT_NAME}.lnk"

if not EXE_PATH.exists():
    print(f".exe not found at {EXE_PATH}")
    print("Build still in progress or failed.")
    sys.exit(1)

# Update shortcut
shell = Dispatch('WScript.Shell')
shortcut = shell.CreateShortCut(str(SHORTCUT_PATH))
shortcut.Targetpath = str(EXE_PATH)
shortcut.Arguments = "--mock"
shortcut.WorkingDirectory = str(PROJECT_DIR)
shortcut.Description = "Wall-E Companion - Robot Control Panel"
shortcut.save()

print(f"Shortcut updated to point to: {EXE_PATH}")
print(f"Size: {EXE_PATH.stat().st_size / (1024*1024):.1f} MB")