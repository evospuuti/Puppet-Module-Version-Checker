/**
 * Puppet Module Tracker JavaScript
 * Vergleicht Server- und Forge-Versionen von Puppet-Modulen
 */

// Server-Versionen der Puppet-Module
const serverVersions = {
    'dsc-auditpolicydsc': '1.4.0-0-9',
    'puppet-alternatives': '6.0.0',
    'puppet-archive': '7.1.0',
    'puppet-systemd': '8.2.0',
    'puppetlabs-apt': '10.0.1',
    'puppetlabs-facts': '1.7.0',
    'puppetlabs-inifile': '6.2.0',
    'puppetlabs-powershell': '6.0.2',
    'puppetlabs-registry': '5.0.3',
    'puppetlabs-stdlib': '9.7.0',
    'saz-sudo': '9.0.2',
    'puppet-ca_cert': '3.1.0'
};

// Module zum Sortieren und Filtern der Tabelle
let moduleData = [];
let currentSort = { column: null, direction: 'asc' };
let filterValue = '';

/**
 * Lädt die Moduldaten von der API und aktualisiert die Tabelle
 */
async function fetchModuleData() {
    try {
        // Daten mit Ladeanimation abrufen
        moduleData = await fetchWithLoading('/api/modules', {}, 'loadingIndicator', 'errorMessage');

        // Tabelle aktualisieren
        updateTable();

        // Erfolgsbenachrichtigung anzeigen
        showToast('Moduldaten erfolgreich aktualisiert', 'success');

        // Custom Event auslösen, um die Statuszusammenfassung zu aktualisieren
        document.dispatchEvent(new CustomEvent('modulesLoaded'));
    } catch (error) {
        console.error('Fehler beim Abrufen der Moduldaten:', error);
        // Fehler wird bereits durch fetchWithLoading angezeigt
    }
}

/**
 * Aktualisiert die Tabelle mit den aktuellen Moduldaten und berücksichtigt Sortierung und Filter
 */
function updateTable() {
    const moduleList = document.getElementById('moduleList');
    if (!moduleList) return;

    moduleList.innerHTML = '';

    // Daten filtern, wenn ein Filter gesetzt ist
    let filteredData = moduleData;
    if (filterValue) {
        const searchTerm = filterValue.toLowerCase();
        filteredData = moduleData.filter(module =>
            module.name.toLowerCase().includes(searchTerm) ||
            (module.forgeVersion && module.forgeVersion.toLowerCase().includes(searchTerm))
        );
    }

    // Daten sortieren, wenn eine Sortierung gesetzt ist
    if (currentSort.column !== null) {
        filteredData.sort((a, b) => {
            let aValue = a[currentSort.column] || '';
            let bValue = b[currentSort.column] || '';

            // Spezialfall für Versionsvergleich
            if (currentSort.column === 'forgeVersion' || currentSort.column === 'serverVersion') {
                return compareVersions(
                    currentSort.column === 'serverVersion' ? serverVersions[a.name] : aValue,
                    currentSort.column === 'serverVersion' ? serverVersions[b.name] : bValue
                ) * (currentSort.direction === 'asc' ? 1 : -1);
            }

            // Standardsortierung für andere Spalten
            return aValue.localeCompare(bValue) * (currentSort.direction === 'asc' ? 1 : -1);
        });
    }

    // Tabelle mit den gefilterten und sortierten Daten füllen
    filteredData.forEach(module => {
        const row = document.createElement('tr');
        const serverVersion = serverVersions[module.name] || 'Unbekannt';
        const comparison = compareVersions(serverVersion, module.forgeVersion);

        // Zeilenfarbe basierend auf Status
        let rowClass = '';
        if (module.deprecated) {
            rowClass = 'status-red';
        } else if (comparison < 0) {
            rowClass = 'status-yellow';
        } else {
            rowClass = 'status-green';
        }

        // Versionsstatustext
        let versionStatus = 'Aktuell';
        if (module.deprecated) {
            versionStatus = 'Deprecated';
        } else if (comparison < 0) {
            versionStatus = 'Update verfügbar';
        }

        // Zeile erstellen
        row.innerHTML = `
            <td class="px-4 py-2 border-t border-muted">${module.name}</td>
            <td class="px-4 py-2 border-t border-muted">${serverVersion}</td>
            <td class="px-4 py-2 border-t border-muted">${module.forgeVersion || 'Unbekannt'}</td>
            <td class="px-4 py-2 border-t border-muted">
                <span class="${module.deprecated ? 'text-error' : comparison < 0 ? 'text-warning' : 'text-success'}">
                    ${versionStatus}
                </span>
            </td>
            <td class="px-4 py-2 border-t border-muted">
                <a href="${module.url}" target="_blank" class="text-primary hover:underline">Forge Link</a>
            </td>
            <td class="px-4 py-2 border-t border-muted">
                <button onclick="showModuleDetails('${module.name}')" class="px-2 py-1 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors">
                    Details
                </button>
            </td>
        `;
        row.className = rowClass;
        moduleList.appendChild(row);
    });

    // Modulzähler aktualisieren
    updateModuleCounter(filteredData.length, moduleData.length);
}

/**
 * Aktualisiert den Zähler für gefilterte/gesamte Module
 */
function updateModuleCounter(filteredCount, totalCount) {
    const counter = document.getElementById('moduleCounter');
    if (counter) {
        counter.textContent = filteredCount === totalCount
            ? `${totalCount} Module geladen`
            : `${filteredCount} von ${totalCount} Modulen angezeigt`;
    }
}

/**
 * Setzt die Sortierung für eine Spalte
 */
function sortBy(column) {
    // Beim Klick auf die gleiche Spalte Sortierrichtung umkehren
    if (currentSort.column === column) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.column = column;
        currentSort.direction = 'asc';
    }

    // Sortierungsindikatoren aktualisieren
    updateSortIndicators();

    // Tabelle mit neuer Sortierung aktualisieren
    updateTable();
}

/**
 * Aktualisiert die Sortierungsindikatoren in der Tabelle
 */
function updateSortIndicators() {
    // Alle Sortiersymbole zurücksetzen
    const headers = document.querySelectorAll('#moduleTable th[data-sort]');
    headers.forEach(header => {
        const sortSpan = header.querySelector('.sort-indicator');
        if (sortSpan) {
            sortSpan.textContent = '';
        }
    });

    // Aktuelles Sortiersymbol setzen
    if (currentSort.column !== null) {
        const activeHeader = document.querySelector(`#moduleTable th[data-sort="${currentSort.column}"]`);
        if (activeHeader) {
            const sortSpan = activeHeader.querySelector('.sort-indicator');
            if (sortSpan) {
                sortSpan.textContent = currentSort.direction === 'asc' ? ' ↑' : ' ↓';
            }
        }
    }
}

/**
 * Filtert die Tabelle basierend auf dem Suchbegriff
 */
function filterTable() {
    filterValue = document.getElementById('moduleFilter').value;
    updateTable();
}

/**
 * Zeigt Details eines Moduls in einem Modal-Dialog an
 */
function showModuleDetails(moduleName) {
    const module = moduleData.find(m => m.name === moduleName);
    if (!module) return;

    const serverVersion = serverVersions[module.name] || 'Unbekannt';
    const comparison = compareVersions(serverVersion, module.forgeVersion);

    // Status-Klasse und Text
    let statusClass = 'text-success';
    let statusText = 'Aktuell';

    if (module.deprecated) {
        statusClass = 'text-error';
        statusText = 'Deprecated';
    } else if (comparison < 0) {
        statusClass = 'text-warning';
        statusText = 'Update verfügbar';
    }

    // Modal-Inhalt erstellen
    const modalContent = `
        <div class="bg-card rounded-lg shadow-lg max-w-3xl mx-auto">
            <div class="p-4 bg-muted flex justify-between items-center rounded-t-lg">
                <h3 class="text-xl font-bold">${module.name}</h3>
                <button onclick="closeModal()" class="text-muted-foreground hover:text-foreground" aria-label="Schließen">
                    &times;
                </button>
            </div>
            <div class="p-6">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                    <div>
                        <h4 class="text-sm font-medium text-muted-foreground mb-1">Server Version</h4>
                        <p class="text-lg font-medium">${serverVersion}</p>
                    </div>
                    <div>
                        <h4 class="text-sm font-medium text-muted-foreground mb-1">Forge Version</h4>
                        <p class="text-lg font-medium">${module.forgeVersion || 'Unbekannt'}</p>
                    </div>
                    <div>
                        <h4 class="text-sm font-medium text-muted-foreground mb-1">Status</h4>
                        <p class="text-lg font-medium ${statusClass}">${statusText}</p>
                    </div>
                    <div>
                        <h4 class="text-sm font-medium text-muted-foreground mb-1">Deprecated</h4>
                        <p class="text-lg font-medium">${module.deprecated ? 'Ja' : 'Nein'}</p>
                    </div>
                </div>
                
                <div class="mb-4">
                    <h4 class="text-sm font-medium text-muted-foreground mb-1">Forge Link</h4>
                    <a href="${module.url}" target="_blank" class="text-primary hover:underline">${module.url}</a>
                </div>
                
                ${comparison < 0 ? `
                <div class="bg-yellow-50 dark:bg-yellow-900/30 border-l-4 border-warning p-4 mb-4">
                    <h4 class="font-bold">Update empfohlen</h4>
                    <p>Die installierte Version ist ${Math.abs(comparison)} Version(en) hinter der aktuellen Version zurück.</p>
                </div>
                ` : ''}
                
                ${module.deprecated ? `
                <div class="bg-red-50 dark:bg-red-900/30 border-l-4 border-error p-4 mb-4">
                    <h4 class="font-bold">Modul Deprecated</h4>
                    <p>Dieses Modul wird nicht mehr gepflegt und sollte ersetzt werden.</p>
                </div>
                ` : ''}
                
                <div class="flex justify-end mt-6">
                    <button onclick="closeModal()" class="px-4 py-2 bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/90 transition-colors">
                        Schließen
                    </button>
                </div>
            </div>
        </div>
    `;

    // Modal anzeigen
    const modalContainer = document.getElementById('modalContainer');
    if (modalContainer) {
        modalContainer.innerHTML = modalContent;
        modalContainer.classList.remove('hidden');
    }
}

/**
 * Schließt den Modal-Dialog
 */
function closeModal() {
    const modalContainer = document.getElementById('modalContainer');
    if (modalContainer) {
        modalContainer.classList.add('hidden');
    }
}

/**
 * Initialisiert die Seite
 */
document.addEventListener('DOMContentLoaded', () => {
    // Event-Listener für Filter-Input
    const filterInput = document.getElementById('moduleFilter');
    if (filterInput) {
        filterInput.addEventListener('input', filterTable);
    }

    // Event-Listener für sortierbare Spalten
    const sortableHeaders = document.querySelectorAll('#moduleTable th[data-sort]');
    sortableHeaders.forEach(header => {
        header.addEventListener('click', () => {
            sortBy(header.getAttribute('data-sort'));
        });
    });

    // Initialen Tabellendaten laden
    fetchModuleData();
});