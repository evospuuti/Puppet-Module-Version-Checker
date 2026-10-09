# Puppet Module Version Checker

Kleines Dashboard, das getrackte Versionen gegen ihre Upstream-Quellen prüft:

- **Puppet Module** gegen die [Puppet Forge API](https://forgeapi.puppet.com)
- **GitHub Releases** (z.B. Puppetboard) gegen die GitHub Releases API

Backend: Flask (`server.py`), Frontend: statisches HTML/Vanilla-JS unter
`public/`. Deployment läuft auf Vercel (`vercel.json`).

## Lokale Entwicklung

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server.py          # läuft auf http://127.0.0.1:5000
```

Der Werkzeug-Debugger (interaktive Python-Konsole im Browser) ist
standardmäßig aus. Aktivieren nur lokal mit `FLASK_DEBUG=1`; `HOST=0.0.0.0`
macht den Server im LAN erreichbar - nie beides zusammen.

## Tests

```bash
pip install pytest
pytest tests/
```

## Versionen pflegen

**`versions.json`**:

- `puppet_modules`: Modulname → installierte Version
- `github_releases`: `owner/repo` → getrackte Version

Empfohlen: Mit der Umgebungsvariable `GITHUB_TOKEN` werden GitHub-Abfragen
authentifiziert. Ohne Token gilt das Limit von 60 Requests/h pro IP - bei
geteilten Egress-IPs (Vercel) ist das schnell erschöpft und die GitHub-Checks
laufen auf HTTP 403. Ein Fine-grained Token ohne Berechtigungen reicht
(nur öffentliche Repos).

## API-Endpoints

| Endpoint | Beschreibung |
|---|---|
| `GET /api/modules` | Puppet Module + GitHub Releases mit Forge-/Release-Vergleich |
| `GET /api/system_status` | Zusammenfassung für das Dashboard (deprecated oder fehlgeschlagene Checks → `Warnung`, nur Updates → `Info`) |
| `GET /api/versions` | Rohdaten aus `versions.json` |

Die Ergebnisse werden serverseitig 5 Minuten im Speicher gecacht (ein
gemeinsamer Cache für beide Daten-Endpoints; bei parallelen Requests auf
leeren Cache fragt nur einer die Upstream-APIs ab). Der gesamte Abruf hat ein
Budget von 8 s, langsamere Quellen erscheinen als Timeout-Fehler. Das
Frontend cacht zusätzlich per
Stale-While-Revalidate in `localStorage`. API-Antworten tragen einen ETag;
ein Conditional GET mit passendem `If-None-Match` liefert 304 ohne Body.
"Aktualisieren" im Frontend erzwingt die Revalidierung, die vorhandenen
Daten bleiben dabei sichtbar.
