var providers = [];
var sortColumn = 'name';
var sortAsc = true;

var debouncedFilter = debounce(function() { renderTable(); }, 150);

document.addEventListener('DOMContentLoaded', function() {
    fetchProviders();
    document.getElementById('refreshBtn').addEventListener('click', function() {
        // Bei manuellem Refresh: Cache löschen und neu laden
        try { localStorage.removeItem(_getCacheKey('/api/terraform-providers')); } catch(e) {}
        fetchProviders();
    });
    document.getElementById('filter').addEventListener('input', debouncedFilter);
});

function fetchProviders() {
    fetchSWR('/api/terraform-providers',
        // onData: Daten anzeigen (cached oder frisch)
        function(data, isFresh) {
            providers = data;
            renderTable();
            updateStats();

            var ts = document.getElementById('lastUpdated');
            if (ts) {
                if (isFresh) {
                    ts.textContent = 'Aktualisiert: ' + new Date().toLocaleTimeString('de-DE');
                } else {
                    ts.innerHTML = '<span class="stale-indicator"><span class="stale-dot"></span>wird aktualisiert</span>';
                }
            }
        },
        // onError
        function(e) {
            console.error(e);
            document.getElementById('providerTable').innerHTML =
                '<tr><td colspan="6"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></td></tr>';
        },
        // onLoading: Skeleton statt Spinner
        function() {
            var table = document.getElementById('providerTable');
            table.textContent = '';
            table.appendChild(createSkeletonRows(4, 6));
        }
    );
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
    updateSortHeaders();

    var fragment = document.createDocumentFragment();
    for (var i = 0; i < filtered.length; i++) {
        var p = filtered[i];
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td><strong>' + escapeHtml(p.displayName) + '</strong></td>' +
            '<td class="text-muted">' + escapeHtml(p.namespace) + '</td>' +
            '<td><code>' + escapeHtml(p.installedVersion) + '</code></td>' +
            '<td><code>' + escapeHtml(p.latestVersion) + '</code></td>' +
            '<td><span class="badge ' + getBadgeClass(p.status) + '">' + getStatusText(p.status) + '</span></td>' +
            '<td><a href="' + escapeHtml(p.url) + '" target="_blank" rel="noopener noreferrer">Registry</a></td>';
        fragment.appendChild(tr);
    }
    var table = document.getElementById('providerTable');
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

function getSortOrder(status) {
    if (status === 'error') return 2;
    if (status === 'outdated') return 1;
    return 0;
}

function updateStats() {
    var current = 0, outdated = 0, errors = 0;
    for (var i = 0; i < providers.length; i++) {
        if (providers[i].status === 'current') current++;
        else if (providers[i].status === 'outdated') outdated++;
        else if (providers[i].status === 'error') errors++;
    }
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
