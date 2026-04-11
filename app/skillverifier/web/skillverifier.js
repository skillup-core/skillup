// ============================================================================
// Skillup Verifier - Common JavaScript
// ============================================================================

// Detect if running in iframe or web browser (use global variables from shared common)
const isInIframe = window.isInIframe;
const isInWebBrowser = window.isInWebBrowser;

// State is declared in individual HTML files (dashboard.html, verify.html, results.html)
// Each view initializes verifierState based on its mode (mock data for web browser, null for desktop)

let currentLanguage = 'en';

// ============================================================================
// i18n
// ============================================================================
const i18n = {
    en: {
        totalFiles: 'Total Files',
        errors: 'Errors',
        warnings: 'Warnings',
        passed: 'Passed',
        recentActivity: 'Recent Activity',
        noActivity: 'No recent activity',
        filesToVerify: 'Files to Verify',
        filePlaceholder: 'Enter file or directory paths (comma separated)',
        defineFile: 'Define File (optional)',
        dataDb: 'Data DB (optional)',
        startVerify: 'Start Verification',
        verifying: 'Verifying...',
        ready: 'Ready',
        completed: 'Completed',
        addDirectory: 'Add Directory',
        addFile: 'Add File',
        logs: 'Logs',
        results: 'Results',
        noResults: 'No results yet. Run verification first.',
        filterPlaceholder: 'Search files, errors...',
        expandAll: 'Expand All',
        collapseAll: 'Collapse All',
        filterDialogTitle: 'Filter by Error/Warning Types',
        filterSectionErrors: 'Errors',
        filterSectionWarnings: 'Warnings',
        filterSectionClean: 'Clean Files',
        filterSelectAll: 'Select All',
        filterDeselectAll: 'Deselect All',
        filterShowCleanFiles: 'Show files with no errors',
        btnCancel: 'Cancel',
        btnApply: 'Apply'
    },
    ko: {
        totalFiles: '전체 파일',
        errors: '에러',
        warnings: '경고',
        passed: '통과',
        recentActivity: '최근 활동',
        noActivity: '최근 활동 없음',
        filesToVerify: '검증할 파일',
        filePlaceholder: '파일 또는 디렉토리 경로 (쉼표로 구분)',
        defineFile: 'Define 파일 (선택)',
        dataDb: '데이터 DB (선택)',
        startVerify: '검증 시작',
        verifying: '검증 중...',
        ready: '준비중',
        completed: '완료',
        addDirectory: '디렉토리 추가',
        addFile: '파일 추가',
        logs: '로그',
        results: '결과',
        noResults: '결과가 없습니다. 먼저 검증을 실행하세요.',
        filterPlaceholder: '파일, 에러 검색...',
        expandAll: '모두 펼치기',
        collapseAll: '모두 접기',
        filterDialogTitle: '에러/경고 타입 필터',
        filterSectionErrors: '에러',
        filterSectionWarnings: '경고',
        filterSectionClean: '정상 파일',
        filterSelectAll: '전체 선택',
        filterDeselectAll: '전체 해제',
        filterShowCleanFiles: '에러가 없는 파일 표시',
        btnCancel: '취소',
        btnApply: '적용'
    }
};

// ============================================================================
// Internal Tab Navigation (app menu items rendered inside app)
// ============================================================================
const appMenuItems = [
    { id: 'dashboard', name: 'Dashboard', name_ko: '대시보드' },
    { id: 'verify', name: 'File Verify', name_ko: '파일검증' },
    { id: 'results', name: 'Results', name_ko: '결과' }
];

function getCurrentViewId() {
    // Determine current view from URL filename
    const path = window.location.pathname;
    const filename = path.split('/').pop().replace('.html', '');
    return filename || 'dashboard';
}

function buildAppTabBar() {
    const currentViewId = getCurrentViewId();
    const container = document.createElement('div');
    container.className = 'app-tab-bar';
    container.id = 'app-tab-bar';

    appMenuItems.forEach(item => {
        const tab = document.createElement('a');
        tab.className = 'app-tab' + (item.id === currentViewId ? ' active' : '');
        tab.dataset.tabId = item.id;
        const label = currentLanguage === 'ko' ? item.name_ko : item.name;
        tab.textContent = label;
        tab.onclick = () => {
            window.parent.postMessage({ action: 'switchView', viewId: item.id }, '*');
        };
        container.appendChild(tab);
    });

    return container;
}

function insertAppTabBar() {
    const existing = document.getElementById('app-tab-bar');
    if (existing) existing.remove();

    const tabBar = buildAppTabBar();
    // Insert before .content-container (the main content div), or prepend to body
    const contentContainer = document.querySelector('.content-container');
    if (contentContainer) {
        document.body.insertBefore(tabBar, contentContainer);
    } else {
        document.body.prepend(tabBar);
    }
}

function updateAppTabBarLanguage() {
    const tabs = document.querySelectorAll('.app-tab');
    tabs.forEach(tab => {
        const item = appMenuItems.find(m => m.id === tab.dataset.tabId);
        if (item) {
            tab.textContent = currentLanguage === 'ko' ? item.name_ko : item.name;
        }
    });
}

// ============================================================================
// Parent Communication
// ============================================================================
function sendToParent(action, data = {}) {
    if (isInIframe) {
        window.parent.postMessage({ action, ...data }, '*');
    }
}

function apiCall(action, data = {}) {
    return new Promise((resolve) => {
        if (isInIframe) {
            const messageId = Date.now() + Math.random();
            const handler = (event) => {
                if (event.data && event.data.messageId === messageId) {
                    window.removeEventListener('message', handler);
                    resolve(event.data.result);
                }
            };
            window.addEventListener('message', handler);
            window.parent.postMessage({ action: 'api', messageId, apiAction: action, apiData: data }, '*');
            setTimeout(() => {
                window.removeEventListener('message', handler);
                resolve(null);
            }, 10000);
        } else {
            // Direct API call
            fetch(`/api/${action}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(resolve)
            .catch(() => resolve(null));
        }
    });
}

// Listen for messages from parent
window.addEventListener('message', (event) => {
    const data = event.data;
    if (!data || !data.action) return;

    switch (data.action) {
        case 'setLanguage':
            currentLanguage = data.language;
            applyTranslations();
            updateAppTabBarLanguage();
            if (typeof onLanguageChange === 'function') {
                onLanguageChange(data.language);
            }
            break;

        case 'setActiveTab':
            // Update active tab when desktop switches to this cached iframe
            document.querySelectorAll('.app-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.tabId === data.viewId);
            });
            break;
        case 'updateState':
            if (data.state) {
                console.log('[DEBUG] updateState received:', data.state);
                console.log('[DEBUG] results count:', data.state.results ? data.state.results.length : 0);

                // Initialize verifierState with defaults if null
                if (!verifierState) {
                    verifierState = {
                        running: false,
                        progress: 0,
                        total: 0,
                        current_file: '',
                        logs: [],
                        results: [],
                        error: null,
                        files_input: '',
                        define_file_input: '',
                        data_db_input: ''
                    };
                }

                // Ensure logs and results arrays exist
                if (!verifierState.logs) verifierState.logs = [];
                if (!verifierState.results) verifierState.results = [];

                // Handle incremental log updates (new_logs field for throttled updates)
                if (data.state.new_logs && Array.isArray(data.state.new_logs) && data.state.new_logs.length > 0) {
                    // Append new logs to existing logs
                    verifierState.logs.push(...data.state.new_logs);
                    // Keep last 1000 logs
                    if (verifierState.logs.length > 1000) {
                        verifierState.logs = verifierState.logs.slice(-1000);
                    }
                }

                // Update state (skip logs/results if not provided to avoid overwriting)
                const stateUpdate = { ...data.state };
                delete stateUpdate.new_logs;  // Remove new_logs as it's already handled

                // Only update logs/results if they're present in the update
                if (!data.state.hasOwnProperty('logs')) {
                    delete stateUpdate.logs;
                }
                if (!data.state.hasOwnProperty('results')) {
                    delete stateUpdate.results;
                }

                Object.assign(verifierState, stateUpdate);
                console.log('[DEBUG] verifierState.results after assign:', verifierState.results ? verifierState.results.length : 0);
                if (typeof onStateUpdate === 'function') {
                    onStateUpdate();
                }
            }
            break;
        case 'requestFocus':
            // Focus body so keyboard scroll (up/down) works immediately
            if (!document.body.hasAttribute('tabindex')) {
                document.body.setAttribute('tabindex', '-1');
            }
            document.body.focus();
            break;
    }
});

// ============================================================================
// Template Functions
// ============================================================================
function createStatCard(value, label, type = '') {
    const typeClass = type ? ` ${type}` : '';
    return `
        <div class="stat-card${typeClass}">
            <div class="stat-value">${escapeHtml(String(value))}</div>
            <div class="stat-label" data-i18n="${label}">${i18n[currentLanguage][label] || label}</div>
        </div>
    `;
}

function createStatsGrid(stats) {
    return `
        <div class="stats-grid">
            ${createStatCard(stats.totalFiles, 'totalFiles')}
            ${createStatCard(stats.errors, 'errors', 'error')}
            ${createStatCard(stats.warnings, 'warnings', 'warning')}
            ${stats.passed !== undefined ? createStatCard(stats.passed, 'passed', 'success') : ''}
        </div>
    `;
}

function createFilterRow() {
    const t = i18n[currentLanguage] || i18n.en;
    return `
        <div class="filter-row">
            <input type="text" class="form-control" id="filter-input" data-i18n-placeholder="filterPlaceholder" placeholder="${t.filterPlaceholder}" oninput="applyResultsFilter()">
            <button class="btn btn-secondary" onclick="openFilterDialog()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="vertical-align: middle;">
                    <path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/>
                </svg>
            </button>
            <button class="btn btn-secondary" id="expand-all-btn" onclick="expandAllResults()" data-i18n="expandAll">${t.expandAll}</button>
        </div>
    `;
}

function createResultFileHeader(result, index, badges) {
    return `
        <div class="result-file-header" onclick="toggleResultFile(${index})">
            <div class="result-file-name">
                <svg class="expand-icon" viewBox="0 0 24 24"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>
                <span>${escapeHtml(result.filepath)}</span>
            </div>
            <div class="file-badges">${badges}</div>
        </div>
    `;
}

function createErrorItem(err, index) {
    const typeClass = err.type === 'error' ? 'result-error' : 'result-warning';
    const errLine = err.line || 0;
    return `
        <div class="${typeClass}" data-file-index="${index}" data-line="${errLine}" onclick="toggleCodeViewer(this, ${index}, ${errLine})">
            <div class="error-type-label ${err.type}">${err.type.toUpperCase()}</div>
            <div class="error-details">
                ${err.line ? `Line <strong>${err.line}</strong>` : ''}
                ${err.function ? ` in function <strong>${escapeHtml(err.function)}</strong>` : ''}
            </div>
            <div class="error-message">${escapeHtml(err.message || '')}</div>
        </div>
    `;
}

function createErrorList(errors, index) {
    if (errors.length === 0) return '';

    let errorListHtml = '<div class="error-list">';
    errors.forEach((err) => {
        errorListHtml += createErrorItem(err, index);
    });
    errorListHtml += '</div>';
    return errorListHtml;
}

function createFileBadges(errorCount, warningCount) {
    let badges = '';
    if (errorCount > 0) {
        badges += `<span class="file-badge badge-error">${errorCount} error${errorCount !== 1 ? 's' : ''}</span>`;
    }
    if (warningCount > 0) {
        badges += `<span class="file-badge badge-warning">${warningCount} warning${warningCount !== 1 ? 's' : ''}</span>`;
    }
    if (errorCount === 0 && warningCount === 0) {
        badges += `<span class="file-badge badge-success">OK</span>`;
    }
    return badges;
}

function createResultFile(result, index) {
    const errors = result.errors || [];
    const errorCount = errors.filter(e => e.type === 'error').length;
    const warningCount = errors.filter(e => e.type === 'warning').length;

    let fileClass = 'result-file';
    if (errorCount > 0) fileClass += ' has-errors';
    else if (warningCount > 0) fileClass += ' has-warnings';
    else fileClass += ' no-errors';

    const badges = createFileBadges(errorCount, warningCount);
    const errorListHtml = createErrorList(errors, index);
    const filename = result.filepath ? result.filepath.toLowerCase() : '';

    return `
        <div class="${fileClass}" data-index="${index}" data-filename="${escapeHtml(filename)}">
            ${createResultFileHeader(result, index, badges)}
            ${errorListHtml}
        </div>
    `;
}

function createLogLine(log) {
    return `<div class="log-line">${ansiToHtml(log.message)}</div>`;
}

function createVerifyForm() {
    const t = i18n[currentLanguage] || i18n.en;

    // Get values from verifierState (if available)
    const filesValue = (window.appState && window.appState.files_input) || '';
    const defineValue = (window.appState && window.appState.define_file_input) || '';
    const dataDbValue = (window.appState && window.appState.data_db_input) || '';

    return `
        <div class="form-group">
            <label data-i18n="filesToVerify">${t.filesToVerify}</label>
            <div class="file-input-row">
                <input type="text" class="form-control" id="verify-files"
                    value="${escapeHtml(filesValue)}"
                    data-i18n-placeholder="filePlaceholder" placeholder="${t.filePlaceholder}"
                    onchange="saveFormInputs()">
                <button class="btn btn-secondary" onclick="addDirectory()" data-i18n="addDirectory" style="white-space: nowrap;">${t.addDirectory}</button>
                <button class="btn btn-secondary" onclick="addFile()" data-i18n="addFile" style="white-space: nowrap;">${t.addFile}</button>
            </div>
        </div>
        <div class="form-group">
            <label data-i18n="defineFile">${t.defineFile}</label>
            <input type="text" class="form-control" id="verify-define"
                value="${escapeHtml(defineValue)}"
                onchange="saveFormInputs()">
        </div>
        <div class="form-group">
            <label data-i18n="dataDb">${t.dataDb}</label>
            <input type="text" class="form-control" id="verify-datadb"
                value="${escapeHtml(dataDbValue)}"
                onchange="saveFormInputs()">
        </div>
        <button class="btn btn-primary" id="btn-start-verify" onclick="startVerification()" data-i18n="startVerify">${t.startVerify}</button>
    `;
}

// Save form inputs to Python backend
async function saveFormInputs() {
    if (window.isInWebBrowser) return;

    const filesInput = document.getElementById('verify-files')?.value || '';
    const defineFile = document.getElementById('verify-define')?.value || '';
    const dataDb = document.getElementById('verify-datadb')?.value || '';

    try {
        await window.callPython('save_verify_inputs', {
            files_input: filesInput,
            define_file_input: defineFile,
            data_db_input: dataDb
        });

        // Update local state
        if (window.appState) {
            window.appState.files_input = filesInput;
            window.appState.define_file_input = defineFile;
            window.appState.data_db_input = dataDb;
        }
    } catch (error) {
        console.error('Failed to save form inputs:', error);
    }
}

// ============================================================================
// Utilities
// ============================================================================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function ansiToHtml(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    html = html.replace(/\x1b\[92m/g, '<span style="color: #3fb950">');
    html = html.replace(/\x1b\[93m/g, '<span style="color: #d29922">');
    html = html.replace(/\x1b\[91m/g, '<span style="color: #f85149">');
    html = html.replace(/\x1b\[0m/g, '</span>');
    return html;
}

function highlightText(text, searchText) {
    if (!text || !searchText) return escapeHtml(text);

    const escapedText = escapeHtml(text);
    const searchLower = searchText.toLowerCase();
    const textLower = text.toLowerCase();

    let result = '';
    let lastIndex = 0;

    while (true) {
        const index = textLower.indexOf(searchLower, lastIndex);
        if (index === -1) {
            result += escapedText.substring(lastIndex);
            break;
        }

        result += escapedText.substring(lastIndex, index);
        result += '<mark class="highlight-match">';
        result += escapedText.substring(index, index + searchText.length);
        result += '</mark>';

        lastIndex = index + searchText.length;
    }

    return result;
}

function applyTranslations() {
    const t = i18n[currentLanguage] || i18n.en;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.dataset.i18n;
        if (t[key]) el.textContent = t[key];
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.dataset.i18nPlaceholder;
        if (t[key]) el.placeholder = t[key];
    });
}

// Notify parent that view is ready
document.addEventListener('DOMContentLoaded', () => {
    applyTranslations();

    // Insert internal tab bar for desktop iframe mode
    if (isInIframe) {
        insertAppTabBar();
    }

    if (isInWebBrowser) {
        // Web browser mode - show banner and trigger initial update
        console.log('[Web Browser Mode] Running independently for debugging');
        // Call onStateUpdate if defined to render with mock data
        if (typeof onStateUpdate === 'function') {
            onStateUpdate();
        }
    } else {
        sendToParent('viewReady');
    }
});
