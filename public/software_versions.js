let softwareData = [];

async function loadSoftwareData() {
    try {
        const response = await fetch('/api/software_versions');
        softwareData = await response.json();
        updateTable();
    } catch (error) {
        console.error('Error loading software data:', error);
        alert('Fehler beim Laden der Software-Daten. Bitte versuchen Sie es später erneut.');
    }
}

function updateTable() {
    const tableBody = document.getElementById('softwareList');
    if (!tableBody) {
        console.error('Element with id "softwareList" not found');
        return;
    }
    
    tableBody.innerHTML = '';
    
    softwareData.forEach((software, index) => {
        const row = document.createElement('tr');
        const lastUpdatedDate = new Date(software.lastUpdated);
        const threeMonthsAgo = new Date();
        threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
        
        const isOutdated = lastUpdatedDate < threeMonthsAgo;
        row.className = `border-t border-border ${isOutdated ? 'bg-yellow-100 dark:bg-yellow-900' : ''}`;
        
        row.innerHTML = `
            <td class="px-4 py-2">${software.name}</td>
            <td class="px-4 py-2">${software.currentVersion}</td>
            <td class="px-4 py-2">${software.lastUpdated}</td>
            <td class="px-4 py-2">${software.status}</td>
            <td class="px-4 py-2">${software.link ? `<a href="${software.link}" target="_blank" class="text-blue-600 hover:underline">Link</a>` : ''}</td>
            <td class="px-4 py-2">
                <button onclick="editSoftware(${index})" class="px-2 py-1 bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors mr-2">Bearbeiten</button>
                <button onclick="deleteSoftware(${index})" class="px-2 py-1 bg-destructive text-destructive-foreground rounded hover:bg-destructive/90 transition-colors">Löschen</button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

async function addSoftware() {
    const name = document.getElementById('softwareName').value;
    const currentVersion = document.getElementById('currentVersion').value;
    const lastUpdated = document.getElementById('lastUpdated').value;
    const status = document.getElementById('status').value;
    const link = document.getElementById('softwareLink').value;

    if (!name || !currentVersion || !lastUpdated) {
        alert('Bitte füllen Sie alle Pflichtfelder aus.');
        return;
    }

    const newSoftware = { name, currentVersion, lastUpdated, status, link };

    try {
        const response = await fetch('/api/software_versions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(newSoftware),
        });

        if (response.ok) {
            await loadSoftwareData();
            clearInputs();
        } else {
            const errorText = await response.text();
            throw new Error(`Server responded with status ${response.status}: ${errorText}`);
        }
    } catch (error) {
        console.error('Error adding software:', error);
        alert(`Fehler beim Hinzufügen der Software: ${error.message}`);
    }
}

function editSoftware(index) {
    const software = softwareData[index];
    document.getElementById('softwareName').value = software.name;
    document.getElementById('currentVersion').value = software.currentVersion;
    document.getElementById('lastUpdated').value = software.lastUpdated;
    document.getElementById('status').value = software.status;
    document.getElementById('softwareLink').value = software.link || '';
    
    const addButton = document.querySelector('button[onclick="addSoftware()"]');
    addButton.textContent = 'Aktualisieren';
    addButton.onclick = () => updateSoftware(index);
}

async function updateSoftware(index) {
    const name = document.getElementById('softwareName').value;
    const currentVersion = document.getElementById('currentVersion').value;
    const lastUpdated = document.getElementById('lastUpdated').value;
    const status = document.getElementById('status').value;
    const link = document.getElementById('softwareLink').value;

    if (!name || !currentVersion || !lastUpdated) {
        alert('Bitte füllen Sie alle Pflichtfelder aus.');
        return;
    }

    const updatedSoftware = { name, currentVersion, lastUpdated, status, link };

    try {
        const response = await fetch(`/api/software_versions/${index}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(updatedSoftware),
        });

        if (response.ok) {
            await loadSoftwareData();
            clearInputs();
            resetAddButton();
        } else {
            const errorText = await response.text();
            throw new Error(`Server responded with status ${response.status}: ${errorText}`);
        }
    } catch (error) {
        console.error('Error updating software:', error);
        alert(`Fehler beim Aktualisieren der Software: ${error.message}`);
    }
}

async function deleteSoftware(index) {
    if (!confirm('Sind Sie sicher, dass Sie diese Software löschen möchten?')) {
        return;
    }

    try {
        const response = await fetch(`/api/software_versions/${index}`, {
            method: 'DELETE',
        });

        if (response.ok) {
            await loadSoftwareData();
        } else {
            const errorText = await response.text();
            throw new Error(`Server responded with status ${response.status}: ${errorText}`);
        }
    } catch (error) {
        console.error('Error deleting software:', error);
        alert(`Fehler beim Löschen der Software: ${error.message}`);
    }
}

function clearInputs() {
    document.getElementById('softwareName').value = '';
    document.getElementById('currentVersion').value = '';
    document.getElementById('lastUpdated').value = '';
    document.getElementById('status').value = 'Aktuell';
    document.getElementById('softwareLink').value = '';
}

function resetAddButton() {
    const addButton = document.querySelector('button[onclick="addSoftware()"]');
    addButton.textContent = 'Hinzufügen';
    addButton.onclick = addSoftware;
}

// Load software data when the page loads
document.addEventListener('DOMContentLoaded', loadSoftwareData);