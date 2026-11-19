@echo off
setlocal
chcp 65001 >nul
title WALL-E - Entrenar Cerebro (PPO)
cd /d "%~dp0"

echo.
echo ========================================
echo   WALL-E - Entrenamiento del Cerebro
echo   RecurrentPPO (LSTM) sobre entorno V5
echo ========================================
echo.
echo OJO: el entrenamiento usa toda la CPU. Si abres el simulador
echo mientras entrena, el lanzador del simulador cierra este proceso
echo para liberar CPU. Entrena con el simulador cerrado.
echo.

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set STEPS=%~1
if "%STEPS%"=="" set STEPS=600000

echo Entrenando %STEPS% pasos.
echo Checkpoints cada 10000 pasos en models\checkpoints
echo Modelo final en models\walle_ppo_model_v5_recovery.zip
echo.

%PY% -u train_walle_v5.py --timesteps %STEPS% --workers 2 --vec dummy

echo.
echo Entrenamiento terminado. Modelo en models\walle_ppo_model_v5_recovery.zip
pause
exit /b 0
