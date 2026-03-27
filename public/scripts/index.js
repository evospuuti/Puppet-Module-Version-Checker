document.addEventListener('DOMContentLoaded', function() {
    loadStatus();

    // Prefetch für Unterseiten-Daten
    prefetchData(['/api/modules', '/api/avd-components']);
});

function loadStatus() {
    fetchSWR('/api/system_status',
        // onData: Daten anzeigen (cached oder frisch)
        function(data, isFresh) {
            document.getElementById('puppetStatus').textContent = data.puppet.status;
            document.getElementById('puppetStatus').className = 'stat-value ' + getStatusClass(data.puppet.status);

            document.getElementById('avdStatus').textContent = data.avd.status;
            document.getElementById('avdStatus').className = 'stat-value ' + getStatusClass(data.avd.status);

            var fragment = document.createDocumentFragment();

            var row1 = document.createElement('tr');
            row1.innerHTML =
                '<td>Puppet Module</td>' +
                '<td><span class="badge ' + getBadgeClass(data.puppet.status) + '">' + escapeHtml(data.puppet.status) + '</span></td>' +
                '<td>' + escapeHtml(data.puppet.details) + '</td>';
            fragment.appendChild(row1);

            var row2 = document.createElement('tr');
            row2.innerHTML =
                '<td>AVD Komponenten</td>' +
                '<td><span class="badge ' + getBadgeClass(data.avd.status) + '">' + escapeHtml(data.avd.status) + '</span></td>' +
                '<td>' + escapeHtml(data.avd.details) + '</td>';
            fragment.appendChild(row2);

            var table = document.getElementById('statusTable');
            table.textContent = '';
            table.appendChild(fragment);

            var ts = document.getElementById('lastUpdated');
            if (ts && data.timestamp) {
                var prefix = isFresh ? 'Aktualisiert: ' : '';
                var suffix = isFresh ? ' UTC' : ' UTC (Cache)';
                ts.textContent = prefix + data.timestamp + suffix;
                // Stale-Indikator
                if (!isFresh) {
                    ts.innerHTML = '<span class="stale-indicator"><span class="stale-dot"></span>' +
                        escapeHtml(data.timestamp) + ' UTC &middot; wird aktualisiert</span>';
                }
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
