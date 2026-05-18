// desktopModal: common modal infrastructure for iframe apps.
// Exposed on window.desktopModal for iframe access via parent.desktopModal.

window.desktopModal = (function() {
    var _config = null;
    var _keydownHandler = null;
    var _bodyClickHandler = null;
    var _dragState = null;
    var _iframeKeyHandler = null;
    var _iframeDoc = null;

    var _MODAL_PASSTHROUGH_KEYS = new Set(['Escape','Enter','Tab','F3']);

    function _installIframeKeyBlock() {
        _removeIframeKeyBlock();
        try {
            var iframe = document.querySelector('iframe.iframe-visible');
            if (!iframe || !iframe.contentWindow) return;
            var doc = iframe.contentWindow.document;
            _iframeKeyHandler = function(e) {
                if (_MODAL_PASSTHROUGH_KEYS.has(e.key)) return;
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
            };
            doc.addEventListener('keydown', _iframeKeyHandler, true);
            _iframeDoc = doc;
        } catch(err) {}
    }

    function _removeIframeKeyBlock() {
        if (_iframeDoc && _iframeKeyHandler) {
            try { _iframeDoc.removeEventListener('keydown', _iframeKeyHandler, true); } catch(e) {}
            _iframeDoc = null;
            _iframeKeyHandler = null;
        }
    }

    function _getFocusable() {
        var box = document.getElementById('desktop-modal-box');
        return Array.from(box.querySelectorAll(
            'button:not([disabled]),input:not([disabled]),select:not([disabled]),' +
            'textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
        ));
    }

    // position: 'center' | 'iframe-center' | 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left'
    function _positionBox(boxEl, position) {
        var MARGIN = 24;
        if (position === 'center') {
            boxEl.style.left = '50%';
            boxEl.style.top = '50%';
            boxEl.style.transform = 'translate(-50%, -50%)';
            return;
        }
        boxEl.style.transform = 'none';
        boxEl.style.visibility = 'hidden';
        boxEl.style.left = '0px';
        boxEl.style.top = '0px';
        requestAnimationFrame(function() {
            var bw = boxEl.offsetWidth, bh = boxEl.offsetHeight;
            var vw = window.innerWidth, vh = window.innerHeight;
            var left, top;
            if (position === 'iframe-center') {
                var iframe = document.querySelector('iframe.iframe-visible');
                if (iframe) {
                    var r = iframe.getBoundingClientRect();
                    left = r.left + (r.width - bw) / 2;
                    top  = r.top  + (r.height - bh) / 2;
                } else {
                    left = vw / 2 - bw / 2; top = vh / 2 - bh / 2;
                }
            } else if (position === 'bottom-right') { left = vw - bw - MARGIN; top = vh - bh - MARGIN; }
            else if (position === 'bottom-left')     { left = MARGIN;           top = vh - bh - MARGIN; }
            else if (position === 'top-right')        { left = vw - bw - MARGIN; top = MARGIN; }
            else if (position === 'top-left')         { left = MARGIN;           top = MARGIN; }
            else                                      { left = vw / 2 - bw / 2; top = vh / 2 - bh / 2; }
            boxEl.style.left = Math.max(0, left) + 'px';
            boxEl.style.top  = Math.max(0, top)  + 'px';
            boxEl.style.visibility = '';
        });
    }

    function _setupDrag(boxEl) {
        boxEl.style.cursor = 'move';
        boxEl.style.userSelect = 'none';

        function onPointerDown(e) {
            if (e.button !== 0) return;
            var tag = e.target.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' ||
                tag === 'BUTTON' || tag === 'A' || tag === 'LABEL') return;
            var rect = boxEl.getBoundingClientRect();
            _dragState = { startX: e.clientX, startY: e.clientY, startLeft: rect.left, startTop: rect.top };
            boxEl.setPointerCapture(e.pointerId);
            e.preventDefault();
        }
        function onPointerMove(e) {
            if (!_dragState) return;
            var dx = e.clientX - _dragState.startX;
            var dy = e.clientY - _dragState.startY;
            var left = _dragState.startLeft + dx;
            var top  = _dragState.startTop  + dy;
            var bw = boxEl.offsetWidth, bh = boxEl.offsetHeight;
            left = Math.max(0, Math.min(left, window.innerWidth  - bw));
            top  = Math.max(0, Math.min(top,  window.innerHeight - bh));
            boxEl.style.left = left + 'px';
            boxEl.style.top  = top  + 'px';
            boxEl.style.transform = 'none';
        }
        function onPointerUp() { _dragState = null; }

        boxEl.addEventListener('pointerdown',   onPointerDown);
        boxEl.addEventListener('pointermove',   onPointerMove);
        boxEl.addEventListener('pointerup',     onPointerUp);
        boxEl.addEventListener('pointercancel', onPointerUp);

        return function cleanup() {
            boxEl.removeEventListener('pointerdown',   onPointerDown);
            boxEl.removeEventListener('pointermove',   onPointerMove);
            boxEl.removeEventListener('pointerup',     onPointerUp);
            boxEl.removeEventListener('pointercancel', onPointerUp);
            boxEl.style.cursor = '';
            boxEl.style.userSelect = '';
            _dragState = null;
        };
    }

    var _dragCleanup = null;

    function _applyThemeOverride(boxEl, titleEl, forcedTheme) {
        if (forcedTheme === 'light') {
            boxEl.style.background    = '#f5f5f7';
            boxEl.style.borderColor   = '#d2d2d7';
            titleEl.style.color       = '#1d1d1f';
        } else if (forcedTheme === 'dark') {
            boxEl.style.background    = '#20242b';
            boxEl.style.borderColor   = '#373c47';
            titleEl.style.color       = '#eceef2';
        } else {
            boxEl.style.background    = 'var(--bg-secondary,#20242b)';
            boxEl.style.borderColor   = 'var(--border-color,#373c47)';
            titleEl.style.color       = 'var(--text-primary,#eceef2)';
        }
    }

    function close() {
        var overlay = document.getElementById('desktop-modal-overlay');
        overlay.style.display = 'none';
        if (_keydownHandler) {
            document.removeEventListener('keydown', _keydownHandler, true);
            _keydownHandler = null;
        }
        if (_bodyClickHandler) {
            document.getElementById('desktop-modal-body').removeEventListener('click', _bodyClickHandler);
            _bodyClickHandler = null;
        }
        if (_dragCleanup) { _dragCleanup(); _dragCleanup = null; }
        _removeIframeKeyBlock();
        var boxEl   = document.getElementById('desktop-modal-box');
        var titleEl = document.getElementById('desktop-modal-title');
        _applyThemeOverride(boxEl, titleEl, null);
        var cb = _config && _config.onClose;
        _config = null;
        if (cb) cb();
    }

    function open(config) {
        if (_config) close();
        _config = config;

        var titleEl = document.getElementById('desktop-modal-title');
        var boxEl   = document.getElementById('desktop-modal-box');
        _applyThemeOverride(boxEl, titleEl, config.forcedTheme || null);

        if (config.noPadding) {
            boxEl.style.padding = '0';
            titleEl.style.padding = '12px 20px 10px';
            titleEl.style.marginBottom = '0';
        } else {
            boxEl.style.padding = '16px 20px 20px';
            titleEl.style.padding = '0';
            titleEl.style.marginBottom = '10px';
        }
        titleEl.textContent = config.title || '';

        var bodyEl = document.getElementById('desktop-modal-body');
        if (config.element) {
            bodyEl.innerHTML = '';
            bodyEl.appendChild(config.element);
        } else {
            bodyEl.innerHTML = config.html || '';
        }

        var footer = document.getElementById('desktop-modal-footer');
        footer.innerHTML = '';
        var buttons = config.buttons != null ? config.buttons : [{ label: 'OK', primary: true }];
        bodyEl.style.marginBottom = buttons.length > 0 ? '16px' : '0';
        var firstPrimary = null;
        buttons.forEach(function(btnDef) {
            var btn = document.createElement('button');
            btn.className = 'btn ' + (btnDef.danger ? 'btn-danger' : btnDef.primary ? 'btn-primary' : 'btn-secondary');
            btn.style.cssText = 'font-size:13px;padding:6px 16px;margin-left:8px;';
            btn.textContent = btnDef.label;
            if (btnDef.id) btn.id = btnDef.id;
            btn.addEventListener('click', function() {
                if (btnDef.onClick) btnDef.onClick(); else close();
            });
            footer.appendChild(btn);
            if (btnDef.primary && !firstPrimary) firstPrimary = btn;
        });

        if (config.onBodyClick) {
            _bodyClickHandler = config.onBodyClick;
            document.getElementById('desktop-modal-body').addEventListener('click', _bodyClickHandler);
        }

        var overlay = document.getElementById('desktop-modal-overlay');
        if (config.draggable) {
            overlay.style.background = 'transparent';
            overlay.style.pointerEvents = 'none';
            overlay.onclick = null;
            _positionBox(boxEl, config.position || 'center');
            _dragCleanup = _setupDrag(boxEl);
        } else {
            overlay.style.background = 'rgba(0,0,0,0.5)';
            overlay.style.pointerEvents = 'all';
            overlay.onclick = function(e) { if (e.target === overlay) close(); };
            _positionBox(boxEl, config.position || 'center');
            _dragCleanup = null;
        }

        overlay.style.display = 'block';

        _keydownHandler = function(e) {
            var focusable = _getFocusable();
            if (e.key === 'Tab') {
                e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
                if (focusable.length === 0) return;
                var idx = focusable.indexOf(document.activeElement);
                var next = e.shiftKey
                    ? (idx <= 0 ? focusable.length - 1 : idx - 1)
                    : (idx >= focusable.length - 1 ? 0 : idx + 1);
                focusable[next].focus();
            } else if (e.key === 'Escape') {
                e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
                close();
            } else if (e.key === 'Enter') {
                var activeEl = document.activeElement;
                if (activeEl && activeEl.tagName === 'TEXTAREA') return;
                if (!activeEl || !footer.contains(activeEl)) {
                    var primary = footer.querySelector('.btn-primary') || footer.querySelector('button');
                    if (primary) {
                        e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
                        primary.click();
                    }
                }
            }
        };
        document.addEventListener('keydown', _keydownHandler, true);
        setTimeout(_installIframeKeyBlock, 0);

        if (firstPrimary) firstPrimary.focus();
        else { var focusable2 = _getFocusable(); if (focusable2.length > 0) focusable2[0].focus(); }
    }

    return { open: open, close: close, isOpen: function() { return _config !== null; } };
})();

// openBoard: open a skillform board list in a modal dialog.
// infoApiName: Python API handler returning {list_form_path, schema}
// title: modal title string
window.desktopModal.openBoard = async function(infoApiName, title) {
    var lang = currentLanguage || 'en';
    var info = await apiCall(infoApiName, {});
    if (!info || !info.list_form_path) return;
    var skillformApp = apps ? apps.find(function(a) { return a.id_name === 'skillform'; }) : null;
    if (!skillformApp) return;
    var schemaPath = encodeURIComponent(info.list_form_path);
    var url = '/app/' + skillformApp.id + '/runner.html?schema_path=' + schemaPath + '&lang=' + lang;
    var iframe = document.createElement('iframe');
    iframe.src = url;
    var _schema   = info.schema || {};
    var _docProps = _schema.docProps || {};
    var _grid     = _schema.grid || {};
    var _scale    = (_docProps.fontSize || 14) / 14;
    var _MARGIN   = 16;
    var _gridRowH = Math.round((_grid.rowHeight || 56) * _scale);
    var _cellW    = Math.round((_grid.cellW    || 56) * _scale);
    var _formSize = _docProps.formSize || {};
    var _maxCol = 0, _maxRow = 0;
    (_schema.fields || []).forEach(function(f) {
        _maxCol = Math.max(_maxCol, (f.col || 0) + (f.w || 1));
        _maxRow = Math.max(_maxRow, (f.row || 0) + (f.h || 1));
    });
    if (_formSize.mode === 'set') {
        if (_formSize.cols > 0) _maxCol = _formSize.cols;
        if (_formSize.rows > 0) _maxRow = _formSize.rows;
    }
    iframe.style.cssText = 'width:' + (_maxCol * _cellW + _MARGIN * 2) + 'px;height:' + (_maxRow * _gridRowH + _MARGIN * 2) + 'px;border:none;display:block;';
    iframe.setAttribute('allowtransparency', 'true');
    var _theme = _docProps.theme || 'light';
    var _forcedTheme = null;
    if (_theme === 'invert') {
        var _sel = document.getElementById('theme-select');
        var _cur = (_sel && _sel.value) ? _sel.value : 'default';
        _forcedTheme = (_cur === 'default') ? 'light' : 'dark';
    } else if (_theme === 'light') {
        _forcedTheme = 'light';
    } else if (_theme === 'dark') {
        _forcedTheme = 'dark';
    }
    window.desktopModal.open({ title: title, element: iframe, buttons: [], noPadding: true, forcedTheme: _forcedTheme });
};
