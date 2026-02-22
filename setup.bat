@echo off
setlocal

set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%.venv
set XKNXPROJECT_DIR=%SCRIPT_DIR%..\xknxproject

echo =^> Prüfe Python-Installation ...
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden. Bitte Python 3.11+ installieren und zum PATH hinzufügen.
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo =^> Erstelle virtuelles Environment in %VENV_DIR% ...
python -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo FEHLER: Konnte virtuelles Environment nicht erstellen.
    pause
    exit /b 1
)

echo =^> Installiere Abhängigkeiten ...
"%VENV_DIR%\Scripts\pip" install --upgrade pip --quiet
"%VENV_DIR%\Scripts\pip" install -r "%SCRIPT_DIR%requirements.txt" --quiet
"%VENV_DIR%\Scripts\pip" install websockets xknx --quiet

echo =^> Installiere xknxproject (lokale Entwicklungsversion) ...
if not exist "%XKNXPROJECT_DIR%" (
    echo FEHLER: Verzeichnis %XKNXPROJECT_DIR% nicht gefunden.
    echo Bitte sicherstellen, dass xknxproject als Schwester-Verzeichnis vorhanden ist.
    pause
    exit /b 1
)
"%VENV_DIR%\Scripts\pip" install -e "%XKNXPROJECT_DIR%" --quiet

echo.
echo Fertig! Server starten mit:
echo   run.bat
echo.
pause
