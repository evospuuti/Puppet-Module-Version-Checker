import json
import pytest
from unittest.mock import patch, MagicMock
import server


@pytest.fixture(autouse=True)
def reset_versions_cache():
    """Reset the in-memory versions cache before each test."""
    server._versions_cache = None
    yield
    server._versions_cache = None


@pytest.fixture(autouse=True)
def reset_flask_cache():
    """Reset Flask-Caching before each test."""
    server.cache.clear()


@pytest.fixture
def client():
    """Flask test client."""
    server.app.config['TESTING'] = True
    with server.app.test_client() as client:
        yield client


@pytest.fixture
def mock_versions():
    """Standard test versions."""
    return {
        "puppet_modules": {
            "puppetlabs-stdlib": "9.7.0"
        },
        "terraform_providers": {
            "hashicorp/random": "3.7.2"
        }
    }


# ============================================================================
# UNIT TESTS - load_versions
# ============================================================================

def test_load_versions_returns_dict():
    """versions.json wird korrekt geladen."""
    result = server.load_versions()
    assert isinstance(result, dict)
    assert 'puppet_modules' in result
    assert 'terraform_providers' in result


def test_load_versions_caches_result():
    """Zweiter Aufruf verwendet den In-Memory-Cache."""
    result1 = server.load_versions()
    result2 = server.load_versions()
    assert result1 is result2


def test_load_versions_file_not_found():
    """Gibt leere Defaults zurück wenn versions.json fehlt."""
    with patch('builtins.open', side_effect=FileNotFoundError):
        result = server.load_versions()
    assert result == {"puppet_modules": {}, "terraform_providers": {}}


def test_load_versions_invalid_json():
    """Gibt leere Defaults zurück bei ungültigem JSON."""
    with patch('builtins.open', side_effect=json.JSONDecodeError("err", "", 0)):
        result = server.load_versions()
    assert result == {"puppet_modules": {}, "terraform_providers": {}}


# ============================================================================
# UNIT TESTS - _fetch_single_module
# ============================================================================

def test_fetch_single_module_current():
    """Modul wird als 'current' erkannt wenn Versionen übereinstimmen."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '9.7.0'},
        'deprecated_at': None
    }

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('puppetlabs-stdlib', '9.7.0')

    assert result['status'] == 'current'
    assert result['forgeVersion'] == '9.7.0'
    assert result['deprecated'] is False


def test_fetch_single_module_outdated():
    """Modul wird als 'outdated' erkannt bei Versionsunterschied."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '10.0.0'},
        'deprecated_at': None
    }

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('puppetlabs-stdlib', '9.7.0')

    assert result['status'] == 'outdated'
    assert result['forgeVersion'] == '10.0.0'


def test_fetch_single_module_deprecated():
    """Deprecated-Status wird korrekt erkannt."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '9.7.0'},
        'deprecated_at': '2024-01-01'
    }

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('old-module', '9.7.0')

    assert result['deprecated'] is True


def test_fetch_single_module_timeout():
    """Timeout wird als Error-Status zurückgegeben."""
    with patch.object(server.requests.Session, 'get', side_effect=server.requests.Timeout):
        result = server._fetch_single_module('puppetlabs-stdlib', '9.7.0')

    assert result['status'] == 'error'
    assert result['error'] == 'Timeout'


def test_fetch_single_module_http_error():
    """HTTP-Fehler wird als Error-Status zurückgegeben."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('nonexistent-module', '1.0.0')

    assert result['status'] == 'error'
    assert 'HTTP 404' in result['error']


def test_fetch_single_module_connection_error():
    """Verbindungsfehler wird korrekt behandelt."""
    with patch.object(server.requests.Session, 'get',
                      side_effect=server.requests.ConnectionError):
        result = server._fetch_single_module('puppetlabs-stdlib', '9.7.0')

    assert result['status'] == 'error'
    assert result['error'] == 'Verbindungsfehler'


def test_fetch_single_module_url_format():
    """Modul-URL wird korrekt formatiert (- zu /)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '1.0.0'},
        'deprecated_at': None
    }

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('puppetlabs-stdlib', '1.0.0')

    assert result['url'] == 'https://forge.puppet.com/modules/puppetlabs/stdlib'


# ============================================================================
# UNIT TESTS - _fetch_single_provider
# ============================================================================

def test_fetch_single_provider_current():
    """Provider wird als 'current' erkannt bei gleicher Version."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': '3.7.2'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert result['status'] == 'current'
    assert result['displayName'] == 'random'
    assert result['namespace'] == 'hashicorp'


def test_fetch_single_provider_outdated():
    """Provider wird als 'outdated' erkannt bei Versionsunterschied."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': '4.0.0'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert result['status'] == 'outdated'
    assert result['latestVersion'] == '4.0.0'


def test_fetch_single_provider_invalid_name():
    """Ungültiger Provider-Name gibt Error-Status zurück."""
    result = server._fetch_single_provider('invalid-no-slash', '1.0.0')
    assert result['status'] == 'error'
    assert 'Ungültiger Provider-Name' in result['error']


def test_fetch_single_provider_strips_v_prefix():
    """Version mit 'v'-Prefix wird korrekt verglichen."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': 'v3.7.2'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', 'v3.7.2')

    assert result['status'] == 'current'


def test_fetch_single_provider_timeout():
    """Timeout wird als Error-Status zurückgegeben."""
    with patch.object(server.requests.Session, 'get', side_effect=server.requests.Timeout):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert result['status'] == 'error'
    assert result['error'] == 'Timeout'


def test_fetch_single_provider_with_metadata():
    """Provider-Metadaten (description, source, publishedAt) werden übernommen."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'version': '3.7.2',
        'description': 'Random provider',
        'source': 'https://github.com/hashicorp/terraform-provider-random',
        'published_at': '2024-01-15T00:00:00Z'
    }

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert result['description'] == 'Random provider'
    assert result['source'] == 'https://github.com/hashicorp/terraform-provider-random'
    assert result['publishedAt'] == '2024-01-15T00:00:00Z'


def test_fetch_single_provider_connection_error():
    """Verbindungsfehler wird korrekt behandelt."""
    with patch.object(server.requests.Session, 'get',
                      side_effect=server.requests.ConnectionError):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert result['status'] == 'error'
    assert result['error'] == 'Verbindungsfehler'


# ============================================================================
# UNIT TESTS - Connection Pooling (autoresearch-Pattern)
# ============================================================================

def test_get_http_session_returns_session():
    """_get_http_session gibt eine requests.Session zurück."""
    session = server._get_http_session()
    assert isinstance(session, server.requests.Session)
    assert session.headers.get('User-Agent') == 'Version-Checker/2.0'


def test_get_http_session_reuses_session():
    """Gleicher Thread bekommt die gleiche Session (Connection Pooling)."""
    session1 = server._get_http_session()
    session2 = server._get_http_session()
    assert session1 is session2


def test_get_http_session_has_retry_adapter():
    """Session hat HTTPAdapter mit Retry-Strategie."""
    session = server._get_http_session()
    adapter = session.get_adapter('https://example.com')
    assert isinstance(adapter, server.HTTPAdapter)
    assert adapter.max_retries.total == 3
    assert 429 in adapter.max_retries.status_forcelist
    assert 503 in adapter.max_retries.status_forcelist


# ============================================================================
# UNIT TESTS - fetch_all_data (autoresearch-Pattern: paralleler Fetch)
# ============================================================================

def test_fetch_all_data_returns_both(mock_versions):
    """fetch_all_data gibt modules und providers zurück."""
    mock_module = MagicMock()
    mock_module.status_code = 200
    mock_module.json.return_value = {
        'current_release': {'version': '9.7.0'},
        'deprecated_at': None
    }
    mock_provider = MagicMock()
    mock_provider.status_code = 200
    mock_provider.json.return_value = {'version': '3.7.2'}

    with patch.object(server, 'load_versions', return_value=mock_versions), \
         patch.object(server.requests.Session, 'get',
                      side_effect=[mock_module, mock_provider]):
        result = server.fetch_all_data()

    assert 'modules' in result
    assert 'providers' in result
    assert len(result['modules']) == 1
    assert len(result['providers']) == 1


def test_fetch_all_data_empty_versions():
    """fetch_all_data mit leeren Versionen gibt leere Listen zurück."""
    with patch.object(server, 'load_versions',
                      return_value={"puppet_modules": {}, "terraform_providers": {}}):
        result = server.fetch_all_data()

    assert result == {'modules': [], 'providers': []}


# ============================================================================
# INTEGRATION TESTS - API ROUTES
# ============================================================================

def test_api_modules_returns_json(client):
    """GET /api/modules gibt JSON zurück."""
    with patch.object(server, 'fetch_modules_data', return_value=[]):
        res = client.get('/api/modules')
    assert res.status_code == 200
    assert res.content_type == 'application/json'


def test_api_terraform_providers_returns_json(client):
    """GET /api/terraform-providers gibt JSON zurück."""
    with patch.object(server, 'fetch_terraform_data', return_value=[]):
        res = client.get('/api/terraform-providers')
    assert res.status_code == 200
    assert res.content_type == 'application/json'


def test_api_system_status_returns_all_fields(client):
    """GET /api/system_status enthält puppet, terraform und timestamp."""
    with patch.object(server, 'fetch_all_data',
                      return_value={'modules': [], 'providers': []}):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert 'puppet' in data
    assert 'terraform' in data
    assert 'timestamp' in data
    assert data['puppet']['status'] == 'OK'
    assert data['terraform']['status'] == 'OK'


def test_api_system_status_detects_outdated(client):
    """System-Status erkennt outdated Module korrekt."""
    mock_data = {
        'modules': [
            {'status': 'current', 'deprecated': False},
            {'status': 'outdated', 'deprecated': False},
        ],
        'providers': []
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['puppet']['status'] == 'Info'
    assert '1 Updates' in data['puppet']['details']


def test_api_system_status_detects_deprecated(client):
    """System-Status priorisiert deprecated über outdated."""
    mock_data = {
        'modules': [
            {'status': 'outdated', 'deprecated': True},
            {'status': 'outdated', 'deprecated': False},
        ],
        'providers': []
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['puppet']['status'] == 'Warnung'


def test_api_system_status_detects_terraform_errors(client):
    """System-Status erkennt Terraform-Provider Fehler."""
    mock_data = {
        'modules': [],
        'providers': [
            {'status': 'current'},
            {'status': 'error'},
        ]
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['terraform']['status'] == 'Warnung'
    assert '1 Provider mit Fehlern' in data['terraform']['details']


def test_api_system_status_detects_terraform_outdated(client):
    """System-Status erkennt Terraform-Provider Updates."""
    mock_data = {
        'modules': [],
        'providers': [
            {'status': 'current'},
            {'status': 'outdated'},
        ]
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['terraform']['status'] == 'Info'
    assert '1 Updates' in data['terraform']['details']


def test_api_system_status_error_handling(client):
    """System-Status gibt Error-Status bei Ausnahme zurück."""
    with patch.object(server, 'fetch_all_data', side_effect=Exception('test')):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['puppet']['status'] == 'Error'
    assert data['terraform']['status'] == 'Error'


def test_api_versions_returns_json(client):
    """GET /api/versions gibt die versions.json-Daten zurück."""
    res = client.get('/api/versions')
    assert res.status_code == 200
    data = res.get_json()
    assert 'puppet_modules' in data
    assert 'terraform_providers' in data


def test_api_modules_error_returns_500(client):
    """API gibt 500 zurück bei internem Fehler."""
    with patch.object(server, 'fetch_modules_data', side_effect=Exception('test')):
        res = client.get('/api/modules')
    assert res.status_code == 500
    assert 'error' in res.get_json()


def test_api_terraform_error_returns_500(client):
    """API gibt 500 zurück bei internem Terraform-Fehler."""
    with patch.object(server, 'fetch_terraform_data', side_effect=Exception('test')):
        res = client.get('/api/terraform-providers')
    assert res.status_code == 500
    assert 'error' in res.get_json()


# ============================================================================
# INTEGRATION TESTS - STATIC ROUTES
# ============================================================================

def test_serve_index(client):
    """GET / liefert index.html."""
    res = client.get('/')
    assert res.status_code == 200
    assert b'Version Tracker' in res.data


def test_serve_puppet_page(client):
    """GET /puppet.html liefert die Puppet-Seite."""
    res = client.get('/puppet.html')
    assert res.status_code == 200
    assert b'Puppet Module' in res.data


def test_serve_terraform_page(client):
    """GET /terraform.html liefert die Terraform-Seite."""
    res = client.get('/terraform.html')
    assert res.status_code == 200
    assert b'Terraform Provider' in res.data


def test_serve_unknown_path_returns_404(client):
    """Unbekannte Pfade liefern 404 statt 200."""
    res = client.get('/nonexistent-page')
    assert res.status_code == 404


def test_favicon_returns_svg(client):
    """GET /favicon.ico gibt SVG zurück."""
    res = client.get('/favicon.ico')
    assert res.status_code == 200
    assert 'svg' in res.content_type


# ============================================================================
# INTEGRATION TESTS - SECURITY HEADERS
# ============================================================================

def test_security_headers_present(client):
    """Alle Sicherheits-Header werden gesetzt."""
    res = client.get('/')
    assert res.headers.get('X-Content-Type-Options') == 'nosniff'
    assert res.headers.get('X-Frame-Options') == 'DENY'
    assert res.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    assert 'Content-Security-Policy' in res.headers


def test_csp_no_unsafe_inline(client):
    """CSP enthält kein unsafe-inline."""
    res = client.get('/')
    csp = res.headers.get('Content-Security-Policy', '')
    assert 'unsafe-inline' not in csp


def test_static_files_have_cache_headers(client):
    """Statische Dateien haben Cache-Control Header."""
    res = client.get('/styles/shared.css')
    assert 'max-age' in res.headers.get('Cache-Control', '')


def test_favicon_has_long_cache(client):
    """Favicon hat langen Cache-Header (1 Woche)."""
    res = client.get('/favicon.ico')
    assert '604800' in res.headers.get('Cache-Control', '')


# ============================================================================
# INTEGRATION TESTS - RESOURCE HINTS (autoresearch-Pattern)
# ============================================================================

def test_index_has_dns_prefetch(client):
    """Index-Seite enthält DNS-Prefetch für externe APIs."""
    res = client.get('/')
    assert b'dns-prefetch' in res.data
    assert b'forgeapi.puppet.com' in res.data
    assert b'registry.terraform.io' in res.data


def test_index_has_page_prefetch(client):
    """Index-Seite enthält Prefetch für Detail-Seiten."""
    res = client.get('/')
    assert b'prefetch' in res.data
    assert b'puppet.html' in res.data
    assert b'terraform.html' in res.data


def test_puppet_page_has_dns_prefetch(client):
    """Puppet-Seite enthält DNS-Prefetch für Forge API."""
    res = client.get('/puppet.html')
    assert b'dns-prefetch' in res.data
    assert b'forgeapi.puppet.com' in res.data


def test_terraform_page_has_dns_prefetch(client):
    """Terraform-Seite enthält DNS-Prefetch für Registry API."""
    res = client.get('/terraform.html')
    assert b'dns-prefetch' in res.data
    assert b'registry.terraform.io' in res.data


# ============================================================================
# UNIT TESTS - Worker Pool Configuration
# ============================================================================

def test_max_workers_is_ten():
    """Thread Pool hat 10 Worker (optimiert von 6)."""
    assert server._MAX_WORKERS == 10
