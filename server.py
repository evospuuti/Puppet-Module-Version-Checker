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
        return {"puppet_modules": {}, "terraform_providers": {}}
    except json.JSONDecodeError as e:
        logger.error("Error parsing versions.json: %s", e)
        return {"puppet_modules": {}, "terraform_providers": {}}

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


def _fetch_single_provider(provider_name, installed_version):
    """Holt Daten für einen einzelnen Terraform-Provider von der Registry."""
    parts = provider_name.split('/')
    if len(parts) != 2:
        return {
            'name': provider_name,
            'displayName': provider_name,
            'namespace': '',
            'installedVersion': installed_version,
            'latestVersion': 'N/A',
            'status': 'error',
            'error': f'Ungültiger Provider-Name: {provider_name}',
            'url': ''
        }
    namespace, name = parts

    provider_data = {
        'name': provider_name,
        'displayName': name,
        'namespace': namespace,
        'installedVersion': installed_version,
        'latestVersion': 'N/A',
        'status': 'unknown',
        'url': f'https://registry.terraform.io/providers/{provider_name}'
    }

    session = _get_http_session()
    try:
        url = f'https://registry.terraform.io/v1/providers/{namespace}/{name}'
        response = session.get(url, timeout=10, headers={'Accept': 'application/json'})

        if response.status_code == 200:
            data = response.json()

            if 'version' in data:
                latest_version = data['version']
                provider_data['latestVersion'] = latest_version

                installed_clean = installed_version.lstrip('v')
                latest_clean = latest_version.lstrip('v')

                provider_data['status'] = 'current' if installed_clean == latest_clean else 'outdated'

            if 'description' in data:
                provider_data['description'] = data['description']
            if 'source' in data:
                provider_data['source'] = data['source']
            if 'published_at' in data:
                provider_data['publishedAt'] = data['published_at']

        else:
            logger.warning("Registry API status %d for %s", response.status_code, provider_name)
            provider_data['status'] = 'error'
            provider_data['error'] = f"HTTP {response.status_code}"

    except requests.Timeout:
        provider_data['status'] = 'error'
        provider_data['error'] = 'Timeout'
    except requests.RequestException:
        provider_data['status'] = 'error'
        provider_data['error'] = 'Verbindungsfehler'
    except Exception:
        logger.exception("Unexpected error for provider %s", provider_name)
        provider_data['status'] = 'error'
        provider_data['error'] = 'Unerwarteter Fehler'

    return provider_data

# ============================================================================
# DATA FETCHING LOGIC (cached, parallel, optimized worker count)
# ============================================================================

# autoresearch-Pattern: Mehr Worker für bessere Parallelisierung
# (analog zu multiprocessing.Pool für parallele Shard-Downloads)
_MAX_WORKERS = 20

@cache.cached(timeout=300, key_prefix='puppet_modules_data')
def fetch_modules_data():
    """Holt alle Puppet Module Daten parallel vom Forge (mit Cache)."""
    versions = load_versions()
    installed_modules = versions.get('puppet_modules', {})

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_single_module, name, version): name
            for name, version in installed_modules.items()
        }
        results = []
        for future in as_completed(futures):
            results.append(future.result())
        return results


@cache.cached(timeout=300, key_prefix='terraform_providers_data')
def fetch_terraform_data():
    """Holt alle Terraform Provider Daten parallel von der Registry (mit Cache)."""
    versions = load_versions()
    installed_providers = versions.get('terraform_providers', {})

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_single_provider, name, version): name
            for name, version in installed_providers.items()
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
    """Holt Module UND Provider parallel in einem einzigen Aufruf.

    autoresearch-Pattern: Überlappung von I/O-Operationen.
    Statt sequentiell modules, dann providers zu laden, werden beide
    gleichzeitig gestartet.
    """
    versions = load_versions()
    installed_modules = versions.get('puppet_modules', {})
    installed_providers = versions.get('terraform_providers', {})

    modules = []
    providers = []

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        module_futures = {
            executor.submit(_fetch_single_module, name, version): ('module', name)
            for name, version in installed_modules.items()
        }
        provider_futures = {
            executor.submit(_fetch_single_provider, name, version): ('provider', name)
            for name, version in installed_providers.items()
        }

        all_futures = {**module_futures, **provider_futures}
        for future in as_completed(all_futures):
            kind, _name = all_futures[future]
            result = future.result()
            if kind == 'module':
                modules.append(result)
            else:
                providers.append(result)

    return {'modules': modules, 'providers': providers}

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
# API ROUTES - TERRAFORM PROVIDERS
# ============================================================================

@app.route('/api/terraform-providers', methods=['GET'])
@limiter.limit("30 per minute")
def get_terraform_providers():
    """Ruft Terraform Provider Informationen von der Terraform Registry ab."""
    try:
        result = fetch_terraform_data()
        return jsonify(result)
    except Exception:
        logger.exception("Critical error in get_terraform_providers")
        return jsonify({'error': 'Serverfehler beim Laden der Provider'}), 500

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
    terraform_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}

    try:
        all_data = fetch_all_data()
        modules = all_data['modules']
        providers = all_data['providers']

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

        # Terraform-Analyse
        tf_outdated = 0
        tf_errors = 0
        for provider in providers:
            if provider.get('status') == 'outdated':
                tf_outdated += 1
            elif provider.get('status') == 'error':
                tf_errors += 1

        if tf_errors > 0:
            terraform_status = {"status": "Warnung", "details": f"{tf_errors} Provider mit Fehlern"}
        elif tf_outdated > 0:
            terraform_status = {"status": "Info", "details": f"{tf_outdated} Updates verfügbar"}
        else:
            terraform_status = {"status": "OK", "details": "Alle Provider aktuell"}

    except Exception:
        logger.exception("Error fetching system status")
        puppet_status = {"status": "Error", "details": "Fehler beim Laden"}
        terraform_status = {"status": "Error", "details": "Fehler beim Laden"}

    return jsonify({
        "puppet": puppet_status,
        "terraform": terraform_status,
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
_KNOWN_PAGES = {'', 'index.html', 'puppet.html', 'terraform.html'}

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
