import os
import ssl
import OpenSSL
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
from urllib.parse import urlparse
from datetime import datetime, timedelta
import threading
import time
import hashlib

app = Flask(__name__)
CORS(app)

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
        "CACHE_REDIS_URL": redis_url
    })

cache = Cache(app, config=cache_config)

# Pushover configuration
PUSHOVER_USER_KEY = "ukiu6xsyzf67o17bq2p4ucvs83dx84"
PUSHOVER_API_TOKEN = "aoz51q2bfsb74dzfn3dc2xmoie8mzo"

def send_pushover_notification(message, title):
    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title
    }
    response = requests.post(url, data=data)
    return response.status_code == 200

def generate_pseudonym(url):
    hash_object = hashlib.md5(url.encode())
    return hash_object.hexdigest()[:8]

websites = [
    {
        'id': generate_pseudonym('https://www.rapunzel.de'),
        'url': 'https://www.rapunzel.de',
        'name': 'Kunde A',
        'status': 'Unknown',
        'last_checked': 'Never',
        'cert_expiry': 'Unknown'
    },
    {
        'id': generate_pseudonym('https://www.spherea.de'),
        'url': 'https://www.spherea.de',
        'name': 'Kunde B',
        'status': 'Unknown',
        'last_checked': 'Never',
        'cert_expiry': 'Unknown'
    }
]

def check_website(site):
    try:
        response = requests.get(site['url'], timeout=5)
        site['status'] = 'Online' if response.status_code == 200 else 'Offline'
        
        # Check SSL certificate
        hostname = urlparse(site['url']).netloc
        cert = ssl.get_server_certificate((hostname, 443))
        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
        expiry_date = datetime.strptime(x509.get_notAfter().decode('ascii'), '%Y%m%d%H%M%SZ')
        site['cert_expiry'] = expiry_date.strftime('%Y-%m-%d %H:%M:%S')
        
    except requests.RequestException:
        site['status'] = 'Offline'
        if site.get('last_status') != 'Offline':
            send_pushover_notification(f"Website {site['name']} (ID: {site['id']}) is offline!", "Website Monitoring Alert")
    
    site['last_checked'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    site['last_status'] = site['status']

def monitor_websites():
    while True:
        for site in websites:
            check_website(site)
        time.sleep(60)  # Wait for 1 minute

# Start the monitoring in a separate thread
monitor_thread = threading.Thread(target=monitor_websites, daemon=True)
monitor_thread.start()

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

@app.route('/api/check_website', methods=['GET'])
def get_website_status():
    safe_websites = [{k: v for k, v in site.items() if k != 'url'} for site in websites]
    return jsonify(safe_websites)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(f"public/{path}"):
        return send_from_directory('public', path)
    else:
        return send_from_directory('public', 'index.html')

if __name__ == '__main__':
    app.run(debug=False)