/**
 * DesktopAlert — topbar badge + toast + popup list notification system.
 * No localStorage.
 */
(function() {
    'use strict';

    var _alerts = [];   // [{app_id, chatroom_id, message, onClick}]
    var _badgeEl = null;
    var _toastEl = null;
    var _toastTimer = null;

    function _ensureBadge() {
        if (_badgeEl) return;

        var avatar = document.getElementById('topbar-avatar');
        if (!avatar) return;

        _badgeEl = document.createElement('div');
        _badgeEl.id = 'desktop-alert-badge';
        _badgeEl.style.cssText = [
            'display:none',
            'position:absolute',
            'top:-4px',
            'right:-4px',
            'min-width:16px',
            'height:16px',
            'background:#e74c3c',
            'color:#fff',
            'border-radius:8px',
            'font-size:10px',
            'font-weight:600',
            'line-height:16px',
            'text-align:center',
            'padding:0 4px',
            'pointer-events:none',
            'z-index:100'
        ].join(';');

        avatar.appendChild(_badgeEl);

        avatar.onclick = function(e) {
            e.stopPropagation();
            if (_toastEl) {
                _dismissToast();
                return;
            }
            _toggleAlertList();
        };
    }

    function _updateBadge() {
        _ensureBadge();
        if (!_badgeEl) return;
        var avatar = document.getElementById('topbar-avatar');
        var count = _alerts.length;
        if (count === 0) {
            _badgeEl.style.display = 'none';
            if (avatar) avatar.style.cursor = 'default';
        } else {
            _badgeEl.style.display = 'block';
            _badgeEl.textContent = count > 99 ? '99+' : String(count);
            if (avatar) avatar.style.cursor = 'pointer';
        }
    }

    // Toast: auto-shown on new alert, anchored below avatar
    function _showToast(opts) {
        if (_toastEl) {
            clearTimeout(_toastTimer);
            _toastEl.remove();
            _toastEl = null;
        }

        var avatar = document.getElementById('topbar-avatar');
        if (!avatar) return;

        var rect = avatar.getBoundingClientRect();
        var toastTop = rect.bottom + 8;
        var toastRight = window.innerWidth - rect.right;

        var toast = document.createElement('div');
        _toastEl = toast;
        var isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        var toastBg     = isDark ? '#3d3000' : '#fff8c5';
        var toastBorder = isDark ? '#7a6000' : '#e6b800';
        var toastColor  = isDark ? '#ffe066' : '#5a4000';

        toast.style.cssText = [
            'position:fixed',
            'top:' + toastTop + 'px',
            'right:' + toastRight + 'px',
            'max-width:280px',
            'background:' + toastBg,
            'border:1px solid ' + toastBorder,
            'border-radius:8px',
            'box-shadow:0 4px 20px rgba(0,0,0,0.45)',
            'padding:10px 14px',
            'font-size:13px',
            'color:' + toastColor,
            'font-weight:500',
            'cursor:pointer',
            'z-index:9999',
            'opacity:1',
            'transition:opacity 0.4s'
        ].join(';');

        // Tail pointing up-right toward avatar
        var tail = document.createElement('div');
        tail.style.cssText = [
            'position:absolute',
            'top:-7px',
            'right:10px',
            'width:0',
            'height:0',
            'border-left:7px solid transparent',
            'border-right:7px solid transparent',
            'border-bottom:7px solid ' + toastBorder
        ].join(';');
        toast.appendChild(tail);

        var tailInner = document.createElement('div');
        tailInner.style.cssText = [
            'position:absolute',
            'top:-5px',
            'right:10px',
            'width:0',
            'height:0',
            'border-left:7px solid transparent',
            'border-right:7px solid transparent',
            'border-bottom:7px solid ' + toastBg
        ].join(';');
        toast.appendChild(tailInner);

        var text = document.createElement('span');
        text.textContent = opts.message || 'New message';
        toast.appendChild(text);

        toast.onclick = function() {
            _dismissToast();
            if (typeof opts.onClick === 'function') opts.onClick();
        };

        document.body.appendChild(toast);
        _toastTimer = setTimeout(_dismissToast, 30000);
    }

    function _dismissToast() {
        if (!_toastEl) return;
        _toastEl.style.opacity = '0';
        var el = _toastEl;
        _toastEl = null;
        setTimeout(function() { if (el.parentNode) el.remove(); }, 400);
    }

    // Popup list: shown on avatar click
    function _toggleAlertList() {
        var existing = document.getElementById('desktop-alert-popup');
        if (existing) { existing.remove(); return; }

        var avatar = document.getElementById('topbar-avatar');
        var rect = avatar ? avatar.getBoundingClientRect() : {bottom: 50, right: window.innerWidth - 12};
        var listTop = rect.bottom + 8;
        var listRight = window.innerWidth - rect.right;

        var popup = document.createElement('div');
        popup.id = 'desktop-alert-popup';
        popup.style.cssText = [
            'position:fixed',
            'top:' + listTop + 'px',
            'right:' + listRight + 'px',
            'width:300px',
            'max-height:360px',
            'overflow-y:auto',
            'background:#1e2a35',
            'border:1px solid #4a6278',
            'border-radius:8px',
            'box-shadow:0 4px 20px rgba(0,0,0,0.55)',
            'z-index:9999'
        ].join(';');

        // Tail pointing up-right toward avatar
        var tail = document.createElement('div');
        tail.style.cssText = [
            'position:absolute',
            'top:-7px',
            'right:10px',
            'width:0',
            'height:0',
            'border-left:7px solid transparent',
            'border-right:7px solid transparent',
            'border-bottom:7px solid #4a6278'
        ].join(';');
        popup.appendChild(tail);

        var tailInner = document.createElement('div');
        tailInner.style.cssText = [
            'position:absolute',
            'top:-5px',
            'right:10px',
            'width:0',
            'height:0',
            'border-left:7px solid transparent',
            'border-right:7px solid transparent',
            'border-bottom:7px solid #1e2a35'
        ].join(';');
        popup.appendChild(tailInner);

        if (_alerts.length === 0) {
            var empty = document.createElement('div');
            empty.style.cssText = 'padding:16px;color:#8aabb8;font-size:13px;text-align:center;';
            empty.textContent = 'No notifications';
            popup.appendChild(empty);
        } else {
            _alerts.forEach(function(alert) {
                var key = (alert.app_id || '') + ':' + (alert.chatroom_id || '');

                var item = document.createElement('div');
                item.style.cssText = [
                    'display:flex',
                    'align-items:center',
                    'padding:10px 12px',
                    'border-bottom:1px solid #2e3f4e',
                    'cursor:pointer',
                    'font-size:13px',
                    'color:#d4e6f1'
                ].join(';');

                var msgSpan = document.createElement('span');
                msgSpan.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                msgSpan.textContent = alert.message || 'New message';
                item.appendChild(msgSpan);

                var closeBtn = document.createElement('span');
                closeBtn.textContent = '×';  // ×
                closeBtn.style.cssText = [
                    'margin-left:10px',
                    'color:#8aabb8',
                    'font-size:16px',
                    'line-height:1',
                    'flex-shrink:0',
                    'padding:0 2px'
                ].join(';');
                closeBtn.onmouseenter = function() { this.style.color = '#e74c3c'; };
                closeBtn.onmouseleave = function() { this.style.color = '#8aabb8'; };
                closeBtn.onclick = function(e) {
                    e.stopPropagation();
                    DesktopAlert.clear({app_id: alert.app_id, chatroom_id: alert.chatroom_id});
                    popup.remove();
                    if (_alerts.length > 0) _toggleAlertList();
                };
                item.appendChild(closeBtn);

                item.onmouseenter = function() { this.style.background = '#253444'; };
                item.onmouseleave = function() { this.style.background = ''; };
                item.onclick = function(e) {
                    if (e.target === closeBtn) return;
                    popup.remove();
                    if (typeof alert.onClick === 'function') alert.onClick();
                };

                popup.appendChild(item);
            });
        }

        document.body.appendChild(popup);

        setTimeout(function() {
            document.addEventListener('click', function _close(e) {
                if (!popup.contains(e.target)) {
                    popup.remove();
                    document.removeEventListener('click', _close);
                }
            });
        }, 50);
    }

    var DesktopAlert = {
        add: function(opts) {
            var key = (opts.app_id || '') + ':' + (opts.chatroom_id || '');
            var existing = _alerts.findIndex(function(a) {
                return (a.app_id || '') + ':' + (a.chatroom_id || '') === key;
            });
            if (existing >= 0) {
                _alerts[existing] = opts;
            } else {
                _alerts.push(opts);
            }
            _updateBadge();
            _showToast(opts);
        },

        clear: function(opts) {
            var key = (opts.app_id || '') + ':' + (opts.chatroom_id || '');
            _alerts = _alerts.filter(function(a) {
                return (a.app_id || '') + ':' + (a.chatroom_id || '') !== key;
            });
            _updateBadge();
        },

        clearAll: function() {
            _alerts = [];
            _updateBadge();
        },
    };

    window.DesktopAlert = DesktopAlert;
})();
