@echo off
rem Entrenamiento headless con log. Lo lanza el agente o el usuario.
rem No abrir el simulador mientras esto corre: su lanzador mata train_walle*.
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

set STEPS=%~1
if "%STEPS%"=="" set STEPS=600000

echo [%DATE% %TIME%] arrancando %STEPS% pasos > models\train_v5_run.log
%PY% -u train_walle_v5.py --timesteps %STEPS% --workers 2 --vec dummy >> models\train_v5_run.log 2>&1
echo [%DATE% %TIME%] EXITCODE=%errorlevel% >> models\train_v5_run.log
