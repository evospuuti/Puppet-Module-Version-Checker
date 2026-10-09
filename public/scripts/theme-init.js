// Theme-Erkennung vor dem ersten Render (verhindert Flash of White).
// localStorage kann werfen (Storage blockiert, Privatmodus) - dann gilt
// die Systemeinstellung.
(function() {
    var t = null;
    try { t = localStorage.getItem('theme'); } catch (e) {}
    if (t === 'dark' || (!t && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
    }
})();
