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
