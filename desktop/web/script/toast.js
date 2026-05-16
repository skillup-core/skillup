// showToast: brief notification toast
// options.type: 'ok' (default) or 'err'
// options.delay: auto-dismiss ms, default 5000
window.showToast = function(msg, options) {
    var opts = options || {};
    var isErr = opts.type === 'err';
    var delay = opts.delay || 5000;
    var container = document.getElementById('skillup-toast-container');
    var toastEl = document.createElement('div');
    var bg = window.getComputedStyle(document.body).backgroundColor;
    var m = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)/);
    var isDark = m ? (parseInt(m[1]) + parseInt(m[2]) + parseInt(m[3])) / 3 < 128 : true;
    var bgColor   = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.07)';
    var textColor = isDark ? 'rgba(255,255,255,0.75)' : 'rgba(0,0,0,0.65)';
    var errColor  = isErr ? 'var(--color-danger,#dc3545)' : textColor;
    var accent    = isErr ? 'var(--color-danger,#dc3545)' : 'var(--color-success,#198754)';
    // close button: normal/hover colors per dark/light mode
    var closeFg        = isDark ? 'rgba(255,255,255,0.75)' : 'rgba(0,0,0,0.65)';
    var closeHoverBg   = isDark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.70)';
    var closeHoverFg   = isDark ? '#222' : '#fff';
    toastEl.className = 'toast align-items-center border';
    toastEl.style.cssText = 'background:' + bgColor + ';border-color:var(--border-color,#ced4da)!important;color:' + errColor + ';width:220px;max-width:220px;margin-top:6px;pointer-events:auto';
    toastEl.setAttribute('role', 'alert');
    toastEl.innerHTML =
        '<div class="d-flex align-items-center">' +
        '<div style="width:3px;align-self:stretch;background:' + accent + ';border-radius:2px 0 0 2px;flex-shrink:0"></div>' +
        '<div class="toast-body" style="font-size:0.82rem;padding:8px 10px">' + msg + '</div>' +
        '<button type="button" data-bs-dismiss="toast" style="' +
            'flex-shrink:0;margin-left:auto;margin-right:8px;padding:0;width:20px;height:20px;' +
            'border:none;border-radius:3px;cursor:pointer;outline:none;' +
            'background:transparent;color:' + closeFg + ';' +
            'font-size:14px;line-height:20px;text-align:center;' +
            'transition:background 0.15s,color 0.15s' +
        '">' +
        '&#x2715;' +
        '</button>' +
        '</div>';
    container.appendChild(toastEl);

    var closeBtn = toastEl.querySelector('button[data-bs-dismiss="toast"]');
    closeBtn.addEventListener('mouseenter', function() {
        this.style.background = closeHoverBg;
        this.style.color = closeHoverFg;
    });
    closeBtn.addEventListener('mouseleave', function() {
        this.style.background = 'transparent';
        this.style.color = closeFg;
    });

    var bsToast = new bootstrap.Toast(toastEl, { delay: delay });
    bsToast.show();
    toastEl.addEventListener('hidden.bs.toast', function() { toastEl.remove(); });
};
