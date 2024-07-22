function toggleDarkMode() {
    const isDarkMode = document.documentElement.classList.toggle('dark');
    localStorage.setItem('darkMode', isDarkMode);
    updateButtonText(isDarkMode);
}

function updateButtonText(isDarkMode) {
    const button = document.getElementById('darkModeToggle');
    button.textContent = isDarkMode ? 'Light Mode' : 'Dark Mode';
}

const serverVersions = {
    'dsc-auditpolicydsc': '1.4.0-0-9',
    'puppet-ca_cert': '3.1.0',
    'puppet-alternatives': '5.1.0',
    'puppet-archive': '7.1.0',
    'puppet-systemd': '7.1.0',
    'puppetlabs-apt': '9.4.0',
    'puppetlabs-facts': '1.4.0',
    'puppetlabs-inifile': '6.1.1',
    'puppetlabs-powershell': '6.0.0',
    'puppetlabs-registry': '5.0.1',
    'puppetlabs-stdlib': '9.6.0',
    'saz-sudo': '8.0.0'
};

function compareVersions(v1, v2) {
    const parts1 = v1.replace(/^v/, '').split('-')[0].split('.').map(Number);
    const parts2 = v2.replace(/^v/, '').split('-')[0].split('.').map(Number);
    for (let i = 0; i < 3; i++) {
        if (parts1[i] > parts2[i]) return 1;
        if (parts1[i] < parts2[i]) return -1;
    }
    return 0;
}

async function fetchModuleData() {
    const loadingIndicator = document.getElementById('loadingIndicator');
    const errorMessage = document.getElementById('errorMessage');
    loadingIndicator.classList.remove('hidden');
    errorMessage.classList.add('hidden');

    try {
        const response = await fetch('/api/modules');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const modules = await response.json();

        const moduleList = document.getElementById('moduleList');
        moduleList.innerHTML = '';

        modules.forEach(module => {
            const row = document.createElement('tr');
            const serverVersion = serverVersions[module.name] || 'Unbekannt';
            const comparison = compareVersions(serverVersion, module.forgeVersion);
            
            let rowClass = '';
            if (module.deprecated) {
                rowClass = 'bg-red-500/20';
            } else if (comparison !== 0) {
                rowClass = 'bg-yellow-500/20';
            }
            
            row.innerHTML = `
                <td class="px-4 py-2 border-t border-muted">${module.name}</td>
                <td class="px-4 py-2 border-t border-muted">${serverVersion}</td>
                <td class="px-4 py-2 border-t border-muted">${module.forgeVersion}</td>
                <td class="px-4 py-2 border-t border-muted">${module.deprecated ? 'Deprecated' : 'Aktiv'}</td>
                <td class="px-4 py-2 border-t border-muted">
                    <a href="${module.url}" target="_blank" class="text-primary hover:underline">Forge Link</a>
                </td>
            `;
            row.className = rowClass;
            moduleList.appendChild(row);
        });
    } catch (error) {
        console.error('Fehler beim Abrufen der Moduldaten:', error);
        errorMessage.textContent = 'Fehler beim Laden der Daten. Bitte versuchen Sie es später erneut.';
        errorMessage.classList.remove('hidden');
    } finally {
        loadingIndicator.classList.add('hidden');
    }
}

document.addEventListener('DOMContentLoaded', (event) => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true';
    if (isDarkMode) {
        document.documentElement.classList.add('dark');
    }
    updateButtonText(isDarkMode);

    // Prüfe das System-Farbschema
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
        document.documentElement.classList.add('light');
        updateButtonText(true);
    }

    // Lade die Moduldaten beim Seitenaufruf
    fetchModuleData();
});

// Reagiere auf Änderungen des System-Farbschemas
window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', e => {
    const newColorScheme = e.matches ? "light" : "dark";
    document.documentElement.classList.toggle('light', e.matches);
    updateButtonText(e.matches);
});