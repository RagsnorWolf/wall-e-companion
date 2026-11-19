@echo off
setlocal
chcp 65001 >nul
title WALL-E - Simulador Robot Fisico
cd /d "%~dp0"

echo.
echo ========================================
echo   WALL-E - Simulador de Robot Fisico
echo   Cerebro Motor (PyBullet + PPO)
echo ========================================
echo.

:: Verificar entorno virtual del simulador
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo No se encontro Python ni el entorno virtual.
    echo Instalalo y ejecuta: pip install -r requirements.txt
    pause
    exit /b 1
  )
)

:: Limpieza previa. Dos cosas distintas, las dos rompen el arranque:
::  1) Una ventana de PyBullet huerfana deja el viewport en checker y sin
::     WALL-E, y bloquea el lanzamiento siguiente.
::  2) Un entrenamiento de PyBullet en marcha satura la CPU: la ventana
::     OpenGL tarda minutos en crearse y el chat marca "no responde".
echo Cerrando instancias y entrenamientos anteriores...
powershell -NoProfile -Command "$p = @(Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*interactive_walle.py*' -or $_.CommandLine -like '*train_walle*' -or $_.CommandLine -like '*multiprocessing-fork*' }); if ($p | Where-Object { $_.CommandLine -like '*train_walle*' }) { Write-Host '[AVISO] Habia un entrenamiento en curso: lo cerre para liberar CPU.' }; foreach ($x in $p) { Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

:: UTF-8 para que los acentos y el abanico LiDAR no rompan los prints.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo Iniciando WALL-E Simulador Robot...
echo.
echo Instrucciones en la ventana de chat:
echo  - Escribe: "avanza 2 metros", "gira 90 grados", "detente"
echo  - Modo PPO (autonomo): haga clic en "Modo: PPO" en la cabecera
echo  - Camara: clic izquierdo = rotar ^| rueda = zoom ^| Ctrl+clic = mover
echo  - Sensores: abanico LiDAR azul de 72 rayos (entorno V4)
echo  - Califica: "Lo hizo bien" / "No lo hizo bien"
echo.

%PY% interactive_walle.py --env v3

if errorlevel 1 (
  echo.
  echo El simulador se cerro con error.
  pause
)
exit /b 0
