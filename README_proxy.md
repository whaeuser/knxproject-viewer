# KNX Gateway Proxy

Ermöglicht die Anbindung eines **entfernten KNX-Busses** (z. B. Raspberry Pi mit KNX/IP-Gateway) an den OpenKNXViewer-Server über eine gesicherte WebSocket-Verbindung (WSS + Token-Authentifizierung).

## Architektur

```
Remote-Rechner (z. B. Raspberry Pi)       Server (OpenKNXViewer)
┌──────────────────────────────┐           ┌──────────────────────────┐
│  knx_proxy [setup|start]     │           │  server.py               │
│  ┌────────────────────────┐  │  WSS +    │  /ws/remote-gateway      │
│  │  knx_gateway_proxy.py  │──┼──Token───►│                          │
│  │  xknx (TUNNELING/IP)   │  │  ◄─write──│  → _process_telegram()   │
│  └────────────────────────┘  │  ◄─read───│  (wie lokales Gateway)   │
└──────────────────────────────┘           └──────────────────────────┘
```

**Verbindungsrichtung:** Der Proxy verbindet sich aktiv zum Server — nicht umgekehrt. Dadurch sind keine Portfreigaben auf dem Remote-Rechner nötig (Firewall-freundlich).

---

## Voraussetzungen

| | Remote-Rechner | Server |
|---|---|---|
| Python | 3.9+ | bereits vorhanden |
| Pakete | `xknx`, `websockets` | bereits installiert |
| Netzwerk | ausgehende WSS-Verbindung zum Server | HTTPS/WSS empfohlen |

---

## Einrichtung auf dem Remote-Rechner

### 1. Dateien kopieren

Folgende drei Dateien auf den Remote-Rechner übertragen (z. B. per `scp`):

```
knx_gateway_proxy.py
knx_proxy              ← Mac / Linux / Raspberry Pi
knx_proxy.bat          ← Windows
```

### 2. Virtuelle Umgebung erstellen

**Mac / Linux / Raspberry Pi:**
```bash
chmod +x knx_proxy
./knx_proxy setup
```

**Windows:**
```cmd
knx_proxy.bat setup
```

Das Skript erstellt automatisch `.venv-proxy/` im selben Verzeichnis und installiert `xknx` und `websockets`.

---

## Token vom Server abrufen

Im OpenKNXViewer-Browser-Interface:

1. ⚙-Button in der Kopfzeile → Gateway-Konfiguration öffnen
2. **Verbindungstyp** auf **Remote-Gateway (Proxy)** umstellen
3. **Speichern** klicken
4. Token anzeigen und mit **⎘** in die Zwischenablage kopieren

Das fertige Start-Kommando wird direkt im Modal angezeigt und kann kopiert werden.

---

## Proxy starten

**Mac / Linux / Raspberry Pi:**
```bash
./knx_proxy \
  --server-url "wss://mein-server.de/ws/remote-gateway?token=TOKEN" \
  --knx-ip 192.168.1.100
```

**Windows:**
```cmd
knx_proxy.bat ^
  --server-url "wss://mein-server.de/ws/remote-gateway?token=TOKEN" ^
  --knx-ip 192.168.1.100
```

**Lokaler Test (ohne TLS):**
```bash
./knx_proxy \
  --server-url "ws://localhost:8002/ws/remote-gateway?token=TOKEN" \
  --knx-ip 192.168.1.100 \
  --ssl-no-verify
```

---

## Alle Optionen

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `--server-url URL` | — | WebSocket-URL des Servers inkl. Token (**Pflichtfeld**) |
| `--knx-ip IP` | — | IP-Adresse des lokalen KNX/IP-Gateways (**Pflichtfeld**) |
| `--knx-port PORT` | `3671` | UDP-Port des KNX/IP-Gateways |
| `--knx-type ip` | `ip` | Verbindungstyp (`usb` noch nicht unterstützt) |
| `--ssl-no-verify` | aus | TLS-Zertifikat nicht prüfen (nur für lokale Tests) |

---

## Konfigurationsdatei (Alternative zu CLI-Argumenten)

Statt langer Kommandozeilenargumente kann eine `proxy_config.json` im selben Verzeichnis angelegt werden:

```json
{
  "server_url": "wss://mein-server.de/ws/remote-gateway?token=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "knx_ip": "192.168.1.100",
  "knx_port": 3671,
  "ssl_no_verify": false
}
```

Dann reicht:
```bash
./knx_proxy
```

CLI-Argumente überschreiben Werte aus der Datei.

---

## Autostart auf dem Raspberry Pi (systemd)

Um den Proxy automatisch beim Systemstart zu laden:

```bash
sudo nano /etc/systemd/system/knx-proxy.service
```

```ini
[Unit]
Description=KNX Gateway Proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/knx-proxy
ExecStart=/home/pi/knx-proxy/.venv-proxy/bin/python3 /home/pi/knx-proxy/knx_gateway_proxy.py \
    --server-url "wss://mein-server.de/ws/remote-gateway?token=TOKEN" \
    --knx-ip 192.168.1.100
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable knx-proxy
sudo systemctl start knx-proxy
sudo systemctl status knx-proxy
```

---

## Nachrichtenprotokoll

### Proxy → Server

| Typ | Felder | Beschreibung |
|-----|--------|--------------|
| `telegram` | `src`, `ga`, `apci`, `payload_type`, `payload_value` | KNX-Telegramm vom Bus |
| `status` | `connected`, `hw_type` | Verbindungsstatus-Meldung |

### Server → Proxy

| Typ | Felder | Beschreibung |
|-----|--------|--------------|
| `write` | `ga`, `payload_type`, `payload_value` | Schreibbefehl an den Bus |
| `read` | `ga` | Leseanforderung an den Bus |

---

## Sicherheit

- **Authentifizierung:** UUID4-Token (122 Bit Entropie) als URL-Parameter — WSS verschlüsselt die URL
- **Verschlüsselung:** WSS (TLS) für alle Daten in Transit
- **Produktionseinsatz:** Server hinter Reverse-Proxy (nginx / Caddy) mit gültigem TLS-Zertifikat empfohlen
- **Token erneuern:** Im Gateway-Modal unter ⚙ → Token wird beim ersten Start automatisch generiert und in `config.json` gespeichert

---

## Fehlersuche

**Proxy verbindet sich nicht:**
- Token korrekt? Im Browser-Modal angezeigten Token verwenden
- Verbindungstyp im Modal auf „Remote-Gateway" gesetzt und gespeichert?
- Server erreichbar? `curl https://mein-server.de/api/mode` testen

**KNX-Gateway nicht gefunden:**
- IP-Adresse des KNX/IP-Gateways prüfen (`--knx-ip`)
- Sind Proxy und KNX-Gateway im selben Netzwerk?

**Abhängigkeiten fehlen:**
```bash
./knx_proxy setup
```

**Logs ansehen (Raspberry Pi mit systemd):**
```bash
journalctl -u knx-proxy -f
```
