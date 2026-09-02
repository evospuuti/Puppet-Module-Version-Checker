// Dark Mode Toggle
function toggleDarkMode() {
    var root = document.documentElement;
    var dark = root.classList.toggle('dark');
    try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch (e) {}
}

// Mobile Navigation Toggle
function toggleNav() {
    var links = document.getElementById('navLinks') || document.querySelector('.nav-links');
    var open = links.classList.toggle('open');
    var toggle = document.getElementById('navToggle');
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
}

// HTML Escaping (XSS-Schutz) - escapt auch Quotes, damit die Funktion
// sicher in Attributwerten (z.B. href="...") verwendet werden kann
function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
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

// Versions-/Textvergleich: "10.0.0" sortiert nach "9.0.0", nicht davor
var _collator = (typeof Intl !== 'undefined' && Intl.Collator)
    ? new Intl.Collator('de', { numeric: true, sensitivity: 'base' })
    : null;
function compareText(a, b) {
    a = a == null ? '' : String(a);
    b = b == null ? '' : String(b);
    return _collator ? _collator.compare(a, b) : a.localeCompare(b);
}

// "Aktualisiert"-Anzeige: frisch = Text, aus Cache = pulsierender Indikator
function renderUpdatedAt(el, isFresh, text) {
    if (!el) return;
    if (isFresh) {
        el.textContent = 'Aktualisiert: ' + text;
    } else {
        el.innerHTML = '<span class="stale-indicator"><span class="stale-dot"></span>' +
            escapeHtml(text) + '</span>';
    }
}

function renderUpdateError(el, e) {
    if (!el) return;
    el.innerHTML = '<span class="text-danger">' + escapeHtml(getErrorMessage(e)) + '</span>';
}

// Button während eines laufenden Requests sperren
function setBusy(btn, busy) {
    if (!btn) return;
    btn.disabled = busy;
    btn.setAttribute('aria-busy', busy ? 'true' : 'false');
    if (busy) {
        btn.setAttribute('data-label', btn.textContent);
        btn.textContent = 'Lädt…';
    } else if (btn.getAttribute('data-label')) {
        btn.textContent = btn.getAttribute('data-label');
    }
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
 * @param {function} onError - Callback(error, hadCache) bei Fehler; wird nur
 *        aufgerufen wenn kein Cache angezeigt wird oder force gesetzt ist
 * @param {function} onLoading - Callback() wenn kein Cache und geladen wird
 * @param {object} [opts] - { force: true } erzwingt die Revalidierung auch
 *        bei frischem Cache (manueller Refresh); die alten Daten bleiben
 *        dabei sichtbar, es gibt keinen Skeleton-Flash
 * @returns {Promise} löst auf, sobald die Revalidierung abgeschlossen ist
 *        (auch im Fehlerfall - Fehler laufen über onError)
 */
function fetchSWR(url, onData, onError, onLoading, opts) {
    var force = !!(opts && opts.force);
    var cached = _getCache(url);
    var hadCache = false;

    // Sofort gecachte Daten anzeigen (stale)
    if (cached && cached.data) {
        hadCache = true;
        onData(cached.data, false);
    }

    // Wenn Cache noch frisch ist, nicht neu laden
    if (hadCache && !force && !_isCacheStale(cached)) {
        return Promise.resolve(cached.data);
    }

    // Kein Cache vorhanden -> Loading-State anzeigen
    if (!hadCache && onLoading) {
        onLoading();
    }

    // Im Hintergrund frische Daten holen (revalidate)
    return fetchDeduped(url).then(function(data) {
        _setCache(url, data);
        onData(data, true);
        return data;
    }, function(err) {
        // Bei vorhandenem Cache bleiben die alten Daten stehen; nur bei
        // manuellem Refresh wird der Fehler trotzdem gemeldet
        if (!hadCache || force) onError(err, hadCache);
        return null;
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
    var promise = fetch(url, { headers: { 'Accept': 'application/json' } }).then(function(res) {
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

// Prefetch für nächste Seite: füllt den SWR-Cache, damit die Unterseite
// beim Aufruf sofort Daten hat. Läuft nur, wenn der Cache fehlt/veraltet ist.
function prefetchData(urls) {
    var run = function() {
        urls.forEach(function(url) {
            var cached = _getCache(url);
            if (cached && cached.data && !_isCacheStale(cached)) return;
            fetchDeduped(url).then(function(data) {
                _setCache(url, data);
            }, function() { /* Prefetch-Fehler ignorieren */ });
        });
    };
    if (!window.requestIdleCallback) {
        setTimeout(run, 1000);
        return;
    }
    window.requestIdleCallback(run, { timeout: 3000 });
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
            // Breite über CSS-Klassen (w1-w4) statt inline style: die CSP
            // erlaubt nur style-src 'self', inline-Styles würden blockiert
            var w = 1 + Math.floor(Math.random() * 4);
            html += '<td><div class="skeleton-line skeleton-w' + w + '"></div></td>';
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

    // Sortierbare Spalten-Header (Maus + Tastatur)
    var sortHeaders = document.querySelectorAll('th.sortable');
    var onSort = function(ev) {
        if (ev.type === 'keydown') {
            if (ev.key !== 'Enter' && ev.key !== ' ') return;
            ev.preventDefault();
        }
        if (typeof sortBy === 'function') {
            sortBy(this.getAttribute('data-sort'));
        }
    };
    for (var i = 0; i < sortHeaders.length; i++) {
        sortHeaders[i].addEventListener('click', onSort);
        sortHeaders[i].addEventListener('keydown', onSort);
    }
});
