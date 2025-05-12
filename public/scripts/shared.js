/**
 * Gemeinsame JavaScript-Funktionen für alle Seiten des System Trackers
 * Enthält Theme-Management, Toast-Benachrichtigungen und Hilfsfunktionen
 */

// Theme Management
function toggleDarkMode() {
    const isDarkMode = document.documentElement.classList.toggle('dark');
    localStorage.setItem('darkMode', isDarkMode);
    updateButtonText(isDarkMode);
}

function updateButtonText(isDarkMode) {
    const button = document.getElementById('darkModeToggle');
    if (button) {
        button.textContent = isDarkMode ? 'Light Mode' : 'Dark Mode';
        button.setAttribute('aria-label', isDarkMode ? 'Zu Light Mode wechseln' : 'Zu Dark Mode wechseln');
    }
}

function initializeTheme() {
    // Check for saved preference or use system preference
    const savedTheme = localStorage.getItem('darkMode');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    const shouldUseDarkMode = savedTheme === 'true' || (savedTheme === null && prefersDark);

    if (shouldUseDarkMode) {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }

    updateButtonText(shouldUseDarkMode);
}

// Toast Notifications System
function createToastContainer() {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    return container;
}

function showToast(message, type = 'info', duration = 3000) {
    const container = createToastContainer();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button aria-label="Schließen" class="close-btn">&times;</button>
    `;

    container.appendChild(toast);

    // Add close button functionality
    const closeBtn = toast.querySelector('.close-btn');
    closeBtn.addEventListener('click', () => {
        container.removeChild(toast);
    });

    // Auto-remove after duration
    setTimeout(() => {
        if (container.contains(toast)) {
            container.removeChild(toast);
        }
    }, duration);
}

// Response Handling Helpers
function handleApiResponse(response, successCallback, errorMessage = 'Ein Fehler ist aufgetreten') {
    if (response.ok) {
        successCallback();
    } else {
        showToast(errorMessage, 'error');
        console.error('API Error:', response.status, response.statusText);
    }
}

async function fetchWithLoading(url, options, loadingElId, errorElId = null) {
    const loadingEl = document.getElementById(loadingElId);
    const errorEl = errorElId ? document.getElementById(errorElId) : null;

    if (loadingEl) loadingEl.classList.remove('hidden');
    if (errorEl) errorEl.classList.add('hidden');

    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        if (errorEl) {
            errorEl.textContent = 'Fehler beim Laden der Daten. Bitte versuchen Sie es später erneut.';
            errorEl.classList.remove('hidden');
        } else {
            showToast('Fehler beim Laden der Daten', 'error');
        }
        throw error;
    } finally {
        if (loadingEl) loadingEl.classList.add('hidden');
    }
}

// Date Formatting
function formatDate(dateString) {
    if (!dateString) return 'Unbekannt';

    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;

    return date.toLocaleDateString('de-DE', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

// Responsive Navigation
function setupMobileNav() {
    const mobileNavToggle = document.getElementById('mobileNavToggle');
    const navLinks = document.querySelector('.nav-mobile');

    if (mobileNavToggle && navLinks) {
        mobileNavToggle.addEventListener('click', () => {
            navLinks.classList.toggle('hidden');
        });
    }
}

// Version Comparison
function compareVersions(v1, v2) {
    if (!v1 || !v2) return 0;

    const parts1 = v1.replace(/^v/, '').split('-')[0].split('.').map(Number);
    const parts2 = v2.replace(/^v/, '').split('-')[0].split('.').map(Number);

    // Fill with zeros if needed
    while (parts1.length < 3) parts1.push(0);
    while (parts2.length < 3) parts2.push(0);

    for (let i = 0; i < 3; i++) {
        if (parts1[i] > parts2[i]) return 1;
        if (parts1[i] < parts2[i]) return -1;
    }

    return 0;
}

// Date Difference in Years
function getYearDifference(date1, date2) {
    const d1 = new Date(date1);
    const d2 = new Date(date2);

    if (isNaN(d1.getTime()) || isNaN(d2.getTime())) {
        return 0;
    }

    const diffTime = Math.abs(d2 - d1);
    const diffYears = diffTime / (1000 * 60 * 60 * 24 * 365.25);

    return diffYears;
}

// Table Sorting
function sortTable(table, column, type = 'string') {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aValue = a.cells[column].textContent.trim();
        const bValue = b.cells[column].textContent.trim();

        if (type === 'number') {
            return parseFloat(aValue) - parseFloat(bValue);
        } else if (type === 'date') {
            return new Date(aValue) - new Date(bValue);
        } else {
            return aValue.localeCompare(bValue);
        }
    });

    // Clear and append sorted rows
    while (tbody.firstChild) {
        tbody.removeChild(tbody.firstChild);
    }

    rows.forEach(row => tbody.appendChild(row));
}

// Initialize common functionality
document.addEventListener('DOMContentLoaded', () => {
    initializeTheme();
    setupMobileNav();

    // Expose functions to global scope
    window.toggleDarkMode = toggleDarkMode;
    window.showToast = showToast;
    window.formatDate = formatDate;
    window.compareVersions = compareVersions;
    window.sortTable = sortTable;
});