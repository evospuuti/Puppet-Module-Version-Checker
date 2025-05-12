import os
import ssl
import socket
import OpenSSL
import requests
import asyncio
import aiohttp
import threading
import time
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
from urllib.parse import urlparse

app = Flask(__name__)
CORS(app)

# Verbesserte Cache-Konfiguration
cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
}

if "REDIS_URL" in os.environ:
    redis_url = os.environ["REDIS_URL"]
    parsed_url = urlparse(redis_url)
    if not parsed_url.scheme:
        redis_url = f"redis://{redis_url}"
    
    cache_config.update({
        "CACHE_TYPE": "redis",
        "CACHE_REDIS_URL": redis_url,
        "CACHE_OPTIONS": {"socket_timeout": 5, "socket_connect_timeout": 5}
    })

cache = Cache(app, config=cache_config)

# Pushover configuration
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "ukiu6xsyzf67o17bq2p4ucvs83dx84")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", "aoz51q2bfsb74dzfn3dc2xmoie8mzo")

def send_pushover_notification(message, title):
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
    except:
        return False

# Websites zu überwachen mit initialem Status
websites = [
    {'url': 'https://www.spherea.de', 'status': 'Unknown', 'last_checked': 'Never', 'cert_expiry': 'Unknown'},
    {'url': 'https://www.rapunzel.de', 'status': 'Unknown', 'last_checked': 'Never', 'cert_expiry': 'Unknown'}
]

# OPTIMIERUNG 1: Effiziente SSL-Zertifikatsprüfung
def check_ssl_certificate(hostname, port=443, timeout=3.0):
    """Effizientere Methode zur Prüfung von SSL-Zertifikaten."""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                expiry_date = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y GMT')
                return expiry_date.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        print(f"SSL check error for {hostname}: {e}")
        return 'Unknown'

# OPTIMIERUNG 2: Parallelisierte Websiteprüfung
def check_website(site):
    """Optimierte Website-Prüfung mit schnellerem SSL-Check."""
    try:
        start_time = time.time()
        response = requests.get(site['url'], timeout=5, verify=True)
        response_time = time.time() - start_time
        
        site['status'] = 'Online' if response.status_code == 200 else 'Offline'
        site['response_time'] = round(response_time * 1000, 2)  # ms
        
        # Effizienterer SSL-Check
        if site['url'].startswith('https://'):
            hostname = urlparse(site['url']).netloc
            site['cert_expiry'] = check_ssl_certificate(hostname)
        
    except requests.RequestException as e:
        site['status'] = 'Offline'
        site['error'] = str(e)
        
        # Benachrichtigung nur bei Statusänderung
        if site.get('last_status') != 'Offline':
            send_pushover_notification(f"Website {site['url']} is offline! Error: {str(e)}", "Website Monitoring Alert")
    
    site['last_checked'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    site['last_status'] = site['status']
    return site

# OPTIMIERUNG 3: Parallelisierte Prüfung aller Websites
def check_all_websites():
    """Parallelisierte Prüfung aller Websites mit ThreadPoolExecutor."""
    global websites  # Diese Zeile muss am Anfang der Funktion stehen
    
    with ThreadPoolExecutor(max_workers=min(len(websites), 10)) as executor:
        updated_sites = list(executor.map(check_website, websites))
    
    # Atomar aktualisieren und cachen
    websites = updated_sites
    
    # Cache aktualisieren
    cache.set('website_status', websites, timeout=60)
    return websites

# OPTIMIERUNG 4: Hintergrund-Thread mit besserer Fehlerbehandlung
def monitor_websites():
    """Hintergrundprozess zur Überwachung von Websites mit Fehlerbehandlung."""
    while True:
        try:
            check_all_websites()
            # Logging
            print(f"[{datetime.now()}] Websites checked successfully")
        except Exception as e:
            print(f"[{datetime.now()}] Error in website monitoring: {e}")
        
        # Warte 60 Sekunden bis zur nächsten Prüfung
        time.sleep(60)

# OPTIMIERUNG 5: Asynchrone Version der Website-Prüfung (für zukünftige Verwendung)
async def monitor_websites_async():
    """Asynchroner Hintergrundprozess zur Überwachung von Websites."""
    global websites  # Diese Zeile muss am Anfang der Funktion stehen
    
    while True:
        try:
            tasks = [check_website_async(site) for site in websites]
            updated_sites = await asyncio.gather(*tasks)
            
            # Update globals
            websites = updated_sites
            cache.set('website_status', websites, timeout=60)
        
        # SSL-Check muss separat erfolgen, da aiohttp keinen direkten Zugriff auf Zertifikate bietet
        if site['url'].startswith('https://'):
            hostname = urlparse(site['url']).netloc
            site['cert_expiry'] = check_ssl_certificate(hostname)
            
    except Exception as e:
        site['status'] = 'Offline'
        site['error'] = str(e)
        
        if site.get('last_status') != 'Offline':
            send_pushover_notification(f"Website {site['url']} is offline! Error: {str(e)}", "Website Monitoring Alert")
    
    site['last_checked'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    site['last_status'] = site['status']
    return site

async def monitor_websites_async():
    """Asynchroner Hintergrundprozess zur Überwachung von Websites."""
    while True:
        try:
            tasks = [check_website_async(site) for site in websites]
            updated_sites = await asyncio.gather(*tasks)
            
            # Update globals and cache
            global websites
            websites = updated_sites
            cache.set('website_status', websites, timeout=60)
            
            print(f"[{datetime.now()}] Websites checked successfully (async)")
        except Exception as e:
            print(f"[{datetime.now()}] Error in async website monitoring: {e}")
        
        await asyncio.sleep(60)

# OPTIMIERUNG 6: Gecachter API-Endpunkt mit Fallback
@app.route('/api/check_website', methods=['GET'])
@cache.cached(timeout=30, key_prefix='website_status')
def get_website_status():
    """Optimierter API-Endpunkt mit Cache und Fallback."""
    # Force-Parameter für sofortige Aktualisierung
    force_check = request.args.get('force', '').lower() == 'true'
    
    # Prüfe, ob ein Cache-Wert existiert
    cached_data = cache.get('website_status')
    
    # Wenn kein Cache oder Force, führe neue Prüfung durch
    if force_check or not cached_data:
        try:
            return jsonify(check_all_websites())
        except Exception as e:
            print(f"Error checking websites: {e}")
            if cached_data:
                return jsonify(cached_data)  # Fallback auf Cache
            return jsonify(websites)  # Fallback auf letzte bekannte Werte
    
    # Gib Cache zurück
    return jsonify(cached_data)

# Ergänzende Routen (wie im Original)
@app.route('/styles/<path:filename>')
def serve_styles(filename):
    return send_from_directory('public/styles', filename)

@app.route('/scripts/<path:filename>')
def serve_scripts(filename):
    return send_from_directory('public/scripts', filename)

@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/styles/') or request.path.startswith('/scripts/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'  # 1 day
    return response

@app.route('/api/modules', methods=['GET'])
@cache.cached(timeout=3600)
def get_modules():
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
        except requests.RequestException:
            result.append({
                'name': module,
                'error': 'Failed to fetch data'
            })
    return jsonify(result)

@app.route('/api/eol/<system>', methods=['GET'])
@cache.cached(timeout=86400)
def get_eol_data(system):
    try:
        url = f'https://endoflife.date/api/{system}.json'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if system == 'debian':
            data = [version for version in data if version['cycle'] in ['11', '12']]
        elif system == 'sles':
            data = [version for version in data if version['cycle'] in ['12.5', '15', '15.1', '15.2', '15.3', '15.4', '15.5', '15.6']]
        elif system == 'windows-server':
            data = [version for version in data if version['cycle'] in ['2019', '2022']]
        
        return jsonify(data)
    except requests.RequestException:
        return jsonify({"error": f"Failed to fetch {system} EOL data"}), 500

@app.route('/api/software_versions', methods=['GET'])
def get_software_versions():
    software_versions = cache.get('software_versions')
    if software_versions is None:
        software_versions = []
    return jsonify(software_versions)

@app.route('/api/software_versions', methods=['POST'])
def add_software_version():
    new_software = request.json
    software_versions = cache.get('software_versions')
    if software_versions is None:
        software_versions = []
    software_versions.append(new_software)
    cache.set('software_versions', software_versions)
    return jsonify({"message": "Software added successfully"}), 201

@app.route('/api/software_versions/<int:index>', methods=['PUT'])
def update_software_version(index):
    updated_software = request.json
    software_versions = cache.get('software_versions')
    if software_versions is None or index >= len(software_versions):
        return jsonify({"error": "Software not found"}), 404
    software_versions[index] = updated_software
    cache.set('software_versions', software_versions)
    return jsonify({"message": "Software updated successfully"})

@app.route('/api/software_versions/<int:index>', methods=['DELETE'])
def delete_software_version(index):
    software_versions = cache.get('software_versions')
    if software_versions is None or index >= len(software_versions):
        return jsonify({"error": "Software not found"}), 404
    del software_versions[index]
    cache.set('software_versions', software_versions)
    return jsonify({"message": "Software deleted successfully"})

# API-Endpunkt für Systemstatus-Zusammenfassung
@app.route('/api/system_status', methods=['GET'])
def get_system_status():
    # Puppet Module Status
    puppet_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        modules = get_modules().json
        update_count = 0
        deprecated_count = 0
        
        for module in modules:
            if module.get('deprecated'):
                deprecated_count += 1
            elif 'error' not in module:
                server_version = {
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
                }.get(module['name'], 'Unbekannt')
                
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
        online_count = sum(1 for site in websites if site['status'] == 'Online')
        total_count = len(websites)
        
        if online_count == total_count:
            website_status = {"status": "OK", "details": f"Alle {total_count} Websites online"}
        elif online_count > 0:
            website_status = {"status": "Warnung", "details": f"{online_count}/{total_count} Websites online"}
        else:
            website_status = {"status": "Kritisch", "details": "Alle Websites offline"}
    except Exception as e:
        website_status = {"status": "Error", "details": str(e)}
    
    # SSL Status
    ssl_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
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
                except:
                    pass
        
        if critical_certs:
            ssl_status = {"status": "Kritisch", "details": f"{len(critical_certs)} Zertifikate laufen in <7 Tagen ab"}
        elif warning_certs:
            ssl_status = {"status": "Warnung", "details": f"{len(warning_certs)} Zertifikate laufen in <30 Tagen ab"}
        else:
            ssl_status = {"status": "OK", "details": "Alle Zertifikate gültig"}
    except Exception as e:
        ssl_status = {"status": "Error", "details": str(e)}
    
    # EOL Status
    eol_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        warning_days = 365  # 1 Jahr Warnung
        
        warning_systems = []
        expired_systems = []
        
        # Debian
        debian_data = get_eol_data('debian').json
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
        
        # SLES
        sles_data = get_eol_data('sles').json
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
        
        # Windows Server
        windows_data = get_eol_data('windows-server').json
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

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(f"public/{path}"):
        return send_from_directory('public', path)
    else:
        return send_from_directory('public', 'index.html')

if __name__ == '__main__':
    # Starte den Monitoring-Thread im Hintergrund
    monitor_thread = threading.Thread(target=monitor_websites, daemon=True)
    monitor_thread.start()
    
    # Für Development-Server
    # In Produktion besser gunicorn mit worker_class='gevent' verwenden
    app.run(debug=False, threaded=True)
