@echo off
REM Build Wall-E Companion .exe
REM Usage: build.bat

cd /d "%~dp0"

echo Building Wall-E Companion .exe...
echo.

python build_exe.py

echo.
if exist "dist\Wall-E-Companion.exe" (
    echo EXITO: Ejecutable creado en dist\Wall-E-Companion.exe
    echo.
    echo Tamano:
    dir dist\Wall-E-Companion.exe
) else (
    echo ERROR: No se genero el ejecutable
)

pause