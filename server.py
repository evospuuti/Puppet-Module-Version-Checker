import os
import json
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================================
# APP SETUP
# ============================================================================

app = Flask(__name__)

# CORS nur für eigene Origin erlauben (Vercel-Domain + lokale Entwicklung)
CORS(app, origins=[
    'https://puppet-module-version-checker.vercel.app',
    'http://localhost:5000',
    'http://127.0.0.1:5000'
])

# Cache-Konfiguration - FileSystemCache für bessere Persistenz auf Vercel
cache = Cache(app, config={
    "CACHE_TYPE": "FileSystemCache",
    "CACHE_DIR": os.path.join(os.environ.get('TMPDIR', '/tmp'), 'version-checker-cache'),
    "CACHE_DEFAULT_TIMEOUT": 300
})

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
        with open(versions_file, 'r') as f:
            _versions_cache = json.load(f)
            return _versions_cache
    except FileNotFoundError:
        logger.warning("versions.json not found, using empty defaults")
        return {"puppet_modules": {}, "avd_components": [], "github_releases": {}}
    except json.JSONDecodeError as e:
        logger.error("Error parsing versions.json: %s", e)
        return {"puppet_modules": {}, "avd_components": [], "github_releases": {}}

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
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
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

def _fetch_single_module(module_name, installed_version):
    """Holt Daten für ein einzelnes Puppet-Modul vom Forge."""
    module_data = {
        'name': module_name,
        'serverVersion': installed_version,
        'forgeVersion': 'N/A',
        'status': 'unknown',
        'deprecated': False,
        'url': f'https://forge.puppet.com/modules/{module_name.replace("-", "/")}'
    }

    session = _get_http_session()
    try:
        url = f'https://forgeapi.puppet.com/v3/modules/{module_name}'
        response = session.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if 'current_release' in data and 'version' in data['current_release']:
                forge_version = data['current_release']['version']
                module_data['forgeVersion'] = forge_version
                module_data['status'] = 'current' if installed_version == forge_version else 'outdated'

            module_data['deprecated'] = data.get('deprecated_at') is not None
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
    release_data = {
        'name': repo_name,
        'serverVersion': tracked_version,
        'forgeVersion': 'N/A',
        'status': 'unknown',
        'deprecated': False,
        'url': f'https://github.com/{repo_name}'
    }

    session = _get_http_session()
    headers = {'Accept': 'application/vnd.github+json'}
    gh_token = os.environ.get('GITHUB_TOKEN')
    if gh_token:
        headers['Authorization'] = f'token {gh_token}'

    try:
        url = f'https://api.github.com/repos/{repo_name}/releases/latest'
        response = session.get(url, timeout=10, headers=headers)

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


def _fetch_single_avd_component(component):
    """Holt die neueste Version einer AVD-Komponente basierend auf check_type."""
    result = {
        'name': component['name'],
        'category': component.get('category', ''),
        'location': component.get('location', ''),
        'tracked': component.get('tracked', ''),
        'latestVersion': 'N/A',
        'status': 'unknown',
        'link': component.get('link', ''),
        'note': component.get('note', ''),
        'checkType': component.get('check_type', 'manual'),
    }

    check_type = component.get('check_type', 'manual')

    if check_type == 'manual':
        result['latestVersion'] = component.get('known_latest', '-')
        result['status'] = 'manual'
        return result

    session = _get_http_session()

    try:
        if check_type == 'github_release':
            repo = component.get('check_source', '')
            headers = {'Accept': 'application/vnd.github+json'}
            gh_token = os.environ.get('GITHUB_TOKEN')
            if gh_token:
                headers['Authorization'] = f'token {gh_token}'

            url = f'https://api.github.com/repos/{repo}/releases/latest'
            response = session.get(url, timeout=10, headers=headers)

            if response.status_code == 200:
                data = response.json()
                tag = data.get('tag_name', '')
                if tag:
                    result['latestVersion'] = tag.lstrip('v')
                    result['status'] = 'current'
            else:
                logger.warning("GitHub API status %d for %s", response.status_code, repo)
                result['status'] = 'error'
                result['error'] = f"HTTP {response.status_code}"

        elif check_type == 'terraform_registry':
            provider = component.get('check_source', '')
            parts = provider.split('/')
            if len(parts) != 2:
                result['status'] = 'error'
                result['error'] = f'Ungültiger Provider-Name: {provider}'
                return result
            namespace, name = parts

            url = f'https://registry.terraform.io/v1/providers/{namespace}/{name}'
            response = session.get(url, timeout=10, headers={'Accept': 'application/json'})

            if response.status_code == 200:
                data = response.json()
                if 'version' in data:
                    result['latestVersion'] = data['version'].lstrip('v')
                    result['status'] = 'current'
            else:
                logger.warning("Registry API status %d for %s", response.status_code, provider)
                result['status'] = 'error'
                result['error'] = f"HTTP {response.status_code}"

    except requests.Timeout:
        result['status'] = 'error'
        result['error'] = 'Timeout'
    except requests.RequestException:
        result['status'] = 'error'
        result['error'] = 'Verbindungsfehler'
    except Exception:
        logger.exception("Unexpected error for AVD component %s", component['name'])
        result['status'] = 'error'
        result['error'] = 'Unerwarteter Fehler'

    return result

# ============================================================================
# DATA FETCHING LOGIC (cached, parallel, optimized worker count)
# ============================================================================

# autoresearch-Pattern: Mehr Worker für bessere Parallelisierung
# (analog zu multiprocessing.Pool für parallele Shard-Downloads)
_MAX_WORKERS = 20

@cache.cached(timeout=300, key_prefix='puppet_modules_data')
def fetch_modules_data():
    """Holt alle Puppet Module + GitHub Release Daten parallel (mit Cache)."""
    versions = load_versions()
    installed_modules = versions.get('puppet_modules', {})
    github_releases = versions.get('github_releases', {})

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_single_module, name, version): name
            for name, version in installed_modules.items()
        }
        futures.update({
            executor.submit(_fetch_single_github_release, name, version): name
            for name, version in github_releases.items()
        })
        results = []
        for future in as_completed(futures):
            results.append(future.result())
        return results


@cache.cached(timeout=300, key_prefix='avd_components_data')
def fetch_avd_data():
    """Holt alle AVD-Komponenten Daten parallel (mit Cache)."""
    versions = load_versions()
    avd_components = versions.get('avd_components', [])

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_single_avd_component, comp): comp['name']
            for comp in avd_components
        }
        results = []
        for future in as_completed(futures):
            results.append(future.result())
        return results

# ============================================================================
# COMBINED DATA FETCH (autoresearch-Pattern: prefetch/overlap I/O)
# ============================================================================

@cache.cached(timeout=300, key_prefix='all_data')
def fetch_all_data():
    """Holt Module UND AVD-Komponenten parallel in einem einzigen Aufruf.

    autoresearch-Pattern: Überlappung von I/O-Operationen.
    Statt sequentiell modules, dann AVD-Komponenten zu laden, werden beide
    gleichzeitig gestartet.
    """
    versions = load_versions()
    installed_modules = versions.get('puppet_modules', {})
    avd_components = versions.get('avd_components', [])
    github_releases = versions.get('github_releases', {})

    modules = []
    avd_results = []

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        module_futures = {
            executor.submit(_fetch_single_module, name, version): ('module', name)
            for name, version in installed_modules.items()
        }
        gh_futures = {
            executor.submit(_fetch_single_github_release, name, version): ('module', name)
            for name, version in github_releases.items()
        }
        avd_futures = {
            executor.submit(_fetch_single_avd_component, comp): ('avd', comp['name'])
            for comp in avd_components
        }

        all_futures = {**module_futures, **gh_futures, **avd_futures}
        for future in as_completed(all_futures):
            kind, _name = all_futures[future]
            result = future.result()
            if kind == 'module':
                modules.append(result)
            else:
                avd_results.append(result)

    return {'modules': modules, 'avd_components': avd_results}

# ============================================================================
# STATIC FILES ROUTES
# ============================================================================

@app.route('/styles/<path:filename>')
def serve_styles(filename):
    """Serve CSS files."""
    return send_from_directory('public/styles', filename)

@app.route('/scripts/<path:filename>')
def serve_scripts(filename):
    """Serve JavaScript files."""
    return send_from_directory('public/scripts', filename)

@app.route('/favicon.ico')
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

    try:
        all_data = fetch_all_data()
        modules = all_data['modules']
        avd_components = all_data['avd_components']

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

        # AVD-Analyse
        avd_errors = 0
        avd_manual = 0
        avd_ok = 0
        for comp in avd_components:
            if comp.get('status') == 'error':
                avd_errors += 1
            elif comp.get('status') == 'manual':
                avd_manual += 1
            else:
                avd_ok += 1

        if avd_errors > 0:
            avd_status = {"status": "Warnung", "details": f"{avd_errors} Komponenten mit Fehlern"}
        elif avd_manual > 0:
            avd_status = {"status": "Info", "details": f"{avd_ok} auto-geprüft, {avd_manual} manuell"}
        else:
            avd_status = {"status": "OK", "details": "Alle Komponenten geprüft"}

    except Exception:
        logger.exception("Error fetching system status")
        puppet_status = {"status": "Error", "details": "Fehler beim Laden"}
        avd_status = {"status": "Error", "details": "Fehler beim Laden"}

    return jsonify({
        "puppet": puppet_status,
        "avd": avd_status,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
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
def serve(path):
    """Serve static HTML files. Returns 404 for unknown paths."""
    if path in _KNOWN_PAGES:
        filename = 'index.html' if path == '' else path
        return send_from_directory('public', filename)

    # Statische Dateien (CSS, JS, Bilder) direkt ausliefern
    if path and os.path.exists(os.path.join('public', path)):
        return send_from_directory('public', path)

    return send_from_directory('public', 'index.html'), 404

# ============================================================================
# VERCEL EXPORT & LOCAL DEVELOPMENT
# ============================================================================
# Die Flask App wird automatisch von Vercel als WSGI-App erkannt.

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
