import os
import requests
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_caching import Cache
from urllib.parse import urlparse

app = Flask(__name__)
CORS(app)

# Cache-Konfiguration für Vercel (serverless-freundlich)
cache_config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
}

# Deaktiviere Redis in serverless Umgebungen
if "REDIS_URL" in os.environ and not os.environ.get("VERCEL"):
    try:
        redis_url = os.environ["REDIS_URL"]
        parsed_url = urlparse(redis_url)
        if not parsed_url.scheme:
            redis_url = f"redis://{redis_url}"
        
        cache_config.update({
            "CACHE_TYPE": "redis",
            "CACHE_REDIS_URL": redis_url,
            "CACHE_OPTIONS": {"socket_timeout": 5, "socket_connect_timeout": 5}
        })
        print("Using Redis cache")
    except Exception as e:
        print(f"Redis connection failed, falling back to SimpleCache: {e}")
        cache_config = {
            "CACHE_TYPE": "SimpleCache",
            "CACHE_DEFAULT_TIMEOUT": 300
        }
else:
    print("Using SimpleCache (no Redis or Vercel environment)")

cache = Cache(app, config=cache_config)



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
            data = [version for version in data if version['cycle'] in ['2019', '2022', '2025']]
        
        return jsonify(data)
    except requests.RequestException:
        return jsonify({"error": f"Failed to fetch {system} EOL data"}), 500


# PuTTY and WinSCP tracking functionality
import json
import re
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    print("BeautifulSoup4 not available - using fallback mode")
    BS4_AVAILABLE = False

class SoftwareChecker:
    def __init__(self):
        self.data_file = "putty_winscp_status.json"
        # Installed versions - diese können in CLAUDE.md oder Umgebungsvariablen konfiguriert werden
        self.installed_versions = {
            'putty': os.environ.get('PUTTY_VERSION', '0.83'),
            'winscp': os.environ.get('WINSCP_VERSION', '6.5'),
            'filezilla-server': os.environ.get('FILEZILLA_SERVER_VERSION', '1.9.4'),
            'firefox': os.environ.get('FIREFOX_VERSION', '128.12.0')
        }
    
    def compare_versions(self, v1, v2):
        """Compare two version strings"""
        try:
            parts1 = [int(x) for x in v1.split('.')]
            parts2 = [int(x) for x in v2.split('.')]
            
            # Pad with zeros if needed
            while len(parts1) < len(parts2):
                parts1.append(0)
            while len(parts2) < len(parts1):
                parts2.append(0)
            
            for i in range(len(parts1)):
                if parts1[i] < parts2[i]:
                    return -1  # v1 is older
                elif parts1[i] > parts2[i]:
                    return 1   # v1 is newer
            return 0  # equal
        except:
            return 0  # If comparison fails, assume equal
        
    def check_github_releases(self, owner, repo):
        """Check latest release from GitHub"""
        try:
            headers = {'Accept': 'application/vnd.github.v3+json'}
            response = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "name": repo,
                    "latest_version": data.get("tag_name", "Unknown").lstrip("v"),
                    "release_date": data.get("published_at", "Unknown"),
                    "release_url": data.get("html_url", ""),
                    "last_checked": datetime.now().isoformat(),
                    "status": "active",
                    "source": "GitHub"
                }
        except Exception as e:
            print(f"Error checking GitHub {owner}/{repo}: {e}")
        
        return None
    
    def check_putty(self):
        """Check PuTTY version from official website"""
        installed_version = self.installed_versions.get('putty', 'Unknown')
        
        if not BS4_AVAILABLE:
            latest_version = "0.78"
            comparison = self.compare_versions(installed_version, latest_version)
            return {
                "name": "putty",
                "installed_version": installed_version,
                "latest_version": latest_version,
                "update_available": comparison < 0,
                "release_date": "Check website for details", 
                "release_url": "https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html",
                "last_checked": datetime.now().isoformat(),
                "status": "active",
                "source": "Static (BS4 unavailable)"
            }
            
        try:
            response = requests.get("https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html", timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # Look for version in the title or main heading
                title = soup.find('title')
                if title:
                    version_match = re.search(r'PuTTY.*?(\d+\.\d+)', title.text)
                    if version_match:
                        version = version_match.group(1)
                        comparison = self.compare_versions(installed_version, version)
                        return {
                            "name": "putty",
                            "installed_version": installed_version,
                            "latest_version": version,
                            "update_available": comparison < 0,
                            "release_date": "Check website for details",
                            "release_url": "https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html",
                            "last_checked": datetime.now().isoformat(),
                            "status": "active",
                            "source": "Official Website"
                        }
        except Exception as e:
            print(f"Error checking PuTTY: {e}")
        
        latest_version = "0.78"
        comparison = self.compare_versions(installed_version, latest_version)
        return {
            "name": "putty",
            "installed_version": installed_version,
            "latest_version": f"{latest_version} (fallback)",
            "update_available": comparison < 0,
            "error": "Failed to fetch version",
            "last_checked": datetime.now().isoformat()
        }
    
    def check_winscp(self):
        """Check WinSCP version from GitHub or official site"""
        installed_version = self.installed_versions.get('winscp', 'Unknown')
        
        # First try GitHub API (doesn't need BeautifulSoup)
        github_result = self.check_github_releases("winscp", "winscp")
        if github_result and "error" not in github_result:
            comparison = self.compare_versions(installed_version, github_result["latest_version"])
            github_result["installed_version"] = installed_version
            github_result["update_available"] = comparison < 0
            return github_result
        
        # Fallback to web scraping only if BS4 is available
        if BS4_AVAILABLE:
            try:
                response = requests.get("https://winscp.net/eng/downloads.php", timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    # Look for version pattern
                    version_match = re.search(r'WinSCP\s+(\d+\.\d+(?:\.\d+)?)', response.text)
                    if version_match:
                        version = version_match.group(1)
                        comparison = self.compare_versions(installed_version, version)
                        return {
                            "name": "winscp",
                            "installed_version": installed_version,
                            "latest_version": version,
                            "update_available": comparison < 0,
                            "release_date": "Check website for details",
                            "release_url": "https://winscp.net/eng/downloads.php",
                            "last_checked": datetime.now().isoformat(),
                            "status": "active",
                            "source": "Official Website"
                        }
            except Exception as e:
                print(f"Error checking WinSCP website: {e}")
        
        latest_version = "6.1.2"
        comparison = self.compare_versions(installed_version, latest_version)
        return {
            "name": "winscp",
            "installed_version": installed_version,
            "latest_version": f"{latest_version} (fallback)",
            "update_available": comparison < 0,
            "release_date": "Check website for details",
            "release_url": "https://winscp.net/eng/downloads.php",
            "last_checked": datetime.now().isoformat(),
            "status": "active",
            "source": "Static (fallback)"
        }
    
    def check_filezilla_server(self):
        """Check FileZilla Server version from GitHub"""
        installed_version = self.installed_versions.get('filezilla-server', 'Unknown')
        
        # Try GitHub API first
        github_result = self.check_github_releases("filezilla-project", "filezilla")
        if github_result and "error" not in github_result:
            # Extract server version from release name if possible
            version = github_result["latest_version"]
            # FileZilla releases are like "3.66.5" but we need server version
            # Try alternative approach
            
        # Try FileZilla Server download page
        if BS4_AVAILABLE:
            try:
                response = requests.get("https://filezilla-project.org/download.php?type=server", timeout=10)
                if response.status_code == 200:
                    # Look for version pattern
                    version_match = re.search(r'FileZilla Server (\d+\.\d+(?:\.\d+)?)', response.text)
                    if version_match:
                        version = version_match.group(1)
                        comparison = self.compare_versions(installed_version, version)
                        return {
                            "name": "filezilla-server",
                            "installed_version": installed_version,
                            "latest_version": version,
                            "update_available": comparison < 0,
                            "release_date": "Check website for details",
                            "release_url": "https://filezilla-project.org/download.php?type=server",
                            "last_checked": datetime.now().isoformat(),
                            "status": "active",
                            "source": "Official Website"
                        }
            except Exception as e:
                print(f"Error checking FileZilla Server: {e}")
        
        # Fallback
        latest_version = "1.9.4"
        comparison = self.compare_versions(installed_version, latest_version)
        return {
            "name": "filezilla-server",
            "installed_version": installed_version,
            "latest_version": f"{latest_version} (fallback)",
            "update_available": comparison < 0,
            "release_date": "Check website for details",
            "release_url": "https://filezilla-project.org/download.php?type=server",
            "last_checked": datetime.now().isoformat(),
            "status": "active",
            "source": "Static (fallback)"
        }
    
    def check_firefox(self):
        """Check Firefox version from Mozilla API"""
        installed_version = self.installed_versions.get('firefox', 'Unknown')
        
        try:
            # Mozilla provides a simple API for latest Firefox version
            response = requests.get("https://product-details.mozilla.org/1.0/firefox_versions.json", timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Use LATEST_FIREFOX_VERSION for stable release
                version = data.get('LATEST_FIREFOX_VERSION', '').replace('esr', '')
                if version:
                    comparison = self.compare_versions(installed_version, version)
                    return {
                        "name": "firefox",
                        "installed_version": installed_version,
                        "latest_version": version,
                        "update_available": comparison < 0,
                        "release_date": "Check website for details",
                        "release_url": "https://www.mozilla.org/firefox/new/",
                        "last_checked": datetime.now().isoformat(),
                        "status": "active",
                        "source": "Mozilla API"
                    }
        except Exception as e:
            print(f"Error checking Firefox: {e}")
        
        # Fallback
        latest_version = "128.0.0"
        comparison = self.compare_versions(installed_version, latest_version)
        return {
            "name": "firefox",
            "installed_version": installed_version,
            "latest_version": f"{latest_version} (fallback)",
            "update_available": comparison < 0,
            "release_date": "Check website for details",
            "release_url": "https://www.mozilla.org/firefox/new/",
            "last_checked": datetime.now().isoformat(),
            "status": "active",
            "source": "Static (fallback)"
        }
    
    def run_checks(self):
        """Run software checks for all configured software"""
        results = {}
        
        print("Checking PuTTY...")
        results["putty"] = self.check_putty()
        
        print("Checking WinSCP...")
        results["winscp"] = self.check_winscp()
        
        print("Checking FileZilla Server...")
        results["filezilla-server"] = self.check_filezilla_server()
        
        print("Checking Firefox...")
        results["firefox"] = self.check_firefox()
        
        # Save results to cache
        cache.set('putty_winscp_data', results, timeout=3600)  # 1 hour cache
        
        print(f"Software check completed at {datetime.now()}")
        return results

# Global software checker instance
software_checker = SoftwareChecker()

@app.route('/api/test_software')
def test_software():
    """Simple test endpoint to debug issues"""
    try:
        import sys
        return jsonify({
            "status": "OK",
            "python_version": sys.version,
            "available_modules": {
                "requests": "requests" in sys.modules,
                "beautifulsoup4": "bs4" in sys.modules,
                "lxml": "lxml" in sys.modules
            },
            "test_data": {
                "putty": {
                    "name": "putty",
                    "latest_version": "0.78",
                    "last_checked": datetime.now().isoformat(),
                    "status": "test",
                    "source": "Test Data"
                },
                "winscp": {
                    "name": "winscp", 
                    "latest_version": "6.1.2",
                    "last_checked": datetime.now().isoformat(),
                    "status": "test",
                    "source": "Test Data"
                }
            }
        })
    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "error_type": type(e).__name__
        })

@app.route('/api/putty_winscp_status')
def get_putty_winscp_status():
    """API endpoint for PuTTY and WinSCP status data"""
    try:
        # Try to get from cache first
        cached_data = cache.get('putty_winscp_data')
        if cached_data:
            print("Returning cached software data")
            return jsonify(cached_data)
        
        # Try a simple approach first - check if modules are available
        try:
            import requests
            import bs4
            print("Required modules available, attempting web scraping...")
            data = software_checker.run_checks()
            return jsonify(data)
        except ImportError as import_error:
            print(f"Module import failed: {import_error}")
            # Return static fallback data when modules aren't available
            fallback_data = {
                "putty": {
                    "name": "putty",
                    "latest_version": "0.78",
                    "release_date": "Check website for details",
                    "release_url": "https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html",
                    "last_checked": datetime.now().isoformat(),
                    "status": "active",
                    "source": "Static Data (Vercel Limitation)"
                },
                "winscp": {
                    "name": "winscp",
                    "latest_version": "6.1.2", 
                    "release_date": "Check website for details",
                    "release_url": "https://winscp.net/eng/downloads.php",
                    "last_checked": datetime.now().isoformat(),
                    "status": "active",
                    "source": "Static Data (Vercel Limitation)"
                }
            }
            # Cache the fallback data
            cache.set('putty_winscp_data', fallback_data, timeout=3600)
            return jsonify(fallback_data)
            
    except Exception as e:
        print(f"Error getting PuTTY/WinSCP status: {e}")
        # Return a fallback response instead of error
        return jsonify({
            "putty": {
                "name": "putty",
                "latest_version": "0.78 (Static)",
                "error": f"Failed to fetch live version: {str(e)}",
                "last_checked": datetime.now().isoformat(),
                "source": "Fallback Data"
            },
            "winscp": {
                "name": "winscp", 
                "latest_version": "6.1.2 (Static)",
                "error": f"Failed to fetch live version: {str(e)}",
                "last_checked": datetime.now().isoformat(),
                "source": "Fallback Data"
            }
        })

@app.route('/api/refresh_putty_winscp', methods=['POST'])
def refresh_putty_winscp():
    """Manually trigger PuTTY and WinSCP check"""
    try:
        # Clear cache and run fresh check
        cache.delete('putty_winscp_data')
        print("Starting manual refresh of software data...")
        data = software_checker.run_checks()
        return jsonify({"status": "Refresh completed", "data": data})
    except Exception as e:
        print(f"Error refreshing PuTTY/WinSCP: {e}")
        # Return partial data instead of error
        return jsonify({
            "status": "Refresh failed", 
            "error": str(e),
            "data": {
                "putty": {
                    "name": "putty",
                    "error": f"Refresh failed: {str(e)}",
                    "last_checked": datetime.now().isoformat()
                },
                "winscp": {
                    "name": "winscp", 
                    "error": f"Refresh failed: {str(e)}",
                    "last_checked": datetime.now().isoformat()
                }
            }
        })

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
            if 'eol' in version and version['eol'] and version['cycle'] in ['2019', '2022', '2025']:
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
    
    # Software Status (PuTTY/WinSCP)
    software_status = {"status": "Unbekannt", "details": "Keine Daten verfügbar"}
    try:
        cached_data = cache.get('putty_winscp_data')
        if cached_data:
            error_count = 0
            total_count = 0
            for key, software in cached_data.items():
                total_count += 1
                if 'error' in software:
                    error_count += 1
            
            if error_count == 0:
                software_status = {"status": "OK", "details": f"Alle {total_count} Software-Tools erreichbar"}
            elif error_count < total_count:
                software_status = {"status": "Warnung", "details": f"{error_count}/{total_count} Software-Tools mit Fehlern"}
            else:
                software_status = {"status": "Kritisch", "details": "Alle Software-Tools fehlerhaft"}
        else:
            software_status = {"status": "Info", "details": "Noch keine Software-Daten geladen"}
    except Exception as e:
        software_status = {"status": "Error", "details": str(e)}

    return jsonify({
        "puppet": puppet_status,
        "eol": eol_status,
        "software": software_status,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(f"public/{path}"):
        return send_from_directory('public', path)
    else:
        return send_from_directory('public', 'index.html')

def initialize_software_data():
    """Initialize software data on startup"""
    try:
        print("Initializing software data...")
        software_checker.run_checks()
        print("Software data initialized successfully")
    except Exception as e:
        print(f"Error initializing software data: {e}")

if __name__ == '__main__':
    # Initialize software data on startup
    initialize_software_data()
    
    # Für Development-Server
    # In Produktion besser gunicorn mit worker_class='gevent' verwenden
    app.run(debug=False, threaded=True)
