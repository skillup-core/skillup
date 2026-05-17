// Initialization: desktop startup sequence.

async function init() {
    initDragDrop();

    var config = await apiCall('get_config');
    if (config && config.language) {
        currentLanguage = config.language;
        window.currentLanguage = currentLanguage;
        document.getElementById('language-select').value = currentLanguage;
    }

    if (config && config.theme) {
        document.getElementById('theme-select').value = config.theme;
        var themeStylesheet = document.getElementById('theme-stylesheet');
        if (themeStylesheet && config.theme !== 'default') {
            themeStylesheet.href = '/common/style/' + config.theme + '.css';
        }
        if (appContentIframe) sendToIframe('setTheme', { theme: config.theme });
    }

    applyTranslations();

    var homeMenuItem = document.querySelector('#desktop-menu [data-page="home"]');
    if (homeMenuItem) {
        var svgElement = homeMenuItem.querySelector('svg');
        if (svgElement) setTopBarIconSVG(svgElement.cloneNode(true));
    }

    if (config && config.build) {
        var buildEl = document.getElementById('app-build');
        if (buildEl) buildEl.textContent = config.build;
    }
    if (config && config.version) {
        var versionEl = document.getElementById('app-version');
        if (versionEl) versionEl.textContent = config.version;
    }
    if (config && config.build_date) {
        var buildDateEl = document.getElementById('app-build-date');
        if (buildDateEl) buildDateEl.textContent = config.build_date;
    }

    await loadApps();
    updateClock();
    refreshAccountPhoto();
    await apiCall('desktop_ready');
}

document.addEventListener('DOMContentLoaded', init);
