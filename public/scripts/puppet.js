var modules = [];
var sortColumn = 'name';
var sortAsc = true;

// autoresearch-Pattern: Debounced Filter
// Analog zu Gradient Accumulation: Input-Events sammeln und
// DOM-Update erst nach Eingabepause ausführen.
var debouncedFilter = debounce(function() { renderTable(); }, 150);

document.addEventListener('DOMContentLoaded', function() {
    fetchModules();
    document.getElementById('refreshBtn').addEventListener('click', fetchModules);
    document.getElementById('filter').addEventListener('input', debouncedFilter);
});

async function fetchModules() {
    document.getElementById('moduleTable').innerHTML =
        '<tr><td colspan="5"><div class="loading"><div class="spinner"></div> Laden...</div></td></tr>';
    try {
        modules = await fetchDeduped('/api/modules');
        renderTable();
        updateStats();
        updateTimestamp();
    } catch (e) {
        console.error(e);
        document.getElementById('moduleTable').innerHTML =
            '<tr><td colspan="5"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></td></tr>';
    }
}

function sortBy(column) {
    if (sortColumn === column) {
        sortAsc = !sortAsc;
    } else {
        sortColumn = column;
        sortAsc = true;
    }
    renderTable();
}

function renderTable() {
    var filter = document.getElementById('filter').value.toLowerCase();
    var filtered = modules.filter(function(m) {
        return m.name.toLowerCase().includes(filter) ||
            m.serverVersion.toLowerCase().includes(filter);
    });

    // Sortierung
    filtered.sort(function(a, b) {
        var valA, valB;
        if (sortColumn === 'name') { valA = a.name; valB = b.name; }
        else if (sortColumn === 'status') { valA = getSortOrder(a); valB = getSortOrder(b); }
        else if (sortColumn === 'tracked') { valA = a.serverVersion; valB = b.serverVersion; }
        else if (sortColumn === 'forge') { valA = a.forgeVersion; valB = b.forgeVersion; }
        else { valA = a.name; valB = b.name; }

        if (typeof valA === 'string') {
            var cmp = valA.localeCompare(valB);
            return sortAsc ? cmp : -cmp;
        }
        return sortAsc ? valA - valB : valB - valA;
    });

    document.getElementById('moduleCount').textContent = filtered.length + ' Module';

    // Header mit Sortier-Indikatoren aktualisieren
    updateSortHeaders();

    // autoresearch-Pattern: DOM-Batch-Update via DocumentFragment
    // Alle Zeilen im Fragment aufbauen, dann in einem Reflow einfügen.
    var fragment = document.createDocumentFragment();
    for (var i = 0; i < filtered.length; i++) {
        var m = filtered[i];
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td><strong>' + escapeHtml(m.name) + '</strong></td>' +
            '<td><code>' + escapeHtml(m.serverVersion) + '</code></td>' +
            '<td><code>' + escapeHtml(m.forgeVersion) + '</code></td>' +
            '<td><span class="badge ' + getBadgeClass(m) + '">' + getStatusText(m) + '</span></td>' +
            '<td><a href="' + escapeHtml(m.url) + '" target="_blank" rel="noopener noreferrer">Forge</a></td>';
        fragment.appendChild(tr);
    }
    var table = document.getElementById('moduleTable');
    table.textContent = '';
    table.appendChild(fragment);
}

function updateSortHeaders() {
    var headers = document.querySelectorAll('th[data-sort]');
    for (var i = 0; i < headers.length; i++) {
        var th = headers[i];
        var col = th.getAttribute('data-sort');
        var base = th.getAttribute('data-label');
        if (col === sortColumn) {
            th.textContent = base + (sortAsc ? ' \u25B2' : ' \u25BC');
        } else {
            th.textContent = base;
        }
    }
}

function getSortOrder(m) {
    if (m.deprecated) return 3;
    if (m.status === 'error') return 2;
    if (m.status === 'outdated') return 1;
    return 0;
}

function updateStats() {
    var current = 0, outdated = 0, errors = 0;
    for (var i = 0; i < modules.length; i++) {
        if (modules[i].status === 'current') current++;
        else if (modules[i].status === 'outdated') outdated++;
        else if (modules[i].status === 'error' || modules[i].deprecated) errors++;
    }
    document.getElementById('currentCount').textContent = current;
    document.getElementById('outdatedCount').textContent = outdated;
    document.getElementById('errorCount').textContent = errors;
}

function updateTimestamp() {
    var ts = document.getElementById('lastUpdated');
    if (ts) ts.textContent = 'Aktualisiert: ' + new Date().toLocaleTimeString('de-DE');
}

function getBadgeClass(m) {
    if (m.deprecated) return 'badge-danger';
    if (m.status === 'current') return 'badge-success';
    if (m.status === 'outdated') return 'badge-warning';
    return 'badge-danger';
}

function getStatusText(m) {
    if (m.deprecated) return 'Deprecated';
    if (m.status === 'current') return 'Aktuell';
    if (m.status === 'outdated') return 'Update';
    return 'Fehler';
}
