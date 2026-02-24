# KNX Project Viewer

> **Vibe Coded** — dieses Projekt wurde vollständig mit [Claude Code](https://claude.ai/code) erstellt.
>
> **Demo:** [knxviewer.nurdaheim.net](https://knxviewer.nurdaheim.net/)

Web-UI zum Hochladen, Analysieren und Dokumentieren von `.knxproj`-Dateien – mit optionalem Live-Bus-Monitor für KNX/IP-Gateways.

**Stack:** FastAPI · Alpine.js · Tailwind CSS · xknxproject · xknx

---

## Features

### Projektbetrachter (beide Modi)
- `.knxproj`-Datei hochladen (drag & drop oder Dateiauswahl), optional mit Passwort
- **Info** – Projektmetadaten
- **Geräte** – durchsuchbare Tabelle; aufklappbare KO-Liste pro Gerät
- **Gruppenadressen** – durchsuchbar; DPT, Beschreibung, verknüpfte KOs
- **Topologie** – Bereich → Linie → Geräte (aufklappbar)
- **Standorte** – Gebäude → Stockwerk → Raum → Funktionen (aufklappbar)
- **Kommunikationsobjekte** – alle KOs aller Geräte, durchsuchbar, nach Gerät gruppiert
- **Funktionen** – nur sichtbar wenn Projekt Funktionen enthält
- Cross-Tab-Navigation: KO → GA, GA → KO, Gerät → KOs
- DPT- und Flags-Tooltips (100+ Typen)
- Export als Markdown oder PDF

### Live Bus-Monitor (nur privater Server, Port 8002)
- Echtzeit-Telegramme via WebSocket
- **DPT-aware Dekodierung**: Werte mit Einheit (`21.34 °C`, `75 %`, `Ein/Aus`) wenn Projektdatei geladen
- Tooltip auf dem Wert zeigt DPT-Typ und Rohwert, z.B. `DPT: 9.001 | Raw: DPTArray((0x0c, 0x1a))`
- **Letzter Wert** pro Gruppenadresse in der GA-Tabelle
- Persistentes Log mit täglicher Rotation (`logs/knx_bus.log`, 30 Tage), CSV-Export
- **Bus-only-Modus**: Geräte und GAs aus Bus-Telegrammen ableiten ohne Projektdatei
- Inline-Editierung von Namen und Beschreibungen → gespeichert in `annotations.json`
- Verbindungsindikator + Gateway-Konfiguration (IP, Port, Sprache) im Browser
- **Letzte Projektdatei** wird nach dem Parsen gespeichert und beim nächsten Start automatisch vorgeschlagen

---

## Setup & Verwendung

Voraussetzung: Python 3.10+ muss auf dem System installiert sein (alle weiteren Pakete landen im isolierten `.venv/`).

```bash
# Einmalig: virtuelle Umgebung erstellen und Pakete installieren
./openknxviewer setup

# Privater Server starten — Bus-Monitor, Port 8002
./openknxviewer start
# → http://localhost:8002

# Öffentlicher Server starten — nur Projektbetrachter, Port 8004
./openknxviewer start --public
# → http://localhost:8004

# Server stoppen
./openknxviewer stop
./openknxviewer stop --public
./openknxviewer stop --all

# Status anzeigen (Server + Gateway-Verbindung)
./openknxviewer status

# Bus-Log anzeigen
./openknxviewer logs
./openknxviewer logs --lines 100
./openknxviewer logs --follow

# Gateway-Konfiguration anzeigen / setzen
./openknxviewer gateway
./openknxviewer gateway --ip 192.168.1.70 --port 3671 --language de-DE

# Alle Pakete aktualisieren
./openknxviewer update

# Autostart bei Login einrichten (macOS)
./openknxviewer autostart
./openknxviewer autostart --public
./openknxviewer autostart --remove
./openknxviewer autostart --remove --public
```

Beide Server können gleichzeitig laufen.

### Windows

> **Hinweis:** Die Windows-Version (`openknxviewer.bat`) wurde bisher nicht getestet.

```bat
openknxviewer setup
openknxviewer start
openknxviewer start --public
openknxviewer stop
openknxviewer status
openknxviewer logs --lines 100
openknxviewer gateway --ip 192.168.1.70
openknxviewer update
```

> Autostart unter Windows: Aufgabenplanung (Task Scheduler) manuell einrichten.

---

## Öffentlich / Privat

Das Frontend erkennt automatisch den Modus über `GET /api/mode`:

| | Privat (Port 8002) | Öffentlich (Port 8004) |
|---|---|---|
| Projektbetrachter | ✓ | ✓ |
| Bus-Monitor Tab | ✓ | — |
| Letzter Wert (GA-Tab) | ✓ | — |
| Gateway-Konfiguration | ✓ | — |
| WebSocket | ✓ | — |
| Annotations | ✓ | — |
| KNX-Verbindung | ✓ | — |

---

## Gateway-Konfiguration

Im ⚙-Button oben rechts (nur privater Server):
- KNX/IP Gateway IP-Adresse und Port
- Sprache für `.knxproj`-Parsing (`de-DE` Standard, `en-US` möglich)

Gespeichert in `config.json`, automatisch beim Serverstart geladen.
Alternativ per CLI: `./openknxviewer gateway --ip X.X.X.X`

---

## Dateien

```
knxproject-viewer/
├── server.py                    # Privater Server (Port 8002): Bus-Monitor, WebSocket, KNX
├── server_public.py             # Öffentlicher Server (Port 8004): nur Projektbetrachter
├── index.html                   # Single-Page-Frontend (von beiden Servern geteilt)
├── requirements.txt             # Python-Abhängigkeiten
├── openknxviewer                # CLI-Tool (macOS/Linux)
├── openknxviewer.bat            # CLI-Tool (Windows)
├── config.json                  # Gateway-IP, Port, Sprache (automatisch)
├── annotations.json             # Inline-Annotationen (automatisch erstellt)
├── last_project.json            # Letztes geparste Projekt als JSON (automatisch erstellt)
└── logs/
    ├── knx_bus.log              # KNX-Telegrammlog (rotierend, 30 Tage)
    ├── stdout.log               # Server-Stdout
    ├── stderr.log               # Server-Stderr
    ├── stdout-public.log        # Server-Stdout (öffentlich)
    └── stderr-public.log        # Server-Stderr (öffentlich)
```

---

## Abhängigkeiten

```
fastapi
uvicorn[standard]
python-multipart
websockets
xknx
xknxproject
```

---

## Lizenz

Dieses Projekt steht unter der **GNU General Public License v2** (GPL v2),
bedingt durch die Abhängigkeit von [xknxproject](https://github.com/XKNX/xknxproject) (GPL v2).

Das bedeutet: Jeder darf den Code frei verwenden, verändern und weitergeben —
vorausgesetzt, abgeleitete Werke werden ebenfalls unter GPL v2 veröffentlicht.

Siehe [LICENSE](LICENSE).

---

## Danke

Dieses Projekt wäre ohne folgende großartige Open-Source-Bibliotheken nicht möglich:

| Bibliothek | Beschreibung | Lizenz |
|---|---|---|
| [xknxproject](https://github.com/XKNX/xknxproject) | Parst `.knxproj`-Dateien | GPL v2 |
| [xknx](https://github.com/XKNX/xknx) | KNX/IP-Kommunikation und DPT-Dekodierung | MIT |
| [FastAPI](https://fastapi.tiangolo.com) | Modernes Python-Web-Framework | MIT |
| [Alpine.js](https://alpinejs.dev) | Leichtgewichtiges JavaScript-Framework | MIT |
| [Tailwind CSS](https://tailwindcss.com) | Utility-first CSS-Framework | MIT |

Herzlichen Dank an alle Maintainer und Contributors dieser Projekte!
