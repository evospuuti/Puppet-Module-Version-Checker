let softwareData = [];

async function loadSoftwareData() {
    try {
        const response = await fetch('/api/software_versions');
        softwareData = await response.json();
        updateTable();
    } catch (error) {
        console.error('Error loading software data:', error);
    }
}

function updateTable() {
    const tableBody = document.querySelector('#softwareTable tbody');
    tableBody.innerHTML = '';
    softwareData.forEach((software, index) => {
        const row = `
            <tr class="${index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}">
                <td class="p-2">${software.name}</td>
                <td class="p-2">${software.currentVersion}</td>
                <td class="p-2">${software.lastUpdated}</td>
                <td class="p-2">${software.status}</td>
                <td class="p-2">
                    <button onclick="editSoftware(${index})" class="bg-blue-500 text-white p-1 rounded mr-1">Bearbeiten</button>
                    <button onclick="deleteSoftware(${index})" class="bg-red-500 text-white p-1 rounded">Löschen</button>
                </td>
            </tr>
        `;
        tableBody.innerHTML += row;
    });
}

async function addSoftware() {
    const name = document.getElementById('softwareName').value;
    const currentVersion = document.getElementById('currentVersion').value;
    const lastUpdated = document.getElementById('lastUpdated').value;
    const status = document.getElementById('status').value;

    if (!name || !currentVersion || !lastUpdated) {
        alert('Bitte füllen Sie alle Felder aus.');
        return;
    }

    const newSoftware = { name, currentVersion, lastUpdated, status };

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
            throw new Error('Failed to add software');
        }
    } catch (error) {
        console.error('Error adding software:', error);
        alert('Fehler beim Hinzufügen der Software');
    }
}

function editSoftware(index) {
    const software = softwareData[index];
    document.getElementById('softwareName').value = software.name;
    document.getElementById('currentVersion').value = software.currentVersion;
    document.getElementById('lastUpdated').value = software.lastUpdated;
    document.getElementById('status').value = software.status;

    // Ändern Sie den "Hinzufügen" Button zu "Aktualisieren"
    const addButton = document.querySelector('button[onclick="addSoftware()"]');
    addButton.textContent = 'Aktualisieren';
    addButton.onclick = () => updateSoftware(index);
}

async function updateSoftware(index) {
    const name = document.getElementById('softwareName').value;
    const currentVersion = document.getElementById('currentVersion').value;
    const lastUpdated = document.getElementById('lastUpdated').value;
    const status = document.getElementById('status').value;

    if (!name || !currentVersion || !lastUpdated) {
        alert('Bitte füllen Sie alle Felder aus.');
        return;
    }

    const updatedSoftware = { name, currentVersion, lastUpdated, status };

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
            throw new Error('Failed to update software');
        }
    } catch (error) {
        console.error('Error updating software:', error);
        alert('Fehler beim Aktualisieren der Software');
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
            throw new Error('Failed to delete software');
        }
    } catch (error) {
        console.error('Error deleting software:', error);
        alert('Fehler beim Löschen der Software');
    }
}

function clearInputs() {
    document.getElementById('softwareName').value = '';
    document.getElementById('currentVersion').value = '';
    document.getElementById('lastUpdated').value = '';
    document.getElementById('status').value = 'Aktuell';
}

function resetAddButton() {
    const addButton = document.querySelector('button[onclick="updateSoftware()"]');
    addButton.textContent = 'Hinzufügen';
    addButton.onclick = addSoftware;
}

document.addEventListener('DOMContentLoaded', loadSoftwareData);