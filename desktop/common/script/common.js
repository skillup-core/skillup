// ============================================================================
// Skillup - Common Application JavaScript
// ============================================================================
// This file provides common functionality for all Skillup applications.
// It is automatically loaded by appinit.js and should NOT be loaded directly.
//
// Global variables available (set by appinit.js):
//   - window.isInIframe: true if running in desktop iframe
//   - window.isInWebBrowser: true if running in web browser
//   - window.SkillupTheme: theme management API
// ============================================================================

(function() {
    'use strict';

    // Wait for appinit.js to complete
    if (!window.skillupInitialized) {
        console.warn('[Skillup Common] Loaded before appinit.js - some features may not work');
    }

    console.log('[Skillup Common] Common functionality initialized');

    // ========================================================================
    // Utility Functions
    // ========================================================================

    /**
     * Escape HTML to prevent XSS
     */
    window.escapeHtml = function(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    /**
     * Convert ANSI color codes to HTML
     */
    window.ansiToHtml = function(text) {
        if (!text) return '';
        let html = window.escapeHtml(text);
        html = html.replace(/\x1b\[92m/g, '<span style="color: #3fb950">');
        html = html.replace(/\x1b\[93m/g, '<span style="color: #d29922">');
        html = html.replace(/\x1b\[91m/g, '<span style="color: #f85149">');
        html = html.replace(/\x1b\[0m/g, '</span>');
        return html;
    };

    /**
     * Debounce function calls
     */
    window.debounce = function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    /**
     * Show message box using Bootstrap modal
     * Called from Python backend via callJS
     */
    window.showMessageBox = function(data) {
        try {
            const params = typeof data === 'string' ? JSON.parse(data) : data;
            const title = params.title || 'Message';
            const text = params.text || '';

            // Find or create modal element
            let modal = document.getElementById('skillup-msgbox-modal');
            if (!modal) {
                // Create modal element
                const modalHtml = `
                    <div class="modal fade" id="skillup-msgbox-modal" tabindex="-1" data-bs-backdrop="static" data-bs-keyboard="false">
                        <div class="modal-dialog modal-dialog-centered">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title" id="skillup-msgbox-title"></h5>
                                </div>
                                <div class="modal-body" id="skillup-msgbox-body"></div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-primary" data-bs-dismiss="modal">OK</button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                document.body.insertAdjacentHTML('beforeend', modalHtml);
                modal = document.getElementById('skillup-msgbox-modal');
            }

            // Set content
            document.getElementById('skillup-msgbox-title').textContent = title;
            document.getElementById('skillup-msgbox-body').textContent = text;

            // Show modal
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();

            console.log('[Skillup] Message box shown:', title);
        } catch (error) {
            console.error('[Skillup] Failed to show message box:', error);
        }
    };

    // ========================================================================
    // Python ↔ JavaScript Communication API
    // ========================================================================

    // QWebChannel bridge (initialized after QWebChannel loads)
    let _qwebchannelBridge = null;
    let _qwebchannelReady = false;

    /**
     * Initialize QWebChannel for direct Python communication
     */
    function initQWebChannel() {
        if (window.isInWebBrowser) {
            return Promise.resolve(); // Not available in web browser
        }

        if (typeof QWebChannel === 'undefined' || typeof qt === 'undefined') {
            // In iframe context, callPython uses REST API and callJS uses postMessage
            if (window.isInIframe) {
                console.log('[Skillup] Running in iframe - using postMessage for callJS');
            }
            return Promise.resolve();
        }

        return new Promise((resolve) => {
            console.log('[Skillup] Initializing QWebChannel bridge...');

            new QWebChannel(qt.webChannelTransport, function(channel) {
                _qwebchannelBridge = channel.objects.bridge;

                if (_qwebchannelBridge) {
                    _qwebchannelReady = true;
                    console.log('[Skillup] QWebChannel bridge ready - fast mode enabled');

                    // Listen for Python → JavaScript signals
                    if (_qwebchannelBridge.messageReceived) {
                        _qwebchannelBridge.messageReceived.connect(function(type, message) {
                            console.log(`[Skillup] Signal from Python [${type}]:`, message);
                        });
                    }

                    // Listen for Python → JavaScript function calls
                    if (_qwebchannelBridge.callJS) {
                        _qwebchannelBridge.callJS.connect(function(functionName, jsonArgs) {
                            try {
                                const args = JSON.parse(jsonArgs);
                                console.log(`[Skillup] callJS from Python: ${functionName}`, args);

                                // Call the JavaScript function if it exists in window
                                if (typeof window[functionName] === 'function') {
                                    window[functionName](args);
                                } else {
                                    console.debug(`[Skillup] JavaScript function not found: ${functionName}`);
                                }
                            } catch (error) {
                                console.error(`[Skillup] callJS failed for ${functionName}:`, error);
                            }
                        });
                    }
                } else {
                    console.warn('[Skillup] QWebChannel bridge object not found');
                }

                resolve();
            });
        });
    }

    /**
     * Call Python backend function from JavaScript
     * Usage: await callPython('verify_status')
     *
     * Uses QWebChannel if available (fast), falls back to REST API
     */
    window.callPython = async function(action, data = {}) {
        if (window.isInWebBrowser) {
            console.warn('[Skillup] callPython in web browser mode - returning null');
            return null;
        }

        // Intercept file dialog actions - use web-based dialog instead of Qt
        if (action === 'select_directory') {
            return window._showWebFileDialog('directory', data);
        }
        if (action === 'select_file') {
            return window._showWebFileDialog('file', data);
        }

        // Use QWebChannel if available (10x faster)
        if (_qwebchannelReady && _qwebchannelBridge) {
            try {
                const jsonData = JSON.stringify(data);

                // Call Python via QWebChannel (synchronous from Python's perspective)
                return new Promise((resolve, reject) => {
                    _qwebchannelBridge.callPython(action, jsonData, function(resultJson) {
                        try {
                            const result = JSON.parse(resultJson);
                            if (result.error) {
                                console.error(`[Skillup] QWebChannel error: ${result.error}`);
                            }
                            resolve(result);
                        } catch (e) {
                            console.error('[Skillup] Failed to parse QWebChannel result:', e);
                            reject(e);
                        }
                    });
                });
            } catch (error) {
                console.error(`[Skillup] QWebChannel call failed, falling back to REST API:`, error);
                // Fall through to REST API
            }
        }

        // Fallback to REST API (original method)
        try {
            let url;

            // Check if this is an app-specific call
            if (window.skillupAppGuid && isAppSpecificAction(action)) {
                // Route through app-specific handler: /api/callPython/<guid>/<action>
                url = `/api/callPython/${window.skillupAppGuid}/${action}`;
            } else {
                // Direct desktop API call: /api/<action>
                url = `/api/${action}`;
            }

            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`[Skillup] callPython('${action}') failed:`, error);
            throw error;
        }
    };

    /**
     * Determine if an action is app-specific (not a desktop-level action)
     */
    function isAppSpecificAction(action) {
        // Desktop-level actions that should NOT be routed through app handlers
        const desktopActions = new Set([
            'init_app_guid',
            'get_apps',
            'get_config',
            'set_config',
            'launch_app',
            'close_app',
            'get_app_icon',
            'get_app_content',
            'browse_path',
            'open_window',
            'resize_window'
        ]);

        return !desktopActions.has(action);
    }

    /**
     * Alias for backward compatibility
     */
    window.apiCall = window.callPython;

    /**
     * Send message to parent window (desktop.html)
     */
    window.sendToParent = function(action, data = {}) {
        if (window.isInIframe && window.parent) {
            window.parent.postMessage({ action, data }, '*');
        }
    };

    /**
     * Global app state (synced with Python backend)
     * Apps should use this instead of local state variables
     */
    window.appState = null;

    /**
     * Load app state from Python backend
     * Automatically called on page load for apps that define getAppStateAction()
     */
    window.loadAppState = async function(action) {
        if (!action) {
            console.warn('[Skillup] loadAppState called without action');
            return null;
        }

        try {
            const state = await window.callPython(action);
            window.appState = state;
            console.log('[Skillup] App state loaded:', state);

            // Call app-specific callback if defined
            if (typeof window.onAppStateLoaded === 'function') {
                window.onAppStateLoaded(state);
            }

            return state;
        } catch (error) {
            console.error('[Skillup] Failed to load app state:', error);
            return null;
        }
    };

    /**
     * Auto-load app state when DOM is ready
     */
    async function initAppState() {
        if (window.isInWebBrowser) {
            // In web browser mode, skip auto-load (apps provide mock data)
            return;
        }

        // Skip state loading for desktop.html (only needed for app iframes)
        // Desktop loads at root path '/' and doesn't need app state
        const isDesktopPage = window.location.pathname === '/' ||
                              window.location.pathname === '/desktop' ||
                              window.location.pathname === '/desktop/';
        if (isDesktopPage) {
            return;
        }

        // IMPORTANT: Wait for appinit.js to initialize GUID first
        if (!window.skillupInitialized) {
            console.log('[Skillup] Waiting for appinit.js to initialize GUID...');
            await new Promise(resolve => {
                window.addEventListener('skillupInitialized', resolve, { once: true });
            });
        }

        // Initialize QWebChannel for fast communication
        await initQWebChannel();

        // Wait for getAppStateAction to be defined (it's defined in inline scripts)
        // Poll with short timeout to avoid race conditions
        let attempts = 0;
        while (typeof window.getAppStateAction !== 'function' && attempts < 50) {
            await new Promise(resolve => setTimeout(resolve, 10));
            attempts++;
        }

        // Check if app defined the state action
        if (typeof window.getAppStateAction === 'function') {
            const action = window.getAppStateAction();
            if (action) {
                console.log('[Skillup] Loading app state with action:', action);
                await window.loadAppState(action);
            } else {
                console.log('[Skillup] App does not require state loading');
            }
        } else {
            console.log('[Skillup] App does not use getAppStateAction, skipping state load');
        }
    }

    /**
     * In Qt standalone window mode, load language/theme from desktop config
     * since there's no parent iframe to forward these settings via postMessage
     */
    async function initStandaloneSettings() {
        if (!window.isInQtWindow) return;

        try {
            const config = await window.callPython('get_config', {});
            if (!config) return;

            // Apply theme
            if (config.theme && window.SkillupTheme) {
                window.SkillupTheme.setTheme(config.theme);
            }

            // Apply language - use postMessage to self, same as iframe path
            if (config.language) {
                window.postMessage({ action: 'setLanguage', language: config.language }, '*');
            }
        } catch (e) {
            console.warn('[Skillup] Failed to load standalone settings:', e);
        }
    }

    // Load state when DOM is ready
    if (document.readyState === 'loading') {
        // DOM not yet loaded, wait for DOMContentLoaded
        document.addEventListener('DOMContentLoaded', () => {
            initAppState();
            initStandaloneSettings();
        });
    } else {
        // DOM already loaded (common when scripts load late), load immediately
        // But use setTimeout to ensure inline scripts have chance to execute
        setTimeout(() => {
            initAppState();
            initStandaloneSettings();
        }, 0);
    }

    /**
     * Reload app state when view becomes visible
     * Called by desktop when switching tabs
     */
    window.reloadAppState = async function() {
        if (typeof window.getAppStateAction === 'function') {
            const action = window.getAppStateAction();
            if (action) {
                await window.loadAppState(action);
            }
        }

        // Call app-specific callback if defined
        if (typeof window.onViewActivated === 'function') {
            window.onViewActivated();
        }
    };

    // ========================================================================
    // PostMessage Listener for callJS Forwarding from Desktop
    // ========================================================================
    // When running in iframe, desktop.html forwards callJS via postMessage
    if (window.isInIframe) {
        window.addEventListener('message', (event) => {
            const data = event.data;
            if (!data || !data.action) return;

            // Handle theme changes from desktop
            if (data.action === 'setTheme') {
                if (window.SkillupTheme && data.theme) {
                    window.SkillupTheme.setTheme(data.theme);
                }
                return;
            }

            // Handle language changes from desktop
            if (data.action === 'setLanguage') {
                // Language change is handled by individual apps
                return;
            }

            // Handle state reload request from desktop (when tab becomes visible)
            if (data.action === 'reloadAppState') {
                if (window.reloadAppState) {
                    window.reloadAppState();
                }
                return;
            }

            // Handle callJS forwarding from desktop
            if (data.action === 'callJS') {
                const functionName = data.functionName;
                const args = data.args;

                // Call the JavaScript function if it exists in window
                if (typeof window[functionName] === 'function') {
                    window[functionName](args);
                } else {
                    console.debug(`[Skillup Common] JavaScript function not found: ${functionName}`);
                }
            }
        });
    }

    // ========================================================================
    // Web-based File/Directory Dialog (replaces Qt QFileDialog)
    // ========================================================================

    /**
     * Internal: call Python browse_path from the correct context
     * In iframe, we need to route through parent's callPython for desktop actions
     */
    async function _browsePath(data) {
        // browse_path is a desktop-level action, handled by callPython routing
        return window.callPython('browse_path', data);
    }

    /**
     * Show web-based file/directory selection dialog
     * @param {string} mode - 'directory' or 'file'
     * @param {object} data - { language, filter }
     * @returns {Promise<{success: boolean, path?: string, error?: string}>}
     */
    window._showWebFileDialog = function(mode, data = {}) {
        return new Promise((resolve) => {
            const lang = data.language || 'en';
            const isKo = lang !== 'en';
            const isDir = mode === 'directory';

            // Text labels
            const txt = {
                title: isDir
                    ? (isKo ? '디렉토리 선택' : 'Select Directory')
                    : (isKo ? '파일 선택' : 'Select File'),
                select: isKo ? '선택' : 'Select',
                cancel: isKo ? '취소' : 'Cancel',
                name: isKo ? '이름' : 'Name',
                up: isKo ? '상위' : 'Up',
                home: isKo ? '홈' : 'Home',
                empty: isKo ? '(비어 있음)' : '(empty)',
                permDenied: isKo ? '접근 거부' : 'Permission denied',
                loading: isKo ? '로딩...' : 'Loading...'
            };

            // Target element: if in iframe, use parent document; else use own document
            const doc = (window.isInIframe && window.parent) ? window.parent.document : document;

            // Create overlay
            const overlay = doc.createElement('div');
            overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:99999;display:flex;align-items:center;justify-content:center;font-family:var(--font-sans, sans-serif)';

            const dialog = doc.createElement('div');
            dialog.style.cssText = 'background:var(--bg-secondary, #20242b);border:1px solid var(--border-color, #373c47);border-radius:8px;width:560px;height:500px;display:flex;flex-direction:column;color:var(--text-primary, #e4e6eb);box-shadow:0 8px 32px rgba(0,0,0,0.5)';

            // Header
            const header = doc.createElement('div');
            header.style.cssText = 'padding:12px 16px;border-bottom:1px solid var(--border-color, #373c47);display:flex;align-items:center;flex-shrink:0';
            header.innerHTML = '<span style="font-size:14px;font-weight:600">' + escapeHtml(txt.title) + '</span>';

            // Path bar
            const pathBar = doc.createElement('div');
            pathBar.style.cssText = 'padding:8px 16px;display:flex;align-items:center;border-bottom:1px solid var(--border-color, #373c47);flex-shrink:0';

            const btnStyle = 'background:var(--bg-tertiary, #2a2f38);color:var(--text-secondary, #b0b3b8);border:1px solid var(--border-color, #373c47);border-radius:4px;padding:3px 10px;cursor:pointer;font-size:12px;margin-right:6px;font-family:inherit';

            const homeBtn = doc.createElement('button');
            homeBtn.style.cssText = btnStyle;
            homeBtn.textContent = txt.home;

            const pathInput = doc.createElement('input');
            pathInput.type = 'text';
            pathInput.style.cssText = 'flex:1;background:var(--bg-primary, #1a1d23);color:var(--text-primary, #e4e6eb);border:1px solid var(--border-color, #373c47);border-radius:4px;padding:4px 8px;font-size:12px;font-family:var(--font-mono, monospace);outline:none';

            pathBar.appendChild(homeBtn);
            pathBar.appendChild(pathInput);

            // File list
            const listContainer = doc.createElement('div');
            listContainer.style.cssText = 'flex:1;overflow-y:auto;min-height:0;padding:4px 0';

            // Selected file display (file mode only)
            let selectedFileBar = null;
            let selectedFileName = '';
            if (!isDir) {
                selectedFileBar = doc.createElement('div');
                selectedFileBar.style.cssText = 'padding:6px 16px;border-top:1px solid var(--border-color, #373c47);display:flex;align-items:center;flex-shrink:0;font-size:12px';
                const fileLabel = doc.createElement('span');
                fileLabel.style.cssText = 'color:var(--text-secondary, #b0b3b8);margin-right:8px;white-space:nowrap';
                fileLabel.textContent = txt.name + ':';
                const fileNameSpan = doc.createElement('span');
                fileNameSpan.style.cssText = 'color:var(--text-primary, #e4e6eb);font-family:var(--font-mono, monospace)';
                fileNameSpan.id = '_wfd_selected_file';
                selectedFileBar.appendChild(fileLabel);
                selectedFileBar.appendChild(fileNameSpan);
            }

            // Footer
            const footer = doc.createElement('div');
            footer.style.cssText = 'padding:10px 16px;border-top:1px solid var(--border-color, #373c47);display:flex;justify-content:flex-end;flex-shrink:0';

            const cancelBtn = doc.createElement('button');
            cancelBtn.style.cssText = btnStyle + ';padding:5px 16px;font-size:13px';
            cancelBtn.textContent = txt.cancel;

            const selectBtn = doc.createElement('button');
            selectBtn.style.cssText = 'background:var(--accent-primary, #3b82f6);color:#fff;border:none;border-radius:4px;padding:5px 16px;cursor:pointer;font-size:13px;margin-left:8px;font-family:inherit';
            selectBtn.textContent = txt.select;

            footer.appendChild(cancelBtn);
            footer.appendChild(selectBtn);

            dialog.appendChild(header);
            dialog.appendChild(pathBar);
            dialog.appendChild(listContainer);
            if (selectedFileBar) dialog.appendChild(selectedFileBar);
            dialog.appendChild(footer);
            overlay.appendChild(dialog);

            let currentPath = '';

            function joinPath(base, name) {
                if (base === '/') return '/' + name;
                return base + '/' + name;
            }

            function cleanup() {
                window.removeEventListener('keydown', onKey, true);
                if (window.isInIframe) {
                    doc.removeEventListener('keydown', onKey, true);
                }
                if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
            }

            function finish(path) {
                cleanup();
                if (path) {
                    resolve({ success: true, path: path });
                } else {
                    resolve({ success: false, error: 'No selection' });
                }
            }

            cancelBtn.onclick = () => finish(null);
            overlay.onclick = (e) => { if (e.target === overlay) finish(null); };

            selectBtn.onclick = () => {
                if (isDir) {
                    finish(currentPath);
                } else {
                    if (selectedFileName) {
                        finish(joinPath(currentPath, selectedFileName));
                    }
                }
            };

            let rows = [];      // { el, is_dir, name, action }
            let cursorIdx = -1; // keyboard cursor position

            const SEL_BG = 'var(--accent-primary, #3b82f6)';
            const HOV_BG = 'var(--bg-tertiary, #2a2f38)';

            function setCursor(idx) {
                if (cursorIdx >= 0 && cursorIdx < rows.length) {
                    rows[cursorIdx].el.style.background = '';
                    rows[cursorIdx].el.style.color = '';
                }
                cursorIdx = idx;
                if (cursorIdx >= 0 && cursorIdx < rows.length) {
                    rows[cursorIdx].el.style.background = SEL_BG;
                    rows[cursorIdx].el.style.color = '#fff';
                    // Scroll into view (offsetTop relative to listContainer)
                    const el = rows[cursorIdx].el;
                    const ct = listContainer;
                    const relTop = el.offsetTop - ct.offsetTop;
                    if (relTop < ct.scrollTop) {
                        ct.scrollTop = relTop;
                    } else if (relTop + el.offsetHeight > ct.scrollTop + ct.clientHeight) {
                        ct.scrollTop = relTop + el.offsetHeight - ct.clientHeight;
                    }
                }
            }

            async function loadDir(dirPath) {
                listContainer.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-secondary, #b0b3b8);font-size:13px">' + txt.loading + '</div>';
                try {
                    const res = await _browsePath({ path: dirPath });
                    if (!res || !res.success) {
                        listContainer.innerHTML = '<div style="padding:20px;text-align:center;color:var(--error, #ef4444);font-size:13px">' + escapeHtml(res && res.error || 'Error') + '</div>';
                        return;
                    }
                    currentPath = res.path;
                    pathInput.value = currentPath;
                    selectedFileName = '';
                    if (!isDir && doc.getElementById('_wfd_selected_file')) {
                        doc.getElementById('_wfd_selected_file').textContent = '';
                    }

                    const entries = res.entries || [];
                    if (res.error) {
                        // Permission denied but path is valid
                        listContainer.innerHTML = '<div style="padding:20px;text-align:center;color:var(--warning, #f59e0b);font-size:13px">' + escapeHtml(txt.permDenied) + '</div>';
                        return;
                    }

                    // Filter: in directory mode show only dirs; in file mode apply extension filter if set
                    const extFilter = (!isDir && data.filter)
                        ? data.filter.split(/\s+/).map(s => s.replace(/^\*\./, '').toLowerCase()).filter(Boolean)
                        : [];
                    const filtered = isDir
                        ? entries.filter(e => e.is_dir)
                        : entries.filter(e => e.is_dir || extFilter.length === 0 ||
                            extFilter.some(ext => e.name.toLowerCase().endsWith('.' + ext)));

                    listContainer.innerHTML = '';
                    cursorIdx = -1;

                    const rowStyle = 'padding:4px 16px;cursor:pointer;display:flex;align-items:center;font-size:13px;user-select:none';

                    // Build row list for keyboard navigation
                    // Each item: { el, is_dir, name, action() }
                    rows = [];

                    // Add ".." entry at top (unless at root)
                    if (currentPath !== '/') {
                        const dotdot = doc.createElement('div');
                        dotdot.style.cssText = rowStyle;
                        const ddIcon = doc.createElement('span');
                        ddIcon.style.cssText = 'margin-right:8px;font-size:14px;width:18px;text-align:center;flex-shrink:0';
                        ddIcon.textContent = '\uD83D\uDCC1';
                        const ddName = doc.createElement('span');
                        ddName.textContent = '..';
                        dotdot.appendChild(ddIcon);
                        dotdot.appendChild(ddName);
                        listContainer.appendChild(dotdot);
                        rows.push({ el: dotdot, is_dir: true, name: '..', action: () => {
                            const parent = currentPath.replace(/\/[^/]+\/?$/, '') || '/';
                            loadDir(parent);
                        }});
                    }

                    if (filtered.length === 0) {
                        const emptyMsg = doc.createElement('div');
                        emptyMsg.style.cssText = 'padding:20px;text-align:center;color:var(--text-secondary, #b0b3b8);font-size:13px';
                        emptyMsg.textContent = txt.empty;
                        listContainer.appendChild(emptyMsg);
                    }

                    filtered.forEach(entry => {
                        const row = doc.createElement('div');
                        row.style.cssText = rowStyle;

                        const icon = doc.createElement('span');
                        icon.style.cssText = 'margin-right:8px;font-size:14px;width:18px;text-align:center;flex-shrink:0';
                        icon.textContent = entry.is_dir ? '\uD83D\uDCC1' : '\uD83D\uDCC4';

                        const name = doc.createElement('span');
                        name.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
                        name.textContent = entry.name;

                        row.appendChild(icon);
                        row.appendChild(name);

                        if (entry.is_dir) {
                            rows.push({ el: row, is_dir: true, name: entry.name, action: () => {
                                loadDir(joinPath(currentPath, entry.name));
                            }});
                        } else {
                            rows.push({ el: row, is_dir: false, name: entry.name, action: () => {
                                finish(joinPath(currentPath, entry.name));
                            }});
                            row.ondblclick = () => {
                                finish(joinPath(currentPath, entry.name));
                            };
                        }

                        listContainer.appendChild(row);
                    });

                    // Attach mouse events to all rows
                    rows.forEach((item, idx) => {
                        item.el.onmouseenter = () => {
                            if (idx !== cursorIdx) item.el.style.background = HOV_BG;
                        };
                        item.el.onmouseleave = () => {
                            if (idx !== cursorIdx) item.el.style.background = '';
                        };
                        item.el.onclick = () => {
                            overlay.focus();
                            if (item.is_dir) {
                                item.action();
                            } else {
                                // File: select
                                setCursor(idx);
                                selectedFileName = item.name;
                                if (doc.getElementById('_wfd_selected_file')) {
                                    doc.getElementById('_wfd_selected_file').textContent = item.name;
                                }
                            }
                        };
                    });

                } catch (err) {
                    listContainer.innerHTML = '<div style="padding:20px;text-align:center;color:var(--error, #ef4444);font-size:13px">' + escapeHtml(String(err)) + '</div>';
                }
            }

            homeBtn.onclick = () => loadDir('~');

            pathInput.onkeydown = (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    loadDir(pathInput.value.trim() || '~');
                    overlay.focus();
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    e.stopPropagation();
                    overlay.focus();
                }
            };

            // Keyboard navigation - attach to overlay to prevent parent scroll
            overlay.tabIndex = -1;
            overlay.style.outline = 'none';

            function onKey(e) {
                // Skip if path input is focused
                if (document.activeElement === pathInput || doc.activeElement === pathInput) return;

                if (e.key === 'Tab') {
                    // Trap focus inside dialog
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    const focusable = [homeBtn, pathInput, cancelBtn, selectBtn].filter(el => el);
                    const idx = focusable.indexOf(doc.activeElement);
                    const next = e.shiftKey
                        ? (idx <= 0 ? focusable.length - 1 : idx - 1)
                        : (idx >= focusable.length - 1 ? 0 : idx + 1);
                    focusable[next].focus();
                    return;
                }

                if (e.key === 'Escape') {
                    e.preventDefault();
                    e.stopPropagation();
                    finish(null);
                    return;
                }

                if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'PageDown' || e.key === 'PageUp' || e.key === 'Home' || e.key === 'End') {
                    e.preventDefault();
                    e.stopPropagation();
                    if (rows.length === 0) return;
                    const pageSize = Math.max(1, Math.floor(listContainer.clientHeight / 26));
                    let next;
                    if (e.key === 'ArrowDown')  next = Math.min(cursorIdx + 1, rows.length - 1);
                    else if (e.key === 'ArrowUp')   next = Math.max(cursorIdx - 1, 0);
                    else if (e.key === 'PageDown')  next = Math.min(cursorIdx + pageSize, rows.length - 1);
                    else if (e.key === 'PageUp')    next = Math.max(cursorIdx - pageSize, 0);
                    else if (e.key === 'Home')      next = 0;
                    else                            next = rows.length - 1;
                    setCursor(next);
                    // Update file selection for file mode
                    if (!isDir && rows[cursorIdx]) {
                        if (!rows[cursorIdx].is_dir) {
                            selectedFileName = rows[cursorIdx].name;
                            if (doc.getElementById('_wfd_selected_file')) {
                                doc.getElementById('_wfd_selected_file').textContent = rows[cursorIdx].name;
                            }
                        } else {
                            selectedFileName = '';
                            if (doc.getElementById('_wfd_selected_file')) {
                                doc.getElementById('_wfd_selected_file').textContent = '';
                            }
                        }
                    }
                } else if (e.key === 'Enter') {
                    e.preventDefault();
                    e.stopPropagation();
                    if (cursorIdx >= 0 && cursorIdx < rows.length) {
                        const item = rows[cursorIdx];
                        if (item.is_dir) {
                            item.action();
                        } else {
                            finish(joinPath(currentPath, item.name));
                        }
                    }
                }
            }
            // Register keydown on both: iframe window AND parent doc
            // (iframe keeps focus while overlay is in parent document)
            window.addEventListener('keydown', onKey, true);
            if (window.isInIframe) {
                doc.addEventListener('keydown', onKey, true);
            }

            doc.body.appendChild(overlay);

            // Helper: escapeHtml fallback for parent doc context
            function escapeHtml(text) {
                if (!text) return '';
                const d = doc.createElement('div');
                d.textContent = text;
                return d.innerHTML;
            }

            // Start at home directory
            loadDir('~');
        });
    };

    // Signal that callPython is now available
    window.callPythonReady = true;
    window.dispatchEvent(new CustomEvent('callPythonReady'));

})();
