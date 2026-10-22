@echo off
cd /d "%~dp0"
pip install watchdog >nul 2>&1
python scripts/auto_commit.py --interval 1 --push