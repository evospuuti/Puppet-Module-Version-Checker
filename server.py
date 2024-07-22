from flask import Flask, jsonify, send_from_directory
from flask_caching import Cache
import requests
import os
import json

app = Flask(__name__)
CORS(app)

cache_config = {
    'CACHE_TYPE': 'SimpleCache',
}
if 'REDIS_URL' in os.environ:
    cache_config = {
        'CACHE_TYPE': 'redis',
        'CACHE_REDIS_URL': os.environ['REDIS_URL']
    }
cache = Cache(app, config=cache_config)

@app.route('/api/modules', methods=['GET'])
@cache.cached(timeout=86400)
def get_modules():
    try:
        modules = [
            'dsc-auditpolicydsc',
            'pcfens-ca_cert',
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
            except requests.exceptions.RequestException as e:
                result.append({
                    'name': module,
                    'error': f'Failed to fetch data: {str(e)}'
                })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": "An unexpected error occurred"}), 500

@app.route('/api/eol/<system>', methods=['GET'])
@cache.cached(timeout=86400)
def get_eol_data(system):
    try:
        url = f'https://endoflife.date/api/{system}.json'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if system == 'debian':
            # Filter für Debian 11 und 12
            data = [version for version in data if version['cycle'] in ['11', '12']]
        elif system == 'sles':
            # Filter für SLES 12 SP5, 15, 15 SP1 bis SP6
            data = [version for version in data if version['cycle'] in ['12.5', '15', '15.1', '15.2', '15.3', '15.4', '15.5', '15.6']]
        elif system == 'windows-server':
            # Filter für Windows Server 2019 und 2022
            data = [version for version in data if version['cycle'] in ['2019', '2022']]
        
        return jsonify(data)
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to fetch {system} EOL data: {str(e)}"}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(f"public/{path}"):
        return send_from_directory('public', path)
    else:
        return send_from_directory('public', 'index.html')

if __name__ == '__main__':
    app.run(host='localhost', debug=True, port=8000)