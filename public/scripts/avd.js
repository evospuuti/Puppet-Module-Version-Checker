var components = [];
var CATEGORY_ORDER = ['Runner', 'Spoke', 'Session Host', 'Azure Allgemein'];

document.addEventListener('DOMContentLoaded', function() {
    fetchComponents();
    document.getElementById('refreshBtn').addEventListener('click', function() {
        try { localStorage.removeItem(_getCacheKey('/api/avd-components')); } catch(e) {}
        fetchComponents();
    });
});

function fetchComponents() {
    fetchSWR('/api/avd-components',
        function(data, isFresh) {
            components = data;
            renderCategories();
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
            document.getElementById('categoryGroups').innerHTML =
                '<div class="card"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></div>';
        },
        function() {
            var container = document.getElementById('categoryGroups');
            container.textContent = '';
            for (var i = 0; i < CATEGORY_ORDER.length; i++) {
                var card = document.createElement('div');
                card.className = 'card';
                card.innerHTML = '<h3 class="category-title mb-2">' + escapeHtml(CATEGORY_ORDER[i]) + '</h3>' +
                    '<div class="table-container"><table><thead><tr>' +
                    '<th>Name</th><th>Ort</th><th>Tracked</th><th>Neueste</th><th>Status</th><th>Link</th>' +
                    '</tr></thead><tbody></tbody></table></div>';
                var tbody = card.querySelector('tbody');
                tbody.appendChild(createSkeletonRows(2, 6));
                container.appendChild(card);
            }
        }
    );
}

function renderCategories() {
    var grouped = {};
    for (var i = 0; i < CATEGORY_ORDER.length; i++) {
        grouped[CATEGORY_ORDER[i]] = [];
    }
    for (var j = 0; j < components.length; j++) {
        var cat = components[j].category || 'Azure Allgemein';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(components[j]);
    }

    var container = document.getElementById('categoryGroups');
    container.textContent = '';

    for (var k = 0; k < CATEGORY_ORDER.length; k++) {
        var catName = CATEGORY_ORDER[k];
        var items = grouped[catName];
        if (!items || items.length === 0) continue;

        var card = document.createElement('div');
        card.className = 'card';

        var title = document.createElement('h3');
        title.className = 'category-title mb-2';
        title.textContent = catName;
        card.appendChild(title);

        var tableWrap = document.createElement('div');
        tableWrap.className = 'table-container';
        var table = document.createElement('table');
        table.innerHTML =
            '<thead><tr>' +
            '<th>Name</th><th>Ort</th><th>Tracked</th><th>Neueste</th><th>Status</th><th>Link</th>' +
            '</tr></thead>';
        var tbody = document.createElement('tbody');

        for (var m = 0; m < items.length; m++) {
            var c = items[m];
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
            tbody.appendChild(tr);
        }

        table.appendChild(tbody);
        tableWrap.appendChild(table);
        card.appendChild(tableWrap);
        container.appendChild(card);
    }
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
