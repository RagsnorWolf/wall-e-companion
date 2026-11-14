"""Build script for Wall-E Companion .exe using PyInstaller"""

import PyInstaller.__main__
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).parent

# PyInstaller arguments
args = [
    str(ROOT / "ui" / "desktop_app.py"),  # Main script
    "--name=Wall-E-Companion",
    "--onefile",                          # Single .exe file
    "--windowed",                         # No console window (GUI app)
    "--icon=NONE",                        # Add .ico file here if you have one
    "--add-data=config;config",           # Include config folder
    "--add-data=ui/templates;ui/templates", # Include templates
    "--add-data=ui/static;ui/static",     # Include static files
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=PySide6.QtCharts",
    "--hidden-import=qasync",
    "--hidden-import=core.hardware",
    "--hidden-import=core.serial_comm",
    "--hidden-import=core.state_machine",
    "--hidden-import=core.personality",
    "--hidden-import=services.vision",
    "--hidden-import=services.audio",
    "--hidden-import=services.ai_engine",
    "--hidden-import=cv2",
    "--hidden-import=numpy",
    "--hidden-import=serial",
    "--hidden-import=yaml",
    "--hidden-import=loguru",
    "--hidden-import=faster_whisper",
    "--hidden-import=onnxruntime",
    "--hidden-import=torch",
    "--hidden-import=torchaudio",
    "--hidden-import=librosa",
    "--hidden-import=pyaudio",
    "--hidden-import=websockets",
    "--hidden-import=asyncio_mqtt",
    "--collect-all=PySide6",
    "--collect-all=qasync",
    "--clean",
    "--noconfirm",
]

print("Building Wall-E Companion .exe...")
print(f"Main script: {ROOT / 'ui' / 'desktop_app.py'}")
print(f"Output: {ROOT / 'dist' / 'Wall-E-Companion.exe'}")

PyInstaller.__main__.run(args)

print("\nBuild complete!")
exe_path = ROOT / 'dist' / 'Wall-E-Companion.exe'
print(f"Executable: {exe_path}")

# Auto-update desktop shortcut
if exe_path.exists():
    import subprocess
    result = subprocess.run([sys.executable, str(ROOT / 'update_shortcut.py')], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
else:
    print("WARNING: .exe not found after build")