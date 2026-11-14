#!/usr/bin/env python3
"""Create desktop shortcut for Wall-E Companion"""

import os
import sys
from pathlib import Path

try:
    import winshell
    from win32com.client import Dispatch
except ImportError:
    print("Installing winshell and pywin32...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "winshell", "pywin32"])
    import winshell
    from win32com.client import Dispatch

# Paths
PROJECT_DIR = Path(r"E:\Proyecto Wall E\Software de Wall-E")
EXE_PATH = PROJECT_DIR / "dist" / "Wall-E-Companion.exe"
PYTHON_SCRIPT = PROJECT_DIR / "run_desktop.py"
PYTHON_EXE = sys.executable
SHORTCUT_NAME = "Wall-E Companion"
DESKTOP = Path(winshell.desktop())
SHORTCUT_PATH = DESKTOP / f"{SHORTCUT_NAME}.lnk"

# Use .exe if exists, otherwise use python script
if EXE_PATH.exists():
    target = str(EXE_PATH)
    args = "--mock"
    print(f"Using .exe: {EXE_PATH}")
else:
    target = str(PYTHON_EXE)
    args = f'"{PYTHON_SCRIPT}" --mock'
    print(f"Using Python script: {PYTHON_SCRIPT}")

# Create shortcut
shell = Dispatch('WScript.Shell')
shortcut = shell.CreateShortCut(str(SHORTCUT_PATH))
shortcut.Targetpath = target
shortcut.Arguments = args
shortcut.WorkingDirectory = str(PROJECT_DIR)
shortcut.Description = "Wall-E Companion - Robot Control Panel"
# shortcut.IconLocation = str(PROJECT_DIR / "icon.ico")  # Add if you have an icon
shortcut.save()

print(f"Shortcut created at: {SHORTCUT_PATH}")
print(f"Target: {target}")
print(f"Args: {args}")