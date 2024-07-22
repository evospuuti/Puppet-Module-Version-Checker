async function loadSoftwareData() {
    try {
        const response = await fetch('/api/software_versions');
        softwareData = await response.json();
        updateTable();
    } catch (error) {
        console.error('Error loading software data:', error);
    }
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
