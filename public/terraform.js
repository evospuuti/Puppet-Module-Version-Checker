/**
 * Terraform Provider Tracker - Frontend Logic
 */

// Globale Variablen
let providerData = [];
let currentSortColumn = 'displayName';
let currentSortDirection = 'asc';

/**
 * Initialisierung beim Laden der Seite
 */
document.addEventListener('DOMContentLoaded', () => {
    // Provider-Daten laden
    fetchProviderData();

    // Filter-Event-Listener
    const filterInput = document.getElementById('providerFilter');
    if (filterInput) {
        filterInput.addEventListener('input', filterProviders);
    }

    // Sortier-Event-Listener für Tabellenköpfe
    const headers = document.querySelectorAll('#providerTable th[data-sort]');
    headers.forEach(header => {
        header.addEventListener('click', () => {
            const column = header.dataset.sort;
            sortProviders(column);
        });
    });
});

/**
 * Ruft Provider-Daten vom Server ab
 */
async function fetchProviderData() {
    const loadingIndicator = document.getElementById('loadingIndicator');
    const errorMessage = document.getElementById('errorMessage');
    const providerList = document.getElementById('providerList');

    try {
        // Loading-Indikator anzeigen
        if (loadingIndicator) loadingIndicator.classList.remove('hidden');
        if (errorMessage) errorMessage.classList.add('hidden');
        if (providerList) providerList.innerHTML = '';

        const response = await fetch('/api/terraform-providers');

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        providerData = await response.json();

        // Tabelle aktualisieren
        updateProviderTable();

        // Status-Zusammenfassung aktualisieren
        updateStatusSummary();

        // Counter aktualisieren
        updateProviderCounter();

        showToast('Provider-Daten erfolgreich geladen', 'success');

    } catch (error) {
        console.error('Fehler beim Laden der Provider-Daten:', error);
        if (errorMessage) {
            errorMessage.textContent = `Fehler beim Laden der Daten: ${error.message}`;
            errorMessage.classList.remove('hidden');
        }
        showToast('Fehler beim Laden der Provider-Daten', 'error');
    } finally {
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
    }
}

/**
 * Aktualisiert die Provider-Tabelle
 */
function updateProviderTable() {
    const providerList = document.getElementById('providerList');
    if (!providerList) return;

    // Filter anwenden
    const filterInput = document.getElementById('providerFilter');
    const filterValue = filterInput ? filterInput.value.toLowerCase() : '';

    let filteredData = providerData.filter(provider => {
        const searchString = `${provider.name} ${provider.displayName} ${provider.namespace} ${provider.installedVersion} ${provider.latestVersion}`.toLowerCase();
        return searchString.includes(filterValue);
    });

    // Sortieren
    filteredData = sortData(filteredData, currentSortColumn, currentSortDirection);

    // Tabelle rendern
    providerList.innerHTML = filteredData.map(provider => createProviderRow(provider)).join('');

    // Sort-Indikatoren aktualisieren
    updateSortIndicators();
}

/**
 * Erstellt eine Tabellenzeile für einen Provider
 */
function createProviderRow(provider) {
    const statusClass = getStatusClass(provider.status);
    const statusText = getStatusText(provider.status);

    return `
        <tr class="${statusClass}">
            <td class="px-4 py-3 border-t border-muted font-medium">${provider.displayName}</td>
            <td class="px-4 py-3 border-t border-muted text-muted-foreground">${provider.namespace}</td>
            <td class="px-4 py-3 border-t border-muted">
                <code class="bg-muted px-2 py-1 rounded text-sm">${provider.installedVersion}</code>
            </td>
            <td class="px-4 py-3 border-t border-muted">
                <code class="bg-muted px-2 py-1 rounded text-sm">${provider.latestVersion}</code>
            </td>
            <td class="px-4 py-3 border-t border-muted">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusBadgeClass(provider.status)}">
                    ${statusText}
                </span>
            </td>
            <td class="px-4 py-3 border-t border-muted">
                <a href="${provider.url}" target="_blank" rel="noopener noreferrer"
                   class="text-primary hover:underline inline-flex items-center">
                    Registry
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                </a>
            </td>
        </tr>
    `;
}

/**
 * Gibt die CSS-Klasse für den Zeilenhintergrund zurück
 */
function getStatusClass(status) {
    switch (status) {
        case 'current':
            return 'bg-green-50 dark:bg-green-900/20';
        case 'outdated':
            return 'bg-yellow-50 dark:bg-yellow-900/20';
        case 'error':
            return 'bg-red-50 dark:bg-red-900/20';
        default:
            return '';
    }
}

/**
 * Gibt die CSS-Klasse für das Status-Badge zurück
 */
function getStatusBadgeClass(status) {
    switch (status) {
        case 'current':
            return 'bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-100';
        case 'outdated':
            return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-800 dark:text-yellow-100';
        case 'error':
            return 'bg-red-100 text-red-800 dark:bg-red-800 dark:text-red-100';
        default:
            return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-100';
    }
}

/**
 * Gibt den Statustext zurück
 */
function getStatusText(status) {
    switch (status) {
        case 'current':
            return 'Aktuell';
        case 'outdated':
            return 'Update verfügbar';
        case 'error':
            return 'Fehler';
        default:
            return 'Unbekannt';
    }
}

/**
 * Filtert die Provider-Tabelle
 */
function filterProviders() {
    updateProviderTable();
}

/**
 * Sortiert die Provider nach einer Spalte
 */
function sortProviders(column) {
    if (currentSortColumn === column) {
        // Richtung umkehren
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = column;
        currentSortDirection = 'asc';
    }

    updateProviderTable();
}

/**
 * Sortiert die Daten
 */
function sortData(data, column, direction) {
    return [...data].sort((a, b) => {
        let valueA = a[column] || '';
        let valueB = b[column] || '';

        // Strings vergleichen
        if (typeof valueA === 'string') {
            valueA = valueA.toLowerCase();
            valueB = valueB.toLowerCase();
        }

        let comparison = 0;
        if (valueA < valueB) comparison = -1;
        if (valueA > valueB) comparison = 1;

        return direction === 'desc' ? -comparison : comparison;
    });
}

/**
 * Aktualisiert die Sort-Indikatoren in den Tabellenköpfen
 */
function updateSortIndicators() {
    const headers = document.querySelectorAll('#providerTable th[data-sort]');

    headers.forEach(header => {
        const indicator = header.querySelector('.sort-indicator');
        if (!indicator) return;

        if (header.dataset.sort === currentSortColumn) {
            indicator.textContent = currentSortDirection === 'asc' ? ' ▲' : ' ▼';
        } else {
            indicator.textContent = '';
        }
    });
}

/**
 * Aktualisiert die Status-Zusammenfassung
 */
function updateStatusSummary() {
    if (!providerData || providerData.length === 0) return;

    let upToDateCount = 0;
    let updateAvailableCount = 0;
    let errorCount = 0;

    providerData.forEach(provider => {
        switch (provider.status) {
            case 'current':
                upToDateCount++;
                break;
            case 'outdated':
                updateAvailableCount++;
                break;
            case 'error':
                errorCount++;
                break;
        }
    });

    const upToDateEl = document.getElementById('upToDateCount');
    const updateAvailableEl = document.getElementById('updateAvailableCount');
    const errorEl = document.getElementById('errorCount');

    if (upToDateEl) upToDateEl.textContent = upToDateCount;
    if (updateAvailableEl) updateAvailableEl.textContent = updateAvailableCount;
    if (errorEl) errorEl.textContent = errorCount;
}

/**
 * Aktualisiert den Provider-Counter
 */
function updateProviderCounter() {
    const counter = document.getElementById('providerCounter');
    if (counter && providerData) {
        counter.textContent = `${providerData.length} Provider geladen`;
    }
}
