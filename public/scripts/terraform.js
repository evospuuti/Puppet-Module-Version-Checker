var providers = [];

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
    } catch (e) {
        console.error(e);
        document.getElementById('providerTable').innerHTML =
            '<tr><td colspan="6"><div class="error-message">Fehler beim Laden: ' + escapeHtml(e.message) + '</div></td></tr>';
    }
}

function renderTable() {
    var filter = document.getElementById('filter').value.toLowerCase();
    var filtered = providers.filter(function(p) {
        return p.name.toLowerCase().includes(filter) ||
            p.displayName.toLowerCase().includes(filter);
    });

    document.getElementById('providerCount').textContent = filtered.length + ' Provider';
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
