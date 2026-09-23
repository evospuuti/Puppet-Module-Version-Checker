# Puppet Module Version Checker

Kleines Dashboard, das getrackte Versionen gegen ihre Upstream-Quellen prüft:

- **Puppet Module** gegen die [Puppet Forge API](https://forgeapi.puppet.com)
- **GitHub Releases** (z.B. Puppetboard) gegen die GitHub Releases API
- **AVD-Versionsinventar**: alle versionsprüfbaren Artefakte der vier
  AVD-Repos (Core, Packer, AMS, SAP) mit automatischen Latest-Checks gegen
  ausschließlich öffentliche, auth-freie Quellen - GitHub Releases/Commits,
  Terraform Registry, HashiCorp Checkpoint, Chocolatey, PowerShell Gallery
  und die Chrome-Versionhistory. Quellen, die den Azure-Tenant oder
  dev.azure.com erfordern würden, werden bewusst **nicht** abgefragt und
  nur informativ gelistet.

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

**`versions.json`** (Puppet-Teil):

- `puppet_modules`: Modulname → installierte Version
- `github_releases`: `owner/repo` → getrackte Version

**`avd_inventory.json`** (AVD-Teil, Datenmodell aus dem AVD-Versionsinventar):

- `items`: ein Eintrag pro Artefakt. `art` steuert die Vergleichslogik
  (`pin`/`lock` = exakter Vergleich, `constraint` = Range-Auswertung inkl.
  `~>`-Operator, `floating` = nur Latest anzeigen, `intern` = reiner
  Konsistenz-Hinweis). `quelle.typ` steuert den Poller:
  - automatisch: `github-release`, `github-commit`, `tf-registry`,
    `hashicorp-checkpoint`, `choco`, `psgallery`, `chrome-versionhistory`
  - nicht abgefragt: `azure-cli` (bewusst kein Tenant-Zugriff), `ms-learn`,
    `vendor-manuell`, `intern` - hier ggf. `known_latest` von Hand pflegen
- `suppression` an einem Item macht aus "veraltet" ein neutrales
  "Suppressed" mit Grund und Neubewertungs-Trigger
- `kontrakte`, `termine`, `hinweise`: Cross-Repo-Konsistenzchecks,
  Fristen-Timeline und dokumentierte bewusste Entscheidungen

Empfohlen: Mit der Umgebungsvariable `GITHUB_TOKEN` werden GitHub-Abfragen
authentifiziert. Ohne Token gilt das Limit von 60 Requests/h pro IP - bei
geteilten Egress-IPs (Vercel) ist das schnell erschöpft und die GitHub-Checks
laufen auf HTTP 403. Ein Fine-grained Token ohne Berechtigungen reicht
(nur öffentliche Repos).

## API-Endpoints

| Endpoint | Beschreibung |
|---|---|
| `GET /api/modules` | Puppet Module + GitHub Releases mit Forge-/Release-Vergleich |
| `GET /api/avd-components` | AVD-Inventar: geprüfte Items, Kontrakte, Termine, Hinweise |
| `GET /api/system_status` | Zusammenfassung für das Dashboard |
| `GET /api/versions` | Rohdaten aus `versions.json` |

Die Ergebnisse werden serverseitig 5 Minuten im Speicher gecacht (ein
gemeinsamer Cache für alle drei Daten-Endpoints; bei parallelen Requests auf
leeren Cache fragt nur einer die Upstream-APIs ab). Der gesamte Abruf hat ein
Budget von 8 s, langsamere Quellen erscheinen als Timeout-Fehler. Das
Frontend cacht zusätzlich per
Stale-While-Revalidate in `localStorage`. API-Antworten tragen einen ETag;
ein Conditional GET mit passendem `If-None-Match` liefert 304 ohne Body.
"Aktualisieren" im Frontend erzwingt die Revalidierung, die vorhandenen
Daten bleiben dabei sichtbar.
