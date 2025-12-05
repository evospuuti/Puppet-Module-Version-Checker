import os
import json
import requests
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache

app = Flask(__name__)
CORS(app)

# Cache-Konfiguration für Vercel - nur SimpleCache verwenden
cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
}

cache = Cache(app, config=cache_config)

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
        print(f"Warning: {versions_file} not found, using empty defaults")
        return {"puppet_modules": {}, "terraform_providers": {}}
    except json.JSONDecodeError as e:
        print(f"Error parsing versions.json: {e}")
        return {"puppet_modules": {}, "terraform_providers": {}}

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

@app.after_request
def add_cache_headers(response):
    """Add cache headers for static files."""
    if request.path.startswith('/styles/') or request.path.startswith('/scripts/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'  # 1 day
    return response

# ============================================================================
# API ROUTES - PUPPET MODULES
# ============================================================================

@app.route('/api/modules', methods=['GET'])
@cache.cached(timeout=300)  # 5 Minuten Cache
def get_modules():
    """Ruft Puppet Module Informationen vom Puppet Forge ab."""
    try:
        # Lade installierte Versionen aus JSON-Datei
        versions = load_versions()
        installed_modules = versions.get('puppet_modules', {})

        result = []
        for module_name, installed_version in installed_modules.items():
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
                response = requests.get(url, timeout=15, headers={'User-Agent': 'Puppet-Version-Checker/1.0'})

                if response.status_code == 200:
                    data = response.json()

                    if 'current_release' in data and 'version' in data['current_release']:
                        forge_version = data['current_release']['version']
                        module_data['forgeVersion'] = forge_version
                        module_data['status'] = 'current' if installed_version == forge_version else 'outdated'

                    module_data['deprecated'] = data.get('deprecated_at') is not None
                else:
                    print(f"API returned status {response.status_code} for {module_name}")
                    module_data['status'] = 'error'
                    module_data['error'] = f"API returned status {response.status_code}"

            except requests.Timeout:
                print(f"Timeout fetching module {module_name}")
                module_data['status'] = 'error'
                module_data['error'] = 'Request timeout'
            except requests.RequestException as e:
                print(f"Error fetching module {module_name}: {str(e)}")
                module_data['status'] = 'error'
                module_data['error'] = str(e)
            except Exception as e:
                print(f"Unexpected error for module {module_name}: {str(e)}")
                module_data['status'] = 'error'
                module_data['error'] = f"Unexpected error: {str(e)}"

            result.append(module_data)

        return jsonify(result)
    except Exception as e:
        print(f"Critical error in get_modules: {str(e)}")
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

# ============================================================================
# API ROUTES - TERRAFORM PROVIDERS
# ============================================================================

@app.route('/api/terraform-providers', methods=['GET'])
@cache.cached(timeout=300)  # 5 Minuten Cache
def get_terraform_providers():
    """Ruft Terraform Provider Informationen von der Terraform Registry ab."""
    try:
        # Lade installierte Versionen aus JSON-Datei
        versions = load_versions()
        installed_providers = versions.get('terraform_providers', {})

        result = []
        for provider_name, installed_version in installed_providers.items():
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
                # Terraform Registry API v1
                url = f'https://registry.terraform.io/v1/providers/{namespace}/{name}'
                response = requests.get(url, timeout=15, headers={
                    'User-Agent': 'Terraform-Provider-Checker/1.0',
                    'Accept': 'application/json'
                })

                if response.status_code == 200:
                    data = response.json()

                    # Die neueste Version aus der API holen
                    if 'version' in data:
                        latest_version = data['version']
                        provider_data['latestVersion'] = latest_version

                        # Versionen vergleichen (ohne 'v' Präfix falls vorhanden)
                        installed_clean = installed_version.lstrip('v')
                        latest_clean = latest_version.lstrip('v')

                        if installed_clean == latest_clean:
                            provider_data['status'] = 'current'
                        else:
                            provider_data['status'] = 'outdated'

                    # Zusätzliche Informationen
                    if 'description' in data:
                        provider_data['description'] = data['description']
                    if 'source' in data:
                        provider_data['source'] = data['source']
                    if 'published_at' in data:
                        provider_data['publishedAt'] = data['published_at']

                else:
                    print(f"API returned status {response.status_code} for {provider_name}")
                    provider_data['status'] = 'error'
                    provider_data['error'] = f"API returned status {response.status_code}"

            except requests.Timeout:
                print(f"Timeout fetching provider {provider_name}")
                provider_data['status'] = 'error'
                provider_data['error'] = 'Request timeout'
            except requests.RequestException as e:
                print(f"Error fetching provider {provider_name}: {str(e)}")
                provider_data['status'] = 'error'
                provider_data['error'] = str(e)
            except Exception as e:
                print(f"Unexpected error for provider {provider_name}: {str(e)}")
                provider_data['status'] = 'error'
                provider_data['error'] = f"Unexpected error: {str(e)}"

            result.append(provider_data)

        return jsonify(result)
    except Exception as e:
        print(f"Critical error in get_terraform_providers: {str(e)}")
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

# ============================================================================
# API ROUTES - SYSTEM STATUS
# ============================================================================

@app.route('/api/system_status', methods=['GET'])
def get_system_status():
    """Gibt eine Zusammenfassung des gesamten System-Status zurück."""

    # Puppet Module Status
    puppet_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        modules_response = get_modules()
        modules = modules_response.json

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
    except Exception as e:
        puppet_status = {"status": "Error", "details": str(e)}

    # Terraform Provider Status
    terraform_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        providers_response = get_terraform_providers()
        providers = providers_response.json

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
    except Exception as e:
        terraform_status = {"status": "Error", "details": str(e)}

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
# VERCEL EXPORT - WICHTIG FÜR DEPLOYMENT
# ============================================================================
# Die Flask App wird automatisch von Vercel als WSGI-App erkannt.
