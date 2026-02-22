# KNX Project Viewer

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
- **Letzter Wert** pro Gruppenadresse in der GA-Tabelle
- Persistentes Log mit täglicher Rotation (`logs/knx_bus.log`, 30 Tage)
- **Bus-only-Modus**: Geräte und GAs aus Bus-Telegrammen ableiten ohne Projektdatei
- Inline-Editierung von Namen und Beschreibungen → gespeichert in `annotations.json`
- Verbindungsindikator + Gateway-Konfiguration (IP, Port, Sprache) im Browser

---

## Setup & Start

```bash
# Einmalig einrichten (.venv erstellen, Abhängigkeiten installieren)
./setup.sh

# Privater Server starten — Bus-Monitor, Port 8002
./run.sh
# → http://localhost:8002

# Öffentlicher Server starten — nur Projektbetrachter, Port 8004
./run_public.sh
# → http://localhost:8004
```

Beide Server können gleichzeitig laufen.

---

## Autostart (macOS)

```bash
./install-autostart.sh          # privater Server auf Port 8002
./install-autostart-public.sh   # öffentlicher Server auf Port 8004
./uninstall-autostart.sh
./uninstall-autostart-public.sh
```

Startet bei jedem Login automatisch. Logs: `logs/stdout.log`, `logs/stderr.log`.

---

## Dateien

```
knxproject-viewer/
├── server.py                   # Privater Server (Port 8002): Bus-Monitor, WebSocket, KNX
├── server_public.py            # Öffentlicher Server (Port 8004): nur Projektbetrachter
├── index.html                  # Single-Page-Frontend (von beiden Servern geteilt)
├── requirements.txt            # Python-Abhängigkeiten
├── setup.sh                    # Erstellt .venv und installiert alles
├── run.sh                      # Startet privaten Server
├── run_public.sh               # Startet öffentlichen Server
├── install-autostart.sh        # macOS LaunchAgent für privaten Server
├── install-autostart-public.sh # macOS LaunchAgent für öffentlichen Server
├── uninstall-autostart.sh
├── uninstall-autostart-public.sh
├── config.json                 # Gateway-IP, Port, Sprache (automatisch erstellt)
├── annotations.json            # Inline-Annotationen (automatisch erstellt)
└── logs/
    ├── knx_bus.log             # KNX-Telegrammlog (rotierend, 30 Tage)
    ├── stdout.log              # Server-Stdout (Autostart)
    └── stderr.log              # Server-Stderr (Autostart)
```

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

---

## Abhängigkeiten

```
fastapi
uvicorn[standard]
python-multipart
xknx
websockets
xknxproject  # aus ../xknxproject/ (editable install)
```

---

## Testdateien

`.knxproj`-Beispieldateien im Nachbar-Repo:

```
../xknxproject/test/resources/*.knxproj
```
