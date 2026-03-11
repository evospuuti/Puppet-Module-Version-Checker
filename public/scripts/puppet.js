var modules = [];

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
    } catch (e) {
        console.error(e);
        document.getElementById('moduleTable').innerHTML =
            '<tr><td colspan="5"><div class="error-message">Fehler beim Laden: ' + escapeHtml(e.message) + '</div></td></tr>';
    }
}

function renderTable() {
    var filter = document.getElementById('filter').value.toLowerCase();
    var filtered = modules.filter(function(m) {
        return m.name.toLowerCase().includes(filter) ||
            m.serverVersion.toLowerCase().includes(filter);
    });

    document.getElementById('moduleCount').textContent = filtered.length + ' Module';
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
