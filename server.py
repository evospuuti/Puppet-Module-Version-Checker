from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

@app.route('/api/modules')
def get_modules():
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
            response = requests.get(url, timeout=5)  # Added timeout
            response.raise_for_status()  # Raises an HTTPError for bad responses
            data = response.json()
            deprecated = data.get('deprecated_at') is not None
            result.append({
                'name': module,
                'forgeVersion': data['current_release']['version'],
                'url': f'https://forge.puppet.com/modules/{module.replace("-", "/")}',
                'deprecated': deprecated
            })
        except requests.RequestException as e:
            print(f"Error fetching data for {module}: {str(e)}")
            result.append({
                'name': module,
                'error': 'Failed to fetch data'
            })

    return jsonify(result)

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

# Error handler for 404 errors
@app.errorhandler(404)
def not_found(e):
    return jsonify(error=str(e)), 404

# Vercel specififc route for serverless function
@app.route('/api/modules', methods=['GET'])
def api_modules():
    return get_modules()