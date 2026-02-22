@echo off
setlocal

set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%.venv

if not exist "%VENV_DIR%\Scripts\uvicorn.exe" (
    echo Virtuelle Umgebung nicht gefunden. Führe setup.bat aus ...
    call "%SCRIPT_DIR%setup.bat"
    if errorlevel 1 exit /b 1
)

echo =^> Starte KNX Project Viewer auf http://localhost:8002
cd /d "%SCRIPT_DIR%"
"%VENV_DIR%\Scripts\uvicorn" server:app --host 0.0.0.0 --port 8002
