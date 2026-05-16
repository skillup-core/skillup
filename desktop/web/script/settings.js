// Settings: language, theme, translations, hotkey, account, clock.

// ============================================================================
// Language / Theme / Translations
// ============================================================================
async function changeLanguage(lang) {
    currentLanguage = lang;
    window.currentLanguage = currentLanguage;
    await apiCall('set_config', { language: lang });
    applyTranslations();

    var titleKey = 'title.' + (currentPage === 'home' ? 'desktop' : currentPage);
    document.getElementById('page-title').textContent = i18n[currentLanguage][titleKey] || currentPage;

    if (appContentIframe) sendToIframe('setLanguage', { language: lang });

    await loadApps();
    updateTaskbar();

    if (document.getElementById('page-settings').style.display !== 'none') {
        await loadHotkeyStatus();
    }
}

async function changeTheme(theme) {
    var themeStylesheet = document.getElementById('theme-stylesheet');
    if (themeStylesheet) themeStylesheet.href = '/common/style/' + theme + '.css';
    if (appContentIframe) sendToIframe('setTheme', { theme: theme });
    await apiCall('set_config', { theme: theme });
}

function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(function(el) {
        var key = el.dataset.i18n;
        if (i18n[currentLanguage] && i18n[currentLanguage][key]) {
            el.textContent = i18n[currentLanguage][key];
        }
    });
}

// ============================================================================
// Hotkey Management
// ============================================================================
async function loadHotkeyStatus() {
    try {
        var data = await apiCall('hotkey_status');
        if (!data) return;

        var toggle = document.getElementById('hotkey-toggle');
        var statusText = document.getElementById('hotkey-status-text');
        var desktopInfo = document.getElementById('hotkey-desktop-info');
        var desktopName = document.getElementById('desktop-env-name');
        var hotkeyCommand = document.getElementById('hotkey-command');

        toggle.checked = data.registered;
        if (data.registered) {
            statusText.textContent = i18n[currentLanguage]['settings.hotkey_enabled'];
            statusText.style.color = 'var(--success)';
        } else {
            statusText.textContent = i18n[currentLanguage]['settings.hotkey_disabled'];
            statusText.style.color = 'var(--text-secondary)';
        }
        desktopName.textContent = data.desktop.toUpperCase();
        hotkeyCommand.textContent = data.command || '-';
        desktopInfo.style.display = data.registered ? 'block' : 'none';
    } catch (error) {
        console.error('Failed to load hotkey status:', error);
    }
}

async function toggleHotkey(enable) {
    var toggle = document.getElementById('hotkey-toggle');
    var statusText = document.getElementById('hotkey-status-text');
    toggle.disabled = true;
    try {
        var data = await apiCall('toggle_hotkey', { enable: enable });
        toggle.disabled = false;
        if (data && data.success) {
            if (enable) {
                statusText.textContent = i18n[currentLanguage]['settings.hotkey_enabled'];
                statusText.style.color = 'var(--success)';
            } else {
                statusText.textContent = i18n[currentLanguage]['settings.hotkey_disabled'];
                statusText.style.color = 'var(--text-secondary)';
            }
            loadHotkeyStatus();
        } else {
            toggle.checked = !enable;
            var msg = data ? data.message : 'Error';
            var orig = statusText.textContent, origColor = statusText.style.color;
            statusText.textContent = msg;
            statusText.style.color = 'var(--error)';
            setTimeout(function() { statusText.textContent = orig; statusText.style.color = origColor; }, 3000);
        }
    } catch (error) {
        toggle.disabled = false;
        toggle.checked = !enable;
        var origT = statusText.textContent, origC = statusText.style.color;
        statusText.textContent = 'Network error: ' + error.message;
        statusText.style.color = 'var(--error)';
        setTimeout(function() { statusText.textContent = origT; statusText.style.color = origC; }, 3000);
    }
}

// ============================================================================
// Clock
// ============================================================================
var clockIntervalId = null;

function updateClock() {
    var now = new Date();
    var h = String(now.getHours()).padStart(2, '0');
    var m = String(now.getMinutes()).padStart(2, '0');
    var s = String(now.getSeconds()).padStart(2, '0');
    document.getElementById('clock').textContent = h + ':' + m + ':' + s;
    if (clockIntervalId) clearTimeout(clockIntervalId);
    clockIntervalId = setTimeout(updateClock, 1000 - now.getMilliseconds());
}

// ============================================================================
// Account Management
// ============================================================================
var _pendingPhotoDataUri = null;

async function loadAccount() {
    try {
        var data = await apiCall('get_account');
        if (!data || !data.success) return;
        var nameInput = document.getElementById('account-name-input');
        var idDisplay = document.getElementById('account-id-display');
        if (nameInput) nameInput.value = data.name || data.id;
        if (idDisplay) idDisplay.textContent = data.id;
        await refreshAccountPhoto();
    } catch (e) {
        console.error('[Account] Failed to load account:', e);
    }
}

async function refreshAccountPhoto() {
    try {
        var data = await apiCall('get_account_photo', { size: 'small' });
        var src = (data && data.data_uri) ? data.data_uri : '/common/resource/img/default-avatar.svg';
        var topbarImg = document.getElementById('topbar-avatar-img');
        var settingsImg = document.getElementById('account-avatar-img');
        if (topbarImg) topbarImg.src = src;
        if (settingsImg) settingsImg.src = src;
        var removeBtn = document.getElementById('account-remove-photo-btn');
        if (removeBtn) removeBtn.style.display = (data && data.data_uri) ? 'inline-block' : 'none';
    } catch (e) {
        console.error('[Account] Failed to load photo:', e);
    }
}

function onAccountPhotoSelected(event) {
    var file = event.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = async function(e) {
        var dataUri = e.target.result;
        _pendingPhotoDataUri = dataUri;
        var settingsImg = document.getElementById('account-avatar-img');
        if (settingsImg) settingsImg.src = dataUri;
        var nameInput = document.getElementById('account-name-input');
        var name = nameInput ? nameInput.value.trim() : null;
        var result = await apiCall('save_account', { name: name || null, photo: dataUri });
        if (result && result.success) {
            _pendingPhotoDataUri = null;
            await refreshAccountPhoto();
        }
    };
    reader.readAsDataURL(file);
    event.target.value = '';
}

async function saveAccountName() {
    var nameInput = document.getElementById('account-name-input');
    if (!nameInput) return;
    var name = nameInput.value.trim();
    if (!name) return;
    var result = await apiCall('save_account', { name: name });
    if (result && result.success) {
        showMessageBox({ title: '', text: i18n[currentLanguage]['settings.account_name_saved'] });
    }
}

async function removeAccountPhoto() {
    var confirmed = await showConfirmDialog(
        i18n[currentLanguage]['settings.account_remove_photo_confirm_title'],
        i18n[currentLanguage]['settings.account_remove_photo_confirm_text'],
        { yesStyle: 'danger' }
    );
    if (!confirmed) return;
    var result = await apiCall('clear_account_photo');
    if (result && result.success) {
        _pendingPhotoDataUri = null;
        var defaultSrc = '/common/resource/img/default-avatar.svg';
        var settingsImg = document.getElementById('account-avatar-img');
        var topbarImg = document.getElementById('topbar-avatar-img');
        if (settingsImg) settingsImg.src = defaultSrc;
        if (topbarImg) topbarImg.src = defaultSrc;
        var removeBtn = document.getElementById('account-remove-photo-btn');
        if (removeBtn) removeBtn.style.display = 'none';
    }
}
