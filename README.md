# Puppet Module Version Checker

Kleines Dashboard, das getrackte Versionen gegen ihre Upstream-Quellen prüft:

- **Puppet Module** gegen die [Puppet Forge API](https://forgeapi.puppet.com)
- **GitHub Releases** (z.B. Puppetboard) gegen die GitHub Releases API
- **AVD-Komponenten** (Azure Virtual Desktop) gegen GitHub Releases und die
  Terraform Registry; Komponenten ohne API werden als "manuell" gelistet

Backend: Flask (`server.py`), Frontend: statisches HTML/Vanilla-JS unter
`public/`. Deployment läuft auf Vercel (`vercel.json`).

## Lokale Entwicklung

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server.py          # läuft auf http://localhost:5000
```

## Tests

```bash
pip install pytest
pytest tests/
```

## Versionen pflegen

Alle getrackten Versionen leben in `versions.json`:

- `puppet_modules`: Modulname → installierte Version
- `github_releases`: `owner/repo` → getrackte Version
- `avd_components`: Liste von Komponenten mit `check_type`:
  - `github_release` / `terraform_registry`: neueste Version wird automatisch
    abgerufen (`check_source` gibt Repo bzw. Provider an)
  - `manual`: keine API verfügbar; `known_latest` von Hand pflegen und
    `_meta.last_updated` aktualisieren

Optional: Mit der Umgebungsvariable `GITHUB_TOKEN` werden GitHub-Abfragen
authentifiziert (höheres Rate-Limit).

## API-Endpoints

| Endpoint | Beschreibung |
|---|---|
| `GET /api/modules` | Puppet Module + GitHub Releases mit Forge-/Release-Vergleich |
| `GET /api/avd-components` | AVD-Komponenten mit neuester Version |
| `GET /api/system_status` | Zusammenfassung für das Dashboard |
| `GET /api/versions` | Rohdaten aus `versions.json` |

Die Ergebnisse werden serverseitig 5 Minuten gecacht (ein gemeinsamer Cache
für alle drei Daten-Endpoints), das Frontend cacht zusätzlich per
Stale-While-Revalidate in `localStorage`.
