@echo off
:: knx_proxy.bat — Startskript für den KNX Gateway Proxy (Windows)
::
:: Verwendung:
::   knx_proxy.bat setup                         Venv erstellen & Pakete installieren
::   knx_proxy.bat [OPTIONEN]                    Proxy starten
::
:: Optionen (werden direkt an knx_gateway_proxy.py weitergegeben):
::   --server-url URL      WebSocket-URL des Servers inkl. Token
::                         Beispiel: wss://host/ws/remote-gateway?token=TOKEN
::                         Lokal:    ws://localhost:8002/ws/remote-gateway?token=TOKEN
::   --knx-ip IP           IP-Adresse des lokalen KNX/IP-Gateways
::   --knx-port PORT       KNX-Port (Standard: 3671)
::   --knx-type ip         Verbindungstyp (Standard: ip)
::   --ssl-no-verify       TLS-Zertifikat nicht pruefen (nur fuer lokale Tests)
::
:: Konfigurationsdatei (Alternative zu CLI-Argumenten):
::   proxy_config.json im selben Verzeichnis anlegen:
::   {"server_url": "wss://...", "knx_ip": "192.168.1.100"}

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
:: Trailing backslash entfernen
if "!SCRIPT_DIR:~-1!"=="\" set "SCRIPT_DIR=!SCRIPT_DIR:~0,-1!"

set "PROXY_SCRIPT=!SCRIPT_DIR!\knx_gateway_proxy.py"
set "PROXY_CFG=!SCRIPT_DIR!\proxy_config.json"
set "VENV_DIR=!SCRIPT_DIR!\.venv-proxy"
set "VENV_PYTHON=!VENV_DIR!\Scripts\python.exe"

:: ── System-Python finden ──────────────────────────────────────────────────────
set "SYS_PYTHON="
for %%P in (python python3 py) do (
    if "!SYS_PYTHON!"=="" (
        %%P --version >nul 2>&1
        if not errorlevel 1 (
            for /f "delims=" %%V in ('%%P -c "import sys; print(sys.version_info.major)" 2^>nul') do (
                if "%%V"=="3" set "SYS_PYTHON=%%P"
            )
        )
    )
)

:: ── setup ─────────────────────────────────────────────────────────────────────
if /i "%~1"=="setup" goto :cmd_setup
goto :cmd_start

:cmd_setup
if "!SYS_PYTHON!"=="" (
    echo Fehler: Python 3 nicht gefunden.
    echo Bitte Python 3.9+ von https://www.python.org/downloads/ installieren.
    echo Sicherstellen, dass "Add Python to PATH" beim Setup aktiviert ist.
    pause
    exit /b 1
)
for /f "delims=" %%V in ('!SYS_PYTHON! --version 2^>^&1') do echo ==^> Verwende System-Python: %%V
echo ==^> Erstelle virtuelle Umgebung in !VENV_DIR! ...
!SYS_PYTHON! -m venv "!VENV_DIR!"
if errorlevel 1 (
    echo Fehler beim Erstellen der virtuellen Umgebung.
    echo Raspberry Pi / Debian: sudo apt install python3-venv
    pause
    exit /b 1
)
echo ==^> Installiere Abhaengigkeiten (xknx, websockets^) ...
"!VENV_PYTHON!" -m pip install --upgrade pip --quiet
"!VENV_PYTHON!" -m pip install xknx websockets --quiet
if errorlevel 1 (
    echo Fehler bei der Installation der Pakete.
    pause
    exit /b 1
)
echo.
echo Fertig! Proxy starten mit:
echo   knx_proxy.bat --server-url "wss://host/ws/remote-gateway?token=TOKEN" --knx-ip 192.168.1.100
goto :end

:: ── Venv-Pruefung ─────────────────────────────────────────────────────────────
:cmd_start
if not exist "!VENV_PYTHON!" (
    echo Fehler: Virtuelle Umgebung nicht gefunden.
    echo Bitte zuerst ausfuehren:  knx_proxy.bat setup
    pause
    exit /b 1
)

:: proxy_config.json anzeigen wenn vorhanden
if exist "!PROXY_CFG!" (
    echo Konfiguration aus proxy_config.json:
    "!VENV_PYTHON!" -c "import json,sys; d=json.load(open(sys.argv[1])); [print(f'  {k}: {v}') for k,v in d.items() if k!='ssl_no_verify' or v]" "!PROXY_CFG!"
)

:: Ohne Argumente und ohne Config: Hilfe anzeigen
set "HAS_ARGS=0"
if not "%~1"=="" set "HAS_ARGS=1"
if "!HAS_ARGS!"=="0" if not exist "!PROXY_CFG!" (
    echo.
    echo Verwendung: knx_proxy.bat [OPTIONEN]
    echo.
    echo   --server-url URL    WebSocket-URL des Servers inkl. Token
    echo   --knx-ip IP         IP-Adresse des lokalen KNX/IP-Gateways
    echo   --knx-port PORT     KNX-Port ^(Standard: 3671^)
    echo   --knx-type ip       Verbindungstyp ^(Standard: ip^)
    echo   --ssl-no-verify     TLS-Zertifikat nicht pruefen ^(nur fuer Tests^)
    echo.
    echo Alternativ: proxy_config.json im selben Verzeichnis anlegen:
    echo   {"server_url":"wss://...","knx_ip":"192.168.1.100"}
    echo.
    echo Venv neu einrichten:  knx_proxy.bat setup
    pause
    goto :end
)

echo Starte KNX Gateway Proxy ...
"!VENV_PYTHON!" "!PROXY_SCRIPT!" %*
if errorlevel 1 (
    echo.
    echo Proxy beendet mit Fehler.
    pause
)

:end
endlocal
