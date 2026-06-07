// Help overlay system: interactive guided tour for desktop apps.

(function() {
    'use strict';

    var helpData = null;
    var tipPages = [];        // TIP00.md, TIP01.md, ... contents in order
    var tipPageIdx = 0;
    var activeScene = null;
    var currentStepIdx = -1;
    var preFocusElement = null;
    var dimPanels = [];
    var outlineEl = null;
    var tooltipEl = null;
    var introOverlay = null;
    var tipView = false;      // true when showing TIP content inside intro card
    var resizeObservers = [];
    var keyListeners = [];
    var markCache = {};
    var mutationWatcher = null;
    var mutationTimer = null;

    function t(key, fallback) {
        var lang = window.currentLanguage || 'en';
        var dict = (window.i18n && window.i18n[lang]) || {};
        return dict[key] || (window.i18n && window.i18n['en'] && window.i18n['en'][key]) || fallback || key;
    }

    function loc(obj) {
        if (!obj) return '';
        var lang = window.currentLanguage || 'en';
        return obj[lang] || obj['en'] || '';
    }

    function renderMd(text) {
        if (!text) return '';
        if (markCache[text]) return markCache[text];
        var raw = text;
        raw = raw.replace(/<script[\s\S]*?<\/script>/gi, '');
        raw = raw.replace(/on\w+\s*=/gi, 'data-removed=');
        raw = raw.replace(/javascript:/gi, '');
        var html;
        if (window.marked) {
            html = window.marked.parse(raw);
        } else {
            html = '<p>' + raw.replace(/\n/g, '<br>') + '</p>';
        }
        markCache[text] = html;
        return html;
    }

    function getActiveIframe() {
        return window.appContentIframe || null;
    }

    function iframeOffset() {
        var frame = getActiveIframe();
        if (!frame) return { top: 0, left: 0 };
        return frame.getBoundingClientRect();
    }

    function toTopRect(el, scope) {
        var r = el.getBoundingClientRect();
        if (scope === 'desktop') {
            return { top: r.top, left: r.left, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
        }
        var fr = iframeOffset();
        return {
            top: r.top + fr.top,
            left: r.left + fr.left,
            right: r.right + fr.left,
            bottom: r.bottom + fr.top,
            width: r.width,
            height: r.height
        };
    }

    function detectScene() {
        if (!helpData || !helpData.scenes) return null;
        var frame = getActiveIframe();
        for (var i = 0; i < helpData.scenes.length; i++) {
            var scene = helpData.scenes[i];
            if (!scene.detect) return scene;
            var detect = scene.detect;
            if (detect.present) {
                var el = resolveDetectSelector(detect.present, frame);
                if (el) return scene;
            } else if (detect.absent) {
                var el2 = resolveDetectSelector(detect.absent, frame);
                if (!el2) return scene;
            }
        }
        return null;
    }

    function resolveDetectSelector(selector, frame) {
        var el = document.querySelector(selector);
        if (el) return el;
        if (frame && frame.contentDocument) {
            try { return frame.contentDocument.querySelector(selector); } catch(e) {}
        }
        return null;
    }

    function stepScope(step) {
        if (step.scope) return step.scope;
        return (helpData && helpData.scope) || 'iframe';
    }

    function resolveStep(step) {
        var scope = stepScope(step);
        var selector = step.selector;
        if (!selector) return null;

        // apply trap_within constraint
        var trap = activeScene && activeScene.trap_within;
        if (trap) {
            var container;
            if (scope === 'desktop') {
                container = document.querySelector(trap);
            } else {
                var frame = getActiveIframe();
                if (frame && frame.contentDocument) {
                    try { container = frame.contentDocument.querySelector(trap); } catch(e) {}
                }
            }
            if (container) return container.querySelector(selector);
        }

        if (scope === 'desktop') return document.querySelector(selector);
        var frame2 = getActiveIframe();
        if (!frame2 || !frame2.contentDocument) return null;
        try { return frame2.contentDocument.querySelector(selector); } catch(e) { return null; }
    }

    // dim panels: 4-piece surround

    function removeDimPanels() {
        dimPanels.forEach(function(p) { if (p.parentElement) p.parentElement.removeChild(p); });
        dimPanels = [];
    }

    function createDimPanel() {
        var d = document.createElement('div');
        d.className = 'help-dim';
        d.addEventListener('click', closeHelp);
        document.body.appendChild(d);
        return d;
    }

    function ensureDimPanels() {
        if (dimPanels.length === 4) return;
        removeDimPanels();
        for (var i = 0; i < 4; i++) dimPanels.push(createDimPanel());
    }

    function showFullDim() {
        ensureDimPanels();
        var vw = window.innerWidth, vh = window.innerHeight;
        setRect(dimPanels[0], 0, 0, vw, vh);
        setRect(dimPanels[1], 0, 0, 0, 0);
        setRect(dimPanels[2], 0, 0, 0, 0);
        setRect(dimPanels[3], 0, 0, 0, 0);
    }

    function setSpotlight(rect) {
        ensureDimPanels();
        var vw = window.innerWidth, vh = window.innerHeight;
        var top = Math.max(0, rect.top);
        var left = Math.max(0, rect.left);
        var right = Math.min(vw, rect.right);
        var bottom = Math.min(vh, rect.bottom);
        setRect(dimPanels[0], 0, 0, vw, top);
        setRect(dimPanels[1], 0, top, left, bottom - top);
        setRect(dimPanels[2], right, top, vw - right, bottom - top);
        setRect(dimPanels[3], 0, bottom, vw, vh - bottom);
        setOutline(rect);
    }

    function setRect(el, x, y, w, h) {
        el.style.left = x + 'px';
        el.style.top = y + 'px';
        el.style.width = w + 'px';
        el.style.height = h + 'px';
    }

    // outline ring drawn in top-level document (works for both iframe and desktop elements)

    function ensureOutline() {
        if (outlineEl) return;
        outlineEl = document.createElement('div');
        outlineEl.id = 'help-outline';
        outlineEl.style.cssText = 'position:fixed;pointer-events:none;z-index:10150;' +
            'outline:2px solid var(--accent-primary,#3b82f6);outline-offset:2px;border-radius:3px;';
        document.body.appendChild(outlineEl);
    }

    function setOutline(rect) {
        ensureOutline();
        outlineEl.style.left = rect.left + 'px';
        outlineEl.style.top = rect.top + 'px';
        outlineEl.style.width = rect.width + 'px';
        outlineEl.style.height = rect.height + 'px';
        outlineEl.style.display = 'block';
    }

    function removeOutline() {
        if (outlineEl && outlineEl.parentElement) outlineEl.parentElement.removeChild(outlineEl);
        outlineEl = null;
    }

    // tooltip

    function ensureTooltip() {
        if (tooltipEl) return;
        tooltipEl = document.createElement('div');
        tooltipEl.id = 'help-tooltip';
        tooltipEl.setAttribute('role', 'status');
        tooltipEl.setAttribute('aria-live', 'polite');
        document.body.appendChild(tooltipEl);
    }

    function removeTooltip() {
        if (tooltipEl && tooltipEl.parentElement) tooltipEl.parentElement.removeChild(tooltipEl);
        tooltipEl = null;
    }

    function showTooltip(step, rect, total) {
        ensureTooltip();
        var body = loc(step.body_md);
        var title = loc(step.title);
        tooltipEl.innerHTML =
            '<div class="help-tip-counter">' + (currentStepIdx + 1) + ' / ' + total + '</div>' +
            '<div class="help-tip-title">' + escHtml(title) + '</div>' +
            '<div class="help-tip-body">' + renderMd(body) + '</div>' +
            '<div class="help-tip-legend">' + t('help.legend', '←  →  ↑  ↓  Esc') + '</div>';
        positionTooltip(step.tip_side || 'auto', rect);
    }

    function positionTooltip(side, rect) {
        if (!tooltipEl) return;
        tooltipEl.className = '';
        tooltipEl.style.left = '-9999px';
        tooltipEl.style.top = '-9999px';

        var tw = tooltipEl.offsetWidth;
        var th = tooltipEl.offsetHeight;
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        var pad = 12;

        var positions = {
            top: function() {
                return { left: rect.left + rect.width / 2 - tw / 2, top: rect.top - th - pad, cls: 'tip-top' };
            },
            bottom: function() {
                return { left: rect.left + rect.width / 2 - tw / 2, top: rect.bottom + pad, cls: 'tip-bottom' };
            },
            left: function() {
                return { left: rect.left - tw - pad, top: rect.top + rect.height / 2 - th / 2, cls: 'tip-left' };
            },
            right: function() {
                return { left: rect.right + pad, top: rect.top + rect.height / 2 - th / 2, cls: 'tip-right' };
            }
        };

        var order = (side === 'auto') ? ['bottom', 'top', 'right', 'left'] : [side, 'bottom', 'top', 'right', 'left'];

        var chosen = null;
        for (var i = 0; i < order.length; i++) {
            var fn = positions[order[i]];
            if (!fn) continue;
            var pos = fn();
            if (pos.left >= pad && pos.top >= pad && pos.left + tw <= vw - pad && pos.top + th <= vh - pad) {
                chosen = pos;
                break;
            }
        }
        if (!chosen) {
            var pos2 = positions[order[0]]();
            chosen = {
                left: Math.max(pad, Math.min(vw - tw - pad, pos2.left)),
                top: Math.max(pad, Math.min(vh - th - pad, pos2.top)),
                cls: pos2.cls
            };
        }

        tooltipEl.className = chosen.cls;
        tooltipEl.style.left = chosen.left + 'px';
        tooltipEl.style.top = chosen.top + 'px';
    }

    // intro overlay

    function showIntro(scene) {
        removeIntroOverlay();
        tipView = false;
        introOverlay = document.createElement('div');
        introOverlay.id = 'help-intro-overlay';
        introOverlay.setAttribute('role', 'dialog');
        introOverlay.setAttribute('aria-modal', 'true');
        introOverlay.setAttribute('aria-labelledby', 'help-intro-title');

        var iconHtml = '';
        if (helpData.app && helpData.app.icon) {
            iconHtml = '<img class="help-intro-icon" src="' + escAttr(helpData.app.icon) + '" alt="">';
        }
        var appTitle = helpData.app ? loc(helpData.app.title) : '';
        var introBody = loc(scene.intro);
        var tipDisabled = tipPages.length === 0 ? ' disabled' : '';

        introOverlay.innerHTML =
            '<div id="help-intro-card">' +
                '<div class="help-intro-header">' + iconHtml +
                    '<h2 class="help-intro-title" id="help-intro-title">' + escHtml(appTitle) + '</h2>' +
                '</div>' +
                '<div class="help-intro-body">' + renderMd(introBody) + '</div>' +
                '<div class="help-intro-actions">' +
                    '<button class="btn-tour-close">' + t('help.close', '닫기') + '</button>' +
                    '<button class="btn-tour-tip"' + tipDisabled + '>' + t('help.tip', '팁') + '</button>' +
                    '<button class="btn-tour-start">' + t('help.start_tour', '투어 시작') + '</button>' +
                '</div>' +
            '</div>';

        document.body.appendChild(introOverlay);

        introOverlay.addEventListener('click', function(e) {
            if (e.target === introOverlay) closeHelp();
        });
        introOverlay.querySelector('#help-intro-card').addEventListener('click', function(e) {
            e.stopPropagation();
        });
        introOverlay.querySelector('.btn-tour-close').addEventListener('click', closeHelp);
        introOverlay.querySelector('.btn-tour-tip').addEventListener('click', function() {
            if (tipPages.length > 0) { tipPageIdx = 0; showTipView(); }
        });
        introOverlay.querySelector('.btn-tour-start').addEventListener('click', function() {
            removeIntroOverlay();
            startSteps();
        });

        trapFocus(introOverlay);
        introOverlay.querySelector('.btn-tour-start').focus();
    }

    function showTipView() {
        if (!introOverlay) return;
        tipView = true;
        var card = introOverlay.querySelector('#help-intro-card');
        card.classList.add('tip-mode');

        var total = tipPages.length;
        var bodyEl = introOverlay.querySelector('.help-intro-body');
        var actionsEl = introOverlay.querySelector('.help-intro-actions');

        bodyEl.innerHTML = renderMd(tipPages[tipPageIdx]);

        var prevDisabled = tipPageIdx === 0 ? ' disabled' : '';
        var nextDisabled = tipPageIdx === total - 1 ? ' disabled' : '';
        var pageLabel = total > 1 ? '<span class="tip-page-counter">' + (tipPageIdx + 1) + ' / ' + total + '</span>' : '';

        actionsEl.innerHTML =
            '<button class="btn-tour-back">' + t('help.back', '뒤로') + '</button>' +
            '<div class="tip-page-nav">' +
                pageLabel +
                '<button class="btn-tip-prev"' + prevDisabled + '>&#8592;</button>' +
                '<button class="btn-tip-next"' + nextDisabled + '>&#8594;</button>' +
            '</div>' +
            '<button class="btn-tour-close">' + t('help.close', '닫기') + '</button>';

        actionsEl.querySelector('.btn-tour-back').addEventListener('click', function() {
            tipView = false;
            card.classList.remove('tip-mode');
            showIntro(activeScene);
        });
        actionsEl.querySelector('.btn-tip-prev').addEventListener('click', function() {
            if (tipPageIdx > 0) { tipPageIdx--; showTipView(); }
        });
        actionsEl.querySelector('.btn-tip-next').addEventListener('click', function() {
            if (tipPageIdx < total - 1) { tipPageIdx++; showTipView(); }
        });
        actionsEl.querySelector('.btn-tour-close').addEventListener('click', closeHelp);
        trapFocus(introOverlay);
        actionsEl.querySelector('.btn-tour-back').focus();
    }

    function removeIntroOverlay() {
        if (introOverlay && introOverlay.parentElement) introOverlay.parentElement.removeChild(introOverlay);
        introOverlay = null;
    }

    // step walkthrough

    function startSteps() {
        if (!activeScene || !activeScene.steps || activeScene.steps.length === 0) {
            closeHelp();
            return;
        }
        currentStepIdx = 0;
        gotoStep(0);
    }

    function gotoStep(idx) {
        if (!activeScene) return;
        var steps = activeScene.steps;
        if (idx < 0 || idx >= steps.length) return;
        currentStepIdx = idx;
        showStepForElement(steps[idx], steps.length);
    }

    function showStepForElement(step, total) {
        clearMutationWatcher();
        var el = resolveStep(step);
        if (!el) {
            waitForElement(step, total);
            return;
        }
        renderStep(step, el, total);
    }

    function renderStep(step, el, total) {
        var scope = stepScope(step);
        el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'auto' });
        requestAnimationFrame(function() {
            var rect = toTopRect(el, scope);
            setSpotlight(rect);
            showTooltip(step, rect, total);
            setupResizeObservers(step, el, total);
        });
    }

    function waitForElement(step, total) {
        var scope = stepScope(step);
        var doc = (scope === 'desktop') ? document
            : (getActiveIframe() && getActiveIframe().contentDocument);
        if (!doc) { skipStep(step); return; }

        mutationTimer = setTimeout(function() {
            clearMutationWatcher();
            skipStep(step);
        }, 1500);

        mutationWatcher = new MutationObserver(function() {
            var el = resolveStep(step);
            if (el) {
                clearMutationWatcher();
                renderStep(step, el, total);
            }
        });
        mutationWatcher.observe(doc.body, { childList: true, subtree: true, attributes: true });
    }

    function clearMutationWatcher() {
        if (mutationWatcher) { mutationWatcher.disconnect(); mutationWatcher = null; }
        if (mutationTimer) { clearTimeout(mutationTimer); mutationTimer = null; }
    }

    function skipStep(step) {
        console.warn('[help] step not found, skipping:', step.id, step.selector);
        if (currentStepIdx < activeScene.steps.length - 1) {
            gotoStep(currentStepIdx + 1);
        } else {
            closeHelp();
        }
    }

    // ResizeObserver for spotlight repositioning

    function setupResizeObservers(step, el, total) {
        teardownResizeObservers();
        var scope = stepScope(step);

        function reposition() {
            var updated = resolveStep(step);
            if (!updated) return;
            var rect = toTopRect(updated, scope);
            setSpotlight(rect);
            if (tooltipEl) positionTooltip(step.tip_side || 'auto', rect);
        }

        var bodyObs = new ResizeObserver(reposition);
        bodyObs.observe(document.body);
        resizeObservers.push(bodyObs);

        var frame = getActiveIframe();
        if (frame && frame.contentDocument && scope === 'iframe') {
            var iframeObs = new ResizeObserver(reposition);
            iframeObs.observe(frame.contentDocument.body);
            resizeObservers.push(iframeObs);
        }
    }

    function teardownResizeObservers() {
        resizeObservers.forEach(function(o) { o.disconnect(); });
        resizeObservers = [];
    }

    // keyboard handling

    function handleHelpKey(e) {
        if (e.key === 'Escape') {
            e.stopPropagation();
            e.preventDefault();
            closeHelp();
            return;
        }
        if (introOverlay) return;
        if (!activeScene) return;

        if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].indexOf(e.key) !== -1) {
            e.stopPropagation();
            e.preventDefault();
            var dir = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' }[e.key];
            navigateDir(dir);
            return;
        }

        e.stopPropagation();
        e.preventDefault();
    }

    function navigateDir(dir) {
        var steps = activeScene.steps;
        if (dir === 'right' || dir === 'down') {
            if (currentStepIdx < steps.length - 1) gotoStep(currentStepIdx + 1);
        } else {
            if (currentStepIdx > 0) gotoStep(currentStepIdx - 1);
        }
    }

    function addKeyListeners() {
        var topHandler = function(e) { handleHelpKey(e); };
        window.addEventListener('keydown', topHandler, true);
        keyListeners.push({ target: window, handler: topHandler });

        var frame = getActiveIframe();
        if (frame && frame.contentWindow) {
            try {
                var frameHandler = function(e) { handleHelpKey(e); };
                frame.contentWindow.addEventListener('keydown', frameHandler, true);
                keyListeners.push({ target: frame.contentWindow, handler: frameHandler });
            } catch(e) {}
        }
    }

    function removeKeyListeners() {
        keyListeners.forEach(function(l) {
            try { l.target.removeEventListener('keydown', l.handler, true); } catch(e) {}
        });
        keyListeners = [];
    }

    function trapFocus(container) {
        var focusable = container.querySelectorAll('button, [tabindex]:not([tabindex="-1"])');
        if (focusable.length === 0) return;
        var first = focusable[0], last = focusable[focusable.length - 1];
        container.addEventListener('keydown', function(e) {
            if (e.key !== 'Tab') return;
            if (e.shiftKey) {
                if (document.activeElement === first) { e.preventDefault(); last.focus(); }
            } else {
                if (document.activeElement === last) { e.preventDefault(); first.focus(); }
            }
        });
    }

    function closeHelp() {
        clearMutationWatcher();
        teardownResizeObservers();
        removeKeyListeners();
        removeDimPanels();
        removeOutline();
        removeTooltip();
        removeIntroOverlay();
        markCache = {};
        helpData = null;
        tipPages = [];
        tipPageIdx = 0;
        activeScene = null;
        currentStepIdx = -1;
        tipView = false;
        if (preFocusElement) {
            try { preFocusElement.focus(); } catch(e) {}
            preFocusElement = null;
        }
    }

    window.openHelp = function() {
        if (introOverlay || activeScene) return;
        if (!window.currentApp) return;
        var idName = window.currentApp.id_name;
        if (!idName) return;

        preFocusElement = document.activeElement;

        var tourUrl = '/desktop-help-data/' + encodeURIComponent(idName) + '/TOUR.json';

        var tourPromise = fetch(tourUrl).then(function(r) {
            if (!r.ok) return null;
            return r.json();
        });

        // Fetch TIP00_<lang>.md, TIP01_<lang>.md, ... until 404. Max 20 pages.
        function fetchTipPages(idx, acc) {
            if (idx >= 20) return Promise.resolve(acc);
            var n = (idx < 10 ? '0' : '') + idx;
            var lang = window.currentLanguage || 'en';
            return fetch('/desktop-help-data/' + encodeURIComponent(idName) + '/TIP' + n + '_' + lang + '.md')
                .then(function(r) {
                    if (!r.ok) return acc;
                    return r.text().then(function(text) {
                        acc.push(text);
                        return fetchTipPages(idx + 1, acc);
                    });
                })
                .catch(function() { return acc; });
        }

        Promise.all([tourPromise, fetchTipPages(0, [])])
            .then(function(results) {
                var data   = results[0];
                var pages  = results[1];

                if (!data) {
                    showToastMsg(t('help.no_help', '이 앱에 대한 도움말이 없습니다.'));
                    return;
                }
                helpData = data;
                tipPages = pages;

                var scene = detectScene();
                if (!scene) {
                    showToastMsg(t('help.no_scene', '이 화면에 대한 도움말이 없습니다.'));
                    helpData = null;
                    tipPages = [];
                    return;
                }
                activeScene = scene;
                addKeyListeners();
                showFullDim();
                showIntro(scene);
            })
            .catch(function(err) {
                console.error('[help] fetch error', err);
                showToastMsg(t('help.no_help', '이 앱에 대한 도움말이 없습니다.'));
            });
    };

    function showToastMsg(msg) {
        if (window.showToast) window.showToast(msg);
    }

    function escHtml(s) {
        if (!s) return '';
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function escAttr(s) { return escHtml(s); }

    function attachF1(win) {
        win.addEventListener('keydown', function(e) {
            if (e.key === 'F1') {
                e.preventDefault();
                e.stopPropagation();
                window.openHelp();
            }
        }, true);
    }

    attachF1(window);

    var appContent = document.getElementById('app-content');
    if (appContent) {
        new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                m.addedNodes.forEach(function(node) {
                    if (node.tagName === 'IFRAME') {
                        node.addEventListener('load', function() {
                            try { attachF1(node.contentWindow); } catch(e) {}
                        });
                    }
                });
            });
        }).observe(appContent, { childList: true });
    }

})();
