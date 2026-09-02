// AVD-Versionsinventar: gruppierte Darstellung nach Kategorie, mit
// Status-Badges (aktuell/veraltet/suppressed/...), Terminen, Kontrakten
// und bewussten Entscheidungen (Hinweise).

// ?v=2: eigener Cache-Key, damit alte localStorage-Eintraege mit dem
// frueheren Array-Format nicht gegen das neue Objekt-Format laufen
var AVD_API_URL = '/api/avd-components?v=2';

var inventory = null;

document.addEventListener('DOMContentLoaded', function() {
    fetchInventory(false);
    document.getElementById('refreshBtn').addEventListener('click', function() {
        // Manueller Refresh: Cache umgehen, vorhandene Daten bleiben sichtbar
        fetchInventory(true);
    });
});

function fetchInventory(force) {
    var btn = document.getElementById('refreshBtn');
    var ts = document.getElementById('lastUpdated');
    setBusy(btn, true);

    return fetchSWR(AVD_API_URL,
        function(data, isFresh) {
            if (!data || !data.items) return; // altes Cache-Format ignorieren
            inventory = data;
            renderAll();
            renderUpdatedAt(ts, isFresh,
                isFresh ? new Date().toLocaleTimeString('de-DE') : 'wird aktualisiert');
        },
        function(e, hadCache) {
            console.error(e);
            if (hadCache && inventory) {
                // Alte Daten stehen noch - Fehler nur in der Statuszeile zeigen
                renderUpdateError(ts, e);
                return;
            }
            document.getElementById('categoryGroups').innerHTML =
                '<div class="card"><div class="error-message">' + escapeHtml(getErrorMessage(e)) + '</div></div>';
        },
        function() {
            var container = document.getElementById('categoryGroups');
            container.textContent = '';
            for (var i = 0; i < 3; i++) {
                var card = document.createElement('div');
                card.className = 'card';
                card.innerHTML = '<div class="table-container"><table><tbody></tbody></table></div>';
                card.querySelector('tbody').appendChild(createSkeletonRows(4, 6));
                container.appendChild(card);
            }
        },
        { force: !!force }
    ).then(function() { setBusy(btn, false); });
}

function renderAll() {
    updateStats();
    renderCategories();
    renderTermine();
    renderKontrakte();
    renderHinweise();
}

function updateStats() {
    var counts = { current: 0, outdated: 0, floating: 0, manual: 0, intern: 0, error: 0 };
    var items = inventory.items;
    for (var i = 0; i < items.length; i++) {
        var s = items[i].status;
        if (s === 'current' || s === 'suppressed') counts.current++;
        else if (s === 'outdated') counts.outdated++;
        else if (s === 'floating') counts.floating++;
        else if (s === 'manual' || s === 'azure') counts.manual++;
        else if (s === 'intern') counts.intern++;
        else if (s === 'error') counts.error++;
    }
    document.getElementById('currentCount').textContent = counts.current;
    document.getElementById('outdatedCount').textContent = counts.outdated;
    document.getElementById('floatingCount').textContent = counts.floating;
    document.getElementById('manualCount').textContent = counts.manual;
    document.getElementById('internCount').textContent = counts.intern;
    document.getElementById('errorCount').textContent = counts.error;
}

function renderCategories() {
    var container = document.getElementById('categoryGroups');
    container.textContent = '';

    // Einmal nach Kategorie gruppieren statt pro Kategorie alle Items zu filtern
    var byKategorie = {};
    for (var i = 0; i < inventory.items.length; i++) {
        var it = inventory.items[i];
        (byKategorie[it.kategorie] = byKategorie[it.kategorie] || []).push(it);
    }

    var kategorien = inventory.kategorien || [];
    for (var k = 0; k < kategorien.length; k++) {
        var kat = kategorien[k];
        var items = byKategorie[kat.key];
        if (!items || !items.length) continue;

        var card = document.createElement('div');
        card.className = 'card';

        var title = document.createElement('h3');
        title.className = 'category-title';
        title.textContent = kat.titel;
        card.appendChild(title);

        if (kat.hinweis) {
            var sub = document.createElement('p');
            sub.className = 'text-muted text-small mb-2';
            sub.textContent = kat.hinweis;
            card.appendChild(sub);
        }

        var tableWrap = document.createElement('div');
        tableWrap.className = 'table-container';
        var table = document.createElement('table');
        table.innerHTML =
            '<thead><tr>' +
            '<th scope="col">Artefakt</th><th scope="col">Ist</th><th scope="col">Art</th>' +
            '<th scope="col">Neueste</th><th scope="col">Status</th><th scope="col">Repo</th><th scope="col">Link</th>' +
            '</tr></thead>';
        var tbody = document.createElement('tbody');

        for (var m = 0; m < items.length; m++) {
            tbody.appendChild(buildItemRow(items[m]));
        }

        table.appendChild(tbody);
        tableWrap.appendChild(table);
        card.appendChild(tableWrap);
        container.appendChild(card);
    }
}

function buildItemRow(c) {
    var tr = document.createElement('tr');

    var detailBits = [];
    if (c.constraint) detailBits.push('Constraint: <code>' + escapeHtml(c.constraint) + '</code>');
    if (c.note) detailBits.push(escapeHtml(c.note));
    if (c.suppression && c.suppression.grund) {
        detailBits.push('<span class="suppression-note">Suppression: ' + escapeHtml(c.suppression.grund) +
            (c.suppression.trigger ? ' &middot; Trigger: ' + escapeHtml(c.suppression.trigger) : '') + '</span>');
    }
    if (c.fundorte && c.fundorte.length) {
        detailBits.push('<span class="fundort">' + escapeHtml(c.fundorte.join(' · ')) + '</span>');
    }
    var detailHtml = detailBits.length
        ? '<div class="text-muted text-small item-details">' + detailBits.join('<br>') + '</div>'
        : '';

    var repoHtml = (c.repo || []).map(function(r) {
        return '<span class="chip">' + escapeHtml(r) + '</span>';
    }).join(' ');

    var linkHtml = c.link
        ? '<a href="' + escapeHtml(c.link) + '" target="_blank" rel="noopener noreferrer">' +
          (c.link.indexOf('github.com') !== -1 ? 'GitHub' : 'Docs') + '</a>'
        : '-';

    var errHtml = c.error ? '<div class="text-danger text-small">' + escapeHtml(c.error) + '</div>' : '';

    tr.innerHTML =
        '<td><strong>' + escapeHtml(c.artefakt) + '</strong>' + detailHtml + '</td>' +
        '<td><code>' + escapeHtml(c.ist == null ? '-' : c.ist) + '</code></td>' +
        '<td><span class="chip">' + escapeHtml(c.artLabel || artText(c.art)) + '</span></td>' +
        '<td><code>' + escapeHtml(c.latest == null ? '-' : c.latest) + '</code></td>' +
        '<td><span class="badge ' + getBadgeClass(c.status) + '">' + getStatusText(c.status) + '</span>' + errHtml + '</td>' +
        '<td>' + repoHtml + '</td>' +
        '<td>' + linkHtml + '</td>';
    return tr;
}

function renderTermine() {
    var container = document.getElementById('termineSection');
    container.textContent = '';
    var termine = inventory.termine || [];
    if (!termine.length) return;

    var card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = '<h3 class="category-title">Termine &amp; Verfallsdaten</h3>' +
        '<p class="text-muted text-small mb-2">Timeline für anstehende Entscheidungen und Fristen</p>' +
        '<div class="table-container"><table><thead><tr>' +
        '<th scope="col">Datum</th><th scope="col">Ereignis</th><th scope="col">Status</th>' +
        '</tr></thead><tbody></tbody></table></div>';
    var tbody = card.querySelector('tbody');

    var soonLimit = Date.now() + 60 * 24 * 3600 * 1000; // 60 Tage
    for (var i = 0; i < termine.length; i++) {
        var t = termine[i];
        var done = /^erledigt/.test(t.status || '');
        var due = Date.parse(t.datum);
        var soon = !done && !isNaN(due) && due < soonLimit;
        var badgeClass = done ? 'badge-success' : (soon ? 'badge-warning' : 'badge-neutral');

        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td class="nowrap"><code>' + escapeHtml(t.datumLabel || formatDate(t.datum)) + '</code></td>' +
            '<td>' + escapeHtml(t.ereignis) + '</td>' +
            '<td><span class="badge ' + badgeClass + '">' + escapeHtml(t.status) + '</span></td>';
        tbody.appendChild(tr);
    }
    container.appendChild(card);
}

function renderKontrakte() {
    var container = document.getElementById('kontrakteSection');
    container.textContent = '';
    var kontrakte = inventory.kontrakte || [];
    if (!kontrakte.length) return;

    var card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = '<h3 class="category-title">Cross-Repo-Kontrakte</h3>' +
        '<p class="text-muted text-small mb-2">Konsistenz statt Latest - Werte müssen zwischen den Repos übereinstimmen</p>' +
        '<div class="table-container"><table><thead><tr>' +
        '<th scope="col">Kontrakt</th><th scope="col">Beteiligte</th><th scope="col">Prüfung</th>' +
        '</tr></thead><tbody></tbody></table></div>';
    var tbody = card.querySelector('tbody');

    for (var i = 0; i < kontrakte.length; i++) {
        var k = kontrakte[i];
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td><strong>' + escapeHtml(k.name) + '</strong></td>' +
            '<td>' + escapeHtml(k.beteiligte) +
                (k.fundorte ? '<div class="text-muted text-small fundort">' + escapeHtml(k.fundorte) + '</div>' : '') + '</td>' +
            '<td>' + escapeHtml(k.pruefung) + '</td>';
        tbody.appendChild(tr);
    }
    container.appendChild(card);
}

function renderHinweise() {
    var container = document.getElementById('hinweiseSection');
    container.textContent = '';
    var hinweise = inventory.hinweise || [];
    if (!hinweise.length) return;

    var card = document.createElement('div');
    card.className = 'card';
    var listHtml = hinweise.map(function(h) {
        return '<li>' + escapeHtml(h) + '</li>';
    }).join('');
    card.innerHTML = '<h3 class="category-title">Bewusste Entscheidungen</h3>' +
        '<p class="text-muted text-small mb-2">Sieht wie ein Befund aus, ist aber ein dokumentierter Entscheid - nicht alarmieren</p>' +
        '<ul class="hint-list">' + listHtml + '</ul>';
    container.appendChild(card);
}

function formatDate(iso) {
    if (!iso) return '-';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString('de-DE', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function artText(art) {
    if (art === 'pin') return 'Pin';
    if (art === 'lock') return 'Lock';
    if (art === 'constraint') return 'Constraint';
    if (art === 'floating') return 'Floating';
    return 'Intern';
}

function getBadgeClass(status) {
    if (status === 'current') return 'badge-success';
    if (status === 'outdated') return 'badge-warning';
    if (status === 'error') return 'badge-danger';
    if (status === 'suppressed') return 'badge-info';
    return 'badge-neutral';
}

function getStatusText(status) {
    if (status === 'current') return 'Aktuell';
    if (status === 'outdated') return 'Update';
    if (status === 'suppressed') return 'Suppressed';
    if (status === 'floating') return 'Floating';
    if (status === 'azure') return 'Azure (kein Abruf)';
    if (status === 'manual') return 'Manuell';
    if (status === 'intern') return 'Intern';
    return 'Fehler';
}
