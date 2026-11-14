@echo off
REM Wall-E Companion - Start Script (Windows)
REM Usage: start.bat [--mock] [--no-web]

cd /d "%~dp0"

echo Iniciando Wall-E Companion...
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo Creando entorno virtual...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Instalando dependencias...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

REM Run main
python main.py %*

pause