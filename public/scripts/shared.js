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

// autoresearch-Pattern: Debounce für Filter-Input
// Analog zu Gradient Accumulation - sammelt Eingaben und führt
// die teure Operation (DOM-Update) nur einmal aus.
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

// autoresearch-Pattern: Request-Deduplizierung
// Verhindert parallele identische Requests (analog zu Cache-Check
// vor Download in autoresearch's prepare.py).
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

// autoresearch-Pattern: Prefetch für nächste Seite
// Analog zu autoresearch's data prefetching (lädt nächsten Batch
// während aktuelle Daten verarbeitet werden).
function prefetchData(urls) {
    if (!window.requestIdleCallback) {
        // Fallback: nach kurzer Verzögerung prefetchen
        setTimeout(function() {
            urls.forEach(function(url) { fetchDeduped(url); });
        }, 1000);
        return;
    }
    window.requestIdleCallback(function() {
        urls.forEach(function(url) { fetchDeduped(url); });
    }, { timeout: 3000 });
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
