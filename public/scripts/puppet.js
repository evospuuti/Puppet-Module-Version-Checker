var modules = [];
var sortColumn = 'name';
var sortAsc = true;

var debouncedFilter = debounce(function() { renderTable(); }, 150);

document.addEventListener('DOMContentLoaded', function() {
    fetchModules(false);
    document.getElementById('refreshBtn').addEventListener('click', function() {
        // Manueller Refresh: Cache umgehen, vorhandene Daten bleiben sichtbar
        fetchModules(true);
    });
    document.getElementById('filter').addEventListener('input', debouncedFilter);
});

function fetchModules(force) {
    var btn = document.getElementById('refreshBtn');
    var ts = document.getElementById('lastUpdated');
    setBusy(btn, true);

    return fetchSWR('/api/modules',
        // onData: Daten anzeigen (cached oder frisch)
        function(data, isFresh) {
            modules = (data || []).map(function(m) {
                // Suchtext einmal vorberechnen statt pro Tastendruck
                m._search = (m.name + ' ' + m.serverVersion + ' ' + m.forgeVersion).toLowerCase();
                return m;
            });
            renderTable();
            updateStats();
            renderUpdatedAt(ts, isFresh,
                isFresh ? new Date().toLocaleTimeString('de-DE') : 'wird aktualisiert');
        },
        // onError
        function(e, hadCache) {
            console.error(e);
            if (hadCache) {
                // Alte Daten stehen noch - Fehler nur in der Statuszeile zeigen
                renderUpdateError(ts, e);
                return;
            }
            document.getElementById('moduleTable').innerHTML =
                '<tr><td colspan="5"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></td></tr>';
        },
        // onLoading: Skeleton statt Spinner
        function() {
            var table = document.getElementById('moduleTable');
            table.textContent = '';
            table.appendChild(createSkeletonRows(6, 5));
        },
        { force: !!force }
    ).then(function() { setBusy(btn, false); });
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
    var filter = document.getElementById('filter').value.trim().toLowerCase();
    var filtered = filter
        ? modules.filter(function(m) { return m._search.indexOf(filter) !== -1; })
        : modules.slice();

    filtered.sort(function(a, b) {
        var cmp;
        if (sortColumn === 'status') cmp = getSortOrder(a) - getSortOrder(b);
        else if (sortColumn === 'tracked') cmp = compareText(a.serverVersion, b.serverVersion);
        else if (sortColumn === 'forge') cmp = compareText(a.forgeVersion, b.forgeVersion);
        else cmp = compareText(a.name, b.name);
        // Stabile Zweitsortierung nach Name
        if (cmp === 0) cmp = compareText(a.name, b.name);
        return sortAsc ? cmp : -cmp;
    });

    document.getElementById('moduleCount').textContent =
        filtered.length + (filtered.length === 1 ? ' Modul' : ' Module');
    updateSortHeaders();

    var fragment = document.createDocumentFragment();
    for (var i = 0; i < filtered.length; i++) {
        var m = filtered[i];
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td><strong>' + escapeHtml(m.name) + '</strong></td>' +
            '<td><code>' + escapeHtml(m.serverVersion) + '</code></td>' +
            '<td><code>' + escapeHtml(m.forgeVersion) + '</code></td>' +
            '<td><span class="badge ' + getBadgeClass(m) + '">' + getStatusText(m) + '</span></td>' +
            '<td><a href="' + escapeHtml(m.url) + '" target="_blank" rel="noopener noreferrer">' + (m.url.indexOf('github.com') !== -1 ? 'GitHub' : 'Forge') + '</a></td>';
        fragment.appendChild(tr);
    }
    var table = document.getElementById('moduleTable');
    table.textContent = '';
    if (!filtered.length) {
        table.innerHTML = '<tr><td colspan="5" class="text-muted">Keine Module gefunden</td></tr>';
        return;
    }
    table.appendChild(fragment);
}

function updateSortHeaders() {
    var headers = document.querySelectorAll('th[data-sort]');
    for (var i = 0; i < headers.length; i++) {
        var th = headers[i];
        var col = th.getAttribute('data-sort');
        var base = th.getAttribute('data-label');
        if (col === sortColumn) {
            th.textContent = base + (sortAsc ? ' ▲' : ' ▼');
            th.setAttribute('aria-sort', sortAsc ? 'ascending' : 'descending');
        } else {
            th.textContent = base;
            th.removeAttribute('aria-sort');
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
