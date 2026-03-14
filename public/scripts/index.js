document.addEventListener('DOMContentLoaded', function() {
    loadStatus();

    // autoresearch-Pattern: Prefetch für Unterseiten-Daten
    // Während der Dashboard-Status geladen wird, werden die Detail-Daten
    // für Puppet und Terraform bereits im Hintergrund vorgeladen.
    prefetchData(['/api/modules', '/api/terraform-providers']);
});

async function loadStatus() {
    try {
        var data = await fetchDeduped('/api/system_status');

        document.getElementById('puppetStatus').textContent = data.puppet.status;
        document.getElementById('puppetStatus').className = 'stat-value ' + getStatusClass(data.puppet.status);

        document.getElementById('terraformStatus').textContent = data.terraform.status;
        document.getElementById('terraformStatus').className = 'stat-value ' + getStatusClass(data.terraform.status);

        // autoresearch-Pattern: DOM-Batch-Update via DocumentFragment
        // Analog zu Gradient Accumulation: alle DOM-Mutationen sammeln
        // und in einem einzigen Reflow anwenden.
        var fragment = document.createDocumentFragment();

        var row1 = document.createElement('tr');
        row1.innerHTML =
            '<td>Puppet Module</td>' +
            '<td><span class="badge ' + getBadgeClass(data.puppet.status) + '">' + escapeHtml(data.puppet.status) + '</span></td>' +
            '<td>' + escapeHtml(data.puppet.details) + '</td>';
        fragment.appendChild(row1);

        var row2 = document.createElement('tr');
        row2.innerHTML =
            '<td>Terraform Provider</td>' +
            '<td><span class="badge ' + getBadgeClass(data.terraform.status) + '">' + escapeHtml(data.terraform.status) + '</span></td>' +
            '<td>' + escapeHtml(data.terraform.details) + '</td>';
        fragment.appendChild(row2);

        var table = document.getElementById('statusTable');
        table.textContent = '';
        table.appendChild(fragment);

        var ts = document.getElementById('lastUpdated');
        if (ts && data.timestamp) {
            ts.textContent = 'Letzte Aktualisierung: ' + data.timestamp + ' UTC';
        }
    } catch (e) {
        console.error(e);
        document.getElementById('statusTable').innerHTML =
            '<tr><td colspan="3"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></td></tr>';
    }
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
