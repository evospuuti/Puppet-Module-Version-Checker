import os
import json
import logging
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from functools import partial
from datetime import datetime, timezone
from urllib.parse import quote
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from werkzeug.exceptions import NotFound
from werkzeug.middleware.proxy_fix import ProxyFix

# ============================================================================
# APP SETUP
# ============================================================================

app = Flask(__name__)

# Hinter dem Vercel-Proxy steht die Client-IP in X-Forwarded-For. Ohne
# ProxyFix sieht der Rate-Limiter nur die Proxy-IP und alle Nutzer teilen
# sich ein gemeinsames Limit.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Kompaktes JSON ohne \uXXXX-Escapes: Umlaute in Hinweisen/Terminen werden
# als UTF-8 ausgeliefert statt 6 Byte pro Zeichen (kleinere Antworten).
app.json.compact = True
app.json.ensure_ascii = False

# CORS nur für eigene Origin erlauben (Vercel-Domain + lokale Entwicklung)
CORS(app, origins=[
    'https://puppet-module-version-checker.vercel.app',
    'http://localhost:5000',
    'http://127.0.0.1:5000'
])

# Rate-Limiting zum Schutz der API-Endpoints
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://"
)

# Logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ============================================================================
# SECURITY HEADERS
# ============================================================================

@app.after_request
def add_security_headers(response):
    """Sicherheits- und Cache-Header für alle Responses."""
    # Security Headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )

    # Cache-Header für statische Dateien
    if request.path.startswith('/styles/') or request.path.startswith('/scripts/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'

    # CDN-Caching für API-Antworten: Browser cacht nicht (max-age=0), aber die
    # Vercel-Edge cacht 5 Minuten (s-maxage) und liefert danach bis zu 10
    # Minuten stale aus, während im Hintergrund revalidiert wird. Damit
    # erreichen die meisten Requests die Serverless Function gar nicht.
    if (request.path.startswith('/api/') and request.method == 'GET'
            and response.status_code == 200):
        response.headers['Cache-Control'] = (
            'public, max-age=0, s-maxage=300, stale-while-revalidate=600')
        # ETag + Conditional GET: max-age=0 lässt den Browser bei jedem
        # Seitenaufruf revalidieren. Mit passendem If-None-Match geht nur
        # ein 304 ohne Body über die Leitung statt der kompletten JSON-Antwort.
        if not response.direct_passthrough:
            response.add_etag()
            response = response.make_conditional(request)

    return response

# ============================================================================
# VERSION LOADING FROM JSON (cached in memory)
# ============================================================================

_versions_cache = None

def load_versions():
    """Lädt die installierten Versionen aus versions.json (einmalig gecached)."""
    global _versions_cache
    if _versions_cache is not None:
        return _versions_cache

    versions_file = os.path.join(os.path.dirname(__file__), 'versions.json')
    try:
        with open(versions_file, 'r', encoding='utf-8') as f:
            _versions_cache = json.load(f)
            return _versions_cache
    except FileNotFoundError:
        logger.warning("versions.json not found, using empty defaults")
        return {"puppet_modules": {}, "github_releases": {}}
    except json.JSONDecodeError as e:
        logger.error("Error parsing versions.json: %s", e)
        return {"puppet_modules": {}, "github_releases": {}}


_EMPTY_INVENTORY = {"_meta": {}, "kategorien": [], "items": [],
                    "kontrakte": [], "termine": [], "hinweise": []}
_inventory_cache = None


def load_avd_inventory():
    """Lädt das AVD-Versionsinventar aus avd_inventory.json (einmalig gecached)."""
    global _inventory_cache
    if _inventory_cache is not None:
        return _inventory_cache

    inventory_file = os.path.join(os.path.dirname(__file__), 'avd_inventory.json')
    try:
        with open(inventory_file, 'r', encoding='utf-8') as f:
            _inventory_cache = json.load(f)
            return _inventory_cache
    except FileNotFoundError:
        logger.warning("avd_inventory.json not found, using empty defaults")
        return dict(_EMPTY_INVENTORY)
    except json.JSONDecodeError as e:
        logger.error("Error parsing avd_inventory.json: %s", e)
        return dict(_EMPTY_INVENTORY)

# ============================================================================
# VERSION COMPARISON & CONSTRAINT EVALUATION
# ============================================================================

_VERSION_RE = re.compile(r'\d+(?:\.\d+)*')
_CLAUSE_RE = re.compile(r'^(~>|>=|<=|!=|>|<|=)?\s*(\d+(?:\.\d+)*)$')


def _extract_version(text):
    """Zieht die erste Versionsnummer (z.B. '4.81.0') aus einem Freitext."""
    if not text:
        return None
    m = _VERSION_RE.search(str(text))
    return m.group(0) if m else None


def _compare_versions(a, b):
    """Numerischer Segmentvergleich: -1/0/1 wie cmp(a, b)."""
    ta = [int(p) for p in a.split('.')]
    tb = [int(p) for p in b.split('.')]
    length = max(len(ta), len(tb))
    ta += [0] * (length - len(ta))
    tb += [0] * (length - len(tb))
    return (ta > tb) - (ta < tb)


def _satisfies_constraint(version, constraint):
    """Prüft eine Constraint-Liste wie '>= 1.14.0, != 1.15.0, < 2.0.0'.

    Unterstützt >=, >, <=, <, !=, = und den pessimistischen Operator ~>
    (Terraform/Ruby-Semantik). Gibt True/False zurück, oder None wenn die
    Constraint nicht auswertbar ist.
    """
    for clause in constraint.split(','):
        clause = clause.strip()
        if not clause:
            continue
        m = _CLAUSE_RE.match(clause)
        if not m:
            return None
        op = m.group(1) or '='
        ref = m.group(2)
        if op == '~>':
            # ~> X.Y.Z bedeutet >= X.Y.Z und < X.(Y+1); ~> X.Y bedeutet < (X+1)
            if _compare_versions(version, ref) < 0:
                return False
            upper = [int(p) for p in ref.split('.')][:-1]
            if not upper:
                return None
            upper[-1] += 1
            if _compare_versions(version, '.'.join(str(p) for p in upper)) >= 0:
                return False
        else:
            cmp = _compare_versions(version, ref)
            ok = {'=': cmp == 0, '!=': cmp != 0, '>': cmp > 0,
                  '>=': cmp >= 0, '<': cmp < 0, '<=': cmp <= 0}[op]
            if not ok:
                return False
    return True

# ============================================================================
# CONNECTION POOLING (autoresearch-inspired: reuse connections, reduce overhead)
# ============================================================================

_thread_local = threading.local()

def _get_http_session():
    """Thread-lokale Session mit Connection Pooling und Retry (autoresearch-Pattern).

    Inspiriert von autoresearch: Wiederverwendung von Connections statt
    Neuaufbau pro Request. Exponential Backoff bei transienten Fehlern.
    """
    if not hasattr(_thread_local, 'session'):
        session = requests.Session()
        session.headers.update({'User-Agent': 'Version-Checker/2.0'})

        # Exponential Backoff Retry (autoresearch-Pattern: retry with 2^attempt backoff)
        # Nur 1 Retry mit kurzem Backoff: worst case bleibt ein einzelner
        # Check unter ~9s statt >30s (3 Retries mit exponentiellem Backoff)
        # Retry-After wird ignoriert: urllib3 würde sonst bis zu 6h schlafen
        # (retry_after_max) und den Worker-Thread blockieren. 429 wird nicht
        # wiederholt - ein sofortiger Retry ohne Wartezeit bringt nichts.
        retry_strategy = Retry(
            total=1,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
            respect_retry_after_header=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=20,
            pool_maxsize=20,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        _thread_local.session = session
    return _thread_local.session

# ============================================================================
# EINZELNE MODULE/PROVIDER ABRUFEN (für parallele Ausführung)
# ============================================================================

def _module_result(name, version, url):
    """Basis-Ergebnis für Puppet-Module und GitHub-Releases."""
    return {
        'name': name,
        'serverVersion': version,
        'forgeVersion': 'N/A',
        'status': 'unknown',
        'deprecated': False,
        'url': url,
    }


# Neueste Release (höchste Version = current_release des Moduls) statt
# /v3/modules/<slug>: der Modul-Endpoint liefert README, Changelog, Reference
# und die komplette Release-Liste mit (~330 KB pro Modul), hier ~2 KB.
_FORGE_RELEASES_URL = 'https://forgeapi.puppet.com/v3/releases'
_FORGE_EXCLUDE_FIELDS = 'readme changelog license reference metadata tasks plans'


def _forge_result(module_name, installed_version):
    return _module_result(
        module_name, installed_version,
        f'https://forge.puppet.com/modules/{module_name.replace("-", "/", 1)}')


def _github_result(repo_name, tracked_version):
    return _module_result(repo_name, tracked_version,
                          f'https://github.com/{repo_name}')


def _fetch_single_module(module_name, installed_version):
    """Holt Daten für ein einzelnes Puppet-Modul vom Forge."""
    module_data = _forge_result(module_name, installed_version)

    session = _get_http_session()
    try:
        params = {'module': module_name, 'limit': 1, 'sort_by': 'version',
                  'exclude_fields': _FORGE_EXCLUDE_FIELDS}
        response = session.get(_FORGE_RELEASES_URL, params=params,
                               timeout=_REQUEST_TIMEOUT)

        if response.status_code == 200:
            results = response.json().get('results') or []
            if not results:
                # Unbekanntes Modul: Forge antwortet mit 200 und leerer Liste
                module_data['status'] = 'error'
                module_data['error'] = 'Modul nicht gefunden'
                return module_data

            release = results[0]
            forge_version = release.get('version')
            if forge_version:
                module_data['forgeVersion'] = forge_version
                module_data['status'] = 'current' if installed_version == forge_version else 'outdated'

            module_data['deprecated'] = (release.get('module') or {}).get('deprecated_at') is not None
        else:
            logger.warning("Forge API status %d for %s", response.status_code, module_name)
            module_data['status'] = 'error'
            module_data['error'] = f"HTTP {response.status_code}"

    except requests.Timeout:
        module_data['status'] = 'error'
        module_data['error'] = 'Timeout'
    except requests.RequestException:
        module_data['status'] = 'error'
        module_data['error'] = 'Verbindungsfehler'
    except Exception:
        logger.exception("Unexpected error for module %s", module_name)
        module_data['status'] = 'error'
        module_data['error'] = 'Unerwarteter Fehler'

    return module_data


def _fetch_single_github_release(repo_name, tracked_version):
    """Holt die neueste Release-Version eines GitHub-Repos."""
    release_data = _github_result(repo_name, tracked_version)

    session = _get_http_session()
    headers = {'Accept': 'application/vnd.github+json'}
    gh_token = os.environ.get('GITHUB_TOKEN')
    if gh_token:
        headers['Authorization'] = f'token {gh_token}'

    try:
        url = f'https://api.github.com/repos/{repo_name}/releases/latest'
        response = session.get(url, timeout=_REQUEST_TIMEOUT, headers=headers)

        if response.status_code == 200:
            data = response.json()
            tag = data.get('tag_name', '')
            if tag:
                latest = tag.lstrip('v')
                release_data['forgeVersion'] = latest
                tracked_clean = tracked_version.lstrip('v')
                release_data['status'] = 'current' if tracked_clean == latest else 'outdated'
        else:
            logger.warning("GitHub API status %d for %s", response.status_code, repo_name)
            release_data['status'] = 'error'
            release_data['error'] = f"HTTP {response.status_code}"

    except requests.Timeout:
        release_data['status'] = 'error'
        release_data['error'] = 'Timeout'
    except requests.RequestException:
        release_data['status'] = 'error'
        release_data['error'] = 'Verbindungsfehler'
    except Exception:
        logger.exception("Unexpected error for GitHub repo %s", repo_name)
        release_data['status'] = 'error'
        release_data['error'] = 'Unerwarteter Fehler'

    return release_data


# Kurzer Timeout pro Upstream-Call: bei ~35 parallelen Checks muss auch der
# langsamste Call sicher unter dem Vercel-Funktionslimit (10s) bleiben.
_REQUEST_TIMEOUT = 4

# Quelltypen, die ohne Auth automatisch pollbar sind
_AUTO_SOURCE_TYPES = {'github-release', 'github-commit', 'tf-registry',
                      'hashicorp-checkpoint', 'choco', 'psgallery',
                      'chrome-versionhistory'}
_ODATA_VERSION_RE = re.compile(r'<d:Version[^>]*>([^<]+)</d:Version>')


def _fetch_latest_for_source(quelle):
    """Holt die neueste Version für einen Quelltyp aus dem AVD-Inventar.

    Gibt (latest, None) bei Erfolg zurück, sonst (None, fehlermeldung).
    """
    typ = quelle.get('typ', '')
    ref = quelle.get('ref', '') or ''
    session = _get_http_session()

    if typ in ('github-release', 'github-commit'):
        headers = {'Accept': 'application/vnd.github+json'}
        gh_token = os.environ.get('GITHUB_TOKEN')
        if gh_token:
            headers['Authorization'] = f'token {gh_token}'

        if typ == 'github-release':
            url = f'https://api.github.com/repos/{ref}/releases/latest'
            response = session.get(url, timeout=_REQUEST_TIMEOUT, headers=headers)
            if response.status_code == 200:
                tag = response.json().get('tag_name', '')
                if tag:
                    return tag.lstrip('v'), None
                return None, 'Kein tag_name in der Antwort'
        else:
            url = f'https://api.github.com/repos/{ref}/commits'
            params = {'path': quelle.get('path', ''), 'per_page': 1}
            response = session.get(url, params=params,
                                   timeout=_REQUEST_TIMEOUT, headers=headers)
            if response.status_code == 200:
                commits = response.json()
                if commits and commits[0].get('sha'):
                    return commits[0]['sha'][:8], None
                return None, 'Keine Commits in der Antwort'

    elif typ == 'tf-registry':
        url = f'https://registry.terraform.io/v1/providers/{ref}'
        response = session.get(url, timeout=_REQUEST_TIMEOUT, headers={'Accept': 'application/json'})
        if response.status_code == 200:
            version = response.json().get('version', '')
            if version:
                return version.lstrip('v'), None
            return None, 'Keine version in der Antwort'

    elif typ == 'hashicorp-checkpoint':
        url = f'https://checkpoint-api.hashicorp.com/v1/check/{ref}'
        response = session.get(url, timeout=_REQUEST_TIMEOUT, headers={'Accept': 'application/json'})
        if response.status_code == 200:
            version = response.json().get('current_version', '')
            if version:
                return version.lstrip('v'), None
            return None, 'Keine current_version in der Antwort'

    elif typ == 'choco':
        url = ("https://community.chocolatey.org/api/v2/Packages()"
               f"?$filter=Id%20eq%20%27{quote(ref, safe='')}%27%20and%20IsLatestVersion")
        response = session.get(url, timeout=_REQUEST_TIMEOUT)
        if response.status_code == 200:
            m = _ODATA_VERSION_RE.search(response.text)
            if m:
                return m.group(1).strip(), None
            return None, 'Keine Version im OData-Feed'

    elif typ == 'psgallery':
        url = ("https://www.powershellgallery.com/api/v2/FindPackagesById()"
               f"?id=%27{quote(ref, safe='')}%27&$filter=IsLatestVersion")
        response = session.get(url, timeout=_REQUEST_TIMEOUT)
        if response.status_code == 200:
            m = _ODATA_VERSION_RE.search(response.text)
            if m:
                return m.group(1).strip(), None
            return None, 'Keine Version im OData-Feed'

    elif typ == 'chrome-versionhistory':
        url = ('https://versionhistory.googleapis.com/v1/chrome/platforms/'
               'win64/channels/stable/versions?pageSize=1')
        response = session.get(url, timeout=_REQUEST_TIMEOUT)
        if response.status_code == 200:
            versions = response.json().get('versions', [])
            if versions and versions[0].get('version'):
                return versions[0]['version'], None
            return None, 'Keine versions in der Antwort'

    else:
        return None, f'Unbekannter Quelltyp: {typ}'

    logger.warning("API status %d for %s (%s)", response.status_code, ref, typ)
    return None, f'HTTP {response.status_code}'


def _inventory_result(item):
    """Basis-Ergebnis eines Inventar-Eintrags (noch ohne Latest-Check)."""
    quelle = item.get('quelle', {}) or {}
    return {
        'id': item.get('id', ''),
        'kategorie': item.get('kategorie', ''),
        'artefakt': item.get('artefakt', ''),
        'repo': item.get('repo', []),
        'ist': item.get('ist'),
        'constraint': item.get('constraint'),
        'art': item.get('art', 'intern'),
        'artLabel': item.get('artLabel', ''),
        'fundorte': item.get('fundorte', []),
        'quelle': {'typ': quelle.get('typ', 'intern'), 'ref': quelle.get('ref')},
        'link': item.get('link', ''),
        'note': item.get('note', ''),
        'suppression': item.get('suppression'),
        'latest': item.get('known_latest', '-'),
        'status': 'intern',
    }


def _check_inventory_item(item):
    """Prüft einen Eintrag des AVD-Inventars gegen seine Latest-Quelle.

    Status-Werte: current, outdated, suppressed, floating, manual, azure,
    intern, error. `art` steuert die Vergleichslogik, `quelle.typ` den Poller.
    """
    quelle = item.get('quelle', {}) or {}
    art = item.get('art', 'intern')
    result = _inventory_result(item)

    typ = quelle.get('typ', 'intern')

    if typ == 'intern' or art == 'intern':
        result['status'] = 'intern'
        return result
    if typ == 'azure-cli':
        result['status'] = 'azure'
        return result
    if typ not in _AUTO_SOURCE_TYPES:
        result['status'] = 'manual'
        return result

    try:
        latest, error = _fetch_latest_for_source(quelle)
        if error:
            result['status'] = 'error'
            result['error'] = error
            return result

        result['latest'] = latest

        if art in ('pin', 'lock'):
            if typ == 'github-commit':
                ist = (item.get('ist') or '').strip()
                same = bool(ist) and (latest.startswith(ist) or ist.startswith(latest))
                result['status'] = 'current' if same else 'outdated'
            else:
                ist_v = _extract_version(item.get('ist'))
                latest_v = _extract_version(latest)
                if ist_v and latest_v:
                    result['status'] = ('current'
                                        if _compare_versions(ist_v, latest_v) >= 0
                                        else 'outdated')
                else:
                    result['status'] = 'floating'
        elif art == 'constraint' and item.get('constraint'):
            latest_v = _extract_version(latest)
            satisfied = (_satisfies_constraint(latest_v, item['constraint'])
                         if latest_v else None)
            if satisfied is None:
                result['status'] = 'floating'
            else:
                result['status'] = 'current' if satisfied else 'outdated'
        else:
            result['status'] = 'floating'

        if result['status'] == 'outdated' and item.get('suppression'):
            result['status'] = 'suppressed'

    except requests.Timeout:
        result['status'] = 'error'
        result['error'] = 'Timeout'
    except requests.RequestException:
        result['status'] = 'error'
        result['error'] = 'Verbindungsfehler'
    except Exception:
        logger.exception("Unexpected error for inventory item %s", item.get('id'))
        result['status'] = 'error'
        result['error'] = 'Unerwarteter Fehler'

    return result

# ============================================================================
# DATA FETCHING LOGIC (cached, parallel, optimized worker count)
# ============================================================================

# Mindestens so viele Worker wie HTTP-Checks (aktuell 32: Forge, GitHub,
# Auto-Quellen des Inventars), damit alle Upstream-Calls in einer Welle
# laufen statt in zwei nacheinander. Threads entstehen erst bei Bedarf.
_MAX_WORKERS = 40

# Gesamtbudget für den Fan-out. Ein einzelner Call kann trotz
# _REQUEST_TIMEOUT länger dauern (Retry; der Read-Timeout gilt pro recv,
# nicht gesamt). Was nach Ablauf nicht fertig ist, geht als Timeout-Fehler
# in die Antwort, statt die Function ins Vercel-Limit laufen zu lassen.
_FETCH_DEADLINE = 8

# Geteilter Executor: Threads (und damit deren thread-lokale Sessions samt
# Connection Pools) überleben einzelne Requests. Ein per-Request erzeugter
# ThreadPoolExecutor würde bei jedem Aufruf neue Threads starten und das
# Connection Pooling wirkungslos machen.
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)

def fetch_modules_data():
    """Holt alle Puppet Module + GitHub Release Daten (über den fetch_all_data-Cache)."""
    return fetch_all_data()['modules']


def fetch_avd_data():
    """Holt das geprüfte AVD-Inventar (über den fetch_all_data-Cache)."""
    return fetch_all_data()['avd']

# ============================================================================
# IN-MEMORY CACHE (Single-Flight)
# ============================================================================
# Bewusst kein Flask-Caching FileSystemCache: der pickelt Werte in ein
# vorhersagbares Verzeichnis unter /tmp. Wer es vorab anlegt, kann dort
# manipulierte Pickles ablegen (Code-Ausführung beim Laden). Eine warme
# Vercel-Instanz behält Modul-Globals ohnehin über Invocations hinweg.

class _SingleFlightCache:
    """TTL-Cache für einen einzelnen Wert.

    Bei einem Miss rechnet genau ein Thread neu; parallele Requests warten
    auf dessen Ergebnis, statt den kompletten Upstream-Fan-out mehrfach
    anzustoßen (Cache-Stampede).
    """

    def __init__(self, ttl):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._entry = None  # (expires_at, value)

    def _fresh(self):
        entry = self._entry
        if entry and entry[0] > time.monotonic():
            return entry
        return None

    def get_or_compute(self, compute):
        entry = self._fresh()
        if entry:
            return entry[1]
        with self._lock:
            entry = self._fresh()
            if entry:
                return entry[1]
            value = compute()
            self._entry = (time.monotonic() + self._ttl, value)
            return value

    def clear(self):
        self._entry = None


cache = _SingleFlightCache(ttl=300)

# ============================================================================
# COMBINED DATA FETCH (autoresearch-Pattern: prefetch/overlap I/O)
# ============================================================================
# Einziger gecachter Fetch: /api/modules, /api/avd-components und
# /api/system_status teilen sich denselben Cache-Eintrag, statt dieselben
# Upstream-APIs mehrfach abzufragen.

def fetch_all_data():
    """Holt Module UND das AVD-Inventar (5 Minuten gecacht)."""
    return cache.get_or_compute(_fetch_all_data_uncached)


def _fetch_all_data_uncached():
    """Holt Module UND das AVD-Inventar parallel in einem einzigen Aufruf.

    autoresearch-Pattern: Überlappung von I/O-Operationen.
    Statt sequentiell modules, dann Inventar zu laden, wird alles
    gleichzeitig gestartet.
    """
    versions = load_versions()
    inventory = load_avd_inventory()
    installed_modules = versions.get('puppet_modules', {})
    github_releases = versions.get('github_releases', {})
    inventory_items = inventory.get('items', [])

    modules = []
    avd_results = {}

    # future -> (Art, Index im Inventar, Builder für das Timeout-Ergebnis)
    all_futures = {
        _executor.submit(_fetch_single_module, name, version):
            ('module', None, partial(_forge_result, name, version))
        for name, version in installed_modules.items()
    }
    all_futures.update({
        _executor.submit(_fetch_single_github_release, name, version):
            ('module', None, partial(_github_result, name, version))
        for name, version in github_releases.items()
    })
    all_futures.update({
        _executor.submit(_check_inventory_item, item):
            ('avd', idx, partial(_inventory_result, item))
        for idx, item in enumerate(inventory_items)
    })

    def collect(future, result):
        kind, idx, _ = all_futures.pop(future)
        if kind == 'module':
            modules.append(result)
        else:
            avd_results[idx] = result

    try:
        for future in as_completed(all_futures, timeout=_FETCH_DEADLINE):
            collect(future, future.result())
    except FuturesTimeoutError:
        for future in list(all_futures):
            if future.done():
                collect(future, future.result())
                continue
            future.cancel()
            result = all_futures[future][2]()
            result['status'] = 'error'
            result['error'] = 'Timeout'
            collect(future, result)

    avd = {
        'items': [avd_results[i] for i in sorted(avd_results)],
        'kategorien': inventory.get('kategorien', []),
        'kontrakte': inventory.get('kontrakte', []),
        'termine': inventory.get('termine', []),
        'hinweise': inventory.get('hinweise', []),
        'meta': inventory.get('_meta', {}),
    }
    return {
        'modules': modules,
        'avd': avd,
        # Zeitpunkt des Upstream-Abrufs: wird im Dashboard als "Aktualisiert"
        # angezeigt und hält den ETag von /api/system_status über die
        # Cache-Laufzeit stabil (statt bei jedem Request neu zu wechseln).
        'fetched_at': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }

# ============================================================================
# STATIC FILES ROUTES
# ============================================================================

@app.route('/styles/<path:filename>')
@limiter.exempt
def serve_styles(filename):
    """Serve CSS files."""
    return send_from_directory('public/styles', filename)

@app.route('/scripts/<path:filename>')
@limiter.exempt
def serve_scripts(filename):
    """Serve JavaScript files."""
    return send_from_directory('public/scripts', filename)

@app.route('/favicon.ico')
@limiter.exempt
def serve_favicon():
    """Serve favicon (SVG inline)."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="6" fill="#0066cc"/>'
        '<text x="16" y="23" font-size="20" text-anchor="middle" fill="white" '
        'font-family="sans-serif" font-weight="bold">V</text>'
        '</svg>'
    )
    return app.response_class(svg, mimetype='image/svg+xml',
                              headers={'Cache-Control': 'public, max-age=604800'})

# ============================================================================
# API ROUTES - PUPPET MODULES
# ============================================================================

@app.route('/api/modules', methods=['GET'])
@limiter.limit("30 per minute")
def get_modules():
    """Ruft Puppet Module Informationen vom Puppet Forge ab."""
    try:
        result = fetch_modules_data()
        return jsonify(result)
    except Exception:
        logger.exception("Critical error in get_modules")
        return jsonify({'error': 'Serverfehler beim Laden der Module'}), 500

# ============================================================================
# API ROUTES - AVD COMPONENTS
# ============================================================================

@app.route('/api/avd-components', methods=['GET'])
@limiter.limit("30 per minute")
def get_avd_components():
    """Ruft AVD-Komponenten Versionsinformationen ab."""
    try:
        result = fetch_avd_data()
        return jsonify(result)
    except Exception:
        logger.exception("Critical error in get_avd_components")
        return jsonify({'error': 'Serverfehler beim Laden der AVD-Komponenten'}), 500

# ============================================================================
# API ROUTES - SYSTEM STATUS (optimized: parallel fetch)
# ============================================================================

@app.route('/api/system_status', methods=['GET'])
@limiter.limit("30 per minute")
def get_system_status():
    """Gibt eine Zusammenfassung des gesamten System-Status zurück.

    autoresearch-Pattern: Nutzt fetch_all_data() für paralleles Laden
    statt sequentieller Einzelabfragen.
    """

    # Puppet Module Status
    puppet_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    avd_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    timestamp = None

    try:
        all_data = fetch_all_data()
        timestamp = all_data.get('fetched_at')
        modules = all_data['modules']
        avd_items = all_data['avd']['items']

        # Puppet-Analyse
        outdated_count = 0
        deprecated_count = 0
        for module in modules:
            if module.get('deprecated'):
                deprecated_count += 1
            elif module.get('status') == 'outdated':
                outdated_count += 1

        if deprecated_count > 0:
            puppet_status = {"status": "Warnung", "details": f"{deprecated_count} Module deprecated"}
        elif outdated_count > 0:
            puppet_status = {"status": "Info", "details": f"{outdated_count} Updates verfügbar"}
        else:
            puppet_status = {"status": "OK", "details": "Alle Module aktuell"}

        # AVD-Analyse (Inventar-Statuswerte)
        avd_errors = 0
        avd_outdated = 0
        avd_manual = 0
        avd_auto = 0
        for comp in avd_items:
            status = comp.get('status')
            if status == 'error':
                avd_errors += 1
            elif status == 'outdated':
                avd_outdated += 1
            elif status in ('manual', 'azure'):
                avd_manual += 1
            elif status in ('current', 'floating', 'suppressed'):
                avd_auto += 1

        if avd_errors > 0:
            avd_status = {"status": "Warnung", "details": f"{avd_errors} Checks fehlgeschlagen"}
        elif avd_outdated > 0:
            avd_status = {"status": "Warnung", "details": f"{avd_outdated} Artefakte veraltet"}
        elif avd_manual > 0:
            avd_status = {"status": "Info", "details": f"{avd_auto} auto-geprüft, {avd_manual} manuell/Azure"}
        else:
            avd_status = {"status": "OK", "details": "Alle Artefakte geprüft"}

    except Exception:
        logger.exception("Error fetching system status")
        puppet_status = {"status": "Error", "details": "Fehler beim Laden"}
        avd_status = {"status": "Error", "details": "Fehler beim Laden"}

    return jsonify({
        "puppet": puppet_status,
        "avd": avd_status,
        "timestamp": timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    })

# ============================================================================
# API ROUTES - VERSION MANAGEMENT
# ============================================================================

@app.route('/api/versions', methods=['GET'])
@limiter.limit("30 per minute")
def get_versions():
    """Gibt die aktuellen installierten Versionen aus versions.json zurück."""
    versions = load_versions()
    return jsonify(versions)

# ============================================================================
# MAIN ROUTES - HTML PAGES
# ============================================================================

# Bekannte statische Seiten
_KNOWN_PAGES = {'', 'index.html', 'puppet.html', 'avd.html'}

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
@limiter.exempt
def serve(path):
    """Serve static HTML files. Returns 404 for unknown paths."""
    if path in _KNOWN_PAGES:
        filename = 'index.html' if path == '' else path
        return send_from_directory('public', filename)

    # Statische Dateien (CSS, JS, Bilder) direkt ausliefern. Kein
    # os.path.exists vorab: das lief relativ zum CWD statt zu public/ und
    # verriet über die abweichende 404-Antwort, ob eine Datei außerhalb von
    # public/ existiert (z.B. /..%2fserver.py). send_from_directory prüft
    # Traversal selbst.
    if path:
        try:
            return send_from_directory('public', path)
        except NotFound:
            pass

    return send_from_directory('public', 'index.html'), 404

# ============================================================================
# VERCEL EXPORT & LOCAL DEVELOPMENT
# ============================================================================
# Die Flask App wird automatisch von Vercel als WSGI-App erkannt.

if __name__ == '__main__':
    # Nur lokal. Der Werkzeug-Debugger bietet eine interaktive Python-Konsole
    # (Code-Ausführung) - daher standardmäßig aus und nur auf localhost.
    # Aktivieren mit FLASK_DEBUG=1, im LAN erreichbar mit HOST=0.0.0.0.
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1',
            host=os.environ.get('HOST', '127.0.0.1'),
            port=int(os.environ.get('PORT', '5000')))
