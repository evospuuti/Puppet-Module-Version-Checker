"""Performance-Benchmarks: Misst die tatsächlichen Verbesserungen durch autoresearch-Patterns.

Jeder Benchmark vergleicht die optimierte Variante mit einer Baseline und gibt
die gemessene Verbesserung in Prozent aus.
"""
import time
import threading
from unittest.mock import patch, MagicMock
import pytest
import requests
from requests.adapters import HTTPAdapter
import server


@pytest.fixture(autouse=True)
def reset_caches():
    """Reset aller Caches vor jedem Test."""
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


def _make_mock_response(status=200, version='1.0.0', deprecated=None):
    """Erzeugt eine Mock-Response für API-Calls."""
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = {
        'current_release': {'version': version},
        'deprecated_at': deprecated
    }
    return mock


def _make_provider_mock(status=200, version='1.0.0'):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = {'version': version}
    return mock


# ============================================================================
# BENCHMARK 1: Connection Pooling vs Neue Session pro Request
# ============================================================================

class TestConnectionPoolingBenchmark:
    """Misst den Vorteil von Connection Pooling (Thread-lokale Sessions)
    gegenüber dem Erstellen einer neuen Session pro Request."""

    def test_session_reuse_is_faster_than_creation(self):
        """Connection Pooling: Session-Wiederverwendung vs. Neuerstellen."""
        iterations = 500

        # Baseline: Neue Session pro Aufruf (alter Code)
        start = time.perf_counter()
        for _ in range(iterations):
            s = requests.Session()
            s.headers.update({'User-Agent': 'Version-Checker/2.0'})
            s.close()
        baseline_ms = (time.perf_counter() - start) * 1000

        # Optimiert: Thread-lokale Session wiederverwenden
        start = time.perf_counter()
        for _ in range(iterations):
            s = server._get_http_session()  # Gibt gleiche Session zurück
        optimized_ms = (time.perf_counter() - start) * 1000

        speedup = baseline_ms / optimized_ms if optimized_ms > 0 else float('inf')
        print(f"\n  Connection Pooling Benchmark ({iterations} iterations):")
        print(f"    Baseline (neue Session):    {baseline_ms:.2f}ms")
        print(f"    Optimiert (Session reuse):  {optimized_ms:.2f}ms")
        print(f"    Speedup: {speedup:.1f}x schneller")

        assert optimized_ms < baseline_ms, \
            f"Session reuse ({optimized_ms:.2f}ms) sollte schneller sein als Neuerstellen ({baseline_ms:.2f}ms)"

    def test_pooled_session_has_retry_adapter(self):
        """Pooled Session hat Retry-Adapter konfiguriert."""
        session = server._get_http_session()
        adapter = session.get_adapter('https://example.com')
        assert isinstance(adapter, HTTPAdapter)
        assert adapter.max_retries.total == 3
        assert adapter.max_retries.backoff_factor == 1


# ============================================================================
# BENCHMARK 2: Paralleler Fetch (10 Worker) vs Sequential
# ============================================================================

class TestParallelFetchBenchmark:
    """Misst den Vorteil von 10 parallelen Workern gegenüber sequentiellem Fetch."""

    def test_parallel_faster_than_sequential(self):
        """10 Worker parallel vs. sequentiell (simuliert mit Delay)."""
        modules = {f'test-module-{i}': '1.0.0' for i in range(10)}
        delay_per_call = 0.02  # 20ms simulierter Netzwerk-Delay

        def slow_fetch(url, **kwargs):
            time.sleep(delay_per_call)
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {
                'current_release': {'version': '1.0.0'},
                'deprecated_at': None
            }
            return mock

        # Sequentiell
        start = time.perf_counter()
        with patch.object(requests.Session, 'get', side_effect=slow_fetch):
            for name, ver in modules.items():
                server._fetch_single_module(name, ver)
        sequential_ms = (time.perf_counter() - start) * 1000

        # Parallel (mit ThreadPoolExecutor, 10 Worker)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        start = time.perf_counter()
        with patch.object(requests.Session, 'get', side_effect=slow_fetch):
            with ThreadPoolExecutor(max_workers=server._MAX_WORKERS) as executor:
                futures = [
                    executor.submit(server._fetch_single_module, name, ver)
                    for name, ver in modules.items()
                ]
                results = [f.result() for f in as_completed(futures)]
        parallel_ms = (time.perf_counter() - start) * 1000

        speedup = sequential_ms / parallel_ms if parallel_ms > 0 else float('inf')
        print(f"\n  Parallel Fetch Benchmark (10 modules, {delay_per_call*1000:.0f}ms delay each):")
        print(f"    Sequentiell:     {sequential_ms:.1f}ms")
        print(f"    Parallel (10w):  {parallel_ms:.1f}ms")
        print(f"    Speedup: {speedup:.1f}x schneller")

        assert parallel_ms < sequential_ms, \
            f"Parallel ({parallel_ms:.1f}ms) sollte schneller sein als Sequential ({sequential_ms:.1f}ms)"
        assert len(results) == 10


# ============================================================================
# BENCHMARK 3: fetch_all_data vs. separate Aufrufe
# ============================================================================

class TestCombinedFetchBenchmark:
    """Misst den Vorteil von fetch_all_data() (ein paralleler Batch)
    gegenüber zwei separaten fetch_modules_data + fetch_terraform_data."""

    def test_combined_fetch_one_pool_vs_two(self):
        """Ein ThreadPool für alles vs. zwei separate Pools."""
        delay = 0.02
        versions = {
            "puppet_modules": {f'mod-{i}': '1.0.0' for i in range(6)},
            "terraform_providers": {f'ns/prov-{i}': '1.0.0' for i in range(4)}
        }

        def slow_get(url, **kwargs):
            time.sleep(delay)
            mock = MagicMock()
            mock.status_code = 200
            if 'forgeapi' in url:
                mock.json.return_value = {
                    'current_release': {'version': '1.0.0'},
                    'deprecated_at': None
                }
            else:
                mock.json.return_value = {'version': '1.0.0'}
            return mock

        # Zwei separate Pools (alter Ansatz für system_status)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        start = time.perf_counter()
        with patch.object(requests.Session, 'get', side_effect=slow_get), \
             patch.object(server, 'load_versions', return_value=versions):
            # Pool 1: Module
            with ThreadPoolExecutor(max_workers=10) as ex:
                futs = [ex.submit(server._fetch_single_module, n, v)
                        for n, v in versions['puppet_modules'].items()]
                mods = [f.result() for f in as_completed(futs)]
            # Pool 2: Provider
            with ThreadPoolExecutor(max_workers=10) as ex:
                futs = [ex.submit(server._fetch_single_provider, n, v)
                        for n, v in versions['terraform_providers'].items()]
                provs = [f.result() for f in as_completed(futs)]
        two_pools_ms = (time.perf_counter() - start) * 1000

        # Ein kombinierter Pool (fetch_all_data)
        start = time.perf_counter()
        with patch.object(requests.Session, 'get', side_effect=slow_get), \
             patch.object(server, 'load_versions', return_value=versions):
            result = server.fetch_all_data()
        one_pool_ms = (time.perf_counter() - start) * 1000

        speedup = two_pools_ms / one_pool_ms if one_pool_ms > 0 else float('inf')
        print(f"\n  Combined Fetch Benchmark (6 modules + 4 providers, {delay*1000:.0f}ms each):")
        print(f"    Zwei Pools (sequentiell): {two_pools_ms:.1f}ms")
        print(f"    Ein Pool (parallel):      {one_pool_ms:.1f}ms")
        print(f"    Speedup: {speedup:.1f}x schneller")

        assert len(result['modules']) == 6
        assert len(result['providers']) == 4


# ============================================================================
# BENCHMARK 4: Cache Hit vs Cache Miss
# ============================================================================

class TestCacheBenchmark:
    """Misst den Vorteil des Flask-Caching bei wiederholten Requests."""

    def test_cache_hit_much_faster_than_miss(self, client):
        """Cached Response vs. frischer API-Call."""
        delay = 0.05

        def slow_get(url, **kwargs):
            time.sleep(delay)
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {
                'current_release': {'version': '1.0.0'},
                'deprecated_at': None
            }
            return mock

        # Cache Miss (erster Aufruf)
        with patch.object(requests.Session, 'get', side_effect=slow_get):
            start = time.perf_counter()
            res1 = client.get('/api/modules')
            miss_ms = (time.perf_counter() - start) * 1000

        # Cache Hit (zweiter Aufruf, keine API-Calls)
        start = time.perf_counter()
        res2 = client.get('/api/modules')
        hit_ms = (time.perf_counter() - start) * 1000

        speedup = miss_ms / hit_ms if hit_ms > 0 else float('inf')
        print(f"\n  Cache Benchmark:")
        print(f"    Cache Miss: {miss_ms:.1f}ms")
        print(f"    Cache Hit:  {hit_ms:.2f}ms")
        print(f"    Speedup: {speedup:.1f}x schneller")

        assert res1.status_code == 200
        assert res2.status_code == 200
        assert hit_ms < miss_ms, \
            f"Cache Hit ({hit_ms:.2f}ms) sollte schneller sein als Miss ({miss_ms:.1f}ms)"


# ============================================================================
# BENCHMARK 5: API Response Time
# ============================================================================

class TestAPIResponseBenchmark:
    """Misst die Response-Zeiten aller API-Endpoints."""

    def test_all_endpoints_respond_under_threshold(self, client):
        """Alle API-Endpoints antworten unter 100ms (mit Cache)."""
        # Vorbefüllen der Caches
        mock_data = {'modules': [], 'providers': []}
        with patch.object(server, 'fetch_modules_data', return_value=[]), \
             patch.object(server, 'fetch_terraform_data', return_value=[]), \
             patch.object(server, 'fetch_all_data', return_value=mock_data):
            client.get('/api/modules')
            client.get('/api/terraform-providers')
            client.get('/api/system_status')

        endpoints = {
            '/': 'Index HTML',
            '/puppet.html': 'Puppet HTML',
            '/terraform.html': 'Terraform HTML',
            '/favicon.ico': 'Favicon',
            '/styles/shared.css': 'CSS',
            '/scripts/shared.js': 'JS',
            '/api/versions': 'Versions JSON',
        }

        threshold_ms = 100
        print(f"\n  API Response Benchmark (Threshold: {threshold_ms}ms):")

        for path, label in endpoints.items():
            start = time.perf_counter()
            res = client.get(path)
            elapsed_ms = (time.perf_counter() - start) * 1000

            status = "PASS" if elapsed_ms < threshold_ms else "SLOW"
            print(f"    [{status}] {label:20s} {elapsed_ms:6.2f}ms (HTTP {res.status_code})")

            assert res.status_code == 200
            assert elapsed_ms < threshold_ms, \
                f"{label} ({elapsed_ms:.2f}ms) überschreitet {threshold_ms}ms Threshold"


# ============================================================================
# BENCHMARK 6: Thread-Sicherheit
# ============================================================================

class TestThreadSafetyBenchmark:
    """Prüft, dass Connection Pooling thread-sicher funktioniert."""

    def test_different_threads_get_different_sessions(self):
        """Verschiedene Threads bekommen verschiedene Sessions."""
        sessions = {}

        def get_session(thread_id):
            # Erzwinge neue thread-lokale Session
            local = threading.local()
            server._thread_local = local
            s = server._get_http_session()
            sessions[thread_id] = id(s)

        threads = []
        for i in range(5):
            t = threading.Thread(target=get_session, args=(i,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        # Jeder Thread sollte seine eigene Session haben
        unique_sessions = len(set(sessions.values()))
        print(f"\n  Thread Safety Benchmark:")
        print(f"    {len(sessions)} Threads, {unique_sessions} unique Sessions")

        assert unique_sessions == 5, \
            f"Erwartet 5 unique Sessions, bekam {unique_sessions}"
