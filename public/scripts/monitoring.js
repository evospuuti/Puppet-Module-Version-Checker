/**
 * Optimiertes JavaScript für das Website Monitoring mit besserer Performance
 */

// Cache für die Website-Daten, um unnötige API-Aufrufe zu vermeiden
let cachedWebsiteData = null;
let lastFetchTime = 0;
const CACHE_DURATION = 30000; // 30 Sekunden Cache-Zeit

// Statusfarben für schnellere Anzeige
const STATUS_COLORS = {
    online: 'text-success',
    offline: 'text-error',
    unknown: 'text-muted-foreground',
    expired: 'text-error',
    warning: 'text-warning',
    ok: 'text-success'
};

/**
 * Optimierte Funktion zum Abrufen der Website-Daten mit Cache und Parameter für erzwungene Aktualisierung
 */
async function fetchWebsiteData(forceRefresh = false) {
    const now = Date.now();
    
    // Cache verwenden, wenn nicht veraltet und keine erzwungene Aktualisierung
    if (!forceRefresh && cachedWebsiteData && (now - lastFetchTime < CACHE_DURATION)) {
        return cachedWebsiteData;
    }
    
    try {
        // ?force=true erzwingt eine frische Prüfung auf dem Server
        const url = forceRefresh ? '/api/check_website?force=true' : '/api/check_website';
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        // Cache aktualisieren
        cachedWebsiteData = await response.json();
        lastFetchTime = now;
        
        return cachedWebsiteData;
    } catch (error) {
        console.error('Error fetching website data:', error);
        showToast('Fehler beim Laden der Website-Daten', 'error');
        
        // Bei Fehlern den Cache zurückgeben, wenn verfügbar
        return cachedWebsiteData || [];
    }
}

/**
 * Optimierte Funktion zum Aktualisieren der Website-Statustabelle mit Virtual DOM-Ansatz
 * für schnelleres Rendering bei großen Tabellen
 */
function updateMonitoringTable(sites) {
    const tableBody = document.getElementById('monitoringList');
    if (!tableBody) return;
    
    // Erstelle ein DocumentFragment für bessere Performance
    const fragment = document.createDocumentFragment();
    
    // HTML für alle Zeilen vorbereiten
    sites.forEach((site, index) => {
        const row = document.createElement('tr');
        
        // Berechne Tage bis Zertifikatsablauf
        let daysRemaining = 'Unbekannt';
        let statusClass = '';
        
        if (site.cert_expiry && site.cert_expiry !== 'Unknown') {
            const expiryDate = new Date(site.cert_expiry);
            const now = new Date();
            const diffTime = expiryDate - now;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
            daysRemaining = diffDays;
            
            // Statusfarben für schnelles visuelles Feedback
            if (diffDays <= 0) {
                statusClass = STATUS_COLORS.expired;
            } else if (diffDays <= 30) {
                statusClass = STATUS_COLORS.warning;
            } else {
                statusClass = STATUS_COLORS.ok;
            }
        }
        
        // Optimierte HTML-Generierung mit Template Strings
        row.innerHTML = `
            <td class="px-4 py-2 border-t border-muted">${site.url}</td>
            <td class="px-4 py-2 border-t border-muted">
                <span class="${site.status === 'Online' ? STATUS_COLORS.online : STATUS_COLORS.offline}">
                    ${site.status}
                </span>
            </td>
            <td class="px-4 py-2 border-t border-muted">${formatDate(site.last_checked)}</td>
            <td class="px-4 py-2 border-t border-muted">${formatDate(site.cert_expiry)}</td>
            <td class="px-4 py-2 border-t border-muted ${statusClass}">${daysRemaining}</td>
            <td class="px-4 py-2 border-t border-muted">
                <button onclick="showCertificateDetails(${index})" class="px-2 py-1 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors">
                    Details
                </button>
            </td>
        `;
        
        fragment.appendChild(row);
    });
    
    // DOM nur einmal aktualisieren
    tableBody.innerHTML = '';
    tableBody.appendChild(fragment);
}

/**
 * Optimierte Funktion zum Aktualisieren der Statuszusammenfassung mit Lazy-Loading
 */
function updateStatusSummary(sites) {
    // Optimiere DOM-Zugriffe durch Caching der Elemente
    const websiteStatusSummary = document.getElementById('websiteStatusSummary');
    const sslStatusSummary = document.getElementById('sslStatusSummary');
    
    if (!websiteStatusSummary || !sslStatusSummary) return;
    
    // Berechne Zähler in einem Durchlauf, um Schleifendurchläufe zu reduzieren
    const offlineSites = [];
    const expiringSoonSites = [];
    
    sites.forEach(site => {
        // Website-Status
        if (site.status !== 'Online') {
            offlineSites.push(site);
        }
        
        // SSL-Status
        if (site.cert_expiry && site.cert_expiry !== 'Unknown') {
            try {
                const expiryDate = new Date(site.cert_expiry);
                const now = new Date();
                const diffDays = Math.ceil((expiryDate - now) / (1000 * 60 * 60 * 24));
                
                if (diffDays <= 30) {
                    expiringSoonSites.push({
                        url: site.url,
                        days: diffDays
                    });
                }
            } catch (e) {
                console.warn(`Fehler beim Parsen des Ablaufdatums für ${site.url}:`, e);
            }
        }
    });
    
    // Website-Status aktualisieren
    if (offlineSites.length === 0) {
        websiteStatusSummary.innerHTML = `
            <span class="text-success text-xl mr-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
            </span>
            <span>Alle Websites online</span>
        `;
    } else {
        websiteStatusSummary.innerHTML = `
            <span class="text-error text-xl mr-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </span>
            <span>${offlineSites.length} ${offlineSites.length === 1 ? 'Website ist' : 'Websites sind'} offline</span>
        `;
    }
    
    // SSL-Status aktualisieren
    if (expiringSoonSites.length === 0) {
        sslStatusSummary.innerHTML = `
            <span class="text-success text-xl mr-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
            </span>
            <span>Alle Zertifikate gültig</span>
        `;
    } else {
        sslStatusSummary.innerHTML = `
            <span class="text-warning text-xl mr-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
            </span>
            <span>${expiringSoonSites.length} ${expiringSoonSites.length === 1 ? 'Zertifikat läuft' : 'Zertifikate laufen'} in weniger als 30 Tagen ab</span>
        `;
    }
}

/**
 * Optimierte Funktion zur Anzeige von Zertifikatsdetails mit Lazy-Loading
 */
function showCertificateDetails(siteIndex) {
    // Verwende gecachte Daten, wenn verfügbar
    if (cachedWebsiteData && cachedWebsiteData.length > siteIndex) {
        displayCertificateDetails(cachedWebsiteData[siteIndex]);
        return;
    }
    
    // Andernfalls Daten laden
    fetchWebsiteData()
        .then(sites => {
            if (sites.length > siteIndex) {
                displayCertificateDetails(sites[siteIndex]);
            }
        })
        .catch(error => {
            console.error('Error getting certificate details:', error);
            showToast('Fehler beim Laden der Zertifikatsdetails', 'error');
        });
}

/**
 * Hilfsfunktion zum Anzeigen der Zertifikatsdetails
 */
function displayCertificateDetails(site) {
    const certificateDetails = document.getElementById('certificateDetails');
    const noSslSelected = document.getElementById('noSslSelected');
    
    if (!certificateDetails || !noSslSelected) return;
    
    if (site.cert_expiry && site.cert_expiry !== 'Unknown') {
        // Setze Zertifikatsdetails
        document.getElementById('certWebsite').textContent = site.url;
        document.getElementById('certSubject').textContent = site.url.replace('https://', '');
        document.getElementById('certIssuer').textContent = site.certIssuer || 'Nicht verfügbar'; 
        document.getElementById('certValidFrom').textContent = site.certValidFrom || 'Nicht verfügbar';
        document.getElementById('certValidTo').textContent = formatDate(site.cert_expiry);
        
        // Berechne Ablaufwarnung
        const expiryDate = new Date(site.cert_expiry);
        const now = new Date();
        const diffDays = Math.ceil((expiryDate - now) / (1000 * 60 * 60 * 24));
        
        // Verbleibende Zeit formatieren
        const certRemainingTime = document.getElementById('certRemainingTime');
        if (certRemainingTime) {
            if (diffDays <= 0) {
                certRemainingTime.textContent = 'Abgelaufen!';
                certRemainingTime.className = 'cert-expiry-countdown text-error font-bold';
            } else {
                let timeText = `${diffDays} Tage`;
                if (diffDays <= 30) {
                    certRemainingTime.className = 'cert-expiry-countdown text-warning';
                } else {
                    certRemainingTime.className = 'cert-expiry-countdown text-success';
                }
                certRemainingTime.textContent = timeText;
            }
        }
        
        const certWarning = document.getElementById('certWarning');
        const certWarningText = document.getElementById('certWarningText');
        
        if (diffDays <= 0) {
            certWarning.classList.remove('hidden', 'border-warning');
            certWarning.classList.add('border-error');
            certWarningText.textContent = `Das Zertifikat ist bereits abgelaufen! Bitte erneuern Sie es umgehend.`;
        } else if (diffDays <= 30) {
            certWarning.classList.remove('hidden', 'border-error');
            certWarning.classList.add('border-warning');
            certWarningText.textContent = `Das Zertifikat läuft in ${diffDays} Tagen ab. Bitte planen Sie die Erneuerung.`;
        } else {
            certWarning.classList.add('hidden');
        }
        
        certificateDetails.classList.remove('hidden');
        noSslSelected.classList.add('hidden');
    } else {
        // Keine Zertifikatsinformationen verfügbar
        certificateDetails.classList.add('hidden');
        noSslSelected.classList.remove('hidden');
        noSslSelected.innerHTML = `
            <p class="text-muted-foreground">Keine SSL-Zertifikatsinformationen für ${site.url} verfügbar.</p>
        `;
    }
}

/**
 * Optimierte Funktion zum Überprüfen des Website-Status mit Ladeanimation und besserer Fehlerbehandlung
 */
async function checkWebsiteStatus() {
    // Ändere den Button-Status, um doppelte Klicks zu vermeiden
    const updateButton = document.querySelector('button[onclick="checkWebsiteStatus()"]');
    if (updateButton) {
        updateButton.disabled = true;
        updateButton.classList.add('opacity-50');
        updateButton.innerHTML = `
            <span class="inline-block animate-spin mr-2">⟳</span>
            Wird aktualisiert...
        `;
    }
    
    try {
        const data = await fetchWebsiteData(true); // Force refresh
        
        // Aktualisiere UI mit neuen Daten
        updateMonitoringTable(data);
        updateStatusSummary(data);
        
        // Update timestamp
        document.getElementById('lastUpdateTime').textContent = new Date().toLocaleString('de-DE');
        
        // Success notification
        showToast('Website-Status erfolgreich aktualisiert', 'success');
    } catch (error) {
        console.error('Error checking website status:', error);
        showToast('Fehler bei der Aktualisierung des Website-Status', 'error');
    } finally {
        // Button-Status zurücksetzen
        if (updateButton) {
            updateButton.disabled = false;
            updateButton.classList.remove('opacity-50');
            updateButton.textContent = 'Status aktualisieren';
        }
    }
}

/**
 * Exportiert die Tabelle als CSV mit optimierter Verarbeitung
 */
function exportTableToCSV(selector, filename) {
    // Für große Tabellen Web Workers verwenden
    if (window.Worker && cachedWebsiteData && cachedWebsiteData.length > 50) {
        // Hier könnte ein Web Worker verwendet werden
        // Da dies jedoch einen separaten Worker-File erfordern würde,
        // verwenden wir eine optimierte In-Thread-Verarbeitung
        exportLargeTableToCSV(cachedWebsiteData, filename);
        return;
    }
    
    // Standard-Export für kleinere Tabellen
    const rows = document.querySelectorAll('#monitoringList tr');
    
    // CSV-Inhalt generieren
    const csvContent = Array.from(rows).map(row => {
        return Array.from(row.querySelectorAll('td')).map(cell => {
            // Text ohne HTML-Tags extrahieren
            const text = cell.textContent.trim();
            // Anführungszeichen escapen
            return `"${text.replace(/"/g, '""')}"`;
        }).join(',');
    }).join('\n');
    
    // Header-Zeile hinzufügen
    const headerRow = Array.from(document.querySelectorAll('thead th')).map(th =>
        `"${th.textContent.trim().replace(/"/g, '""')}"`
    ).join(',');
    
    const fullCsvContent = headerRow + '\n' + csvContent;
    
    // Download-Link erstellen
    const blob = new Blob([fullCsvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showToast('CSV-Export erfolgreich', 'success');
}

/**
 * Optimierte CSV-Export-Funktion für große Datensätze
 */
function exportLargeTableToCSV(data, filename) {
    // Header-Definition
    const headers = [
        'Website', 'Status', 'Zuletzt geprüft', 'SSL Ablaufdatum', 'Verbleibende Tage'
    ];
    
    // Zeilen vorbereiten
    const rows = data.map(site => {
        // Tage berechnen
        let daysRemaining = 'Unbekannt';
        if (site.cert_expiry && site.cert_expiry !== 'Unknown') {
            try {
                const expiryDate = new Date(site.cert_expiry);
                const now = new Date();
                daysRemaining = Math.ceil((expiryDate - now) / (1000 * 60 * 60 * 24));
            } catch (e) {
                console.warn('Error calculating days for CSV export', e);
            }
        }
        
        return [
            site.url,
            site.status,
            formatDate(site.last_checked),
            formatDate(site.cert_expiry),
            daysRemaining
        ].map(value => `"${String(value).replace(/"/g, '""')}"`).join(',');
    });
    
    // CSV erstellen
    const csv = [
        headers.map(header => `"${header}"`).join(','),
        ...rows
    ].join('\n');
    
    // Download
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url); // Speicher freigeben
    
    showToast('CSV-Export erfolgreich', 'success');
}

/**
 * Autorefresh-Funktionalität mit adaptiver Rate
 */
let autoRefreshIntervalId = null;
let autoRefreshInterval = 60000; // 60 Sekunden Standardintervall

function toggleAutoRefresh() {
    const button = document.getElementById('autoRefreshToggle');
    if (!button) return;
    
    if (autoRefreshIntervalId) {
        // Auto-refresh stoppen
        clearInterval(autoRefreshIntervalId);
        autoRefreshIntervalId = null;
        button.textContent = 'Auto-Refresh starten';
        button.classList.remove('bg-error');
        button.classList.add('bg-primary');
        showToast('Auto-Refresh deaktiviert', 'info');
    } else {
        // Auto-refresh starten
        autoRefreshIntervalId = setInterval(() => {
            // Adaptiver Refresh - nur wenn Tab sichtbar
            if (!document.hidden) {
                checkWebsiteStatus();
            }
        }, autoRefreshInterval);
        
        button.textContent = 'Auto-Refresh stoppen';
        button.classList.remove('bg-primary');
        button.classList.add('bg-error');
        showToast(`Auto-Refresh aktiviert (${autoRefreshInterval/1000}s)`, 'success');
    }
}

function setAutoRefreshInterval(seconds) {
    autoRefreshInterval = seconds * 1000;
    
    // Neustart des Intervalls, wenn aktiv
    if (autoRefreshIntervalId) {
        clearInterval(autoRefreshIntervalId);
        autoRefreshIntervalId = setInterval(() => {
            if (!document.hidden) {
                checkWebsiteStatus();
            }
        }, autoRefreshInterval);
        
        showToast(`Auto-Refresh-Intervall auf ${seconds}s gesetzt`, 'success');
    }
}

// Initialisierung
document.addEventListener('DOMContentLoaded', () => {
    // Initiale Überprüfung
    checkWebsiteStatus();
    
    // Event Listener für Auto-Refresh-Steuerung hinzufügen
    const autoRefreshToggle = document.getElementById('autoRefreshToggle');
    if (autoRefreshToggle) {
        autoRefreshToggle.addEventListener('click', toggleAutoRefresh);
    }
    
    // Intervall-Auswahl
    const intervalSelect = document.getElementById('refreshInterval');
    if (intervalSelect) {
        intervalSelect.addEventListener('change', () => {
            const seconds = parseInt(intervalSelect.value, 10);
            if (!isNaN(seconds)) {
                setAutoRefreshInterval(seconds);
            }
        });
    }
    
    // Tab Visibility API für adaptive Aktualisierung
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && cachedWebsiteData) {
            const now = Date.now();
            // Nur aktualisieren, wenn die Daten älter als 2 Minuten sind
            if (now - lastFetchTime > 120000) {
                checkWebsiteStatus();
            }
        }
    });
});
