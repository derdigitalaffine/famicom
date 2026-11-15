# FamiCom

**Selbst gehostete Familienkommunikation** mit XMPP-Chat und SIP/VoIP-Telefonie, React-PWA, Gruppen, zentraler Familienverwaltung und erweiterbarer FreeSWITCH-Anlage.

> **Entwicklungsstand (15.11.2026):** technische Foundation auf einem Feature-Branch. Die End-to-End-Anbindung von Browser-SIP, mobilen XMPP-Clients, TLS, SIP-Trunk und Video ist noch zu verifizieren. Keine Produktivfreigabe.

## Stack

| Baustein | Aufgabe |
|---|---|
| React 19, Mantine, PWA | Familienoberfläche, Geräte und Anrufe |
| Converse.js 14 | XMPP-Chats, Kontakte, MUC, Verlauf, Datei-Upload (je nach Server-/Client-Feature) |
| SIP.js 0.21 | Browseranrufe über `/sip-ws` |
| Prosody 13 | XMPP-Server mit MUC/MAM/WebSocket und angebundener Authentifizierung |
| FreeSWITCH 1.10 | SIP-Nebenstellen, Rufplan, Konferenzen, optionaler Upstream |
| FastAPI, SQLite | Kanonische Konten, Argon2id, Rollen, Session-Cookies, sichere Provisionierung |
| Caddy | TLS, PWA, XMPP-WS-, SIP-WS- und API-Reverse-Proxy |

## Setup

Auf einem **amd64-Linux** mit Docker Engine + Compose v2, Python 3, OpenSSL, freien Ports 80/443, 5222 sowie SIP/RTP nach Bedarf:

```bash
git clone https://github.com/derdigitalaffine/famicom.git
cd famicom
git switch feat/communications-foundation  # bis zum Merge
./scripts/bootstrap.sh
```

Das Skript verwendet `whiptail` für einen ncurses-artigen Dialog (falls vorhanden; sonst Texteingabe), fragt Domains, TLS-Modus, Administratorkonto, SIP-Bind-IP und NAT-Adresse ab, erzeugt geheimnisgeschützte Konfiguration, startet Compose und legt den ersten Administrator an. Anschließend `docker compose ps` und `./scripts/doctor.sh` prüfen.

**XMPP TLS:** Bootstrap erstellt für native XMPP-Clients zunächst ein nur 30 Tage gültiges selbstsigniertes Zertifikat (SNI `$FAMICOM_DOMAIN`). Ohne Vertrauensstellung im Client klappt die Verbindung nicht. Vor einer öffentlichen Freigabe ein regulär signiertes Zertifikat für die XMPP-Domain bereitstellen, Secrets ersetzen und den XMPP-Container neu starten. Die Caddy-Web-CA ist davon unabhängig.

**Achtung:** Der initiale FreeSWITCH-Container basiert auf einem Community-Image `yukiosaka/freeswitch:latest`, nicht auf einem offiziellen SignalWire-Produktivimage. Vor einem Produktionsbetrieb Digest festschreiben, Image auditieren und gegen Freeswitch-Versionen testen. Native SIP-Clients erreichen Port 5060 nur an der gewählten Bind-Adresse; voreingestellt ist 127.0.0.1. Für Geräte außerhalb des Hosts VPN (WireGuard/Tailscale) oder eigens gehärtetes SIPS verwenden.

### Konten

Mit dem Bootstrap-Admin in der PWA unter **Verwaltung** neue Familienmitglieder anlegen. Jedes Konto besitzt:
- XMPP-JID `benutzer@domain`; Passwort = Kontopasswort; Familienkontakte lassen sich in der XMPP-Weboberfläche direkt nach Namen suchen;
- SIP-Nebenstelle (standardmäßig ab 200) mit **separatem** hochentropischem SIP-Kennwort;
- Rolle `admin`, `adult` oder `child`.

In der PWA unter **Anrufe** das SIP-Kennwort auf eigenen Wunsch abrufen und in Linphone, Groundwire, Zoiper, MicroSIP etc. verwenden. Native XMPP-Apps: Conversations, Monal, Snikket, Gajim (Standardprotokoll, konkrete Funktionalität abhängig vom Client). Der Browserchat verwendet Converse.js, welches ggf. für den Chat nochmals das XMPP-Passwort verlangt; keine dauerhafte Speicherung des Kontopassworts durch die FamiCom-API.

### Sicherheit und externe Anschlüsse

- Keine Demo-Nebenstellen/Standardpasswörter bereitstellen; FreeSWITCH ESL 8021 **nicht veröffentlichen**.
- SIP-Trunks bleiben deaktiviert, bis ein Administrator Provider und Rufnummernpräfixe explizit konfiguriert. Kinderkonten können selbst bei aktiviertem Trunk keine abgehenden Provideranrufe vermitteln. Freigabe-/Billing-Tests sind vor Verwendung nötig.
- `tls internal` (Caddy) ist eine lokale Test-CA und nicht automatisch geräteweit vertrauenswürdig. Für öffentliche Dienste echtes Zertifikat/HTTPS und separate **Prosody STARTTLS**-Vertrauenskette bereitstellen.
- Für entfernte WebRTC-Clients oft zusätzlich TURN/STUN und korrektes NAT / externes RTP erforderlich.
- Gruppentelefonie über den internen Konferenz-Dialplan `8xxx`; serverseitige Videokonferenzen und XMPP-Jingle-zu-SIP-Gateway sind **keine** automatisch verfügbare Funktion.
- `scripts/backup.sh /sicher/backupziel` erstellt angehaltene Snapshots von API-DB, Prosody-Daten und generierter Konfiguration; einschl. SIP-Kennwörtern – unbedingt verschlüsselt aufbewahren.
- Noch **nicht** zugesichert: durchgängig verifizierte OMEMO-Ende-zu-Ende-Verschlüsselung, zuverlässiger mobiler Hintergrund-Push, Notrufe, mobile Video-/Gruppenanrufe und produktive Carrier-Interoperabilität.

## Entwicklungsablauf

```bash
python3 -m pip install -r api/requirements.txt -r api/requirements-dev.txt
python3 -m pytest -q api/tests
cd web && npm install && npm run build
```

Siehe [AGENTS.md](AGENTS.md), [Architektur](docs/architecture.md) und [Roadmap](docs/roadmap.md). GitHub [Issue #1](https://github.com/derdigitalaffine/famicom/issues/1) ist die Architektur-/Prioritätenquelle, mit einer Claim-Issue pro Lieferung.

**Docker-Dateirechte:** Bootstrap schützt das Host-Verzeichnis `.secrets` mit Modus 0700; die einzelnen Compose-Secret-Dateien sind wegen unterschiedlicher Container-UIDs lesbar (0644), jedoch außerhalb des Verzeichnisses nicht über Host-Benutzerpfade zugänglich. Bitte diese Rechte nicht ohne Prüfung ändern; keine Secrets in öffentliche Backups oder freigegebene Verzeichnisse kopieren.

### Live-Integration
CI baut und startet alle Compose-Dienste auf einem echten GitHub-Actions-Linux-Runner. Der Live-Test prüft HTTPS-/API-Erreichbarkeit, Prosody-Konfiguration, authentifizierte FreeSWITCH-Diagnose samt `reloadxml`, außerdem XMPP-STARTTLS mit einem echten SASL-Login und einem bewusst falschen Passwort sowie SIP-REGISTER inklusive Challenge/Digest mit einer tatsächlich provisionierten Nebenstelle. Dieser Test nutzt nur ein kurzlebiges, selbstsigniertes Testzertifikat; er ersetzt **keine** Sicherheits-/Interop-Zertifizierung.
