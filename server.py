import os
import ssl
import socket
import requests
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
from urllib.parse import urlparse

app = Flask(__name__)
CORS(app)

# Vereinfachte Cache-Konfiguration für Vercel Serverless
cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
}

cache = Cache(app, config=cache_config)

# Pushover configuration
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "ukiu6xsyzf67o17bq2p4ucvs83dx84")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "aoz51q2bfsb74dzfn3dc2xmoie8mzo")

def send_pushover_notification(message, title):
    """Sendet Push-Benachrichtigung über Pushover."""
    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title
    }
    try:
        response = requests.post(url, data=data, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Pushover notification error: {e}")
        return False

def check_ssl_certificate(hostname, port=443, timeout=3.0):
    """Prüft SSL-Zertifikat und gibt Ablaufdatum zurück."""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                expiry_date = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y GMT')
                
                # Zusätzliche Zertifikatsinformationen
                cert_info = {
                    'expiry': expiry_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'subject': dict(x[0] for x in cert['subject']),
                    'issuer': dict(x[0] for x in cert['issuer'])
                }
                return cert_info
    except Exception as e:
        print(f"SSL check error for {hostname}: {e}")
        return None

def check_website(site_url):
    """Prüft Website-Status und SSL-Zertifikat."""
    site = {
        'url': site_url,
        'status': 'Unknown',
        'last_checked': 'Never',
        'cert_expiry': 'Unknown',
        'certIssuer': None,
        'certValidFrom': None
    }
    
    try:
        response = requests.get(site_url, timeout=5, verify=True)
        site['status'] = 'Online' if response.status_code == 200 else 'Offline'
        site['response_code'] = response.status_code
        
        # SSL-Zertifikatsprüfung für HTTPS-URLs
        if site_url.startswith('https://'):
            hostname = urlparse(site_url).netloc
            cert_info = check_ssl_certificate(hostname)
            
            if cert_info:
                site['cert_expiry'] = cert_info['expiry']
                site['certIssuer'] = cert_info['issuer'].get('organizationName', 'Unknown')
                
                # Valid From Datum aus dem Zertifikat
                try:
                    context = ssl.create_default_context()
                    with socket.create_connection((hostname, 443), timeout=3.0) as sock:
                        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                            cert = ssock.getpeercert()
                            valid_from = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y GMT')
                            site['certValidFrom'] = valid_from.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
        
    except requests.RequestException as e:
        site['status'] = 'Offline'
        site['error'] = str(e)
        
        # Benachrichtigung bei Offline-Status
        cached_status = cache.get(f'website_status_{site_url}')
        if cached_status != 'Offline':
            send_pushover_notification(
                f"Website {site_url} ist offline! Fehler: {str(e)}", 
                "Website Monitoring Alert"
            )
        cache.set(f'website_status_{site_url}', 'Offline', timeout=300)
    
    site['last_checked'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return site

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
# API ROUTES - WEBSITE MONITORING
# ============================================================================

@app.route('/api/check_website', methods=['GET'])
def get_website_status():
    """
    Prüft den Status aller konfigurierten Websites.
    Query Parameter: force=true für erzwungene Aktualisierung
    """
    websites_to_check = [
        'https://www.spherea.de',
        'https://www.rapunzel.de'
    ]
    
    # Prüfe Cache
    cached_data = cache.get('website_status_all')
    force_check = request.args.get('force', '').lower() == 'true'
    
    if not force_check and cached_data:
        return jsonify(cached_data)
    
    # Führe Checks durch
    results = []
    for url in websites_to_check:
        results.append(check_website(url))
    
    # Cache aktualisieren (60 Sekunden)
    cache.set('website_status_all', results, timeout=60)
    
    return jsonify(results)

# ============================================================================
# API ROUTES - PUPPET MODULES
# ============================================================================

@app.route('/api/modules', methods=['GET'])
@cache.cached(timeout=3600)  # 1 Stunde Cache
def get_modules():
    """Ruft Puppet Module Informationen vom Puppet Forge ab."""
    modules = [
        'dsc-auditpolicydsc',
        'puppet-ca_cert',
        'puppet-alternatives',
        'puppet-archive',
        'puppet-systemd',
        'puppetlabs-apt',
        'puppetlabs-facts',
        'puppetlabs-inifile',
        'puppetlabs-powershell',
        'puppetlabs-registry',
        'puppetlabs-stdlib',
        'saz-sudo'
    ]
    
    result = []
    for module in modules:
        try:
            url = f'https://forgeapi.puppet.com/v3/modules/{module}'
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            deprecated = data.get('deprecated_at') is not None
            
            result.append({
                'name': module,
                'forgeVersion': data['current_release']['version'],
                'url': f'https://forge.puppet.com/modules/{module.replace("-", "/")}',
                'deprecated': deprecated
            })
        except requests.RequestException as e:
            print(f"Error fetching module {module}: {e}")
            result.append({
                'name': module,
                'error': 'Failed to fetch data'
            })
    
    return jsonify(result)

# ============================================================================
# API ROUTES - EOL DATA
# ============================================================================

@app.route('/api/eol/<system>', methods=['GET'])
@cache.cached(timeout=86400)  # 24 Stunden Cache
def get_eol_data(system):
    """
    Ruft End-of-Life Daten für Betriebssysteme ab.
    Unterstützt: debian, sles, windows-server
    """
    try:
        url = f'https://endoflife.date/api/{system}.json'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Filtere relevante Versionen
        if system == 'debian':
            data = [version for version in data if version['cycle'] in ['11', '12']]
        elif system == 'sles':
            data = [version for version in data if version['cycle'] in [
                '12.5', '15', '15.1', '15.2', '15.3', '15.4', '15.5', '15.6'
            ]]
        elif system == 'windows-server':
            data = [version for version in data if version['cycle'] in ['2019', '2022']]
        
        return jsonify(data)
    except requests.RequestException as e:
        print(f"Error fetching EOL data for {system}: {e}")
        return jsonify({"error": f"Failed to fetch {system} EOL data"}), 500

# ============================================================================
# API ROUTES - SOFTWARE VERSIONS
# ============================================================================

@app.route('/api/software_versions', methods=['GET'])
def get_software_versions():
    """Ruft alle gespeicherten Software-Versionen ab."""
    software_versions = cache.get('software_versions')
    if software_versions is None:
        software_versions = []
    return jsonify(software_versions)

@app.route('/api/software_versions', methods=['POST'])
def add_software_version():
    """Fügt eine neue Software-Version hinzu."""
    new_software = request.json
    software_versions = cache.get('software_versions')
    if software_versions is None:
        software_versions = []
    
    software_versions.append(new_software)
    cache.set('software_versions', software_versions)
    
    return jsonify({"message": "Software added successfully"}), 201

@app.route('/api/software_versions/<int:index>', methods=['PUT'])
def update_software_version(index):
    """Aktualisiert eine bestehende Software-Version."""
    updated_software = request.json
    software_versions = cache.get('software_versions')
    
    if software_versions is None or index >= len(software_versions):
        return jsonify({"error": "Software not found"}), 404
    
    software_versions[index] = updated_software
    cache.set('software_versions', software_versions)
    
    return jsonify({"message": "Software updated successfully"})

@app.route('/api/software_versions/<int:index>', methods=['DELETE'])
def delete_software_version(index):
    """Löscht eine Software-Version."""
    software_versions = cache.get('software_versions')
    
    if software_versions is None or index >= len(software_versions):
        return jsonify({"error": "Software not found"}), 404
    
    del software_versions[index]
    cache.set('software_versions', software_versions)
    
    return jsonify({"message": "Software deleted successfully"})

# ============================================================================
# API ROUTES - SYSTEM STATUS
# ============================================================================

@app.route('/api/system_status', methods=['GET'])
def get_system_status():
    """Gibt eine Zusammenfassung des gesamten System-Status zurück."""
    
    # Server-Versionen für Puppet Module
    server_versions = {
        'dsc-auditpolicydsc': '1.4.0-0-9',
        'puppet-alternatives': '6.0.0',
        'puppet-archive': '7.1.0',
        'puppet-systemd': '8.2.0',
        'puppetlabs-apt': '10.0.1',
        'puppetlabs-facts': '1.7.0',
        'puppetlabs-inifile': '6.2.0',
        'puppetlabs-powershell': '6.0.2',
        'puppetlabs-registry': '5.0.3',
        'puppetlabs-stdlib': '9.7.0',
        'saz-sudo': '9.0.2',
        'puppet-ca_cert': '3.1.0'
    }
    
    # Puppet Module Status
    puppet_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        modules_response = get_modules()
        modules = modules_response.json
        
        update_count = 0
        deprecated_count = 0
        
        for module in modules:
            if module.get('deprecated'):
                deprecated_count += 1
            elif 'error' not in module:
                server_version = server_versions.get(module['name'], 'Unbekannt')
                if server_version != 'Unbekannt' and module.get('forgeVersion') != server_version:
                    update_count += 1
        
        if deprecated_count > 0:
            puppet_status = {"status": "Warnung", "details": f"{deprecated_count} Module deprecated"}
        elif update_count > 0:
            puppet_status = {"status": "Info", "details": f"{update_count} Updates verfügbar"}
        else:
            puppet_status = {"status": "OK", "details": "Alle Module aktuell"}
    except Exception as e:
        puppet_status = {"status": "Error", "details": str(e)}
    
    # Website Status
    website_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        websites = cache.get('website_status_all')
        if websites:
            online_count = sum(1 for site in websites if site['status'] == 'Online')
            total_count = len(websites)
            
            if online_count == total_count:
                website_status = {"status": "OK", "details": f"Alle {total_count} Websites online"}
            elif online_count > 0:
                website_status = {"status": "Warnung", "details": f"{online_count}/{total_count} Websites online"}
            else:
                website_status = {"status": "Kritisch", "details": "Alle Websites offline"}
        else:
            website_status = {"status": "Info", "details": "Monitoring verfügbar über /api/check_website"}
    except Exception as e:
        website_status = {"status": "Error", "details": str(e)}
    
    # SSL Status
    ssl_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        websites = cache.get('website_status_all')
        if websites:
            expiry_warning_days = 30
            expiry_critical_days = 7
            
            warning_certs = []
            critical_certs = []
            
            for site in websites:
                if site.get('cert_expiry') and site['cert_expiry'] != 'Unknown':
                    try:
                        expiry_date = datetime.strptime(site['cert_expiry'], '%Y-%m-%d %H:%M:%S')
                        days_until_expiry = (expiry_date - datetime.now()).days
                        
                        if days_until_expiry <= expiry_critical_days:
                            critical_certs.append(site['url'])
                        elif days_until_expiry <= expiry_warning_days:
                            warning_certs.append(site['url'])
                    except Exception as e:
                        print(f"Error parsing cert expiry for {site['url']}: {e}")
            
            if critical_certs:
                ssl_status = {
                    "status": "Kritisch", 
                    "details": f"{len(critical_certs)} Zertifikate laufen in <7 Tagen ab"
                }
            elif warning_certs:
                ssl_status = {
                    "status": "Warnung", 
                    "details": f"{len(warning_certs)} Zertifikate laufen in <30 Tagen ab"
                }
            else:
                ssl_status = {"status": "OK", "details": "Alle Zertifikate gültig"}
        else:
            ssl_status = {"status": "Info", "details": "SSL-Prüfung verfügbar"}
    except Exception as e:
        ssl_status = {"status": "Error", "details": str(e)}
    
    # EOL Status
    eol_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        warning_days = 365  # 1 Jahr Warnung
        warning_systems = []
        expired_systems = []
        
        # Prüfe Debian
        try:
            debian_response = get_eol_data('debian')
            debian_data = debian_response.json
            
            for version in debian_data:
                if 'eol' in version and version['eol']:
                    try:
                        eol_date = datetime.strptime(version['eol'], '%Y-%m-%d')
                        days_until_eol = (eol_date - datetime.now()).days
                        
                        if days_until_eol <= 0:
                            expired_systems.append(f"Debian {version['cycle']}")
                        elif days_until_eol <= warning_days:
                            warning_systems.append(f"Debian {version['cycle']}")
                    except:
                        pass
        except:
            pass
        
        # Prüfe SLES
        try:
            sles_response = get_eol_data('sles')
            sles_data = sles_response.json
            
            for version in sles_data:
                if 'eol' in version and version['eol']:
                    try:
                        eol_date = datetime.strptime(version['eol'], '%Y-%m-%d')
                        days_until_eol = (eol_date - datetime.now()).days
                        
                        if days_until_eol <= 0:
                            expired_systems.append(f"SLES {version['cycle']}")
                        elif days_until_eol <= warning_days:
                            warning_systems.append(f"SLES {version['cycle']}")
                    except:
                        pass
        except:
            pass
        
        # Prüfe Windows Server
        try:
            windows_response = get_eol_data('windows-server')
            windows_data = windows_response.json
            
            for version in windows_data:
                if 'eol' in version and version['eol'] and version['cycle'] in ['2019', '2022']:
                    try:
                        eol_date = datetime.strptime(version['eol'], '%Y-%m-%d')
                        days_until_eol = (eol_date - datetime.now()).days
                        
                        if days_until_eol <= 0:
                            expired_systems.append(f"Windows Server {version['cycle']}")
                        elif days_until_eol <= warning_days:
                            warning_systems.append(f"Windows Server {version['cycle']}")
                    except:
                        pass
        except:
            pass
        
        if expired_systems:
            eol_status = {"status": "Kritisch", "details": f"{len(expired_systems)} Systeme EOL erreicht"}
        elif warning_systems:
            eol_status = {"status": "Warnung", "details": f"{len(warning_systems)} Systeme nahe EOL"}
        else:
            eol_status = {"status": "OK", "details": "Alle Systeme im Support"}
    except Exception as e:
        eol_status = {"status": "Error", "details": str(e)}
    
    return jsonify({
        "puppet": puppet_status,
        "websites": website_status,
        "ssl": ssl_status,
        "eol": eol_status,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

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
# Die Flask App muss für Vercel exportiert werden.
# Das if __name__ == '__main__' wird in der Serverless-Umgebung nicht ausgeführt.
