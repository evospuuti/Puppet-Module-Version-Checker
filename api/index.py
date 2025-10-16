import sys
import os

# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
import ssl
import socket
import OpenSSL
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import urlparse

app = Flask(__name__, static_folder='../public', static_url_path='')
CORS(app)

# Cache configuration
cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
}
cache = Cache(app, config=cache_config)

# Import all routes from server.py
from server import (
    check_module_versions, analyze_module, analyze_all_modules,
    check_website, check_software_versions, check_eol_dates,
    scan_all_projects
)

# Register the routes
app.add_url_rule('/api/check_module_versions', 'check_module_versions', check_module_versions, methods=['POST'])
app.add_url_rule('/api/analyze_module', 'analyze_module', analyze_module, methods=['POST'])
app.add_url_rule('/api/analyze_all_modules', 'analyze_all_modules', analyze_all_modules, methods=['POST'])
app.add_url_rule('/api/check_website', 'check_website', check_website, methods=['GET'])
app.add_url_rule('/api/check_software_versions', 'check_software_versions', check_software_versions, methods=['GET'])
app.add_url_rule('/api/check_eol_dates', 'check_eol_dates', check_eol_dates, methods=['GET'])
app.add_url_rule('/api/scan_all_projects', 'scan_all_projects', scan_all_projects, methods=['GET'])

@app.route('/')
def index():
    """Serve the main index.html file."""
    return send_from_directory('../public', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files from public directory."""
    file_path = os.path.join('../public', path)
    if os.path.exists(os.path.join(app.root_path, file_path)):
        return send_from_directory('../public', path)
    # Default to index.html for client-side routing
    return send_from_directory('../public', 'index.html')

# Export for Vercel
handler = app