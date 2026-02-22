# KNX Project Viewer

Web-UI zum Hochladen und Anzeigen von `.knxproj`-Dateien, basierend auf [xknxproject](https://github.com/XKNX/xknxproject).

**Stack:** FastAPI · Vanilla HTML/JS · Tailwind CSS · Alpine.js

## Dateien

```
knxproject-viewer/
├── server.py        # FastAPI-Backend
├── index.html       # Single-Page-Frontend
├── requirements.txt # Python-Abhängigkeiten
├── setup.sh         # Erstellt .venv und installiert alles
└── run.sh           # Startet den Server (ruft setup.sh bei Bedarf auf)
```

## Setup & Start

```bash
# Einmalig einrichten (erstellt .venv/, installiert Abhängigkeiten)
./setup.sh

# Server starten
./run.sh
# → http://localhost:8000
```

`run.sh` prüft beim Start automatisch, ob das venv existiert, und führt `setup.sh` bei Bedarf nach.

## Backend

- `GET /` → liefert `index.html`
- `POST /api/parse` → `multipart/form-data` mit `file`, `password` (optional), `language` (optional)
  - Parst via `XKNXProj(...).parse()`
  - `InvalidPasswordException` → HTTP 422
  - Sonstige Fehler → HTTP 500

## Frontend-Tabs

| Tab | Inhalt |
|-----|--------|
| **Info** | Projektdetails als Key-Value-Tabelle |
| **Geräte** | Durchsuchbare Tabelle; Klick klappt KOs des Geräts auf |
| **Gruppenadressen** | Durchsuchbar mit Adresse, Name, DPT, Beschreibung |
| **Topologie** | Aufklappbarer Baum: Bereich → Linie → Geräte |
| **Standorte** | Aufklappbarer Baum: Gebäude → Stockwerk → Raum → Funktionen |
| **Kommunikationsobjekte** | Alle KOs aller Geräte, durchsuchbar |
| **Funktionen** | Liste mit verknüpften Gruppenadressen |

## Abhängigkeiten

```
fastapi
uvicorn[standard]
python-multipart
xknxproject
```

xknxproject wird aus dem lokalen Repo als Entwicklungsversion installiert:

```bash
.venv/bin/pip install -e ../xknxproject
```

## Testdateien

`.knxproj`-Beispieldateien liegen im Nachbar-Repo:

```
../xknxproject/test/resources/*.knxproj
```
