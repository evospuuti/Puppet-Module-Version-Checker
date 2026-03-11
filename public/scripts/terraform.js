var providers = [];
var sortColumn = 'name';
var sortAsc = true;

document.addEventListener('DOMContentLoaded', function() {
    fetchProviders();
    document.getElementById('refreshBtn').addEventListener('click', fetchProviders);
    document.getElementById('filter').addEventListener('input', filterTable);
});

async function fetchProviders() {
    document.getElementById('providerTable').innerHTML =
        '<tr><td colspan="6"><div class="loading"><div class="spinner"></div> Laden...</div></td></tr>';
    try {
        var res = await fetch('/api/terraform-providers');
        if (!res.ok) throw new Error('Server antwortet nicht (' + res.status + ')');
        providers = await res.json();
        renderTable();
        updateStats();
        updateTimestamp();
    } catch (e) {
        console.error(e);
        document.getElementById('providerTable').innerHTML =
            '<tr><td colspan="6"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></td></tr>';
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
    var filtered = providers.filter(function(p) {
        return p.name.toLowerCase().includes(filter) ||
            p.displayName.toLowerCase().includes(filter);
    });

    // Sortierung
    filtered.sort(function(a, b) {
        var valA, valB;
        if (sortColumn === 'name') { valA = a.displayName; valB = b.displayName; }
        else if (sortColumn === 'namespace') { valA = a.namespace; valB = b.namespace; }
        else if (sortColumn === 'status') { valA = getSortOrder(a.status); valB = getSortOrder(b.status); }
        else if (sortColumn === 'tracked') { valA = a.installedVersion; valB = b.installedVersion; }
        else if (sortColumn === 'registry') { valA = a.latestVersion; valB = b.latestVersion; }
        else { valA = a.displayName; valB = b.displayName; }

        if (typeof valA === 'string') {
            var cmp = valA.localeCompare(valB);
            return sortAsc ? cmp : -cmp;
        }
        return sortAsc ? valA - valB : valB - valA;
    });

    document.getElementById('providerCount').textContent = filtered.length + ' Provider';

    // Header mit Sortier-Indikatoren aktualisieren
    updateSortHeaders();

    document.getElementById('providerTable').innerHTML = filtered.map(function(p) {
        return '<tr>' +
            '<td><strong>' + escapeHtml(p.displayName) + '</strong></td>' +
            '<td class="text-muted">' + escapeHtml(p.namespace) + '</td>' +
            '<td><code>' + escapeHtml(p.installedVersion) + '</code></td>' +
            '<td><code>' + escapeHtml(p.latestVersion) + '</code></td>' +
            '<td><span class="badge ' + getBadgeClass(p.status) + '">' + getStatusText(p.status) + '</span></td>' +
            '<td><a href="' + escapeHtml(p.url) + '" target="_blank" rel="noopener noreferrer">Registry</a></td>' +
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

function getSortOrder(status) {
    if (status === 'error') return 2;
    if (status === 'outdated') return 1;
    return 0;
}

function filterTable() {
    renderTable();
}

function updateStats() {
    var current = providers.filter(function(p) { return p.status === 'current'; }).length;
    var outdated = providers.filter(function(p) { return p.status === 'outdated'; }).length;
    var errors = providers.filter(function(p) { return p.status === 'error'; }).length;

    document.getElementById('currentCount').textContent = current;
    document.getElementById('outdatedCount').textContent = outdated;
    document.getElementById('errorCount').textContent = errors;
}

function updateTimestamp() {
    var ts = document.getElementById('lastUpdated');
    if (ts) ts.textContent = 'Aktualisiert: ' + new Date().toLocaleTimeString('de-DE');
}

function getBadgeClass(status) {
    if (status === 'current') return 'badge-success';
    if (status === 'outdated') return 'badge-warning';
    return 'badge-danger';
}

function getStatusText(status) {
    if (status === 'current') return 'Aktuell';
    if (status === 'outdated') return 'Update';
    return 'Fehler';
}
