// Dark Mode Toggle
function toggleDarkMode() {
    document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
}

// Mobile Navigation Toggle
function toggleNav() {
    document.querySelector('.nav-links').classList.toggle('open');
}

// HTML Escaping (XSS-Schutz)
function escapeHtml(str) {
    if (str == null) return '';
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

// Bessere Fehlermeldung für bekannte HTTP-Status
function getErrorMessage(e) {
    var msg = e.message || 'Unbekannter Fehler';
    if (msg.indexOf('429') !== -1) return 'Zu viele Anfragen - bitte kurz warten';
    if (msg.indexOf('503') !== -1) return 'Service vorübergehend nicht erreichbar';
    return 'Fehler beim Laden: ' + msg;
}

// Debounce für Filter-Input
function debounce(fn, delay) {
    var timer = null;
    return function() {
        var context = this;
        var args = arguments;
        if (timer) clearTimeout(timer);
        timer = setTimeout(function() {
            fn.apply(context, args);
        }, delay);
    };
}

// ============================================================================
// STALE-WHILE-REVALIDATE CACHE
// Zeigt sofort gecachte Daten aus localStorage an und holt im Hintergrund
// frische Daten. Der User sieht nach dem ersten Besuch nie wieder einen
// Spinner - die Seite lädt sofort.
// ============================================================================

var _CACHE_MAX_AGE_MS = 5 * 60 * 1000; // 5 Minuten

function _getCacheKey(url) {
    return 'swr_' + url;
}

function _getCache(url) {
    try {
        var raw = localStorage.getItem(_getCacheKey(url));
        if (!raw) return null;
        var entry = JSON.parse(raw);
        return entry;
    } catch (e) {
        return null;
    }
}

function _setCache(url, data) {
    try {
        localStorage.setItem(_getCacheKey(url), JSON.stringify({
            data: data,
            timestamp: Date.now()
        }));
    } catch (e) {
        // localStorage voll oder nicht verfügbar - ignorieren
    }
}

function _isCacheStale(entry) {
    if (!entry || !entry.timestamp) return true;
    return (Date.now() - entry.timestamp) > _CACHE_MAX_AGE_MS;
}

/**
 * Stale-While-Revalidate Fetch:
 * 1. Wenn Cache vorhanden: sofort onData(cachedData, false) aufrufen
 * 2. Im Hintergrund frische Daten holen
 * 3. Bei neuen Daten: onData(freshData, true) aufrufen
 * 4. Kein Cache: onLoading() -> fetch -> onData(freshData, true)
 *
 * @param {string} url - API-Endpoint
 * @param {function} onData - Callback(data, isFresh) bei Daten
 * @param {function} onError - Callback(error) bei Fehler
 * @param {function} onLoading - Callback() wenn kein Cache und geladen wird
 */
function fetchSWR(url, onData, onError, onLoading) {
    var cached = _getCache(url);
    var hadCache = false;

    // Sofort gecachte Daten anzeigen (stale)
    if (cached && cached.data) {
        hadCache = true;
        onData(cached.data, false);
    }

    // Wenn Cache noch frisch ist, nicht neu laden
    if (cached && !_isCacheStale(cached)) {
        return;
    }

    // Kein Cache vorhanden -> Loading-State anzeigen
    if (!hadCache && onLoading) {
        onLoading();
    }

    // Im Hintergrund frische Daten holen (revalidate)
    fetchDeduped(url).then(function(data) {
        _setCache(url, data);
        onData(data, true);
    }).catch(function(err) {
        // Nur Fehler anzeigen wenn kein Cache vorhanden war
        if (!hadCache) {
            onError(err);
        }
    });
}

// ============================================================================
// REQUEST DEDUPLICATION
// ============================================================================

var _pendingRequests = {};
function fetchDeduped(url) {
    if (_pendingRequests[url]) {
        return _pendingRequests[url];
    }
    var promise = fetch(url).then(function(res) {
        delete _pendingRequests[url];
        if (!res.ok) throw new Error('Server antwortet nicht (' + res.status + ')');
        return res.json();
    }).catch(function(err) {
        delete _pendingRequests[url];
        throw err;
    });
    _pendingRequests[url] = promise;
    return promise;
}

// Prefetch für nächste Seite
function prefetchData(urls) {
    if (!window.requestIdleCallback) {
        setTimeout(function() {
            urls.forEach(function(url) { fetchDeduped(url); });
        }, 1000);
        return;
    }
    window.requestIdleCallback(function() {
        urls.forEach(function(url) { fetchDeduped(url); });
    }, { timeout: 3000 });
}

// ============================================================================
// SKELETON LOADING
// Erzeugt Placeholder-Zeilen die wie echte Daten aussehen, aber mit
// animierten Balken statt Text. Gibt dem User sofort visuelle Struktur.
// ============================================================================

function createSkeletonRows(count, columns) {
    var fragment = document.createDocumentFragment();
    for (var i = 0; i < count; i++) {
        var tr = document.createElement('tr');
        tr.className = 'skeleton-row';
        var html = '';
        for (var j = 0; j < columns; j++) {
            var width = 40 + Math.floor(Math.random() * 40); // 40-80%
            html += '<td><div class="skeleton-line" style="width:' + width + '%"></div></td>';
        }
        tr.innerHTML = html;
        fragment.appendChild(tr);
    }
    return fragment;
}

// Event-Listener für Navigation (alle Seiten)
document.addEventListener('DOMContentLoaded', function() {
    var navToggle = document.getElementById('navToggle');
    if (navToggle) navToggle.addEventListener('click', toggleNav);

    var themeToggle = document.getElementById('themeToggle');
    if (themeToggle) themeToggle.addEventListener('click', toggleDarkMode);

    // Sortierbare Spalten-Header
    var sortHeaders = document.querySelectorAll('th.sortable');
    for (var i = 0; i < sortHeaders.length; i++) {
        sortHeaders[i].addEventListener('click', function() {
            if (typeof sortBy === 'function') {
                sortBy(this.getAttribute('data-sort'));
            }
        });
    }
});
