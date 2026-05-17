// UI helpers: sidebar toggle, page navigation, top-bar icon.

function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    var sidebar = document.querySelector('.sidebar');
    sidebar.classList.add('animating');
    if (sidebarCollapsed) {
        sidebar.classList.add('collapsed');
    } else {
        sidebar.classList.remove('collapsed');
    }
    setTimeout(function() { sidebar.classList.remove('animating'); }, 200);
}

function showPage(pageName) {
    currentPage = pageName;

    if (currentApp && currentAppMenu) {
        lastAppMenu[currentApp.id] = currentAppMenu;
    }
    currentApp = null;
    currentAppMenu = null;
    appContentIframe = null;
    currentContentType = null;

    document.querySelectorAll('.page').forEach(function(p) { p.style.display = 'none'; });
    var appContent = document.getElementById('app-content');
    if (Object.keys(iframeCache).length > 0) {
        appContent.classList.add('preserve-hidden');
    } else {
        appContent.style.display = 'none';
    }
    appContent.querySelectorAll('iframe').forEach(function(iframe) {
        iframe.classList.remove('iframe-visible');
    });

    var page = document.getElementById('page-' + pageName);
    if (page) page.style.display = 'block';

    document.getElementById('close-app-btn').style.display = 'none';
    document.getElementById('minimize-app-btn').style.display = 'none';
    document.getElementById('popout-app-btn').style.display = 'none';

    setTaskbarActive(null);
    document.querySelectorAll('#desktop-menu .menu-item').forEach(function(item) {
        item.classList.remove('active');
        if (item.dataset.page === pageName) item.classList.add('active');
    });

    var titleKey = 'title.' + (pageName === 'home' ? 'desktop' : pageName);
    document.getElementById('page-title').textContent = i18n[currentLanguage][titleKey] || pageName;

    var menuItem = document.querySelector('#desktop-menu [data-page="' + pageName + '"]');
    if (menuItem) {
        var svgElement = menuItem.querySelector('svg');
        if (svgElement) setTopBarIconSVG(svgElement.cloneNode(true));
        else setTopBarIcon(null);
    } else {
        setTopBarIcon(null);
    }

    if (pageName === 'settings') {
        loadHotkeyStatus();
        loadAccount();
        loadGroups();
        var settingsPage = document.getElementById('page-settings');
        if (settingsPage) setTimeout(function() { settingsPage.focus({ preventScroll: true }); }, 0);
    }
}

function setTopBarIcon(iconSrc) {
    var img = document.getElementById('top-bar-icon');
    var svgWrapper = document.getElementById('top-bar-svg');
    if (iconSrc) {
        img.src = iconSrc;
        img.style.display = 'inline-block';
        if (svgWrapper) svgWrapper.style.display = 'none';
    } else {
        img.style.display = 'none';
        if (svgWrapper) svgWrapper.style.display = 'none';
    }
}

function setTopBarIconSVG(svgElement) {
    var img = document.getElementById('top-bar-icon');
    if (svgElement) {
        svgElement.setAttribute('width', '22');
        svgElement.setAttribute('height', '22');
        svgElement.style.flexShrink = '0';
        svgElement.style.color = 'currentColor';

        svgElement.querySelectorAll('*').forEach(function(el) {
            var hasStroke = el.getAttribute('stroke');
            var hasFill = el.getAttribute('fill');
            if (hasStroke && hasFill === 'none') {
                if (hasStroke !== 'currentColor') el.setAttribute('stroke', 'currentColor');
            } else if (hasStroke && !hasFill) {
                el.setAttribute('stroke', 'currentColor');
            } else if (!hasFill && !hasStroke) {
                el.setAttribute('fill', 'currentColor');
            }
        });

        var iconContainer = img.parentElement;
        img.style.display = 'none';
        var svgWrapper = iconContainer.querySelector('#top-bar-svg');
        if (svgWrapper) {
            svgWrapper.replaceChild(svgElement, svgWrapper.firstChild);
        } else {
            svgWrapper = document.createElement('div');
            svgWrapper.id = 'top-bar-svg';
            svgWrapper.style.display = 'inline-flex';
            svgWrapper.style.alignItems = 'center';
            svgWrapper.style.marginRight = '8px';
            svgWrapper.appendChild(svgElement);
            iconContainer.insertBefore(svgWrapper, img);
        }
        svgWrapper.style.display = 'inline-flex';
    } else {
        img.style.display = 'none';
        var svgWrapper2 = img.parentElement.querySelector('#top-bar-svg');
        if (svgWrapper2) svgWrapper2.style.display = 'none';
    }
}
