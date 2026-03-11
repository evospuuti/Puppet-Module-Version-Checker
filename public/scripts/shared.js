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

// Event-Listener für Navigation (alle Seiten)
document.addEventListener('DOMContentLoaded', function() {
    var navToggle = document.getElementById('navToggle');
    if (navToggle) navToggle.addEventListener('click', toggleNav);

    var themeToggle = document.getElementById('themeToggle');
    if (themeToggle) themeToggle.addEventListener('click', toggleDarkMode);
});
