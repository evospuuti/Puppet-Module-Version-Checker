var modules = [];
var sortColumn = 'name';
var sortAsc = true;

document.addEventListener('DOMContentLoaded', function() {
    fetchModules();
    document.getElementById('refreshBtn').addEventListener('click', fetchModules);
    document.getElementById('filter').addEventListener('input', filterTable);
});

async function fetchModules() {
    document.getElementById('moduleTable').innerHTML =
        '<tr><td colspan="5"><div class="loading"><div class="spinner"></div> Laden...</div></td></tr>';
    try {
        var res = await fetch('/api/modules');
        if (!res.ok) throw new Error('Server antwortet nicht (' + res.status + ')');
        modules = await res.json();
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

    document.getElementById('moduleTable').innerHTML = filtered.map(function(m) {
        return '<tr>' +
            '<td><strong>' + escapeHtml(m.name) + '</strong></td>' +
            '<td><code>' + escapeHtml(m.serverVersion) + '</code></td>' +
            '<td><code>' + escapeHtml(m.forgeVersion) + '</code></td>' +
            '<td><span class="badge ' + getBadgeClass(m) + '">' + getStatusText(m) + '</span></td>' +
            '<td><a href="' + escapeHtml(m.url) + '" target="_blank" rel="noopener noreferrer">Forge</a></td>' +
            '</tr>';
    }).join('');
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

function filterTable() {
    renderTable();
}

function updateStats() {
    var current = modules.filter(function(m) { return m.status === 'current'; }).length;
    var outdated = modules.filter(function(m) { return m.status === 'outdated'; }).length;
    var errors = modules.filter(function(m) { return m.status === 'error' || m.deprecated; }).length;

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
