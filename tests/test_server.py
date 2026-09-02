import json
import time
import threading
import pytest
from unittest.mock import patch, MagicMock, mock_open
import server


@pytest.fixture(autouse=True)
def reset_versions_cache():
    """Reset the in-memory versions/inventory caches before each test."""
    server._versions_cache = None
    server._inventory_cache = None
    yield
    server._versions_cache = None
    server._inventory_cache = None


@pytest.fixture(autouse=True)
def reset_flask_cache():
    """Reset Flask-Caching before each test."""
    server.cache.clear()


@pytest.fixture(autouse=True)
def disable_rate_limiter():
    """In-Memory Rate-Limiter zählt über die Test-Suite hinweg und
    würde nach 30/60 Requests 429 liefern - für Tests deaktivieren."""
    server.limiter.enabled = False
    yield
    server.limiter.enabled = True


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
        }
    }


def _item(**overrides):
    """Baut einen minimalen Inventar-Eintrag fuer Tests."""
    base = {
        'id': 'test-item', 'kategorie': 'toolchain', 'artefakt': 'Test',
        'repo': ['Core'], 'ist': '1.0.0', 'art': 'pin',
        'fundorte': ['a.tf:1'],
        'quelle': {'typ': 'github-release', 'ref': 'foo/bar'},
    }
    base.update(overrides)
    return base


@pytest.fixture
def mock_inventory():
    """Minimales AVD-Inventar fuer Tests."""
    return {
        '_meta': {'stand': '2026-08-15'},
        'kategorien': [{'key': 'toolchain', 'titel': 'Toolchain & IaC'}],
        'items': [
            _item(id='a'),
            _item(id='b', art='intern', quelle={'typ': 'intern'}),
        ],
        'kontrakte': [{'name': 'K', 'beteiligte': 'x', 'pruefung': 'y'}],
        'termine': [{'datum': '2026-08-22', 'ereignis': 'E', 'status': 's'}],
        'hinweise': ['H'],
    }


@pytest.fixture
def multi_module_versions():
    """Versions mit mehreren Modulen und AVD-Komponenten."""
    return {
        "puppet_modules": {
            "puppetlabs-stdlib": "9.7.0",
            "puppetlabs-apt": "11.1.0",
            "puppet-archive": "8.1.0",
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
    assert 'github_releases' in result


def test_load_versions_caches_result():
    """Zweiter Aufruf verwendet den In-Memory-Cache."""
    result1 = server.load_versions()
    result2 = server.load_versions()
    assert result1 is result2


def test_load_versions_file_not_found():
    """Gibt leere Defaults zurück wenn versions.json fehlt."""
    with patch('builtins.open', side_effect=FileNotFoundError):
        result = server.load_versions()
    assert result == {"puppet_modules": {}, "github_releases": {}}


def test_load_versions_invalid_json():
    """Gibt leere Defaults zurück bei ungültigem JSON."""
    with patch('builtins.open', side_effect=json.JSONDecodeError("err", "", 0)):
        result = server.load_versions()
    assert result == {"puppet_modules": {}, "github_releases": {}}


def test_load_versions_contains_puppet_modules():
    """versions.json enthält Puppet Module."""
    result = server.load_versions()
    modules = result.get('puppet_modules', {})
    assert len(modules) > 0





def test_load_versions_puppet_modules_have_versions():
    """Alle Puppet Module haben eine Versionsangabe."""
    result = server.load_versions()
    for name, version in result.get('puppet_modules', {}).items():
        assert isinstance(version, str), f"{name} hat keine String-Version"
        assert len(version) > 0, f"{name} hat leere Version"


def test_load_avd_inventory_returns_dict():
    """avd_inventory.json wird korrekt geladen."""
    result = server.load_avd_inventory()
    assert isinstance(result, dict)
    assert len(result.get('items', [])) > 0
    assert len(result.get('kategorien', [])) > 0


def test_load_avd_inventory_caches_result():
    """Zweiter Aufruf verwendet den In-Memory-Cache."""
    assert server.load_avd_inventory() is server.load_avd_inventory()


def test_load_avd_inventory_file_not_found():
    """Gibt leere Defaults zurück wenn avd_inventory.json fehlt."""
    with patch('builtins.open', side_effect=FileNotFoundError):
        result = server.load_avd_inventory()
    assert result['items'] == []
    assert result['kategorien'] == []


def test_load_avd_inventory_items_valid():
    """Alle Inventar-Eintraege haben id, kategorie, art und gueltigen Quelltyp."""
    inventory = server.load_avd_inventory()
    valid_arts = {'pin', 'lock', 'constraint', 'floating', 'intern'}
    valid_types = server._AUTO_SOURCE_TYPES | {'azure-cli', 'ms-learn', 'vendor-manuell', 'intern'}
    kategorie_keys = {k['key'] for k in inventory['kategorien']}
    ids = set()
    for item in inventory['items']:
        assert item.get('id'), 'Eintrag ohne id'
        assert item['id'] not in ids, f"Doppelte id: {item['id']}"
        ids.add(item['id'])
        assert item.get('kategorie') in kategorie_keys, f"{item['id']}: unbekannte Kategorie"
        assert item.get('art') in valid_arts, f"{item['id']}: ungueltige art"
        assert item.get('quelle', {}).get('typ') in valid_types, f"{item['id']}: ungueltiger Quelltyp"


def test_load_avd_inventory_auto_sources_have_ref():
    """Automatisch pollbare Quellen brauchen eine ref."""
    inventory = server.load_avd_inventory()
    for item in inventory['items']:
        quelle = item.get('quelle', {})
        if quelle.get('typ') in server._AUTO_SOURCE_TYPES:
            assert quelle.get('ref'), f"{item['id']}: Quelle ohne ref"


def test_load_versions_meta_exists():
    """versions.json enthält _meta mit last_updated."""
    result = server.load_versions()
    assert '_meta' in result
    assert 'last_updated' in result['_meta']


def test_load_versions_contains_github_releases():
    """versions.json enthält GitHub-Releases."""
    result = server.load_versions()
    assert len(result.get('github_releases', {})) > 0


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
# UNIT TESTS - Versionsvergleich & Constraints
# ============================================================================

def test_extract_version():
    """Versionsnummern werden aus Freitext extrahiert."""
    assert server._extract_version('v1.2.3') == '1.2.3'
    assert server._extract_version('Lock 4.81.0 (constraint ~> 4.66)') == '4.81.0'
    assert server._extract_version('kein Wert') is None
    assert server._extract_version(None) is None


def test_compare_versions():
    """Numerischer Segmentvergleich."""
    assert server._compare_versions('1.2.3', '1.2.3') == 0
    assert server._compare_versions('1.10.0', '1.9.9') == 1
    assert server._compare_versions('1.2', '1.2.1') == -1


def test_satisfies_constraint_range():
    """Range-Constraints mit >=, != und <."""
    c = '>= 1.14.0, != 1.15.0, < 2.0.0'
    assert server._satisfies_constraint('1.14.8', c) is True
    assert server._satisfies_constraint('1.15.0', c) is False
    assert server._satisfies_constraint('2.0.0', c) is False
    assert server._satisfies_constraint('1.13.9', c) is False


def test_satisfies_constraint_pessimistic():
    """Pessimistischer Operator ~> (Terraform-Semantik)."""
    assert server._satisfies_constraint('0.17.4', '~> 0.17.0') is True
    assert server._satisfies_constraint('0.18.0', '~> 0.17.0') is False
    assert server._satisfies_constraint('4.99.0', '~> 4.66') is True
    assert server._satisfies_constraint('5.0.0', '~> 4.66') is False


def test_satisfies_constraint_unparseable():
    """Nicht auswertbare Constraints geben None zurueck."""
    assert server._satisfies_constraint('1.0.0', 'irgendwas') is None


# ============================================================================
# UNIT TESTS - _check_inventory_item
# ============================================================================

def _response(status_code=200, json_data=None, text=''):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data if json_data is not None else {}
    m.text = text
    return m


def test_check_item_pin_current():
    """Pin: gleiche Version wie Latest -> current."""
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'tag_name': 'v1.0.0'})):
        result = server._check_inventory_item(_item())
    assert result['status'] == 'current'
    assert result['latest'] == '1.0.0'


def test_check_item_pin_outdated():
    """Pin: neuere Version verfuegbar -> outdated."""
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'tag_name': 'v2.0.0'})):
        result = server._check_inventory_item(_item())
    assert result['status'] == 'outdated'
    assert result['latest'] == '2.0.0'


def test_check_item_pin_outdated_suppressed():
    """Pin mit Suppression: outdated wird zu suppressed."""
    item = _item(suppression={'grund': 'bewusster Pin', 'trigger': 'Review'})
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'tag_name': 'v2.0.0'})):
        result = server._check_inventory_item(item)
    assert result['status'] == 'suppressed'
    assert result['suppression']['grund'] == 'bewusster Pin'


def test_check_item_lock_tf_registry():
    """Lock gegen Terraform Registry."""
    item = _item(art='lock', ist='4.81.0',
                 quelle={'typ': 'tf-registry', 'ref': 'hashicorp/azurerm'})
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'version': '4.81.0'})):
        result = server._check_inventory_item(item)
    assert result['status'] == 'current'
    assert result['latest'] == '4.81.0'


def test_check_item_constraint_satisfied():
    """Constraint: Latest innerhalb der Range -> current."""
    item = _item(art='constraint', ist='0.17.x', constraint='~> 0.17.0')
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'tag_name': 'v0.17.5'})):
        result = server._check_inventory_item(item)
    assert result['status'] == 'current'


def test_check_item_constraint_violated():
    """Constraint: Latest ausserhalb der Range -> outdated."""
    item = _item(art='constraint', ist='0.17.x', constraint='~> 0.17.0')
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'tag_name': 'v0.19.0'})):
        result = server._check_inventory_item(item)
    assert result['status'] == 'outdated'


def test_check_item_constraint_violated_suppressed():
    """Constraint + Suppression: outdated wird zu suppressed."""
    item = _item(art='constraint', ist='0.17.x', constraint='~> 0.17.0',
                 suppression={'grund': 'Issue #166', 'trigger': 'Fix-Release'})
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'tag_name': 'v0.19.0'})):
        result = server._check_inventory_item(item)
    assert result['status'] == 'suppressed'


def test_check_item_commit_pin():
    """Commit-Pin: Prefix-Vergleich gegen den neuesten Commit."""
    item = _item(ist='10a904c0',
                 quelle={'typ': 'github-commit', 'ref': 'Azure/RDS-Templates',
                         'path': 'ARM-wvd-templates/DSC'})
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data=[{'sha': '10a904c0ffffffff'}])):
        result = server._check_inventory_item(item)
    assert result['status'] == 'current'

    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data=[{'sha': 'deadbeef00000000'}])):
        result = server._check_inventory_item(item)
    assert result['status'] == 'outdated'


def test_check_item_hashicorp_checkpoint():
    """HashiCorp Checkpoint liefert current_version."""
    item = _item(art='constraint', constraint='>= 1.14.0, < 2.0.0',
                 quelle={'typ': 'hashicorp-checkpoint', 'ref': 'terraform'})
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'current_version': '1.16.2'})):
        result = server._check_inventory_item(item)
    assert result['status'] == 'current'
    assert result['latest'] == '1.16.2'


def test_check_item_choco():
    """Chocolatey-OData wird per Regex geparst."""
    item = _item(ist='2026.2.14', quelle={'typ': 'choco', 'ref': 'testpkg'})
    xml = '<feed><d:Version m:type="Edm.String">2026.2.20</d:Version></feed>'
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(text=xml)):
        result = server._check_inventory_item(item)
    assert result['latest'] == '2026.2.20'
    assert result['status'] == 'outdated'


def test_check_item_psgallery():
    """PowerShell-Gallery-OData wird per Regex geparst."""
    item = _item(ist='1.25.0', quelle={'typ': 'psgallery', 'ref': 'PSScriptAnalyzer'})
    xml = '<feed><d:Version>1.25.0</d:Version></feed>'
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(text=xml)):
        result = server._check_inventory_item(item)
    assert result['status'] == 'current'


def test_check_item_chrome_floating():
    """Chrome-Versionhistory: floating zeigt nur das Latest."""
    item = _item(art='floating', ist='je Build neu',
                 quelle={'typ': 'chrome-versionhistory', 'ref': 'win64/stable'})
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'versions': [{'version': '139.0.1'}]})):
        result = server._check_inventory_item(item)
    assert result['status'] == 'floating'
    assert result['latest'] == '139.0.1'


def test_check_item_pin_without_version_is_floating():
    """Pin ohne extrahierbare Ist-Version faellt auf floating zurueck."""
    item = _item(ist=None)
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'tag_name': 'v1.0.0'})):
        result = server._check_inventory_item(item)
    assert result['status'] == 'floating'


def test_check_item_intern_no_http():
    """Interne Eintraege machen keinen HTTP-Call."""
    item = _item(art='intern', quelle={'typ': 'intern'})
    with patch.object(server.requests.Session, 'get',
                      side_effect=AssertionError('kein HTTP erwartet')):
        result = server._check_inventory_item(item)
    assert result['status'] == 'intern'


def test_check_item_azure_no_http():
    """azure-cli-Quellen brauchen Auth -> Status azure, kein HTTP-Call."""
    item = _item(quelle={'typ': 'azure-cli', 'ref': 'az vm image show'})
    with patch.object(server.requests.Session, 'get',
                      side_effect=AssertionError('kein HTTP erwartet')):
        result = server._check_inventory_item(item)
    assert result['status'] == 'azure'


def test_check_item_manual_uses_known_latest():
    """Manuelle Quellen zeigen known_latest als Latest."""
    item = _item(quelle={'typ': 'ms-learn'}, known_latest='26.01 CU1')
    result = server._check_inventory_item(item)
    assert result['status'] == 'manual'
    assert result['latest'] == '26.01 CU1'


def test_check_item_unknown_source_is_manual():
    """Unbekannte Quelltypen werden als manuell behandelt."""
    result = server._check_inventory_item(_item(quelle={'typ': 'foo'}))
    assert result['status'] == 'manual'


def test_check_item_http_error():
    """HTTP-Fehler wird als Error-Status zurueckgegeben."""
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(status_code=404)):
        result = server._check_inventory_item(_item())
    assert result['status'] == 'error'
    assert 'HTTP 404' in result['error']


def test_check_item_timeout():
    """Timeout wird als Error-Status zurueckgegeben."""
    with patch.object(server.requests.Session, 'get',
                      side_effect=server.requests.Timeout):
        result = server._check_inventory_item(_item())
    assert result['status'] == 'error'
    assert result['error'] == 'Timeout'


def test_check_item_connection_error():
    """Verbindungsfehler wird korrekt behandelt."""
    with patch.object(server.requests.Session, 'get',
                      side_effect=server.requests.ConnectionError):
        result = server._check_inventory_item(_item())
    assert result['status'] == 'error'
    assert result['error'] == 'Verbindungsfehler'


def test_check_item_unexpected_exception():
    """Unerwartete Exception wird als Error behandelt."""
    with patch.object(server.requests.Session, 'get',
                      side_effect=RuntimeError('oops')):
        result = server._check_inventory_item(_item())
    assert result['status'] == 'error'
    assert result['error'] == 'Unerwarteter Fehler'


def test_check_item_preserves_fields():
    """Alle Felder werden korrekt ins Ergebnis uebernommen."""
    item = _item(id='x', artefakt='Artefakt X', repo=['Core', 'Packer'],
                 artLabel='Hash-Pin', link='https://example.com',
                 note='Notiz', fundorte=['f.tf:1', 'g.ps1:2'])
    with patch.object(server.requests.Session, 'get',
                      return_value=_response(json_data={'tag_name': 'v1.0.0'})):
        result = server._check_inventory_item(item)
    assert result['id'] == 'x'
    assert result['artefakt'] == 'Artefakt X'
    assert result['repo'] == ['Core', 'Packer']
    assert result['artLabel'] == 'Hash-Pin'
    assert result['link'] == 'https://example.com'
    assert result['note'] == 'Notiz'
    assert result['fundorte'] == ['f.tf:1', 'g.ps1:2']


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
    assert adapter.max_retries.total == 1
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

def test_fetch_all_data_returns_both(mock_versions, mock_inventory):
    """fetch_all_data gibt modules und das AVD-Inventar zurück."""
    mock_module = MagicMock()
    mock_module.status_code = 200
    mock_module.json.return_value = {
        'current_release': {'version': '9.7.0'},
        'deprecated_at': None,
        'tag_name': 'v1.0.0'
    }

    with patch.object(server, 'load_versions', return_value=mock_versions), \
         patch.object(server, 'load_avd_inventory', return_value=mock_inventory), \
         patch.object(server.requests.Session, 'get', return_value=mock_module):
        result = server.fetch_all_data()

    assert 'modules' in result
    assert 'avd' in result
    assert len(result['modules']) == 1
    assert len(result['avd']['items']) == 2
    assert result['avd']['kontrakte'] == mock_inventory['kontrakte']
    assert result['avd']['termine'] == mock_inventory['termine']
    assert result['avd']['hinweise'] == mock_inventory['hinweise']


def test_fetch_all_data_preserves_item_order(mock_versions, mock_inventory):
    """Inventar-Reihenfolge bleibt trotz as_completed erhalten."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '9.7.0'},
        'deprecated_at': None,
        'tag_name': 'v1.0.0'
    }
    with patch.object(server, 'load_versions', return_value=mock_versions), \
         patch.object(server, 'load_avd_inventory', return_value=mock_inventory), \
         patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server.fetch_all_data()

    assert [i['id'] for i in result['avd']['items']] == ['a', 'b']


def test_fetch_all_data_empty_versions():
    """fetch_all_data mit leeren Quellen gibt leere Listen zurück."""
    with patch.object(server, 'load_versions', return_value={"puppet_modules": {}}), \
         patch.object(server, 'load_avd_inventory',
                      return_value=dict(server._EMPTY_INVENTORY)):
        result = server.fetch_all_data()

    assert result['modules'] == []
    assert result['avd']['items'] == []


def test_fetch_all_data_multiple_items(multi_module_versions, mock_inventory):
    """fetch_all_data mit mehreren Items."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'current_release': {'version': '1.0.0'},
        'deprecated_at': None,
        'tag_name': 'v1.0.0',
        'version': '1.0.0'
    }

    with patch.object(server, 'load_versions', return_value=multi_module_versions), \
         patch.object(server, 'load_avd_inventory', return_value=mock_inventory), \
         patch.object(server.requests.Session, 'get', return_value=mock_response):
        result = server.fetch_all_data()

    assert len(result['modules']) == 3
    assert len(result['avd']['items']) == 2


def test_fetch_all_data_handles_mixed_errors(mock_versions, mock_inventory):
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
         patch.object(server, 'load_avd_inventory', return_value=mock_inventory), \
         patch.object(server.requests.Session, 'get', side_effect=side_effect):
        result = server.fetch_all_data()

    assert len(result['modules']) == 1
    assert len(result['avd']['items']) == 2
    assert result['modules'][0]['status'] == 'current'
    assert result['avd']['items'][0]['status'] == 'error'
    assert result['avd']['items'][1]['status'] == 'intern'


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


_EMPTY_AVD = {'items': [], 'kategorien': [], 'kontrakte': [],
              'termine': [], 'hinweise': [], 'meta': {}}


def test_api_avd_components_returns_json(client):
    """GET /api/avd-components gibt JSON zurück."""
    with patch.object(server, 'fetch_avd_data', return_value=dict(_EMPTY_AVD)):
        res = client.get('/api/avd-components')
    assert res.status_code == 200
    assert res.content_type == 'application/json'


def test_api_avd_components_returns_inventory_object(client):
    """GET /api/avd-components gibt das Inventar-Objekt zurück."""
    with patch.object(server, 'fetch_avd_data', return_value=dict(_EMPTY_AVD)):
        res = client.get('/api/avd-components')
    data = res.get_json()
    assert isinstance(data, dict)
    for key in ('items', 'kategorien', 'kontrakte', 'termine', 'hinweise'):
        assert key in data


def test_api_system_status_returns_all_fields(client):
    """GET /api/system_status enthält puppet, avd und timestamp."""
    with patch.object(server, 'fetch_all_data',
                      return_value={'modules': [], 'avd': {'items': []}}):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert 'puppet' in data
    assert 'avd' in data
    assert 'timestamp' in data
    assert data['puppet']['status'] == 'OK'
    assert data['avd']['status'] == 'OK'


def test_api_system_status_timestamp_format(client):
    """Timestamp hat Format YYYY-MM-DD HH:MM:SS."""
    with patch.object(server, 'fetch_all_data',
                      return_value={'modules': [], 'avd': {'items': []}}):
        res = client.get('/api/system_status')
    data = res.get_json()
    # Prüfe Format: "2026-03-14 12:00:00"
    assert len(data['timestamp']) == 19
    assert data['timestamp'][4] == '-'
    assert data['timestamp'][10] == ' '


def test_api_system_status_puppet_has_status_and_details(client):
    """Puppet-Status enthält status und details."""
    with patch.object(server, 'fetch_all_data',
                      return_value={'modules': [], 'avd': {'items': []}}):
        res = client.get('/api/system_status')
    data = res.get_json()
    assert 'status' in data['puppet']
    assert 'details' in data['puppet']


def test_api_system_status_avd_has_status_and_details(client):
    """AVD-Status enthält status und details."""
    with patch.object(server, 'fetch_all_data',
                      return_value={'modules': [], 'avd': {'items': []}}):
        res = client.get('/api/system_status')
    data = res.get_json()
    assert 'status' in data['avd']
    assert 'details' in data['avd']


def test_api_system_status_detects_outdated(client):
    """System-Status erkennt outdated Module korrekt."""
    mock_data = {
        'modules': [
            {'status': 'current', 'deprecated': False},
            {'status': 'outdated', 'deprecated': False},
        ],
        'avd': {'items': []}
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
        'avd': {'items': []}
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
        'avd': {'items': []}
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['puppet']['status'] == 'Warnung'


def test_api_system_status_detects_avd_errors(client):
    """System-Status erkennt AVD-Komponenten Fehler."""
    mock_data = {
        'modules': [],
        'avd': {'items': [
            {'status': 'current'},
            {'status': 'error'},
        ]}
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['avd']['status'] == 'Warnung'
    assert '1 Checks fehlgeschlagen' in data['avd']['details']


def test_api_system_status_detects_avd_manual(client):
    """System-Status erkennt manuelle AVD-Komponenten."""
    mock_data = {
        'modules': [],
        'avd': {'items': [
            {'status': 'current'},
            {'status': 'manual'},
        ]}
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['avd']['status'] == 'Info'
    assert '1 auto' in data['avd']['details']
    assert '1 manuell' in data['avd']['details']


def test_api_system_status_avd_errors_prio_over_manual(client):
    """AVD: Fehler haben Priorität über manuell."""
    mock_data = {
        'modules': [],
        'avd': {'items': [
            {'status': 'error'},
            {'status': 'manual'},
        ]}
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['avd']['status'] == 'Warnung'


def test_api_system_status_all_ok(client):
    """System-Status ist OK wenn alles aktuell."""
    mock_data = {
        'modules': [{'status': 'current', 'deprecated': False}],
        'avd': {'items': [{'status': 'current'}]}
    }
    with patch.object(server, 'fetch_all_data', return_value=mock_data):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['puppet']['status'] == 'OK'
    assert data['avd']['status'] == 'OK'


def test_api_system_status_error_handling(client):
    """System-Status gibt Error-Status bei Ausnahme zurück."""
    with patch.object(server, 'fetch_all_data', side_effect=Exception('test')):
        res = client.get('/api/system_status')

    data = res.get_json()
    assert data['puppet']['status'] == 'Error'
    assert data['avd']['status'] == 'Error'


def test_api_versions_returns_json(client):
    """GET /api/versions gibt die versions.json-Daten zurück."""
    res = client.get('/api/versions')
    assert res.status_code == 200
    data = res.get_json()
    assert 'puppet_modules' in data
    assert 'github_releases' in data


def test_api_versions_contains_modules(client):
    """GET /api/versions enthält Puppet-Module."""
    res = client.get('/api/versions')
    data = res.get_json()
    assert len(data['puppet_modules']) > 0


def test_api_versions_contains_github_releases(client):
    """GET /api/versions enthält GitHub-Releases."""
    res = client.get('/api/versions')
    data = res.get_json()
    assert len(data['github_releases']) > 0


def test_api_modules_error_returns_500(client):
    """API gibt 500 zurück bei internem Fehler."""
    with patch.object(server, 'fetch_modules_data', side_effect=Exception('test')):
        res = client.get('/api/modules')
    assert res.status_code == 500
    assert 'error' in res.get_json()


def test_api_avd_error_returns_500(client):
    """API gibt 500 zurück bei internem AVD-Fehler."""
    with patch.object(server, 'fetch_avd_data', side_effect=Exception('test')):
        res = client.get('/api/avd-components')
    assert res.status_code == 500
    assert 'error' in res.get_json()


def test_api_modules_error_message(client):
    """Fehler-Response enthält deutsche Fehlermeldung."""
    with patch.object(server, 'fetch_modules_data', side_effect=Exception('test')):
        res = client.get('/api/modules')
    data = res.get_json()
    assert 'Serverfehler' in data['error']


def test_api_avd_error_message(client):
    """Fehler-Response enthält deutsche Fehlermeldung."""
    with patch.object(server, 'fetch_avd_data', side_effect=Exception('test')):
        res = client.get('/api/avd-components')
    data = res.get_json()
    assert 'Serverfehler' in data['error']


def test_api_modules_only_get_allowed(client):
    """POST auf /api/modules gibt 405 zurück."""
    with patch.object(server, 'fetch_modules_data', return_value=[]):
        res = client.post('/api/modules')
    assert res.status_code == 405


def test_api_avd_only_get_allowed(client):
    """POST auf /api/avd-components gibt 405 zurück."""
    with patch.object(server, 'fetch_avd_data', return_value=dict(_EMPTY_AVD)):
        res = client.post('/api/avd-components')
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


def test_serve_avd_page(client):
    """GET /avd.html liefert die AVD-Seite."""
    res = client.get('/avd.html')
    assert res.status_code == 200
    assert b'AVD Versionsinventar' in res.data


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


def test_serve_js_avd(client):
    """GET /scripts/avd.js gibt JavaScript zurück."""
    res = client.get('/scripts/avd.js')
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


def test_api_responses_have_cdn_cache_headers(client):
    """API-Antworten tragen s-maxage fuer das Vercel-Edge-Caching."""
    with patch.object(server, 'fetch_modules_data', return_value=[]):
        res = client.get('/api/modules')
    cc = res.headers.get('Cache-Control', '')
    assert 's-maxage=300' in cc
    assert 'stale-while-revalidate' in cc


def test_api_error_responses_not_cdn_cached(client):
    """Fehlerantworten (500) werden nicht am Edge gecacht."""
    with patch.object(server, 'fetch_modules_data', side_effect=Exception('x')):
        res = client.get('/api/modules')
    assert 's-maxage' not in res.headers.get('Cache-Control', '')


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


def test_index_has_page_prefetch(client):
    """Index-Seite enthält Prefetch für Detail-Seiten."""
    res = client.get('/')
    assert b'prefetch' in res.data
    assert b'puppet.html' in res.data
    assert b'avd.html' in res.data


def test_puppet_page_has_dns_prefetch(client):
    """Puppet-Seite enthält DNS-Prefetch für Forge API."""
    res = client.get('/puppet.html')
    assert b'dns-prefetch' in res.data
    assert b'forgeapi.puppet.com' in res.data


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
    assert b'avdStatus' in res.data


def test_index_has_card_links(client):
    """Index enthält Links zu Puppet und AVD."""
    res = client.get('/')
    assert b'puppet.html' in res.data
    assert b'avd.html' in res.data


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


def test_avd_has_category_container(client):
    """AVD-Seite hat categoryGroups-Container."""
    res = client.get('/avd.html')
    assert b'categoryGroups' in res.data


def test_avd_has_stats(client):
    """AVD-Seite hat Stats-Bereich."""
    res = client.get('/avd.html')
    assert b'currentCount' in res.data
    assert b'manualCount' in res.data


def test_all_pages_have_theme_toggle(client):
    """Alle Seiten haben Theme-Toggle Button."""
    for path in ['/', '/puppet.html', '/avd.html']:
        res = client.get(path)
        assert b'themeToggle' in res.data, f"{path} hat keinen Theme-Toggle"


def test_all_pages_have_viewport_meta(client):
    """Alle Seiten haben Viewport-Meta-Tag."""
    for path in ['/', '/puppet.html', '/avd.html']:
        res = client.get(path)
        assert b'viewport' in res.data, f"{path} hat kein Viewport-Meta"


def test_all_pages_load_shared_js(client):
    """Alle Seiten laden shared.js."""
    for path in ['/', '/puppet.html', '/avd.html']:
        res = client.get(path)
        assert b'shared.js' in res.data, f"{path} lädt nicht shared.js"


def test_all_pages_load_shared_css(client):
    """Alle Seiten laden shared.css."""
    for path in ['/', '/puppet.html', '/avd.html']:
        res = client.get(path)
        assert b'shared.css' in res.data, f"{path} lädt nicht shared.css"


def test_all_pages_load_theme_init(client):
    """Alle Seiten laden theme-init.js."""
    for path in ['/', '/puppet.html', '/avd.html']:
        res = client.get(path)
        assert b'theme-init.js' in res.data, f"{path} lädt nicht theme-init.js"


# ============================================================================
# UNIT TESTS - KNOWN PAGES
# ============================================================================

def test_known_pages_set():
    """_KNOWN_PAGES enthält alle erwarteten Seiten."""
    assert '' in server._KNOWN_PAGES
    assert 'index.html' in server._KNOWN_PAGES
    assert 'puppet.html' in server._KNOWN_PAGES
    assert 'avd.html' in server._KNOWN_PAGES


def test_known_pages_count():
    """_KNOWN_PAGES hat genau 4 Einträge."""
    assert len(server._KNOWN_PAGES) == 4



# ============================================================================
# INTEGRATION TESTS - ETAG / CONDITIONAL GET / JSON-ENCODING
# ============================================================================

def test_api_responses_have_etag(client):
    """API-Antworten tragen einen ETag für Conditional GETs."""
    with patch.object(server, 'fetch_modules_data', return_value=[]):
        res = client.get('/api/modules')
    assert res.headers.get('ETag')


def test_api_conditional_request_returns_304(client):
    """Passender If-None-Match liefert 304 ohne Body."""
    with patch.object(server, 'fetch_modules_data', return_value=[{'name': 'x'}]):
        first = client.get('/api/modules')
        etag = first.headers['ETag']
        second = client.get('/api/modules', headers={'If-None-Match': etag})
    assert first.status_code == 200
    assert second.status_code == 304
    assert second.data == b''


def test_api_conditional_request_stale_etag_returns_200(client):
    """Nicht passender If-None-Match liefert die volle Antwort."""
    with patch.object(server, 'fetch_modules_data', return_value=[{'name': 'x'}]):
        res = client.get('/api/modules', headers={'If-None-Match': '"veraltet"'})
    assert res.status_code == 200
    assert res.get_json() == [{'name': 'x'}]


def test_api_error_responses_have_no_etag(client):
    """Fehlerantworten (500) bekommen keinen ETag."""
    with patch.object(server, 'fetch_modules_data', side_effect=Exception('x')):
        res = client.get('/api/modules')
    assert res.status_code == 500
    assert 'ETag' not in res.headers


def test_api_json_is_compact_utf8(client):
    """JSON ist kompakt und liefert Umlaute als UTF-8 statt \\uXXXX."""
    with patch.object(server, 'fetch_modules_data', return_value=[{'name': 'Prüfung'}]):
        res = client.get('/api/modules')
    assert res.data.strip() == '[{"name":"Prüfung"}]'.encode('utf-8')
    assert b'\\u00fc' not in res.data


def test_system_status_timestamp_is_fetch_time(client, mock_versions, mock_inventory):
    """Der Timestamp im System-Status ist der (gecachte) Abrufzeitpunkt."""
    all_data = {'modules': [], 'avd': {'items': []}, 'fetched_at': '2026-01-02 03:04:05'}
    with patch.object(server, 'fetch_all_data', return_value=all_data):
        res = client.get('/api/system_status')
    assert res.get_json()['timestamp'] == '2026-01-02 03:04:05'


def test_system_status_etag_stable_while_cached(client):
    """Bei gecachten Daten bleibt der ETag von /api/system_status gleich."""
    all_data = {'modules': [], 'avd': {'items': []}, 'fetched_at': '2026-01-02 03:04:05'}
    with patch.object(server, 'fetch_all_data', return_value=all_data):
        a = client.get('/api/system_status')
        b = client.get('/api/system_status')
    assert a.headers['ETag'] == b.headers['ETag']


def test_fetch_all_data_includes_fetched_at(mock_versions, mock_inventory):
    """fetch_all_data liefert den Abrufzeitpunkt mit."""
    with patch.object(server, 'load_versions', return_value=mock_versions), \
         patch.object(server, 'load_avd_inventory', return_value=mock_inventory), \
         patch.object(server, '_fetch_single_module', return_value={'name': 'm'}), \
         patch.object(server, '_check_inventory_item', return_value={'id': 'a'}):
        result = server.fetch_all_data()
    assert 'fetched_at' in result
    time.strptime(result['fetched_at'], "%Y-%m-%d %H:%M:%S")


# ============================================================================
# INTEGRATION TESTS - HTML: LADEREIHENFOLGE & ACCESSIBILITY
# ============================================================================

def test_theme_init_loads_before_stylesheet(client):
    """theme-init.js steht vor dem Stylesheet, damit es nicht auf das CSS wartet."""
    for path in ['/', '/puppet.html', '/avd.html']:
        html = client.get(path).data
        assert html.index(b'theme-init.js') < html.index(b'shared.css'), path


def test_nav_toggle_is_accessible(client):
    """Mobile-Menü-Button hat aria-expanded und aria-controls."""
    for path in ['/', '/puppet.html', '/avd.html']:
        html = client.get(path).data
        assert b'aria-expanded="false"' in html, path
        assert b'aria-controls="navLinks"' in html, path
        assert b'id="navLinks"' in html, path


def test_pages_have_skip_link_and_main_id(client):
    """Skip-Link zeigt auf den main-Bereich."""
    for path in ['/', '/puppet.html', '/avd.html']:
        html = client.get(path).data
        assert b'class="skip-link"' in html, path
        assert b'id="main"' in html, path


def test_active_nav_link_has_aria_current(client):
    """Die aktive Seite ist per aria-current markiert."""
    for path in ['/', '/puppet.html', '/avd.html']:
        html = client.get(path).data
        assert html.count(b'aria-current="page"') == 1, path


def test_puppet_sortable_headers_are_keyboard_focusable(client):
    """Sortierbare Spalten sind per Tab erreichbar."""
    html = client.get('/puppet.html').data
    assert html.count(b'class="sortable"') == 4
    assert html.count(b'tabindex="0"') == 4


def test_puppet_filter_has_label(client):
    """Filter-Input ist per aria-label beschriftet."""
    html = client.get('/puppet.html').data
    assert b'aria-label="Module filtern"' in html
