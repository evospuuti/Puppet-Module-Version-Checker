import os
import logging
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
from urllib.parse import urlparse
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
}

if "REDIS_URL" in os.environ:
    redis_url = os.environ["REDIS_URL"]
    logger.info("Redis URL found in environment variables")
    
    parsed_url = urlparse(redis_url)
    if not parsed_url.scheme:
        redis_url = f"redis://{redis_url}"
    
    cache_config.update({
        "CACHE_TYPE": "redis",
        "CACHE_REDIS_URL": redis_url
    })

try:
    cache = Cache(app, config=cache_config)
    logger.info("Cache initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Redis cache: {e}")
    logger.info("Falling back to SimpleCache")
    cache = Cache(app, config={"CACHE_TYPE": "SimpleCache"})

@app.route('/api/modules', methods=['GET'])
@cache.cached(timeout=3600)  # Cache für 1 Stunde
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
        logger.error(f"Error in get_modules: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

@app.route('/api/eol/<system>', methods=['GET'])
@cache.cached(timeout=86400)  # Cache für 24 Stunden
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
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching EOL data for {system}: {str(e)}")
        return jsonify({"error": f"Failed to fetch {system} EOL data: {str(e)}"}), 500

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

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(f"public/{path}"):
        return send_from_directory('public', path)
    else:
        return send_from_directory('public', 'index.html')

if __name__ == '__main__':
    app.run(debug=False)