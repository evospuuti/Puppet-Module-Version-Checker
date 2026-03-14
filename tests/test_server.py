import json
import time
import threading
import pytest
from unittest.mock import patch, MagicMock, mock_open
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


@pytest.fixture
def multi_module_versions():
    """Versions mit mehreren Modulen und Providern."""
    return {
        "puppet_modules": {
            "puppetlabs-stdlib": "9.7.0",
            "puppetlabs-apt": "11.1.0",
            "puppet-archive": "8.1.0",
        },
        "terraform_providers": {
            "hashicorp/random": "3.7.2",
            "hashicorp/azurerm": "4.55.0",
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


def test_load_versions_contains_puppet_modules():
    """versions.json enthält Puppet Module."""
    result = server.load_versions()
    modules = result.get('puppet_modules', {})
    assert len(modules) > 0


def test_load_versions_contains_terraform_providers():
    """versions.json enthält Terraform Provider."""
    result = server.load_versions()
    providers = result.get('terraform_providers', {})
    assert len(providers) > 0


def test_load_versions_puppet_modules_have_versions():
    """Alle Puppet Module haben eine Versionsangabe."""
    result = server.load_versions()
    for name, version in result.get('puppet_modules', {}).items():
        assert isinstance(version, str), f"{name} hat keine String-Version"
        assert len(version) > 0, f"{name} hat leere Version"


def test_load_versions_terraform_providers_have_versions():
    """Alle Terraform Provider haben eine Versionsangabe."""
    result = server.load_versions()
    for name, version in result.get('terraform_providers', {}).items():
        assert isinstance(version, str), f"{name} hat keine String-Version"
        assert len(version) > 0, f"{name} hat leere Version"


def test_load_versions_terraform_providers_have_slash():
    """Alle Terraform Provider-Namen enthalten einen /."""
    result = server.load_versions()
    for name in result.get('terraform_providers', {}).keys():
        assert '/' in name, f"{name} hat kein / (namespace/name erwartet)"


def test_load_versions_meta_exists():
    """versions.json enthält _meta mit last_updated."""
    result = server.load_versions()
    assert '_meta' in result
    assert 'last_updated' in result['_meta']


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


def test_fetch_single_module_deprecated_and_outdated():
    """Deprecated + outdated: deprecated wird korrekt gesetzt."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '10.0.0'},
        'deprecated_at': '2024-01-01'
    }

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('old-module', '9.0.0')

    assert result['deprecated'] is True
    assert result['status'] == 'outdated'


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


def test_fetch_single_module_http_500():
    """HTTP 500 wird als Error-Status zurückgegeben."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('test-module', '1.0.0')

    assert result['status'] == 'error'
    assert 'HTTP 500' in result['error']


def test_fetch_single_module_http_429():
    """HTTP 429 Too Many Requests wird als Error behandelt."""
    mock_response = MagicMock()
    mock_response.status_code = 429

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('test-module', '1.0.0')

    assert result['status'] == 'error'
    assert 'HTTP 429' in result['error']


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


def test_fetch_single_module_preserves_name():
    """Modul-Name wird im Ergebnis beibehalten."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '1.0.0'},
        'deprecated_at': None
    }

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('puppet-archive', '8.1.0')

    assert result['name'] == 'puppet-archive'
    assert result['serverVersion'] == '8.1.0'


def test_fetch_single_module_missing_current_release():
    """Fehlende current_release führt zu unknown Status."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'deprecated_at': None}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('test-module', '1.0.0')

    assert result['status'] == 'unknown'
    assert result['forgeVersion'] == 'N/A'


def test_fetch_single_module_missing_version_in_release():
    """Fehlende version in current_release führt zu unknown Status."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {},
        'deprecated_at': None
    }

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_module('test-module', '1.0.0')

    assert result['status'] == 'unknown'


def test_fetch_single_module_unexpected_exception():
    """Unerwartete Exception wird als Error behandelt."""
    with patch.object(server.requests.Session, 'get', side_effect=ValueError('unexpected')):
        result = server._fetch_single_module('test-module', '1.0.0')

    assert result['status'] == 'error'
    assert result['error'] == 'Unerwarteter Fehler'


def test_fetch_single_module_default_values():
    """Default-Werte sind korrekt gesetzt vor dem API-Aufruf."""
    with patch.object(server.requests.Session, 'get', side_effect=server.requests.Timeout):
        result = server._fetch_single_module('test-mod', '2.0.0')

    assert result['name'] == 'test-mod'
    assert result['serverVersion'] == '2.0.0'
    assert result['deprecated'] is False


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


def test_fetch_single_provider_empty_name():
    """Leerer Provider-Name gibt Error-Status zurück."""
    result = server._fetch_single_provider('', '1.0.0')
    assert result['status'] == 'error'


def test_fetch_single_provider_too_many_slashes():
    """Provider-Name mit mehreren / gibt Error-Status zurück."""
    result = server._fetch_single_provider('a/b/c', '1.0.0')
    assert result['status'] == 'error'


def test_fetch_single_provider_strips_v_prefix():
    """Version mit 'v'-Prefix wird korrekt verglichen."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': 'v3.7.2'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', 'v3.7.2')

    assert result['status'] == 'current'


def test_fetch_single_provider_strips_v_prefix_installed_only():
    """v-Prefix nur bei installed, aber nicht bei latest."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': '3.7.2'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', 'v3.7.2')

    assert result['status'] == 'current'


def test_fetch_single_provider_strips_v_prefix_latest_only():
    """v-Prefix nur bei latest, aber nicht bei installed."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': 'v3.7.2'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

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


def test_fetch_single_provider_without_optional_metadata():
    """Provider ohne optionale Metadaten hat keine entsprechenden Keys."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': '3.7.2'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert 'description' not in result
    assert 'source' not in result
    assert 'publishedAt' not in result


def test_fetch_single_provider_connection_error():
    """Verbindungsfehler wird korrekt behandelt."""
    with patch.object(server.requests.Session, 'get',
                      side_effect=server.requests.ConnectionError):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert result['status'] == 'error'
    assert result['error'] == 'Verbindungsfehler'


def test_fetch_single_provider_http_500():
    """HTTP 500 wird als Error-Status zurückgegeben."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert result['status'] == 'error'
    assert 'HTTP 500' in result['error']


def test_fetch_single_provider_http_404():
    """HTTP 404 wird als Error-Status zurückgegeben."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/nonexistent', '1.0.0')

    assert result['status'] == 'error'
    assert 'HTTP 404' in result['error']


def test_fetch_single_provider_url_format():
    """Provider-URL wird korrekt formatiert."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': '1.0.0'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/azurerm', '1.0.0')

    assert result['url'] == 'https://registry.terraform.io/providers/hashicorp/azurerm'


def test_fetch_single_provider_preserves_installed_version():
    """Installed version wird im Ergebnis beibehalten."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'version': '1.0.0'}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', '3.7.2')

    assert result['installedVersion'] == '3.7.2'


def test_fetch_single_provider_missing_version_in_response():
    """Fehlende version im Response führt zu unknown Status."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}

    with patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server._fetch_single_provider('hashicorp/random', '1.0.0')

    assert result['status'] == 'unknown'
    assert result['latestVersion'] == 'N/A'


def test_fetch_single_provider_unexpected_exception():
    """Unerwartete Exception wird als Error behandelt."""
    with patch.object(server.requests.Session, 'get', side_effect=RuntimeError('oops')):
        result = server._fetch_single_provider('hashicorp/random', '1.0.0')

    assert result['status'] == 'error'
    assert result['error'] == 'Unerwarteter Fehler'


def test_fetch_single_provider_invalid_name_preserves_data():
    """Ungültiger Name: Felder werden korrekt befüllt."""
    result = server._fetch_single_provider('badname', '1.0.0')
    assert result['name'] == 'badname'
    assert result['displayName'] == 'badname'
    assert result['namespace'] == ''
    assert result['installedVersion'] == '1.0.0'
    assert result['url'] == ''


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


def test_get_http_session_retry_includes_500():
    """Retry umfasst HTTP 500."""
    session = server._get_http_session()
    adapter = session.get_adapter('https://example.com')
    assert 500 in adapter.max_retries.status_forcelist


def test_get_http_session_retry_includes_502():
    """Retry umfasst HTTP 502."""
    session = server._get_http_session()
    adapter = session.get_adapter('https://example.com')
    assert 502 in adapter.max_retries.status_forcelist


def test_get_http_session_retry_includes_504():
    """Retry umfasst HTTP 504."""
    session = server._get_http_session()
    adapter = session.get_adapter('https://example.com')
    assert 504 in adapter.max_retries.status_forcelist


def test_get_http_session_retry_only_get():
    """Retry nur für GET-Requests."""
    session = server._get_http_session()
    adapter = session.get_adapter('https://example.com')
    assert set(adapter.max_retries.allowed_methods) == {"GET"}


def test_get_http_session_has_http_adapter():
    """Session hat auch Adapter für http:// URLs."""
    session = server._get_http_session()
    adapter = session.get_adapter('http://example.com')
    assert isinstance(adapter, server.HTTPAdapter)


def test_get_http_session_pool_connections():
    """Session hat 20 Pool-Connections konfiguriert."""
    session = server._get_http_session()
    adapter = session.get_adapter('https://example.com')
    assert adapter._pool_connections == 20


def test_get_http_session_pool_maxsize():
    """Session hat Pool maxsize von 20."""
    session = server._get_http_session()
    adapter = session.get_adapter('https://example.com')
    assert adapter._pool_maxsize == 20


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


def test_fetch_all_data_multiple_items(multi_module_versions):
    """fetch_all_data mit mehreren Items."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '1.0.0'},
        'deprecated_at': None,
        'version': '1.0.0'
    }

    with patch.object(server, 'load_versions', return_value=multi_module_versions), \
         patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server.fetch_all_data()

    assert len(result['modules']) == 3
    assert len(result['providers']) == 2


def test_fetch_all_data_handles_mixed_errors(mock_versions):
    """fetch_all_data: Ein Fehler beeinflusst nicht die anderen."""
    mock_module = MagicMock()
    mock_module.status_code = 200
    mock_module.json.return_value = {
        'current_release': {'version': '9.7.0'},
        'deprecated_at': None
    }

    def side_effect(url, **kwargs):
        if 'forgeapi' in url:
            return mock_module
        raise server.requests.Timeout()

    with patch.object(server, 'load_versions', return_value=mock_versions), \
         patch.object(server.requests.Session, 'get', side_effect=side_effect):
        result = server.fetch_all_data()

    assert len(result['modules']) == 1
    assert len(result['providers']) == 1
    assert result['modules'][0]['status'] == 'current'
    assert result['providers'][0]['status'] == 'error'


# ============================================================================
# UNIT TESTS - Worker Pool Configuration
# ============================================================================

def test_max_workers_is_twenty():
    """Thread Pool hat 20 Worker für maximale Parallelisierung."""
    assert server._MAX_WORKERS == 20


# ============================================================================
# INTEGRATION TESTS - API ROUTES
# ============================================================================

def test_api_modules_returns_json(client):
    """GET /api/modules gibt JSON zurück."""
    with patch.object(server, 'fetch_modules_data', return_value=[]):
        res = client.get('/api/modules')
    assert res.status_code == 200
    assert res.content_type == 'application/json'


def test_api_modules_returns_list(client):
    """GET /api/modules gibt eine Liste zurück."""
    with patch.object(server, 'fetch_modules_data', return_value=[]):
        res = client.get('/api/modules')
    assert isinstance(res.get_json(), list)


def test_api_modules_with_data(client):
    """GET /api/modules gibt Modul-Daten zurück."""
    mock_data = [{'name': 'test', 'status': 'current', 'forgeVersion': '1.0.0',
                  'serverVersion': '1.0.0', 'deprecated': False,
                  'url': 'https://forge.puppet.com/modules/test'}]
    with patch.object(server, 'fetch_modules_data', return_value=mock_data):
        res = client.get('/api/modules')
    data = res.get_json()
    assert len(data) == 1
    assert data[0]['name'] == 'test'


def test_api_terraform_providers_returns_json(client):
    """GET /api/terraform-providers gibt JSON zurück."""
    with patch.object(server, 'fetch_terraform_data', return_value=[]):
        res = client.get('/api/terraform-providers')
    assert res.status_code == 200
    assert res.content_type == 'application/json'


def test_api_terraform_providers_returns_list(client):
    """GET /api/terraform-providers gibt eine Liste zurück."""
    with patch.object(server, 'fetch_terraform_data', return_value=[]):
        res = client.get('/api/terraform-providers')
    assert isinstance(res.get_json(), list)


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


def test_api_system_status_timestamp_format(client):
    """Timestamp hat Format YYYY-MM-DD HH:MM:SS."""
    with patch.object(server, 'fetch_all_data',
                      return_value={'modules': [], 'providers': []}):
        res = client.get('/api/system_status')
    data = res.get_json()
    # Prüfe Format: "2026-03-14 12:00:00"
    assert len(data['timestamp']) == 19
    assert data['timestamp'][4] == '-'
    assert data['timestamp'][10] == ' '


def test_api_system_status_puppet_has_status_and_details(client):
    """Puppet-Status enthält status und details."""
    with patch.object(server, 'fetch_all_data',
                      return_value={'modules': [], 'providers': []}):
        res = client.get('/api/system_status')
    data = res.get_json()
    assert 'status' in data['puppet']
    assert 'details' in data['puppet']


def test_api_system_status_terraform_has_status_and_details(client):
    """Terraform-Status enthält status und details."""
    with patch.object(server, 'fetch_all_data',
                      return_value={'modules': [], 'providers': []}):
        res = client.get('/api/system_status')
    data = res.get_json()
    assert 'status' in data['terraform']
    assert 'details' in data['terraform']


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


def test_api_system_status_detects_multiple_outdated(client):
    """System-Status zeigt korrekte Anzahl outdated Module."""
    mock_data = {
        'modules': [
            {'status': 'outdated', 'deprecated': False},
            {'status': 'outdated', 'deprecated': False},
            {'status': 'outdated', 'deprecated': False},
        ],
        'providers': []
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert '3 Updates' in data['puppet']['details']


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


def test_api_system_status_terraform_errors_prio_over_outdated(client):
    """Terraform: Fehler haben Priorität über outdated."""
    mock_data = {
        'modules': [],
        'providers': [
            {'status': 'error'},
            {'status': 'outdated'},
        ]
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['terraform']['status'] == 'Warnung'


def test_api_system_status_all_ok(client):
    """System-Status ist OK wenn alles aktuell."""
    mock_data = {
        'modules': [{'status': 'current', 'deprecated': False}],
        'providers': [{'status': 'current'}]
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['puppet']['status'] == 'OK'
    assert data['terraform']['status'] == 'OK'


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


def test_api_versions_contains_modules(client):
    """GET /api/versions enthält Puppet-Module."""
    res = client.get('/api/versions')
    data = res.get_json()
    assert len(data['puppet_modules']) > 0


def test_api_versions_contains_providers(client):
    """GET /api/versions enthält Terraform-Provider."""
    res = client.get('/api/versions')
    data = res.get_json()
    assert len(data['terraform_providers']) > 0


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


def test_api_modules_error_message(client):
    """Fehler-Response enthält deutsche Fehlermeldung."""
    with patch.object(server, 'fetch_modules_data', side_effect=Exception('test')):
        res = client.get('/api/modules')
    data = res.get_json()
    assert 'Serverfehler' in data['error']


def test_api_terraform_error_message(client):
    """Fehler-Response enthält deutsche Fehlermeldung."""
    with patch.object(server, 'fetch_terraform_data', side_effect=Exception('test')):
        res = client.get('/api/terraform-providers')
    data = res.get_json()
    assert 'Serverfehler' in data['error']


def test_api_modules_only_get_allowed(client):
    """POST auf /api/modules gibt 405 zurück."""
    with patch.object(server, 'fetch_modules_data', return_value=[]):
        res = client.post('/api/modules')
    assert res.status_code == 405


def test_api_terraform_only_get_allowed(client):
    """POST auf /api/terraform-providers gibt 405 zurück."""
    with patch.object(server, 'fetch_terraform_data', return_value=[]):
        res = client.post('/api/terraform-providers')
    assert res.status_code == 405


# ============================================================================
# INTEGRATION TESTS - STATIC ROUTES
# ============================================================================

def test_serve_index(client):
    """GET / liefert index.html."""
    res = client.get('/')
    assert res.status_code == 200
    assert b'Version Tracker' in res.data


def test_serve_index_explicit(client):
    """GET /index.html liefert index.html."""
    res = client.get('/index.html')
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


def test_serve_unknown_path_returns_html(client):
    """404 gibt dennoch HTML zurück (index.html als Fallback)."""
    res = client.get('/nonexistent-page')
    assert b'Version Tracker' in res.data


def test_favicon_returns_svg(client):
    """GET /favicon.ico gibt SVG zurück."""
    res = client.get('/favicon.ico')
    assert res.status_code == 200
    assert 'svg' in res.content_type


def test_favicon_contains_valid_svg(client):
    """Favicon enthält gültiges SVG-Markup."""
    res = client.get('/favicon.ico')
    assert b'<svg' in res.data
    assert b'</svg>' in res.data


def test_favicon_contains_v_letter(client):
    """Favicon enthält den Buchstaben V."""
    res = client.get('/favicon.ico')
    assert b'>V</text>' in res.data


def test_serve_css(client):
    """GET /styles/shared.css gibt CSS zurück."""
    res = client.get('/styles/shared.css')
    assert res.status_code == 200


def test_serve_js_shared(client):
    """GET /scripts/shared.js gibt JavaScript zurück."""
    res = client.get('/scripts/shared.js')
    assert res.status_code == 200


def test_serve_js_index(client):
    """GET /scripts/index.js gibt JavaScript zurück."""
    res = client.get('/scripts/index.js')
    assert res.status_code == 200


def test_serve_js_puppet(client):
    """GET /scripts/puppet.js gibt JavaScript zurück."""
    res = client.get('/scripts/puppet.js')
    assert res.status_code == 200


def test_serve_js_terraform(client):
    """GET /scripts/terraform.js gibt JavaScript zurück."""
    res = client.get('/scripts/terraform.js')
    assert res.status_code == 200


def test_serve_theme_init_js(client):
    """GET /scripts/theme-init.js gibt JavaScript zurück."""
    res = client.get('/scripts/theme-init.js')
    assert res.status_code == 200


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


def test_security_headers_on_api(client):
    """Sicherheits-Header auch auf API-Endpoints."""
    with patch.object(server, 'fetch_modules_data', return_value=[]):
        res = client.get('/api/modules')
    assert res.headers.get('X-Content-Type-Options') == 'nosniff'
    assert res.headers.get('X-Frame-Options') == 'DENY'


def test_permissions_policy(client):
    """Permissions-Policy blockiert Kamera, Mikrofon, Geolocation."""
    res = client.get('/')
    pp = res.headers.get('Permissions-Policy', '')
    assert 'camera=()' in pp
    assert 'microphone=()' in pp
    assert 'geolocation=()' in pp


def test_csp_no_unsafe_inline(client):
    """CSP enthält kein unsafe-inline."""
    res = client.get('/')
    csp = res.headers.get('Content-Security-Policy', '')
    assert 'unsafe-inline' not in csp


def test_csp_contains_default_src(client):
    """CSP enthält default-src 'self'."""
    res = client.get('/')
    csp = res.headers.get('Content-Security-Policy', '')
    assert "default-src 'self'" in csp


def test_csp_contains_script_src(client):
    """CSP enthält script-src 'self'."""
    res = client.get('/')
    csp = res.headers.get('Content-Security-Policy', '')
    assert "script-src 'self'" in csp


def test_csp_contains_frame_ancestors_none(client):
    """CSP enthält frame-ancestors 'none'."""
    res = client.get('/')
    csp = res.headers.get('Content-Security-Policy', '')
    assert "frame-ancestors 'none'" in csp


def test_static_files_have_cache_headers(client):
    """Statische Dateien haben Cache-Control Header."""
    res = client.get('/styles/shared.css')
    assert 'max-age' in res.headers.get('Cache-Control', '')


def test_js_files_have_cache_headers(client):
    """JS-Dateien haben Cache-Control Header."""
    res = client.get('/scripts/shared.js')
    assert 'max-age' in res.headers.get('Cache-Control', '')


def test_static_cache_is_one_day(client):
    """Statische Dateien cachen für 1 Tag (86400s)."""
    res = client.get('/styles/shared.css')
    assert '86400' in res.headers.get('Cache-Control', '')


def test_favicon_has_long_cache(client):
    """Favicon hat langen Cache-Header (1 Woche)."""
    res = client.get('/favicon.ico')
    assert '604800' in res.headers.get('Cache-Control', '')


def test_html_pages_no_explicit_cache(client):
    """HTML-Seiten haben keinen expliziten max-age Cache-Header."""
    res = client.get('/')
    cache = res.headers.get('Cache-Control', '')
    # HTML-Seiten sollten keinen langen Cache haben
    assert '86400' not in cache


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
# INTEGRATION TESTS - HTML CONTENT
# ============================================================================

def test_index_has_nav(client):
    """Index enthält Navigation."""
    res = client.get('/')
    assert b'nav' in res.data
    assert b'Dashboard' in res.data


def test_index_has_dashboard_stats(client):
    """Index enthält Dashboard-Stats."""
    res = client.get('/')
    assert b'puppetStatus' in res.data
    assert b'terraformStatus' in res.data


def test_index_has_card_links(client):
    """Index enthält Links zu Puppet und Terraform."""
    res = client.get('/')
    assert b'puppet.html' in res.data
    assert b'terraform.html' in res.data


def test_puppet_has_filter(client):
    """Puppet-Seite hat Filter-Input."""
    res = client.get('/puppet.html')
    assert b'filter' in res.data


def test_puppet_has_refresh_button(client):
    """Puppet-Seite hat Aktualisieren-Button."""
    res = client.get('/puppet.html')
    assert b'refreshBtn' in res.data


def test_puppet_has_sortable_headers(client):
    """Puppet-Seite hat sortierbare Tabellen-Header."""
    res = client.get('/puppet.html')
    assert b'sortable' in res.data


def test_terraform_has_filter(client):
    """Terraform-Seite hat Filter-Input."""
    res = client.get('/terraform.html')
    assert b'filter' in res.data


def test_terraform_has_sortable_headers(client):
    """Terraform-Seite hat sortierbare Tabellen-Header."""
    res = client.get('/terraform.html')
    assert b'sortable' in res.data


def test_all_pages_have_theme_toggle(client):
    """Alle Seiten haben Theme-Toggle Button."""
    for path in ['/', '/puppet.html', '/terraform.html']:
        res = client.get(path)
        assert b'themeToggle' in res.data, f"{path} hat keinen Theme-Toggle"


def test_all_pages_have_viewport_meta(client):
    """Alle Seiten haben Viewport-Meta-Tag."""
    for path in ['/', '/puppet.html', '/terraform.html']:
        res = client.get(path)
        assert b'viewport' in res.data, f"{path} hat kein Viewport-Meta"


def test_all_pages_load_shared_js(client):
    """Alle Seiten laden shared.js."""
    for path in ['/', '/puppet.html', '/terraform.html']:
        res = client.get(path)
        assert b'shared.js' in res.data, f"{path} lädt nicht shared.js"


def test_all_pages_load_shared_css(client):
    """Alle Seiten laden shared.css."""
    for path in ['/', '/puppet.html', '/terraform.html']:
        res = client.get(path)
        assert b'shared.css' in res.data, f"{path} lädt nicht shared.css"


def test_all_pages_load_theme_init(client):
    """Alle Seiten laden theme-init.js."""
    for path in ['/', '/puppet.html', '/terraform.html']:
        res = client.get(path)
        assert b'theme-init.js' in res.data, f"{path} lädt nicht theme-init.js"


# ============================================================================
# INTEGRATION TESTS - JS CONTENT (autoresearch Features)
# ============================================================================

def test_shared_js_has_debounce(client):
    """shared.js enthält debounce-Funktion."""
    res = client.get('/scripts/shared.js')
    assert b'debounce' in res.data


def test_shared_js_has_fetch_deduped(client):
    """shared.js enthält fetchDeduped-Funktion."""
    res = client.get('/scripts/shared.js')
    assert b'fetchDeduped' in res.data


def test_shared_js_has_prefetch_data(client):
    """shared.js enthält prefetchData-Funktion."""
    res = client.get('/scripts/shared.js')
    assert b'prefetchData' in res.data


def test_shared_js_has_escape_html(client):
    """shared.js enthält escapeHtml-Funktion."""
    res = client.get('/scripts/shared.js')
    assert b'escapeHtml' in res.data


def test_shared_js_has_toggle_dark_mode(client):
    """shared.js enthält toggleDarkMode-Funktion."""
    res = client.get('/scripts/shared.js')
    assert b'toggleDarkMode' in res.data


def test_index_js_has_prefetch_calls(client):
    """index.js ruft prefetchData auf."""
    res = client.get('/scripts/index.js')
    assert b'prefetchData' in res.data


def test_index_js_prefetches_api_endpoints(client):
    """index.js prefetcht die API-Endpoints."""
    res = client.get('/scripts/index.js')
    assert b'/api/modules' in res.data
    assert b'/api/terraform-providers' in res.data


def test_puppet_js_uses_debounced_filter(client):
    """puppet.js verwendet debouncedFilter."""
    res = client.get('/scripts/puppet.js')
    assert b'debouncedFilter' in res.data


def test_terraform_js_uses_debounced_filter(client):
    """terraform.js verwendet debouncedFilter."""
    res = client.get('/scripts/terraform.js')
    assert b'debouncedFilter' in res.data


def test_puppet_js_uses_document_fragment(client):
    """puppet.js verwendet DocumentFragment."""
    res = client.get('/scripts/puppet.js')
    assert b'createDocumentFragment' in res.data


def test_terraform_js_uses_document_fragment(client):
    """terraform.js verwendet DocumentFragment."""
    res = client.get('/scripts/terraform.js')
    assert b'createDocumentFragment' in res.data


def test_puppet_js_uses_fetch_swr_not_raw_fetch(client):
    """puppet.js nutzt fetchSWR statt direktem fetch."""
    res = client.get('/scripts/puppet.js')
    assert b'fetchSWR' in res.data


def test_terraform_js_uses_fetch_swr_not_raw_fetch(client):
    """terraform.js nutzt fetchSWR statt direktem fetch."""
    res = client.get('/scripts/terraform.js')
    assert b'fetchSWR' in res.data


# ============================================================================
# INTEGRATION TESTS - CSS CONTENT
# ============================================================================

def test_css_has_dark_mode(client):
    """CSS enthält Dark-Mode Variablen."""
    res = client.get('/styles/shared.css')
    assert b'.dark' in res.data


def test_css_has_contain_on_nav(client):
    """CSS hat contain-Property auf Navigation."""
    res = client.get('/styles/shared.css')
    assert b'contain: layout style' in res.data


def test_css_has_will_change_on_spinner(client):
    """CSS hat will-change auf Spinner."""
    res = client.get('/styles/shared.css')
    assert b'will-change: transform' in res.data


def test_css_has_responsive_breakpoint(client):
    """CSS hat responsive Breakpoint."""
    res = client.get('/styles/shared.css')
    assert b'768px' in res.data


def test_css_has_color_scheme(client):
    """CSS hat color-scheme für Light und Dark."""
    res = client.get('/styles/shared.css')
    assert b'color-scheme: light' in res.data
    assert b'color-scheme: dark' in res.data


# ============================================================================
# UNIT TESTS - KNOWN PAGES
# ============================================================================

def test_known_pages_set():
    """_KNOWN_PAGES enthält alle erwarteten Seiten."""
    assert '' in server._KNOWN_PAGES
    assert 'index.html' in server._KNOWN_PAGES
    assert 'puppet.html' in server._KNOWN_PAGES
    assert 'terraform.html' in server._KNOWN_PAGES


def test_known_pages_count():
    """_KNOWN_PAGES hat genau 4 Einträge."""
    assert len(server._KNOWN_PAGES) == 4


# ============================================================================
# INTEGRATION TESTS - STALE-WHILE-REVALIDATE (spürbare Performance)
# ============================================================================

def test_shared_js_has_fetch_swr(client):
    """shared.js enthält fetchSWR-Funktion."""
    res = client.get('/scripts/shared.js')
    assert b'fetchSWR' in res.data


def test_shared_js_has_cache_functions(client):
    """shared.js enthält Cache-Funktionen (_getCache, _setCache)."""
    res = client.get('/scripts/shared.js')
    assert b'_getCache' in res.data
    assert b'_setCache' in res.data


def test_shared_js_has_stale_check(client):
    """shared.js enthält _isCacheStale-Funktion."""
    res = client.get('/scripts/shared.js')
    assert b'_isCacheStale' in res.data


def test_shared_js_swr_uses_localstorage(client):
    """shared.js SWR nutzt localStorage."""
    res = client.get('/scripts/shared.js')
    assert b'localStorage' in res.data


def test_shared_js_swr_has_max_age(client):
    """shared.js SWR hat konfigurierbare Cache-Dauer."""
    res = client.get('/scripts/shared.js')
    assert b'_CACHE_MAX_AGE_MS' in res.data


def test_index_js_uses_fetch_swr(client):
    """index.js verwendet fetchSWR statt direktem fetch."""
    res = client.get('/scripts/index.js')
    assert b'fetchSWR' in res.data


def test_puppet_js_uses_fetch_swr(client):
    """puppet.js verwendet fetchSWR."""
    res = client.get('/scripts/puppet.js')
    assert b'fetchSWR' in res.data


def test_terraform_js_uses_fetch_swr(client):
    """terraform.js verwendet fetchSWR."""
    res = client.get('/scripts/terraform.js')
    assert b'fetchSWR' in res.data


def test_puppet_js_refresh_clears_cache(client):
    """puppet.js löscht Cache bei manuellem Refresh."""
    res = client.get('/scripts/puppet.js')
    assert b'removeItem' in res.data


def test_terraform_js_refresh_clears_cache(client):
    """terraform.js löscht Cache bei manuellem Refresh."""
    res = client.get('/scripts/terraform.js')
    assert b'removeItem' in res.data


# ============================================================================
# INTEGRATION TESTS - SKELETON LOADING (spürbare Performance)
# ============================================================================

def test_shared_js_has_create_skeleton_rows(client):
    """shared.js enthält createSkeletonRows-Funktion."""
    res = client.get('/scripts/shared.js')
    assert b'createSkeletonRows' in res.data


def test_shared_js_skeleton_creates_fragment(client):
    """shared.js Skeleton nutzt DocumentFragment."""
    res = client.get('/scripts/shared.js')
    # createSkeletonRows sollte createDocumentFragment nutzen
    data = res.data.decode()
    assert 'createDocumentFragment' in data


def test_shared_js_skeleton_uses_skeleton_line_class(client):
    """shared.js Skeleton nutzt skeleton-line CSS-Klasse."""
    res = client.get('/scripts/shared.js')
    assert b'skeleton-line' in res.data


def test_css_has_skeleton_styles(client):
    """CSS enthält Skeleton-Loading Styles."""
    res = client.get('/styles/shared.css')
    assert b'skeleton-line' in res.data
    assert b'skeleton-shimmer' in res.data


def test_css_skeleton_has_animation(client):
    """CSS Skeleton hat shimmer-Animation."""
    res = client.get('/styles/shared.css')
    assert b'@keyframes skeleton-shimmer' in res.data


def test_css_has_stale_indicator(client):
    """CSS enthält Stale-Indikator Styles."""
    res = client.get('/styles/shared.css')
    assert b'stale-indicator' in res.data
    assert b'stale-dot' in res.data


def test_css_stale_dot_has_pulse_animation(client):
    """CSS Stale-Dot hat Pulse-Animation."""
    res = client.get('/styles/shared.css')
    assert b'stale-pulse' in res.data


def test_index_js_uses_skeleton(client):
    """index.js nutzt createSkeletonRows für Loading-State."""
    res = client.get('/scripts/index.js')
    assert b'createSkeletonRows' in res.data


def test_puppet_js_uses_skeleton(client):
    """puppet.js nutzt createSkeletonRows für Loading-State."""
    res = client.get('/scripts/puppet.js')
    assert b'createSkeletonRows' in res.data


def test_terraform_js_uses_skeleton(client):
    """terraform.js nutzt createSkeletonRows für Loading-State."""
    res = client.get('/scripts/terraform.js')
    assert b'createSkeletonRows' in res.data


def test_index_js_shows_stale_indicator(client):
    """index.js zeigt Stale-Indikator bei gecachten Daten."""
    res = client.get('/scripts/index.js')
    assert b'stale-indicator' in res.data


def test_puppet_js_shows_stale_indicator(client):
    """puppet.js zeigt Stale-Indikator bei gecachten Daten."""
    res = client.get('/scripts/puppet.js')
    assert b'stale-indicator' in res.data


def test_terraform_js_shows_stale_indicator(client):
    """terraform.js zeigt Stale-Indikator bei gecachten Daten."""
    res = client.get('/scripts/terraform.js')
    assert b'stale-indicator' in res.data
