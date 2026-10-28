@echo off
setlocal
chcp 65001 >nul
title WALL-E - cabina local
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  set "PY=python"
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    set "PY=py -3"
  ) else (
    echo.
    echo No encontre Python en esta PC.
    echo Instalalo desde https://python.org y volve a intentar.
    echo.
    pause
    exit /b 1
  )
)

%PY% server.py
if errorlevel 1 (
  echo.
  echo El servidor se cerro con error.
  pause
)
