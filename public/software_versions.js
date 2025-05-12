/**
 * Software Versions Tracker JavaScript
 * Verwaltet Software-Versionen und deren Updates
 */

// Speichert die aktuellen Software-Daten
let softwareData = [];
let editingIndex = -1;

/**
 * Lädt die Software-Daten vom Server
 */
async function loadSoftwareData() {
    try {
        // Daten mit Ladeanimation abrufen
        softwareData = await fetchWithLoading('/api/software_versions', {}, 'loadingIndicator', 'errorMessage');

        // Tabelle und Counter aktualisieren
        updateTable();
        updateCounter();

        // Erfolgsbenachrichtigung anzeigen
        showToast('Software-Daten erfolgreich geladen', 'success');
    } catch (error) {
        console.error('Fehler beim Laden der Software-Daten:', error);
        showEmptyState(true);
        // Fehler wird bereits durch fetchWithLoading angezeigt
    }
}

/**
 * Aktualisiert die Tabelle mit den aktuellen Software-Daten
 */
function updateTable() {
    const tableBody = document.getElementById('softwareList');
    if (!tableBody) return;

    // Tabelle leeren
    tableBody.innerHTML = '';

    // Gefilterte Daten erhalten
    const filteredData = getFilteredData();

    // Empty state anzeigen, wenn keine Daten vorhanden sind
    if (filteredData.length === 0) {
        showEmptyState(true);
        return;
    }

    // Empty state ausblenden
    showEmptyState(false);

    // Tabelle mit gefilterten Daten füllen
    filteredData.forEach((software, index) => {
        const row = document.createElement('tr');

        // Prüfen, ob die Software veraltet ist (länger als 3 Monate nicht aktualisiert)
        const lastUpdatedDate = new Date(software.lastUpdated);
        const threeMonthsAgo = new Date();
        threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);

        // Status-Klasse basierend auf dem Software-Status
        let statusClass = '';
        if (software.status === 'Veraltet') {
            statusClass = 'text-error';
        } else if (software.status === 'Update verfügbar') {
            statusClass = 'text-warning';
        } else {
            statusClass = 'text-success';
        }

        // Zeile erstellen
        row.innerHTML = `
            <td class="px-4 py-2 border-t border-muted">${software.name}</td>
            <td class="px-4 py-2 border-t border-muted">${software.currentVersion}</td>
            <td class="px-4 py-2 border-t border-muted">${software.category || 'Sonstiges'}</td>
            <td class="px-4 py-2 border-t border-muted">${formatDate(software.lastUpdated)}</td>
            <td class="px-4 py-2 border-t border-muted">
                <span class="${statusClass}">${software.status}</span>
            </td>
            <td class="px-4 py-2 border-t border-muted">
                <div class="flex space-x-2">
                    <button onclick="showSoftwareDetails(${index})" class="px-2 py-1 bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/90 transition-colors">
                        Details
                    </button>
                    <button onclick="editSoftware(${index})" class="px-2 py-1 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors">
                        Bearbeiten
                    </button>
                    <button onclick="confirmDeleteSoftware(${index})" class="px-2 py-1 bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 transition-colors">
                        Löschen
                    </button>
                </div>
            </td>
        `;

        // Zusätzliche Klasse für veraltete Software
        if (lastUpdatedDate < threeMonthsAgo) {
            row.classList.add('status-yellow');
        }

        // Je nach Status in verschiendenen Farben anzeigen
        if (software.status === 'Veraltet') {
            row.classList.add('status-red');
        } else if (software.status === 'Update verfügbar') {
            row.classList.add('status-yellow');
        }

        tableBody.appendChild(row);
    });

    // Update the software counter
    updateCounter(filteredData.length);
}

/**
 * Zeigt den Empty State an oder blendet ihn aus
 */
function showEmptyState(show) {
    const emptyState = document.getElementById('emptyState');
    if (emptyState) {
        emptyState.classList.toggle('hidden', !show);
    }
}

/**
 * Aktualisiert den Software-Zähler
 */
function updateCounter(filteredCount) {
    const counter = document.getElementById('softwareCounter');
    if (counter) {
        const total = softwareData.length;
        if (filteredCount !== undefined && filteredCount !== total) {
            counter.textContent = `${filteredCount} von ${total} Software-Einträgen`;
        } else {
            counter.textContent = `${total} Software-Einträge`;
        }
    }
}

/**
 * Filtert die Software-Daten basierend auf den aktuellen Filter-Einstellungen
 */
function getFilteredData() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const categoryFilter = document.getElementById('categoryFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;

    return softwareData.filter(software => {
        // Suche nach Name, Version oder Notizen
        const matchesSearch = !searchTerm ||
            software.name.toLowerCase().includes(searchTerm) ||
            software.currentVersion.toLowerCase().includes(searchTerm) ||
            (software.notes && software.notes.toLowerCase().includes(searchTerm));

        // Filter nach Kategorie
        const matchesCategory = !categoryFilter || software.category === categoryFilter;

        // Filter nach Status
        const matchesStatus = !statusFilter || software.status === statusFilter;

        return matchesSearch && matchesCategory && matchesStatus;
    });
}

/**
 * Filtert die Tabelle basierend auf den Suchkriterien
 */
function filterSoftware() {
    updateTable();
}

/**
 * Zeigt die Details einer Software in einem Modal an
 */
function showSoftwareDetails(index) {
    const software = softwareData[index];
    if (!software) return;

    // Status-Klasse basierend auf dem Software-Status
    let statusClass = '';
    let statusIcon = '';

    if (software.status === 'Veraltet') {
        statusClass = 'text-error';
        statusIcon = `
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        `;
    } else if (software.status === 'Update verfügbar') {
        statusClass = 'text-warning';
        statusIcon = `
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
        `;
    } else {
        statusClass = 'text-success';
        statusIcon = `
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
        `;
    }

    // Modal-Inhalt erstellen
    document.getElementById('modalTitle').textContent = software.name;

    document.getElementById('modalContent').innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
                <h4 class="text-sm font-medium text-muted-foreground mb-1">Version</h4>
                <p class="text-lg font-medium">${software.currentVersion}</p>
            </div>
            <div>
                <h4 class="text-sm font-medium text-muted-foreground mb-1">Kategorie</h4>
                <p class="text-lg font-medium">${software.category || 'Sonstiges'}</p>
            </div>
            <div>
                <h4 class="text-sm font-medium text-muted-foreground mb-1">Letzte Aktualisierung</h4>
                <p class="text-lg font-medium">${formatDate(software.lastUpdated)}</p>
            </div>
            <div>
                <h4 class="text-sm font-medium text-muted-foreground mb-1">Status</h4>
                <p class="flex items-center text-lg font-medium ${statusClass}">
                    ${statusIcon}
                    ${software.status}
                </p>
            </div>
        </div>
        
        ${software.link ? `
        <div class="mb-4">
            <h4 class="text-sm font-medium text-muted-foreground mb-1">Software Link</h4>
            <a href="${software.link}" target="_blank" class="text-primary hover:underline">${software.link}</a>
        </div>
        ` : ''}
        
        ${software.notes ? `
        <div class="mb-4">
            <h4 class="text-sm font-medium text-muted-foreground mb-1">Notizen</h4>
            <p class="text-foreground">${software.notes}</p>
        </div>
        ` : ''}
        
        <!-- Überprüfen, ob ein Update-Hinweis angezeigt werden sollte -->
        ${software.status === 'Update verfügbar' ? `
        <div class="bg-yellow-50 dark:bg-yellow-900/30 border-l-4 border-warning p-4 mb-4">
            <h4 class="font-bold">Update verfügbar</h4>
            <p>Es ist ein Update für diese Software verfügbar. Bitte prüfen Sie die Website des Herstellers für weitere Informationen.</p>
        </div>
        ` : ''}
        
        ${software.status === 'Veraltet' ? `
        <div class="bg-red-50 dark:bg-red-900/30 border-l-4 border-error p-4 mb-4">
            <h4 class="font-bold">Software veraltet</h4>
            <p>Diese Software ist veraltet und sollte dringend aktualisiert werden. Fehlende Updates können Sicherheitsrisiken darstellen.</p>
        </div>
        ` : ''}
        
        <div class="flex justify-end mt-6 space-x-2">
            <button onclick="editSoftware(${index})" class="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors">
                Bearbeiten
            </button>
            <button onclick="closeModal()" class="px-4 py-2 bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/90 transition-colors">
                Schließen
            </button>
        </div>
    `;

    // Modal öffnen
    document.getElementById('modalContainer').classList.remove('hidden');
}

/**
 * Schließt das Modal-Fenster
 */
function closeModal() {
    document.getElementById('modalContainer').classList.add('hidden');
}

/**
 * Setzt ein Software-Objekt zum Bearbeiten
 */
function editSoftware(index) {
    // Modal schließen, falls geöffnet
    closeModal();

    // Index für das Bearbeiten speichern
    editingIndex = index;

    // Software-Objekt abrufen
    const software = softwareData[index];
    if (!software) return;

    // Formularfelder mit den Werten füllen
    document.getElementById('softwareName').value = software.name;
    document.getElementById('currentVersion').value = software.currentVersion;
    document.getElementById('category').value = software.category || 'Sonstiges';
    document.getElementById('lastUpdated').value = software.lastUpdated ? software.lastUpdated.split('T')[0] : '';
    document.getElementById('status').value = software.status;
    document.getElementById('softwareLink').value = software.link || '';
    document.getElementById('notes').value = software.notes || '';

    // Submit-Button-Text ändern und Cancel-Button anzeigen
    document.getElementById('submitButton').textContent = 'Aktualisieren';
    document.getElementById('cancelButton').classList.remove('hidden');

    // Zum Formular scrollen
    document.getElementById('softwareForm').scrollIntoView({ behavior: 'smooth' });
}

/**
 * Setzt das Formular zurück (für Abbrechen oder nach dem Hinzufügen/Aktualisieren)
 */
function resetForm() {
    // Formular zurücksetzen
    document.getElementById('softwareForm').reset();

    // Bearbeitungsindex zurücksetzen
    editingIndex = -1;

    // Submit-Button-Text zurücksetzen und Cancel-Button ausblenden
    document.getElementById('submitButton').textContent = 'Hinzufügen';
    document.getElementById('cancelButton').classList.add('hidden');
}

/**
 * Fügt eine neue Software hinzu oder aktualisiert eine bestehende
 */
async function submitSoftwareForm(event) {
    // Standardverhalten des Formulars verhindern
    event.preventDefault();

    // Daten aus Formular abrufen
    const software = {
        name: document.getElementById('softwareName').value,
        currentVersion: document.getElementById('currentVersion').value,
        category: document.getElementById('category').value,
        lastUpdated: document.getElementById('lastUpdated').value,
        status: document.getElementById('status').value,
        link: document.getElementById('softwareLink').value,
        notes: document.getElementById('notes').value
    };

    try {
        if (editingIndex === -1) {
            // Neue Software hinzufügen
            await fetch('/api/software_versions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(software)
            });

            showToast('Software erfolgreich hinzugefügt', 'success');
        } else {
            // Bestehende Software aktualisieren
            await fetch(`/api/software_versions/${editingIndex}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(software)
            });

            showToast('Software erfolgreich aktualisiert', 'success');
        }

        // Formular zurücksetzen und Daten neu laden
        resetForm();
        await loadSoftwareData();
    } catch (error) {
        console.error('Fehler beim Speichern der Software:', error);
        showToast('Fehler beim Speichern der Software', 'error');
    }
}

/**
 * Bestätigung vor dem Löschen einer Software anzeigen
 */
function confirmDeleteSoftware(index) {
    if (confirm('Sind Sie sicher, dass Sie diese Software löschen möchten?')) {
        deleteSoftware(index);
    }
}

/**
 * Löscht eine Software
 */
async function deleteSoftware(index) {
    try {
        // Software löschen
        await fetch(`/api/software_versions/${index}`, {
            method: 'DELETE'
        });

        // Erfolgsmeldung anzeigen und Daten neu laden
        showToast('Software erfolgreich gelöscht', 'success');
        await loadSoftwareData();
    } catch (error) {
        console.error('Fehler beim Löschen der Software:', error);
        showToast('Fehler beim Löschen der Software', 'error');
    }
}

/**
 * Exportiert die Tabelle als CSV-Datei
 */
function exportTableToCSV(tableId, filename) {
    // Filterdaten verwenden, um nur die gefilterten Daten zu exportieren
    const filteredData = getFilteredData();

    // CSV-Header
    const header = ['Software', 'Version', 'Kategorie', 'Letzte Aktualisierung', 'Status', 'Link', 'Notizen'];

    // CSV-Zeilen
    const rows = filteredData.map(software => [
        software.name,
        software.currentVersion,
        software.category || 'Sonstiges',
        formatDate(software.lastUpdated),
        software.status,
        software.link || '',
        software.notes || ''
    ]);

    // CSV-Inhalt erstellen
    const csvContent = [
        header.map(cell => `"${cell}"`).join(','),
        ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    ].join('\n');

    // Download-Link erstellen
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast('CSV-Export erfolgreich', 'success');
}

// Event-Listener für das Formular
document.addEventListener('DOMContentLoaded', () => {
    // Daten laden
    loadSoftwareData();

    // Formular-Submit-Event
    document.getElementById('softwareForm').addEventListener('submit', submitSoftwareForm);

    // Heutiges Datum als Standardwert für das Datum-Feld setzen
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('lastUpdated').value = today;
});