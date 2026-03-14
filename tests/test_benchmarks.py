"""Echte Performance-Benchmarks gegen den bestehenden Code.

Misst reale Response-Zeiten der Flask-App. Kein Caching-Trick, kein Fake.
Cache wird zwischen Messungen gelöscht, damit wir den echten Durchsatz messen.
"""
import time
import statistics
from unittest.mock import patch, MagicMock
import pytest
import server


@pytest.fixture(autouse=True)
def reset_caches():
    server._versions_cache = None
    server.cache.clear()
    yield
    server._versions_cache = None
    server.cache.clear()


@pytest.fixture
def client():
    server.app.config['TESTING'] = True
    with server.app.test_client() as c:
        yield c


def _mock_forge_response(version='9.7.0', deprecated=None):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {
        'current_release': {'version': version},
        'deprecated_at': deprecated
    }
    return m


def _mock_registry_response(version='3.7.2'):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {'version': version}
    return m


def _measure_ms(fn, iterations=20):
    """Misst fn() N-mal, gibt Median, Min, Max in ms zurück."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return {
        'median': statistics.median(times),
        'min': min(times),
        'max': max(times),
        'stdev': statistics.stdev(times) if len(times) > 1 else 0,
    }


def _print_result(label, result, unit='ms'):
    print(f"  {label:45s}  median={result['median']:8.3f}{unit}  "
          f"min={result['min']:8.3f}{unit}  max={result['max']:8.3f}{unit}  "
          f"stdev={result['stdev']:6.3f}{unit}")


# ============================================================================
# BENCHMARK: Statische Seiten
# ============================================================================

class TestStaticResponseTime:

    def test_index_html(self, client):
        result = _measure_ms(lambda: client.get('/'))
        _print_result('GET /', result)
        assert result['median'] < 20

    def test_puppet_html(self, client):
        result = _measure_ms(lambda: client.get('/puppet.html'))
        _print_result('GET /puppet.html', result)
        assert result['median'] < 20

    def test_terraform_html(self, client):
        result = _measure_ms(lambda: client.get('/terraform.html'))
        _print_result('GET /terraform.html', result)
        assert result['median'] < 20

    def test_shared_css(self, client):
        result = _measure_ms(lambda: client.get('/styles/shared.css'))
        _print_result('GET /styles/shared.css', result)
        assert result['median'] < 20

    def test_shared_js(self, client):
        result = _measure_ms(lambda: client.get('/scripts/shared.js'))
        _print_result('GET /scripts/shared.js', result)
        assert result['median'] < 20

    def test_favicon(self, client):
        result = _measure_ms(lambda: client.get('/favicon.ico'))
        _print_result('GET /favicon.ico', result)
        assert result['median'] < 20


# ============================================================================
# BENCHMARK: API Overhead (cached)
# ============================================================================

class TestAPICachedOverhead:

    def test_api_modules_cached(self, client):
        with patch.object(server, 'fetch_modules_data', return_value=[]):
            client.get('/api/modules')
            result = _measure_ms(lambda: client.get('/api/modules'))
        _print_result('GET /api/modules (cached)', result)
        assert result['median'] < 20

    def test_api_terraform_cached(self, client):
        with patch.object(server, 'fetch_terraform_data', return_value=[]):
            client.get('/api/terraform-providers')
            result = _measure_ms(lambda: client.get('/api/terraform-providers'))
        _print_result('GET /api/terraform-providers (cached)', result)
        assert result['median'] < 20

    def test_api_system_status_cached(self, client):
        mock_data = {'modules': [], 'providers': []}
        with patch.object(server, 'fetch_all_data', return_value=mock_data):
            client.get('/api/system_status')
            result = _measure_ms(lambda: client.get('/api/system_status'))
        _print_result('GET /api/system_status (cached)', result)
        assert result['median'] < 20

    def test_api_versions(self, client):
        result = _measure_ms(lambda: client.get('/api/versions'))
        _print_result('GET /api/versions', result)
        assert result['median'] < 20


# ============================================================================
# BENCHMARK: Paralleler Fetch (Cache wird pro Iteration gelöscht!)
# ============================================================================

class TestParallelFetchReal:
    """Misst den echten Parallel-Fetch OHNE Cache-Tricks.
    Cache wird vor jeder Messung gelöscht."""

    def test_fetch_modules_parallel_10ms(self):
        """12 Module parallel mit 10ms simuliertem Delay."""
        delay_ms = 10

        def delayed_get(url, **kwargs):
            time.sleep(delay_ms / 1000)
            return _mock_forge_response()

        def run_once():
            server.cache.clear()
            return server.fetch_modules_data()

        with patch.object(server.requests.Session, 'get', side_effect=delayed_get):
            result = _measure_ms(run_once, iterations=10)

        _print_result(f'fetch_modules (12x, {delay_ms}ms delay, no cache)', result)
        # 12 Items, 10 Worker, 10ms -> ideal 20ms (2 Batches)
        # Erlaubt bis 80ms für ThreadPool-Overhead
        assert result['median'] < 80, f"Zu langsam: {result['median']:.1f}ms"

    def test_fetch_terraform_parallel_10ms(self):
        """8 Provider parallel mit 10ms simuliertem Delay."""
        delay_ms = 10

        def delayed_get(url, **kwargs):
            time.sleep(delay_ms / 1000)
            return _mock_registry_response()

        def run_once():
            server.cache.clear()
            return server.fetch_terraform_data()

        with patch.object(server.requests.Session, 'get', side_effect=delayed_get):
            result = _measure_ms(run_once, iterations=10)

        _print_result(f'fetch_terraform (8x, {delay_ms}ms delay, no cache)', result)
        # 8 Items, 10 Worker, 10ms -> ideal 10ms (1 Batch)
        assert result['median'] < 80

    def test_fetch_all_data_parallel_10ms(self):
        """20 Items (12+8) parallel mit 10ms simuliertem Delay."""
        delay_ms = 10

        def delayed_get(url, **kwargs):
            time.sleep(delay_ms / 1000)
            if 'forgeapi' in url:
                return _mock_forge_response()
            return _mock_registry_response()

        def run_once():
            server.cache.clear()
            return server.fetch_all_data()

        with patch.object(server.requests.Session, 'get', side_effect=delayed_get):
            result = _measure_ms(run_once, iterations=10)

        _print_result(f'fetch_all_data (20x, {delay_ms}ms delay, no cache)', result)
        # 20 Items, 10 Worker, 10ms -> ideal 20ms (2 Batches)
        assert result['median'] < 80


# ============================================================================
# BENCHMARK: Einzelfetch Overhead (mit Mock, misst unseren Code)
# ============================================================================

class TestSingleFetchOverhead:
    """Misst den reinen Code-Overhead einer Fetch-Funktion.
    Mock-Response ohne Netzwerk-Delay = reine Code-Laufzeit."""

    def test_fetch_single_module_overhead(self):
        mock = _mock_forge_response()
        with patch.object(server.requests.Session, 'get', return_value=mock):
            result = _measure_ms(
                lambda: server._fetch_single_module('puppetlabs-stdlib', '9.7.0'),
                iterations=50
            )
        _print_result('_fetch_single_module (mocked, no delay)', result)
        assert result['median'] < 5, f"Zu viel Overhead: {result['median']:.3f}ms"

    def test_fetch_single_provider_overhead(self):
        mock = _mock_registry_response()
        with patch.object(server.requests.Session, 'get', return_value=mock):
            result = _measure_ms(
                lambda: server._fetch_single_provider('hashicorp/random', '3.7.2'),
                iterations=50
            )
        _print_result('_fetch_single_provider (mocked, no delay)', result)
        assert result['median'] < 5, f"Zu viel Overhead: {result['median']:.3f}ms"


# ============================================================================
# BENCHMARK: Cache Miss vs Hit (ehrlich)
# ============================================================================

class TestCacheEffectiveness:

    def test_cache_miss_vs_hit(self):
        """Vergleicht echten Cache-Miss mit Cache-Hit."""
        delay_ms = 10

        def delayed_get(url, **kwargs):
            time.sleep(delay_ms / 1000)
            return _mock_forge_response()

        # Cache Miss: clear + fetch
        def run_miss():
            server.cache.clear()
            return server.fetch_modules_data()

        with patch.object(server.requests.Session, 'get', side_effect=delayed_get):
            miss_result = _measure_ms(run_miss, iterations=5)

        # Cache Hit: fetch einmal, dann messen
        with patch.object(server.requests.Session, 'get', side_effect=delayed_get):
            server.cache.clear()
            server.fetch_modules_data()
            hit_result = _measure_ms(lambda: server.fetch_modules_data(), iterations=20)

        _print_result('Cache MISS (12 modules, 10ms delay)', miss_result)
        _print_result('Cache HIT  (12 modules)', hit_result)

        ratio = miss_result['median'] / hit_result['median'] if hit_result['median'] > 0 else 0
        print(f"  {'Cache speedup':45s}  {ratio:.0f}x")

        assert hit_result['median'] < miss_result['median']
