// App lifecycle: loading, drag-drop reorder, taskbar, launch/exit, iframe management, desktopBus.

// ============================================================================
// App loading and drag-drop reorder
// ============================================================================
var dragState = null;
var dragOccurred = false;

async function loadApps() {
    var result = await apiCall('get_apps');
    if (result && result.apps) {
        apps = result.apps;
        renderApps();
    }
}

async function saveAppOrder() {
    var order = apps.map(function(a) { return a.id; }).join(',');
    await apiCall('set_config', { app_order: order });
}

// Returns { refEl, before } describing where to insert the dragged icon.
// Uses insertion-index logic so adjacent icons always agree on the gap position,
// preventing a double-indicator effect.
function findInsertPoint(clientX, clientY, rects) {
    if (rects.length === 0) return null;

    // Group into rows by top coordinate (tolerance 10px)
    var rows = [];
    rects.forEach(function(item) {
        var rowTop = item.rect.top;
        var row = null;
        for (var i = 0; i < rows.length; i++) {
            if (Math.abs(rows[i].top - rowTop) < 10) { row = rows[i]; break; }
        }
        if (!row) { row = { top: rowTop, items: [] }; rows.push(row); }
        row.items.push(item);
    });
    rows.forEach(function(row) { row.items.sort(function(a, b) { return a.rect.left - b.rect.left; }); });
    rows.sort(function(a, b) { return a.top - b.top; });

    // Find the best row: prefer one whose vertical range contains clientY
    var targetRow = null;
    for (var i = 0; i < rows.length; i++) {
        var first = rows[i].items[0].rect;
        var last  = rows[i].items[rows[i].items.length - 1].rect;
        var rowBottom = Math.max.apply(null, rows[i].items.map(function(it) { return it.rect.bottom; }));
        if (clientY >= first.top && clientY <= rowBottom) { targetRow = rows[i]; break; }
    }
    // Fallback: nearest row by vertical center distance
    if (!targetRow) {
        var nearestRowDist = Infinity;
        rows.forEach(function(row) {
            var midY = (row.items[0].rect.top + Math.max.apply(null, row.items.map(function(it) { return it.rect.bottom; }))) / 2;
            var dist = Math.abs(clientY - midY);
            if (dist < nearestRowDist) { nearestRowDist = dist; targetRow = row; }
        });
    }
    if (!targetRow) return null;

    var items = targetRow.items;
    // Find insertion index by midpoint of each icon
    for (var j = 0; j < items.length; j++) {
        var mid = items[j].rect.left + items[j].rect.width / 2;
        if (clientX < mid) {
            // Insert before items[j]
            return { refEl: items[j].el, before: true };
        }
    }
    // Cursor is past all icons in this row: insert after the last one
    return { refEl: items[items.length - 1].el, before: false };
}

// Place the drop indicator line in the center of the gap between icons.
function positionIndicator(indicator, refEl, before, iconRects) {
    var r = refEl.getBoundingClientRect();
    var lineH = Math.round(r.height * 0.5);
    var x;

    if (before) {
        // Find the icon immediately to the left of refEl in the same row
        var prev = null;
        iconRects.forEach(function(item) {
            if (item.el === refEl) return;
            if (Math.abs(item.rect.top - r.top) < 10 && item.rect.right <= r.left) {
                if (!prev || item.rect.right > prev.rect.right) prev = item;
            }
        });
        x = prev ? Math.round((prev.rect.right + r.left) / 2) - 1 : r.left - 2;
    } else {
        // Find the icon immediately to the right of refEl in the same row
        var next = null;
        iconRects.forEach(function(item) {
            if (item.el === refEl) return;
            if (Math.abs(item.rect.top - r.top) < 10 && item.rect.left >= r.right) {
                if (!next || item.rect.left < next.rect.left) next = item;
            }
        });
        x = next ? Math.round((r.right + next.rect.left) / 2) - 1 : r.right + 2;
    }

    indicator.style.left   = x + 'px';
    indicator.style.top    = (r.top + Math.round((r.height - lineH) / 2)) + 'px';
    indicator.style.height = lineH + 'px';
}

function initDragDrop() {
    document.addEventListener('mousemove', function(e) {
        if (!dragState) return;
        var dx = e.clientX - dragState.startX;
        var dy = e.clientY - dragState.startY;
        if (!dragState.active && Math.sqrt(dx * dx + dy * dy) < 6) return;

        var grid = document.getElementById('app-grid');
        var srcIcon = grid.querySelector('[data-app-id="' + dragState.appId + '"]');
        if (!srcIcon) return;

        if (!dragState.active) {
            dragState.active = true;
            document.body.style.userSelect = 'none';
            srcIcon.classList.add('dragging');

            var rect = srcIcon.getBoundingClientRect();
            var ghost = srcIcon.cloneNode(true);
            ghost.classList.remove('dragging');
            ghost.style.cssText = 'position:fixed;pointer-events:none;opacity:0.85;z-index:9999;' +
                'width:' + srcIcon.offsetWidth + 'px;top:' + rect.top + 'px;left:' + rect.left + 'px;';
            document.body.appendChild(ghost);
            dragState.ghost = ghost;
            dragState.ghostOffX = e.clientX - rect.left;
            dragState.ghostOffY = e.clientY - rect.top;

            // Snapshot rects once; reuse during drag.
            // iconRects: non-src only (for findInsertPoint)
            // allIconRects: all icons including src (for positionIndicator gap calc)
            var allIcons = Array.from(grid.querySelectorAll('.app-icon'));
            dragState.allIconRects = allIcons.map(function(el) {
                return { el: el, rect: el.getBoundingClientRect() };
            });
            dragState.iconRects = dragState.allIconRects.filter(function(item) {
                return item.el.dataset.appId !== dragState.appId;
            });

            // Create drop indicator element
            var indicator = document.createElement('div');
            indicator.className = 'drag-drop-indicator';
            indicator.style.display = 'none';
            document.body.appendChild(indicator);
            dragState.indicator = indicator;

            // Record src's original neighbors to suppress indicator at its own position
            dragState.origPrev = srcIcon.previousElementSibling;
            dragState.origNext = srcIcon.nextElementSibling;

            dragState.lastDropKey = null;
            dragState.dropTarget = null;
        }

        dragState.ghost.style.left = (e.clientX - dragState.ghostOffX) + 'px';
        dragState.ghost.style.top  = (e.clientY - dragState.ghostOffY) + 'px';

        var hit = findInsertPoint(e.clientX, e.clientY, dragState.iconRects);
        if (hit) {
            // Suppress indicator when hit resolves to src's original position:
            // "before nextSibling" and "after prevSibling" both mean "same slot"
            var isSameSlot = (hit.before  && hit.refEl === dragState.origNext) ||
                             (!hit.before && hit.refEl === dragState.origPrev);
            var key = isSameSlot ? '__same__' : hit.refEl.dataset.appId + (hit.before ? 'B' : 'A');
            if (key !== dragState.lastDropKey) {
                dragState.lastDropKey = key;
                if (isSameSlot) {
                    dragState.dropTarget = null;
                    dragState.indicator.style.display = 'none';
                } else {
                    dragState.dropTarget = hit;
                    positionIndicator(dragState.indicator, hit.refEl, hit.before, dragState.allIconRects);
                    dragState.indicator.style.display = 'block';
                }
            }
        }
    });

    document.addEventListener('mouseup', function() {
        if (!dragState) return;
        commitDrag();
    });

    document.addEventListener('keydown', function(e) {
        if (!dragState || !dragState.active) return;
        if (e.key === 'Escape') {
            e.preventDefault();
            cancelDrag();
        }
    });
}

function cancelDrag() {
    if (!dragState) return;
    var grid = document.getElementById('app-grid');
    document.body.style.userSelect = '';
    if (dragState.ghost) dragState.ghost.remove();
    if (dragState.indicator) dragState.indicator.remove();
    var srcIcon = grid.querySelector('[data-app-id="' + dragState.appId + '"]');
    if (srcIcon) srcIcon.classList.remove('dragging');
    dragState = null;
}

function commitDrag() {
    if (!dragState) return;
    var grid = document.getElementById('app-grid');
    document.body.style.userSelect = '';

    if (dragState.ghost) dragState.ghost.remove();
    if (dragState.indicator) dragState.indicator.remove();

    var srcIcon = grid.querySelector('[data-app-id="' + dragState.appId + '"]');
    if (srcIcon) srcIcon.classList.remove('dragging');

    if (dragState.active && dragState.dropTarget) {
        dragOccurred = true;
        var drop = dragState.dropTarget;
        if (drop.before) grid.insertBefore(srcIcon, drop.refEl);
        else grid.insertBefore(srcIcon, drop.refEl.nextSibling);

        var orderedIds = Array.from(grid.querySelectorAll('.app-icon')).map(function(el) { return el.dataset.appId; });
        apps = orderedIds.map(function(id) { return apps.find(function(a) { return a.id === id; }); }).filter(Boolean);
        saveAppOrder();
    } else if (dragState.active) {
        dragOccurred = true;
    }

    dragState = null;
}

function renderApps() {
    var grid = document.getElementById('app-grid');
    var emptyState = document.getElementById('empty-state');
    grid.innerHTML = '';

    if (apps.length === 0) {
        emptyState.style.display = 'block';
        return;
    }
    emptyState.style.display = 'none';

    apps.forEach(function(app) {
        var iconDiv = document.createElement('div');
        iconDiv.className = 'app-icon';
        iconDiv.tabIndex = 0;
        iconDiv.setAttribute('role', 'button');
        iconDiv.dataset.appId = app.id;
        iconDiv.onclick = function() {
            if (dragOccurred) { dragOccurred = false; return; }
            launchApp(app.id);
        };
        iconDiv.onfocus = function() { iconDiv.classList.add('custom-focused'); };
        iconDiv.onblur  = function() { iconDiv.classList.remove('custom-focused'); };
        iconDiv.onkeydown = function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                launchApp(app.id);
            } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                var icons = Array.from(grid.querySelectorAll('.app-icon'));
                var idx = icons.indexOf(iconDiv);
                if (idx === -1) return;
                var cols = Math.floor(grid.offsetWidth / (icons[0] ? icons[0].offsetWidth : 1)) || 1;
                var next = -1;
                if (e.key === 'ArrowRight') next = idx + 1;
                else if (e.key === 'ArrowLeft') next = idx - 1;
                else if (e.key === 'ArrowDown') next = idx + cols;
                else if (e.key === 'ArrowUp') next = idx - cols;
                if (next >= 0 && next < icons.length) { e.preventDefault(); icons[next].focus(); }
            }
        };
        iconDiv.addEventListener('mousedown', function(e) {
            if (e.button !== 0) return;
            dragState = { appId: app.id, startX: e.clientX, startY: e.clientY,
                active: false, ghost: null, targetAppId: null, insertBefore: true,
                ghostOffX: 0, ghostOffY: 0 };
        });

        var fallbackSvg = "<svg viewBox=\\'0 0 24 24\\' fill=\\'#4cc9f0\\'><path d=\\'M4 8h4V4H4v4zm6 12h4v-4h-4v4zm-6 0h4v-4H4v4zm0-6h4v-4H4v4zm6 0h4v-4h-4v4zm6-10v4h4V4h-4zm-6 4h4V4h-4v4zm6 6h4v-4h-4v4zm0 6h4v-4h-4v4z\\'/></svg>";
        iconDiv.innerHTML =
            '<div class="app-icon-image">' +
            '<img draggable="false" src="/app/' + app.id + '/icon.svg" alt="' + app.name + '" onerror="this.parentElement.innerHTML=\'' + fallbackSvg + '\'">' +
            '</div>' +
            '<span class="app-icon-name">' + app.name + '</span>';

        grid.appendChild(iconDiv);
    });

    var firstIcon = grid.querySelector('.app-icon');
    if (firstIcon) firstIcon.focus();

    var contentArea = document.getElementById('content-area');
    contentArea.addEventListener('click', function(e) {
        if (e.target === grid || e.target === contentArea) {
            var fi = grid.querySelector('.app-icon');
            if (fi) fi.focus();
        }
    });
}

// ============================================================================
// Taskbar
// ============================================================================
function updateTaskbar() {
    var taskbarApps = document.getElementById('taskbar-apps');
    var taskbarList = document.getElementById('taskbar-app-list');

    if (runningApps.length === 0) {
        taskbarApps.style.display = 'none';
        return;
    }
    taskbarApps.style.display = 'block';
    taskbarList.innerHTML = '';

    runningApps.forEach(function(appId) {
        var appInfo = apps.find(function(a) { return a.id === appId; });
        if (!appInfo) return;

        var item = document.createElement('a');
        item.className = 'taskbar-app-item' + (currentApp && currentApp.id === appId ? ' active' : '');
        item.dataset.appId = appId;

        var iconSrc = '/app/' + appId + '/' + (appInfo.icon || 'icon.svg');
        item.innerHTML = '<img class="taskbar-app-icon" src="' + iconSrc + '" onerror="this.src=\'/common/resource/img/favicon.svg\'" alt=""><span class="taskbar-app-name">' + appInfo.name + '</span><span class="taskbar-app-close"><svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg></span>';

        item.onclick = function(e) {
            if (e.target.closest('.taskbar-app-close')) return;
            launchApp(appId);
        };
        var closeBtn = item.querySelector('.taskbar-app-close');
        closeBtn.onclick = function(e) { e.stopPropagation(); exitAppById(appId); };
        taskbarList.appendChild(item);
    });
}

function setTaskbarActive(appId) {
    document.querySelectorAll('.taskbar-app-item').forEach(function(item) {
        item.classList.toggle('active', item.dataset.appId === appId);
    });
    document.querySelectorAll('#desktop-menu .menu-item').forEach(function(item) {
        item.classList.toggle('active', !appId && item.dataset.page === 'home');
    });
}

// ============================================================================
// App launch / exit
// ============================================================================
var currentAppMenu = null;
var lastAppMenu = {};

async function launchApp(appId, initialMenu) {
    var appInfo = apps.find(function(a) { return a.id === appId; });
    if (appInfo && appInfo.new_window === 'single') {
        var lang = currentLanguage || 'en';
        var menuId = (appInfo.menu_items && appInfo.menu_items.length > 0) ? appInfo.menu_items[0].id : 'dashboard';
        var url = '/app/' + appId + '/' + menuId + '.html?standalone=1&lang=' + lang;
        var focusResult = await apiCall('open_window', { url: url, title: appInfo.name || 'Skillup', mode: 'single' });
        if (focusResult && focusResult.focused) return;
    }

    var result = await apiCall('launch_app', { app_id: appId });
    if (result && result.success) {
        currentApp = apps.find(function(a) { return a.id === appId; });
        _loadAppHandlers(appId);

        if (!runningApps.includes(appId)) runningApps.push(appId);
        updateTaskbar();
        setTaskbarActive(appId);

        document.getElementById('page-title').textContent = currentApp ? currentApp.name : appId;
        setTopBarIcon(currentApp ? '/app/' + currentApp.id + '/' + (currentApp.icon || 'icon.svg') : null);

        document.getElementById('close-app-btn').style.display = 'block';
        document.getElementById('minimize-app-btn').style.display = 'block';
        var newWindowMode = currentApp ? currentApp.new_window : 'false';
        document.getElementById('popout-app-btn').style.display = (newWindowMode === 'false') ? 'none' : 'block';

        document.querySelectorAll('.page').forEach(function(p) { p.style.display = 'none'; });
        var appContent = document.getElementById('app-content');
        appContent.classList.remove('preserve-hidden');
        appContent.style.display = 'block';

        var hasCachedIframes = Object.keys(iframeCache).some(function(key) { return key.startsWith(appId + '_'); });
        if (hasCachedIframes && lastAppMenu[appId]) {
            handleAppMenuClick(lastAppMenu[appId]);
        } else if (initialMenu) {
            handleAppMenuClick(initialMenu);
        } else if (currentApp && currentApp.menu_items && currentApp.menu_items.length > 0) {
            handleAppMenuClick(currentApp.menu_items[0].id);
        } else {
            renderAppView(appId, 'dashboard');
        }
    } else {
        var lang2 = i18n[currentLanguage] || i18n['en'];
        showMessageBox({ title: lang2['app.launch_failed_title'], text: lang2['app.launch_failed_text'] });
    }
}

async function backToDesktop() {
    if (currentApp && currentAppMenu) lastAppMenu[currentApp.id] = currentAppMenu;
    currentApp = null;
    currentAppMenu = null;
    appContentIframe = null;
    currentContentType = null;

    setTaskbarActive(null);
    document.getElementById('close-app-btn').style.display = 'none';
    document.getElementById('minimize-app-btn').style.display = 'none';
    document.getElementById('popout-app-btn').style.display = 'none';

    var appContent = document.getElementById('app-content');
    if (Object.keys(iframeCache).length > 0) {
        appContent.classList.add('preserve-hidden');
    } else {
        appContent.style.display = 'none';
    }
    appContent.querySelectorAll('iframe').forEach(function(iframe) {
        iframe.classList.remove('iframe-visible');
    });

    document.getElementById('page-home').style.display = 'block';
    document.getElementById('page-title').textContent = i18n[currentLanguage]['title.desktop'] || 'Desktop';
    var homeMenuItem = document.querySelector('#desktop-menu [data-page="home"]');
    if (homeMenuItem) {
        var svgElement = homeMenuItem.querySelector('svg');
        if (svgElement) setTopBarIconSVG(svgElement.cloneNode(true));
        else setTopBarIcon(null);
    } else {
        setTopBarIcon(null);
    }
}

function clearAppIframes(appId) {
    var appContent = document.getElementById('app-content');
    Object.keys(iframeCache).forEach(function(key) {
        if (key.startsWith(appId + '_')) {
            var iframe = iframeCache[key];
            if (iframe && iframe.parentElement) iframe.parentElement.removeChild(iframe);
            delete iframeCache[key];
        }
    });
    delete lastAppMenu[appId];
    if (Object.keys(iframeCache).length === 0) {
        appContent.classList.remove('preserve-hidden');
        appContent.style.display = 'none';
    }
}

async function exitApp() {
    var closingAppId = currentApp ? currentApp.id : null;
    await apiCall('close_app');
    await backToDesktop();
    if (closingAppId) {
        clearAppIframes(closingAppId);
        var idx = runningApps.indexOf(closingAppId);
        if (idx !== -1) runningApps.splice(idx, 1);
        updateTaskbar();
    }
}

async function exitAppById(appId) {
    var wasCurrentApp = currentApp && currentApp.id === appId;
    if (wasCurrentApp) { await exitApp(); return; }
    var appInfo = apps.find(function(a) { return a.id === appId; });
    if (appInfo) {
        await apiCall('close_app', { app_id: appId });
        clearAppIframes(appId);
        var idx = runningApps.indexOf(appId);
        if (idx !== -1) runningApps.splice(idx, 1);
        delete lastAppMenu[appId];
        updateTaskbar();
    }
}

function _detachRemoveFromTaskbar(appId) {
    var idx = runningApps.indexOf(appId);
    if (idx !== -1) runningApps.splice(idx, 1);
    currentApp = null;
    currentAppMenu = null;
    updateTaskbar();
}

async function openSuggestBoard() {
    var lang = currentLanguage || 'en';
    var title = (i18n[lang] || i18n['en'])['settings.suggest'] || '건의하기';
    await window.desktopModal.openBoard('suggest_board_info', title);
}

async function openInNewWindow() {
    if (!currentApp || !currentAppMenu) return;
    var lang = currentLanguage || 'en';
    var rawMode = currentApp.new_window || 'true';
    var url = '/app/' + currentApp.id + '/' + currentAppMenu + '.html?standalone=1&lang=' + lang;
    var title = currentApp.name || 'Skillup';

    if (rawMode === 'single') {
        var focusResult = await apiCall('open_window', { url: url, title: title, mode: 'single' });
        if (focusResult && focusResult.focused) return;
        document.body.classList.add('app-standalone');
        await apiCall('detach_to_new_window', { url: url, title: title });
        _detachRemoveFromTaskbar(currentApp.id);
    } else if (rawMode === 'true') {
        document.body.classList.add('app-standalone');
        await apiCall('detach_to_new_window', { url: url, title: title, multi: true });
        _detachRemoveFromTaskbar(currentApp.id);
    } else {
        await apiCall('open_window', { url: url, title: title, mode: 'true' });
    }
}

function handleAppMenuClick(menuId) {
    currentAppMenu = menuId;
    if (currentApp) renderAppView(currentApp.id, menuId);
}

// ============================================================================
// Iframe management
// ============================================================================
window.appContentIframe = null;
var currentContentType = null;
var iframeCache = {};

async function renderAppView(appId, viewId) {
    renderAppViewIframe(appId, viewId, '/app/' + appId + '/' + viewId + '.html', 'view');
}

function renderAppViewIframe(appId, viewId, contentPath, type) {
    var appContent = document.getElementById('app-content');
    var cacheKey = appId + '_' + viewId;
    var langParam = (currentLanguage && currentLanguage !== 'en') ? 'lang=' + encodeURIComponent(currentLanguage) : '';
    if (langParam && contentPath.indexOf('lang=') === -1) {
        contentPath += (contentPath.indexOf('?') !== -1 ? '&' : '?') + langParam;
    }

    if (type === 'view') {
        var iframe = iframeCache[cacheKey];
        if (iframe && iframe.parentElement === appContent) {
            showIframe(iframe);
            appContentIframe = iframe;
            currentContentType = 'view';
            sendToIframe('setLanguage', { language: currentLanguage });
            sendToIframe('setTheme', { theme: document.getElementById('theme-select').value || 'default' });
            sendToIframe('setActiveTab', { viewId: viewId });
        } else {
            iframe = document.createElement('iframe');
            iframe.id = 'app-iframe-' + cacheKey;
            iframe.dataset.appId = appId;
            iframe.dataset.viewId = viewId;
            iframe.dataset.cacheKey = cacheKey;
            iframe.style.border = 'none';
            iframe.src = contentPath;
            appContent.appendChild(iframe);
            iframeCache[cacheKey] = iframe;
            appContentIframe = iframe;
            currentContentType = 'view';
            iframe.onload = function() {
                setTimeout(function() {
                    showIframe(iframe);
                    sendToIframe('setLanguage', { language: currentLanguage });
                    sendToIframe('setTheme', { theme: document.getElementById('theme-select').value || 'default' });
                }, 100);
            };
        }
    } else {
        var contentCacheKey = appId + '_content';
        if (!appContentIframe || appContentIframe.dataset.appId !== appId || currentContentType !== 'content') {
            var cachedIframe = iframeCache[contentCacheKey];
            if (cachedIframe && cachedIframe.parentElement === appContent) {
                showIframe(cachedIframe);
                appContentIframe = cachedIframe;
                currentContentType = 'content';
                sendToIframe('setLanguage', { language: currentLanguage });
                sendToIframe('setTheme', { theme: document.getElementById('theme-select').value || 'default' });
                sendToIframe('showView', { viewId: viewId });
            } else {
                var newIframe = document.createElement('iframe');
                newIframe.id = 'app-iframe-' + contentCacheKey;
                newIframe.dataset.appId = appId;
                newIframe.dataset.cacheKey = contentCacheKey;
                newIframe.style.border = 'none';
                newIframe.src = contentPath;
                appContent.appendChild(newIframe);
                iframeCache[contentCacheKey] = newIframe;
                appContentIframe = newIframe;
                currentContentType = 'content';
                newIframe.onload = function() {
                    setTimeout(function() {
                        showIframe(newIframe);
                        sendToIframe('setLanguage', { language: currentLanguage });
                        sendToIframe('setTheme', { theme: document.getElementById('theme-select').value || 'default' });
                        sendToIframe('showView', { viewId: viewId });
                    }, 100);
                };
            }
        } else {
            sendToIframe('showView', { viewId: viewId });
        }
    }
}

function showIframe(targetIframe) {
    var appContent = document.getElementById('app-content');
    appContent.querySelectorAll('iframe').forEach(function(iframe) {
        iframe.classList.remove('iframe-visible');
    });
    targetIframe.classList.add('iframe-visible');
    if (targetIframe.contentWindow) {
        targetIframe.contentWindow.postMessage({ action: 'requestFocus' }, '*');
    }
    try {
        if (targetIframe.contentWindow) {
            var iframeDoc = targetIframe.contentWindow.document;
            if (iframeDoc) {
                iframeDoc.addEventListener('keydown', handleIframeKeydown, true);
                iframeDoc.addEventListener('keyup', handleIframeKeyup, true);
            }
        }
    } catch(e) {}
}

function handleIframeKeydown(e) {
    if (e.ctrlKey && e.key === 'Tab') {
        e.preventDefault();
        e.stopImmediatePropagation();
        showSwitcher(e.shiftKey);
    } else if (switcherActive && e.key === 'Escape') {
        e.preventDefault();
        e.stopImmediatePropagation();
        document.getElementById('app-switcher').classList.remove('visible');
        switcherActive = false;
        switcherIndex = -1;
    }
}

function handleIframeKeyup(e) {
    if (switcherActive && e.key === 'Control') {
        e.preventDefault();
        e.stopImmediatePropagation();
        commitSwitcher();
    }
}

function sendToIframe(action, data) {
    data = data || {};
    if (appContentIframe && appContentIframe.contentWindow) {
        appContentIframe.contentWindow.postMessage(Object.assign({ action: action }, data), '*');
    }
}

// ============================================================================
// desktopBus: app-specific message handler registry
// ============================================================================
window.desktopBus = (function() {
    var _handlers = {};
    return {
        on:       function(action, fn) { _handlers[action] = fn; },
        off:      function(action)     { delete _handlers[action]; },
        has:      function(action)     { return !!_handlers[action]; },
        dispatch: function(action, data, event) {
            if (_handlers[action]) { _handlers[action](data, event); return true; }
            return false;
        }
    };
})();

function _loadAppHandlers(appId, onLoad) {
    var url = '/app/' + appId + '/web/desktop_handlers.js';
    var old = document.getElementById('_app_handlers_script');
    if (old) old.remove();
    var script = document.createElement('script');
    script.id = '_app_handlers_script';
    script.src = url;
    script.onload  = onLoad || null;
    script.onerror = onLoad || null;
    document.head.appendChild(script);
}

// Listen for messages from iframes
window.addEventListener('message', function(event) {
    var data = event.data;
    if (!data || !data.action) return;

    if (desktopBus.dispatch(data.action, data, event)) return;

    switch (data.action) {
        case 'contentReady':
            if (currentAppMenu) sendToIframe('showView', { viewId: currentAppMenu });
            sendToIframe('setLanguage', { language: currentLanguage });
            sendToIframe('setTheme', { theme: document.getElementById('theme-select').value || 'default' });
            break;
        case 'viewReady':
            sendToIframe('setLanguage', { language: currentLanguage });
            sendToIframe('setTheme', { theme: document.getElementById('theme-select').value || 'default' });
            break;
        case 'api':
            handleIframeApiCall(data);
            break;
        case 'showMessageBox':
            window.showMessageBox({ title: data.title, text: data.text });
            break;
        case 'switchView':
            if (data.viewId && currentApp) handleAppMenuClick(data.viewId);
            break;
        case 'navigateIframe':
            // Navigate current app iframe to a new URL (with query params).
            // Keep iframeCache entry so the app restores to this page on re-focus.
            if (data.url && appContentIframe) {
                // Resolve relative URLs against the iframe's current src so that
                // "project_new.html" becomes "/app/c0d3hub1/project_new.html" instead
                // of being resolved relative to the desktop page.
                var resolvedUrl = data.url;
                if (resolvedUrl && !/^https?:\/\/|^\//.test(resolvedUrl)) {
                    var currentSrc = appContentIframe.src || '';
                    var basePath = currentSrc.substring(0, currentSrc.lastIndexOf('/') + 1);
                    if (basePath) resolvedUrl = basePath + resolvedUrl;
                }
                appContentIframe.src = resolvedUrl;
            }
            break;
        case 'desktopModal.close':
            window.desktopModal.close();
            break;
    }
});

async function handleIframeApiCall(data) {
    var result = await apiCall(data.apiAction, data.apiData || {});
    if (appContentIframe && appContentIframe.contentWindow) {
        appContentIframe.contentWindow.postMessage({ messageId: data.messageId, result: result }, '*');
    }
}
