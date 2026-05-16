// Modal dialogs: message box, input dialog, confirm dialog, toast,
// startup fortune, Wayland IME warning.

// showMessageBox: called via callJS from Python (lib/msgbox.py show())
window.showMessageBox = function(args) {
    var title = args.title || '';
    var text = args.text || '';
    document.getElementById('msgbox-dialog-title').textContent = title;
    document.getElementById('msgbox-dialog-text').textContent = text;
    var dialog = document.getElementById('msgbox-dialog');
    dialog.style.display = 'flex';

    var btn = document.getElementById('msgbox-dialog-ok');
    var close = function() {
        dialog.style.display = 'none';
        btn.removeEventListener('click', close);
        document.removeEventListener('keydown', onKeydown, true);
    };
    var onKeydown = function(e) {
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            close();
        } else if (e.key === 'Tab') {
            e.preventDefault();
            btn.focus();
        }
    };
    btn.addEventListener('click', close);
    document.addEventListener('keydown', onKeydown, true);
    btn.focus();
};

// showInputDialog: reusable JS input dialog, returns Promise<string|null>
window.showInputDialog = function(title, defaultValue) {
    return new Promise(function(resolve) {
        document.getElementById('input-dialog-title').textContent = title;
        var input = document.getElementById('input-dialog-value');
        input.value = defaultValue || '';
        var dialog = document.getElementById('input-dialog');
        dialog.style.display = 'flex';

        var onOk = function() { dialog.style.display = 'none'; cleanup(); resolve(input.value); };
        var onCancel = function() { dialog.style.display = 'none'; cleanup(); resolve(null); };
        var onKeydown = function(e) {
            if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); onOk(); }
            else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); onCancel(); }
        };
        var onBackdrop = function(e) { if (e.target === dialog) onCancel(); };
        function cleanup() {
            document.getElementById('input-dialog-ok').removeEventListener('click', onOk);
            document.getElementById('input-dialog-cancel').removeEventListener('click', onCancel);
            document.removeEventListener('keydown', onKeydown, true);
            dialog.removeEventListener('click', onBackdrop);
        }
        document.getElementById('input-dialog-ok').addEventListener('click', onOk);
        document.getElementById('input-dialog-cancel').addEventListener('click', onCancel);
        document.addEventListener('keydown', onKeydown, true);
        dialog.addEventListener('click', onBackdrop);
        setTimeout(function() { input.select(); input.focus(); }, 50);
    });
};

// showConfirmBox: called via callJS from Python (lib/msgbox.py confirm())
window.showConfirmBox = function(args) {
    var confirmId = args.confirm_id;
    showConfirmDialog(args.title || '', args.text || '').then(function(confirmed) {
        apiCall('confirm_result', { confirm_id: confirmId, confirmed: confirmed });
    });
};

// showConfirmDialog: reusable JS confirm dialog, returns Promise<bool>
// options.yesStyle: 'danger' for red yes button
window.showConfirmDialog = function(title, text, options) {
    return new Promise(function(resolve) {
        document.getElementById('confirm-dialog-title').textContent = title;
        document.getElementById('confirm-dialog-text').textContent = text;
        var yesBtn = document.getElementById('confirm-dialog-yes');
        yesBtn.classList.remove('btn-primary', 'btn-danger');
        yesBtn.classList.add((options && options.yesStyle === 'danger') ? 'btn-danger' : 'btn-primary');
        var dialog = document.getElementById('confirm-dialog');
        dialog.style.display = 'flex';

        var noBtn = document.getElementById('confirm-dialog-no');
        var onYes = function() { dialog.style.display = 'none'; cleanup(); resolve(true); };
        var onNo  = function() { dialog.style.display = 'none'; cleanup(); resolve(false); };
        var onKeydown = function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
                if (document.activeElement === noBtn) onNo(); else onYes();
            } else if (e.key === 'Escape') {
                e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
                onNo();
            } else if (e.key === 'Tab') {
                e.preventDefault();
                if (document.activeElement === yesBtn) noBtn.focus(); else yesBtn.focus();
            }
        };
        var onBackdrop = function(e) { if (e.target === dialog) onNo(); };
        var cleanup = function() {
            document.getElementById('confirm-dialog-yes').removeEventListener('click', onYes);
            document.getElementById('confirm-dialog-no').removeEventListener('click', onNo);
            document.removeEventListener('keydown', onKeydown, true);
            dialog.removeEventListener('click', onBackdrop);
        };
        document.getElementById('confirm-dialog-yes').addEventListener('click', onYes);
        document.getElementById('confirm-dialog-no').addEventListener('click', onNo);
        document.addEventListener('keydown', onKeydown, true);
        dialog.addEventListener('click', onBackdrop);
        yesBtn.focus();
    });
};

// showStartupFortune: called via callJS from Python (fortune app on_skillup_started)
window.showStartupFortune = function(args) {
    var ko = args.ko || '';
    var en = args.en || '';
    var date = args.date || '';
    var langPref = args.language_pref || 'auto';
    var uiLang = (typeof currentLanguage !== 'undefined') ? currentLanguage : 'en';
    var lang = (langPref === 'ko' || langPref === 'en') ? langPref : uiLang;

    var dateStr = '';
    if (date && date.length >= 8) {
        var y = date.slice(0,4), mo = date.slice(4,6), d = date.slice(6,8);
        if (lang === 'ko') {
            dateStr = y + '년 ' + parseInt(mo) + '월 ' + parseInt(d) + '일';
        } else {
            var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
            dateStr = months[parseInt(mo)-1] + ' ' + parseInt(d) + ', ' + y;
        }
    }

    var text  = (lang === 'ko') ? ko : en;
    var title = (lang === 'ko') ? '오늘의 운세' : "Today's Fortune";
    var okLabel = (lang === 'ko') ? '확인' : 'OK';

    document.getElementById('sfd-date').textContent = dateStr;
    document.getElementById('sfd-title').textContent = title;
    document.getElementById('sfd-text').textContent = text;
    document.getElementById('sfd-ok-btn').textContent = okLabel;

    var overlay = document.getElementById('startup-fortune-overlay');
    overlay.style.display = 'flex';
    overlay.onclick = function(e) { if (e.target === overlay) overlay.style.display = 'none'; };
};

// showWaylandImeDialog: called via callJS from Python
(function() {
    var _WAYLAND_IME_I18N = {
        ko: {
            title: '한글 입력 안내',
            desc: '현재 <b>Wayland</b> 세션에서 실행 중입니다.<br>한글 등 다국어 입력을 사용하려면, 로그인 화면에서 아래 그림과 같이 <b>Classic (X11 display server)</b>를 선택한 후 다시 로그인하세요.',
            dismiss: '일주일간 보지 않기',
            ok: '확인'
        },
        en: {
            title: 'Input Method Notice',
            desc: 'You are running under a <b>Wayland</b> session.<br>To enable Korean and other multilingual input, please log out and select <b>Classic (X11 display server)</b> at the login screen as shown below.',
            dismiss: "Don't show for a week",
            ok: 'OK'
        }
    };

    window.showWaylandImeDialog = function() {
        var lang = (typeof currentLanguage !== 'undefined' && currentLanguage === 'ko') ? 'ko' : 'en';
        var t = _WAYLAND_IME_I18N[lang];
        document.getElementById('wayland-ime-title').textContent = t.title;
        document.getElementById('wayland-ime-desc').innerHTML = t.desc;
        document.getElementById('wayland-ime-dismiss-label').textContent = t.dismiss;
        document.getElementById('wayland-ime-ok-btn').textContent = t.ok;
        document.getElementById('wayland-ime-dialog').style.display = 'flex';
    };

    function closeWaylandImeDialog() {
        var dismiss = document.getElementById('wayland-ime-dismiss-check').checked;
        document.getElementById('wayland-ime-dialog').style.display = 'none';
        if (dismiss) {
            apiCall('set_config', { wayland_ime_dismissed_time: Math.floor(Date.now() / 1000) }).catch(function() {});
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        var okBtn = document.getElementById('wayland-ime-ok-btn');
        if (okBtn) okBtn.addEventListener('click', closeWaylandImeDialog);
    });
})();
