// Ctrl+Tab app switcher, iframe tab trap, ibus IME workaround.

// ============================================================================
// iframeTabTrap: installed by desktop_handlers.js files via desktopBus
// ============================================================================
(function() {
    var _doc = null, _handler = null;
    desktopBus.installIframeTabTrap = function(sourceWindow) {
        desktopBus.removeIframeTabTrap();
        try {
            var iframeDoc = sourceWindow && sourceWindow.document;
            if (!iframeDoc) return;
            _handler = function(e) {
                if (e.key === 'Tab') {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                }
            };
            iframeDoc.addEventListener('keydown', _handler, true);
            _doc = iframeDoc;
        } catch(e) {}
    };
    desktopBus.removeIframeTabTrap = function() {
        if (_doc && _handler) {
            try { _doc.removeEventListener('keydown', _handler, true); } catch(e) {}
            _doc = null; _handler = null;
        }
    };
})();

// ============================================================================
// App Switcher (Ctrl+Tab)
// ============================================================================
var switcherActive = false;
var switcherIndex = -1;

function getSwitcherApps() {
    return runningApps.map(function(id) { return apps.find(function(a) { return a.id === id; }); }).filter(Boolean);
}

function showSwitcher(reverse) {
    var list = getSwitcherApps();
    if (list.length === 0) return;

    if (!switcherActive) {
        switcherActive = true;
        var curId = currentApp ? currentApp.id : null;
        switcherIndex = curId ? list.findIndex(function(a) { return a.id === curId; }) : list.length - 1;
        if (switcherIndex === -1) switcherIndex = list.length - 1;
    }

    if (reverse) switcherIndex = (switcherIndex - 1 + list.length) % list.length;
    else         switcherIndex = (switcherIndex + 1) % list.length;

    renderSwitcher(list);
    document.getElementById('app-switcher').classList.add('visible');
}

function renderSwitcher(list) {
    var container = document.getElementById('app-switcher-list');
    container.innerHTML = '';
    list.forEach(function(app, i) {
        var item = document.createElement('div');
        item.className = 'app-switcher-item' + (i === switcherIndex ? ' selected' : '');
        var iconSrc = app.icon ? '/app/' + app.id + '/' + app.icon : '/common/resource/img/favicon.svg';
        item.innerHTML = '<img src="' + iconSrc + '" onerror="this.src=\'/common/resource/img/favicon.svg\'"><span>' + app.name + '</span>';
        item.onclick = function() { switcherIndex = i; commitSwitcher(); };
        container.appendChild(item);
    });
}

async function commitSwitcher() {
    var list = getSwitcherApps();
    document.getElementById('app-switcher').classList.remove('visible');
    switcherActive = false;
    if (list.length === 0 || switcherIndex < 0 || switcherIndex >= list.length) return;
    var target = list[switcherIndex];
    switcherIndex = -1;
    if (!currentApp || currentApp.id !== target.id) await launchApp(target.id);
}

window.addEventListener('keydown', function(e) {
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
}, true);

document.addEventListener('keydown', function(e) {
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
}, true);

window.addEventListener('keyup', function(e) {
    if (switcherActive && e.key === 'Control') {
        e.preventDefault();
        e.stopImmediatePropagation();
        commitSwitcher();
    }
}, true);

document.addEventListener('keyup', function(e) {
    if (switcherActive && e.key === 'Control') {
        e.preventDefault();
        e.stopImmediatePropagation();
        commitSwitcher();
    }
}, true);

// ============================================================================
// ibus 1.5.3 workaround: track Korean/English IME state
// ============================================================================
(function() {
    var _imeActive = false;
    var _ALPHA_CODES = new Set([
        'KeyA','KeyB','KeyC','KeyD','KeyE','KeyF','KeyG','KeyH','KeyI',
        'KeyJ','KeyK','KeyL','KeyM','KeyN','KeyO','KeyP','KeyQ','KeyR',
        'KeyS','KeyT','KeyU','KeyV','KeyW','KeyX','KeyY','KeyZ'
    ]);

    function setImeActive(active) {
        if (active !== _imeActive) {
            _imeActive = active;
            if (typeof callPython === 'function') {
                callPython('ibus_notify_korean', { ime_active: _imeActive });
            }
        }
    }

    function onCompositionStart() { setImeActive(true); }

    function onKeydown(e) {
        if (_ALPHA_CODES.has(e.code) && e.keyCode !== 229) setImeActive(false);
        var isToggle = (e.key === 'Hangul' || e.key === 'HangulMode' || (e.key === ' ' && e.shiftKey));
        if (isToggle && !_imeActive) {
            e.preventDefault();
            if (typeof callPython === 'function') {
                callPython('ibus_restart_request', { reason: 'toggle_key' });
            }
        }
    }

    function installOnDoc(doc) {
        doc.addEventListener('compositionstart', onCompositionStart, true);
        doc.addEventListener('keydown', onKeydown, true);
    }

    installOnDoc(document);

    function installOnIframe(iframe) {
        try { installOnDoc(iframe.contentWindow.document); } catch(ex) {}
    }

    var _iframeObserver = new MutationObserver(function() {
        var iframes = document.querySelectorAll('iframe.iframe-visible');
        iframes.forEach(function(iframe) {
            if (iframe._ibusTrackerInstalled) return;
            installOnIframe(iframe);
            iframe.addEventListener('load', function() { installOnIframe(iframe); });
            iframe._ibusTrackerInstalled = true;
        });
    });

    document.addEventListener('DOMContentLoaded', function() {
        var appContent = document.getElementById('app-content');
        if (appContent) {
            _iframeObserver.observe(appContent, {
                childList: true, subtree: true, attributes: true, attributeFilter: ['class']
            });
        }
    });
})();
