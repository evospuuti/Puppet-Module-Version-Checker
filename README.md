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
python server.py          # läuft auf http://localhost:5000
```

## Tests

```bash
pip install pytest
pytest tests/
```

## Versionen pflegen

**`versions.json`** (Puppet-Teil):

- `puppet_modules`: Modulname → installierte Version. Statt einer
  Zeichenkette kann ein Objekt stehen, wenn ein anderes Modul die
  Version deckelt:

  ```json
  "puppetlabs-stdlib": {
    "installed": "9.7.0",
    "constraint": "< 10.0.0",
    "constrained_by": ["puppet-systemd 10.0.0 (>= 9.0.0 < 10.0.0)"],
    "note": "Kein Upgrade-Pfad - das deckelnde Modul ist selbst aktuell."
  }
  ```

  Verletzt die neueste Forge-Version die `constraint`, meldet das
  Dashboard den Status **„Gedeckelt"** statt „Update" und zeigt an, wer
  deckelt. Damit bleiben dauerhaft nicht behebbare Zeilen von den echten
  offenen Updates unterscheidbar.
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

Optional: Mit der Umgebungsvariable `GITHUB_TOKEN` werden GitHub-Abfragen
authentifiziert (höheres Rate-Limit).

## API-Endpoints

| Endpoint | Beschreibung |
|---|---|
| `GET /api/modules` | Puppet Module + GitHub Releases mit Forge-/Release-Vergleich |
| `GET /api/avd-components` | AVD-Inventar: geprüfte Items, Kontrakte, Termine, Hinweise |
| `GET /api/system_status` | Zusammenfassung für das Dashboard |
| `GET /api/versions` | Rohdaten aus `versions.json` |

Die Ergebnisse werden serverseitig 5 Minuten gecacht (ein gemeinsamer Cache
für alle drei Daten-Endpoints), das Frontend cacht zusätzlich per
Stale-While-Revalidate in `localStorage`.
