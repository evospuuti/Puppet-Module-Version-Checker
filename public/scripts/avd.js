var components = [];
var sortColumn = 'name';
var sortAsc = true;

var debouncedFilter = debounce(function() { renderTable(); }, 150);

document.addEventListener('DOMContentLoaded', function() {
    fetchComponents();
    document.getElementById('refreshBtn').addEventListener('click', function() {
        try { localStorage.removeItem(_getCacheKey('/api/avd-components')); } catch(e) {}
        fetchComponents();
    });
    document.getElementById('filter').addEventListener('input', debouncedFilter);
});

function fetchComponents() {
    fetchSWR('/api/avd-components',
        function(data, isFresh) {
            components = data;
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
        function(e) {
            console.error(e);
            document.getElementById('componentTable').innerHTML =
                '<tr><td colspan="6"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></td></tr>';
        },
        function() {
            var table = document.getElementById('componentTable');
            table.textContent = '';
            table.appendChild(createSkeletonRows(6, 6));
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
    var filtered = components.filter(function(c) {
        return c.name.toLowerCase().includes(filter) ||
            c.location.toLowerCase().includes(filter) ||
            c.tracked.toLowerCase().includes(filter);
    });

    filtered.sort(function(a, b) {
        var valA, valB;
        if (sortColumn === 'name') { valA = a.name; valB = b.name; }
        else if (sortColumn === 'location') { valA = a.location; valB = b.location; }
        else if (sortColumn === 'tracked') { valA = a.tracked; valB = b.tracked; }
        else if (sortColumn === 'latest') { valA = a.latestVersion; valB = b.latestVersion; }
        else if (sortColumn === 'status') { valA = getSortOrder(a.status); valB = getSortOrder(b.status); }
        else { valA = a.name; valB = b.name; }

        if (typeof valA === 'string') {
            var cmp = valA.localeCompare(valB);
            return sortAsc ? cmp : -cmp;
        }
        return sortAsc ? valA - valB : valB - valA;
    });

    document.getElementById('componentCount').textContent = filtered.length + ' Komponenten';
    updateSortHeaders();

    var fragment = document.createDocumentFragment();
    for (var i = 0; i < filtered.length; i++) {
        var c = filtered[i];
        var noteHtml = c.note ? ' <span class="text-muted text-small">(' + escapeHtml(c.note) + ')</span>' : '';
        var linkHtml = c.link
            ? '<a href="' + escapeHtml(c.link) + '" target="_blank" rel="noopener noreferrer">Docs</a>'
            : '-';
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td><strong>' + escapeHtml(c.name) + '</strong>' + noteHtml + '</td>' +
            '<td class="text-muted"><code>' + escapeHtml(c.location) + '</code></td>' +
            '<td><code>' + escapeHtml(c.tracked) + '</code></td>' +
            '<td><code>' + escapeHtml(c.latestVersion) + '</code></td>' +
            '<td><span class="badge ' + getBadgeClass(c.status) + '">' + getStatusText(c.status) + '</span></td>' +
            '<td>' + linkHtml + '</td>';
        fragment.appendChild(tr);
    }
    var table = document.getElementById('componentTable');
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
    if (status === 'manual') return 1;
    return 0;
}

function updateStats() {
    var current = 0, manual = 0, errors = 0;
    for (var i = 0; i < components.length; i++) {
        if (components[i].status === 'current') current++;
        else if (components[i].status === 'manual') manual++;
        else if (components[i].status === 'error') errors++;
    }
    document.getElementById('currentCount').textContent = current;
    document.getElementById('manualCount').textContent = manual;
    document.getElementById('errorCount').textContent = errors;
}

function getBadgeClass(status) {
    if (status === 'current') return 'badge-success';
    if (status === 'manual') return 'badge-warning';
    return 'badge-danger';
}

function getStatusText(status) {
    if (status === 'current') return 'OK';
    if (status === 'manual') return 'Manuell';
    return 'Fehler';
}
