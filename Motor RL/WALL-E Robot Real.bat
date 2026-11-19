@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title WALL-E - Simulador + Robot Real
cd /d "%~dp0"

echo.
echo ========================================
echo   WALL-E - Cerebro en la PC
echo   Simulador PyBullet -^> ESP32 -^> UNO
echo ========================================
echo.

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  where python >nul 2>nul
  if !errorlevel!==0 (
    set "PY=python"
  ) else (
    echo No se encontro Python ni el entorno virtual.
    pause
    exit /b 1
  )
)

set "ROBOT_ARGS="
set "IP=%~1"
if "%IP%"=="" if exist "robot_ip.txt" (
  set /p IP=<robot_ip.txt
  echo IP leida de robot_ip.txt: !IP!
)
if "%IP%"=="" (
  set /p IP=Escribe la IP del ESP32, por ejemplo 192.168.1.50: 
)
if "%IP%"=="" (
  echo Sin IP: se abre solo el simulador, sin enlace al robot.
) else (
  >"robot_ip.txt" echo !IP!
  set "ROBOT_ARGS=--robot !IP!"
)

echo Cerrando instancias anteriores...
powershell -NoProfile -Command "$p = @(Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*interactive_walle.py*' -or $_.CommandLine -like '*train_walle*' -or $_.CommandLine -like '*multiprocessing-fork*' }); if ($p | Where-Object { $_.CommandLine -like '*train_walle*' }) { Write-Host '[AVISO] Habia un entrenamiento en curso: lo cerre para liberar CPU.' }; foreach ($x in $p) { Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo Enlace de orugas: !ROBOT_ARGS!
echo Si el robot no responde, el simulador arranca igual.
echo.

%PY% interactive_walle.py --env v3 !ROBOT_ARGS!

if errorlevel 1 (
  echo.
  echo El simulador se cerro con error.
  pause
)
exit /b 0
