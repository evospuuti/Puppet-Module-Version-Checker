document.addEventListener('DOMContentLoaded', loadStatus);

async function loadStatus() {
    try {
        var res = await fetch('/api/system_status');
        if (!res.ok) throw new Error('Server antwortet nicht (' + res.status + ')');
        var data = await res.json();

        document.getElementById('puppetStatus').textContent = data.puppet.status;
        document.getElementById('puppetStatus').className = 'stat-value ' + getStatusClass(data.puppet.status);

        document.getElementById('terraformStatus').textContent = data.terraform.status;
        document.getElementById('terraformStatus').className = 'stat-value ' + getStatusClass(data.terraform.status);

        document.getElementById('statusTable').innerHTML =
            '<tr>' +
                '<td>Puppet Module</td>' +
                '<td><span class="badge ' + getBadgeClass(data.puppet.status) + '">' + escapeHtml(data.puppet.status) + '</span></td>' +
                '<td>' + escapeHtml(data.puppet.details) + '</td>' +
            '</tr>' +
            '<tr>' +
                '<td>Terraform Provider</td>' +
                '<td><span class="badge ' + getBadgeClass(data.terraform.status) + '">' + escapeHtml(data.terraform.status) + '</span></td>' +
                '<td>' + escapeHtml(data.terraform.details) + '</td>' +
            '</tr>';
    } catch (e) {
        console.error(e);
        document.getElementById('statusTable').innerHTML =
            '<tr><td colspan="3"><div class="error-message">Fehler beim Laden: ' + escapeHtml(e.message) + '</div></td></tr>';
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
