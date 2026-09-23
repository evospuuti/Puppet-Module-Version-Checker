document.addEventListener('DOMContentLoaded', function() {
    loadStatus();

    // Prefetch für die Puppet-Seite
    prefetchData(['/api/modules']);
});

function loadStatus() {
    fetchSWR('/api/system_status',
        // onData: Daten anzeigen (cached oder frisch)
        function(data, isFresh) {
            var puppetEl = document.getElementById('puppetStatus');
            puppetEl.textContent = data.puppet.status;
            puppetEl.className = 'stat-value ' + getStatusClass(data.puppet.status);

            var fragment = document.createDocumentFragment();
            fragment.appendChild(buildStatusRow('Puppet Module', data.puppet));

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
