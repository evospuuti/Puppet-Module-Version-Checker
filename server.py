import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
import requests

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

# Cache-Konfiguration für Vercel - nur SimpleCache verwenden
cache = Cache(app, config={
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
})

# HTTP Session für Connection-Pooling (wiederverwendet TCP-Verbindungen)
http_session = requests.Session()
http_session.headers.update({'User-Agent': 'Version-Checker/2.0'})

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
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )

    # Cache-Header für statische Dateien
    if request.path.startswith('/styles/') or request.path.startswith('/scripts/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'

    return response

# ============================================================================
# VERSION LOADING FROM JSON
# ============================================================================

def load_versions():
    """Lädt die installierten Versionen aus versions.json."""
    versions_file = os.path.join(os.path.dirname(__file__), 'versions.json')
    try:
        with open(versions_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("versions.json not found, using empty defaults")
        return {"puppet_modules": {}, "terraform_providers": {}}
    except json.JSONDecodeError as e:
        logger.error("Error parsing versions.json: %s", e)
        return {"puppet_modules": {}, "terraform_providers": {}}

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

    try:
        url = f'https://forgeapi.puppet.com/v3/modules/{module_name}'
        response = http_session.get(url, timeout=10)

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
    namespace, name = provider_name.split('/')

    provider_data = {
        'name': provider_name,
        'displayName': name,
        'namespace': namespace,
        'installedVersion': installed_version,
        'latestVersion': 'N/A',
        'status': 'unknown',
        'url': f'https://registry.terraform.io/providers/{provider_name}'
    }

    try:
        url = f'https://registry.terraform.io/v1/providers/{namespace}/{name}'
        response = http_session.get(url, timeout=10, headers={'Accept': 'application/json'})

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
# DATA FETCHING LOGIC (cached, parallel)
# ============================================================================

@cache.cached(timeout=300, key_prefix='puppet_modules_data')
def fetch_modules_data():
    """Holt alle Puppet Module Daten parallel vom Forge (mit Cache)."""
    versions = load_versions()
    installed_modules = versions.get('puppet_modules', {})

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(_fetch_single_module, name, version)
            for name, version in installed_modules.items()
        ]
        return [f.result() for f in futures]


@cache.cached(timeout=300, key_prefix='terraform_providers_data')
def fetch_terraform_data():
    """Holt alle Terraform Provider Daten parallel von der Registry (mit Cache)."""
    versions = load_versions()
    installed_providers = versions.get('terraform_providers', {})

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(_fetch_single_provider, name, version)
            for name, version in installed_providers.items()
        ]
        return [f.result() for f in futures]

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

# ============================================================================
# API ROUTES - PUPPET MODULES
# ============================================================================

@app.route('/api/modules', methods=['GET'])
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
def get_terraform_providers():
    """Ruft Terraform Provider Informationen von der Terraform Registry ab."""
    try:
        result = fetch_terraform_data()
        return jsonify(result)
    except Exception:
        logger.exception("Critical error in get_terraform_providers")
        return jsonify({'error': 'Serverfehler beim Laden der Provider'}), 500

# ============================================================================
# API ROUTES - SYSTEM STATUS
# ============================================================================

@app.route('/api/system_status', methods=['GET'])
def get_system_status():
    """Gibt eine Zusammenfassung des gesamten System-Status zurück."""

    # Puppet Module Status
    puppet_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        modules = fetch_modules_data()

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
    except Exception:
        logger.exception("Error fetching puppet status")
        puppet_status = {"status": "Error", "details": "Fehler beim Laden"}

    # Terraform Provider Status
    terraform_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        providers = fetch_terraform_data()

        outdated_count = 0
        error_count = 0

        for provider in providers:
            if provider.get('status') == 'outdated':
                outdated_count += 1
            elif provider.get('status') == 'error':
                error_count += 1

        if error_count > 0:
            terraform_status = {"status": "Warnung", "details": f"{error_count} Provider mit Fehlern"}
        elif outdated_count > 0:
            terraform_status = {"status": "Info", "details": f"{outdated_count} Updates verfügbar"}
        else:
            terraform_status = {"status": "OK", "details": "Alle Provider aktuell"}
    except Exception:
        logger.exception("Error fetching terraform status")
        terraform_status = {"status": "Error", "details": "Fehler beim Laden"}

    return jsonify({
        "puppet": puppet_status,
        "terraform": terraform_status,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# ============================================================================
# API ROUTES - VERSION MANAGEMENT
# ============================================================================

@app.route('/api/versions', methods=['GET'])
def get_versions():
    """Gibt die aktuellen installierten Versionen aus versions.json zurück."""
    versions = load_versions()
    return jsonify(versions)

# ============================================================================
# MAIN ROUTES - HTML PAGES
# ============================================================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """Serve static HTML files and fallback to index.html for SPA routing."""
    if path != "" and os.path.exists(f"public/{path}"):
        return send_from_directory('public', path)
    else:
        return send_from_directory('public', 'index.html')

# ============================================================================
# VERCEL EXPORT & LOCAL DEVELOPMENT
# ============================================================================
# Die Flask App wird automatisch von Vercel als WSGI-App erkannt.

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
