document.addEventListener('DOMContentLoaded', function() {
    loadStatus();

    // Prefetch für Unterseiten-Daten (?v=2 = Cache-Key der AVD-Inventar-Seite)
    prefetchData(['/api/modules', '/api/avd-components?v=2']);
});

function loadStatus() {
    fetchSWR('/api/system_status',
        // onData: Daten anzeigen (cached oder frisch)
        function(data, isFresh) {
            var puppetEl = document.getElementById('puppetStatus');
            puppetEl.textContent = data.puppet.status;
            puppetEl.className = 'stat-value ' + getStatusClass(data.puppet.status);

            var avdEl = document.getElementById('avdStatus');
            avdEl.textContent = data.avd.status;
            avdEl.className = 'stat-value ' + getStatusClass(data.avd.status);

            var fragment = document.createDocumentFragment();
            fragment.appendChild(buildStatusRow('Puppet Module', data.puppet));
            fragment.appendChild(buildStatusRow('AVD Inventar', data.avd));

            var table = document.getElementById('statusTable');
            table.textContent = '';
            table.appendChild(fragment);

            if (data.timestamp) {
                renderUpdatedAt(document.getElementById('lastUpdated'), isFresh,
                    data.timestamp + (isFresh ? ' UTC' : ' UTC · wird aktualisiert'));
            }
        },
        // onError
        function(e) {
            console.error(e);
            document.getElementById('statusTable').innerHTML =
                '<tr><td colspan="3"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></td></tr>';
        },
        // onLoading: Skeleton anzeigen
        function() {
            var table = document.getElementById('statusTable');
            table.textContent = '';
            table.appendChild(createSkeletonRows(2, 3));
        }
    );
}

function buildStatusRow(label, entry) {
    var tr = document.createElement('tr');
    tr.innerHTML =
        '<td>' + escapeHtml(label) + '</td>' +
        '<td><span class="badge ' + getBadgeClass(entry.status) + '">' + escapeHtml(entry.status) + '</span></td>' +
        '<td>' + escapeHtml(entry.details) + '</td>';
    return tr;
}

function getStatusClass(status) {
    if (status === 'OK') return 'text-success';
    if (status === 'Info') return 'text-warning';
    return 'text-danger';
}

function getBadgeClass(status) {
    if (status === 'OK') return 'badge-success';
    if (status === 'Info') return 'badge-warning';
    return 'badge-danger';
}
