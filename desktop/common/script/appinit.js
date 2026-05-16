// ============================================================================
// Skillup - Application Initialization
// ============================================================================
// This file is the single entry point for all Skillup applications.
// It handles:
//   - Execution mode detection (Desktop iframe vs Web browser)
//   - Dynamic resource loading (Bootstrap, theme CSS, common JS)
//   - Theme management system
//
// Usage in HTML files:
//   <!-- Desktop iframe mode -->
//   <script src="/common/script/appinit.js"></script>
//
//   <!-- Web browser mode (relative path from app/*/web/*.html) -->
//   <script src="../../../../web/common/script/appinit.js"></script>
// ============================================================================

(function() {
    'use strict';

    // ========================================================================
    // Environment Detection
    // ========================================================================
    window.isInIframe = window.parent !== window;
    // Qt standalone window: explicitly flagged via ?standalone=1 URL param
    const _urlParams = new URLSearchParams(window.location.search);
    window.isInQtWindow = !window.isInIframe && _urlParams.get('standalone') === '1';
    window.isInWebBrowser = !window.isInIframe && !window.isInQtWindow;

    // Determine base path for resources
    // Qt standalone window uses HTTP server just like iframe mode
    const basePath = (window.isInIframe || window.isInQtWindow) ? '/' : '../../../../web/';

    const modeStr = window.isInIframe ? 'Desktop iframe' : (window.isInQtWindow ? 'Qt standalone window' : 'Web browser');
    console.log(`[Skillup AppInit] Mode: ${modeStr}`);
    console.log(`[Skillup AppInit] Base path: ${basePath}`);

    // ========================================================================
    // App Context (GUID with random prefix for security)
    // ========================================================================
    window.skillupAppId = null;
    window.skillupAppGuid = null;

    // ========================================================================
    // Resource Loading Utilities
    // ========================================================================
    function loadCSS(href, attributes = {}) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;

        // Apply additional attributes
        Object.keys(attributes).forEach(key => {
            link.setAttribute(key, attributes[key]);
        });

        document.head.appendChild(link);
        console.log(`[Skillup AppInit] Loaded CSS: ${href}`);
        return link;
    }

    function loadScript(src, attributes = {}) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;

            // Apply additional attributes
            Object.keys(attributes).forEach(key => {
                script.setAttribute(key, attributes[key]);
            });

            script.onload = () => {
                console.log(`[Skillup AppInit] Loaded script: ${src}`);
                resolve();
            };
            script.onerror = () => {
                console.error(`[Skillup AppInit] Failed to load script: ${src}`);
                reject(new Error(`Failed to load script: ${src}`));
            };

            document.head.appendChild(script);
        });
    }

    // ========================================================================
    // Theme Management System
    // ========================================================================
    window.SkillupTheme = {
        current: 'default',
        themeLink: null,

        /**
         * Set the current theme
         * @param {string} theme - Theme name (e.g., 'default', 'white')
         */
        setTheme(theme) {
            // Remove existing theme CSS
            if (this.themeLink) {
                this.themeLink.remove();
            }

            // Load new theme CSS
            this.themeLink = loadCSS(
                `${basePath}common/style/${theme}.css`,
                { 'data-theme-css': 'true' }
            );

            this.current = theme;

            console.log(`[Skillup AppInit] Theme set to: ${theme}`);
        },

        /**
         * Initialize theme from saved preference or default
         * In iframe mode, theme is controlled by desktop
         * In web browser mode, use localStorage
         */
        init() {
            let savedTheme = 'default';

            if (window.isInIframe) {
                // In iframe mode, try to get theme from parent's theme-select
                // This prevents flicker by loading correct theme immediately
                try {
                    const parentThemeSelect = window.parent.document.getElementById('theme-select');
                    if (parentThemeSelect && parentThemeSelect.value) {
                        savedTheme = parentThemeSelect.value;
                        console.log('[Skillup AppInit] Using parent theme:', savedTheme);
                    }
                } catch (e) {
                    // Cross-origin or access denied - will use postMessage later
                    console.log('[Skillup AppInit] Cannot access parent theme, will use postMessage');
                }
            } else if (window.isInWebBrowser) {
                // In web browser mode, use localStorage
                try {
                    savedTheme = localStorage.getItem('skillup-theme') || 'default';
                } catch (e) {
                    console.warn('[Skillup AppInit] Could not load theme preference:', e);
                }
            }

            this.setTheme(savedTheme);
        }
    };

    // ========================================================================
    // Core Resource Loading
    // ========================================================================

    // Load Bootstrap CSS
    loadCSS(`${basePath}common/bootstrap/5.3.3/bootstrap.min.css`);

    // Initialize theme (loads default.css or saved preference)
    window.SkillupTheme.init();

    // Load Bootstrap JavaScript (async)
    loadScript(`${basePath}common/bootstrap/5.3.3/bootstrap.bundle.min.js`)
        .catch(err => console.error('[Skillup AppInit] Bootstrap JS load error:', err));

    // Note: common.js is loaded AFTER GUID initialization to ensure
    // window.skillupInitialized is set before common.js checks it

    // ========================================================================
    // App GUID Initialization
    // ========================================================================

    /**
     * Extract app ID from URL path
     * Expected: /app/{appId}/file.html
     */
    function getAppIdFromPath() {
        const path = window.location.pathname;
        const match = path.match(/\/app\/([^\/]+)\//);
        return match ? match[1] : null;
    }

    /**
     * Request randomized GUID from Python backend
     * This prevents cross-app attacks by making GUIDs session-specific
     */
    async function initializeAppGuid() {
        window.skillupAppId = getAppIdFromPath();
        if (!window.skillupAppId) {
            console.warn('[Skillup AppInit] Could not extract app ID from path');
            return;
        }

        console.log('[Skillup AppInit] App ID:', window.skillupAppId);

        if (window.isInWebBrowser) {
            // Web browser mode - use mock GUID
            window.skillupAppGuid = 'mock_' + window.skillupAppId;
            console.log('[Skillup AppInit] Web browser mode - using mock GUID');
            return;
        }

        // Desktop mode - request randomized GUID from Python
        try {
            const response = await fetch('/api/init_app_guid', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    app_id: window.skillupAppId,
                    path: window.location.pathname
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.success && data.randomized_guid) {
                window.skillupAppGuid = data.randomized_guid;
                console.log('[Skillup AppInit] Randomized GUID received:', window.skillupAppGuid);
            } else {
                throw new Error(data.error || 'Failed to get GUID');
            }

        } catch (error) {
            console.error('[Skillup AppInit] Failed to initialize GUID:', error);
            // Fallback to app ID (not secure, but allows basic functionality)
            window.skillupAppGuid = window.skillupAppId;
        }
    }

    // ========================================================================
    // Initialization Complete
    // ========================================================================

    // Initialize app GUID before marking as complete
    initializeAppGuid().then(() => {
        console.log('[Skillup AppInit] GUID initialization complete');
        window.skillupInitialized = true;

        // Dispatch event for other scripts
        window.dispatchEvent(new CustomEvent('skillupInitialized', {
            detail: {
                appId: window.skillupAppId,
                appGuid: window.skillupAppGuid
            }
        }));

        // Load QWebChannel if in desktop iframe mode (not in standalone window)
        // Standalone window uses REST API via GUID routing - QWebChannel bypasses GUID and breaks routing
        if (!window.isInWebBrowser && !window.isInQtWindow && typeof qt !== 'undefined') {
            console.log('[Skillup AppInit] Loading QWebChannel...');
            return loadScript('qrc:///qtwebchannel/qwebchannel.js');
        } else {
            return Promise.resolve();
        }
    }).then(() => {
        // Load common application JavaScript AFTER QWebChannel is loaded
        return loadScript(`${basePath}common/script/common.js`);
    }).then(() => {
        console.log('[Skillup AppInit] Initialization complete');
    }).catch(err => {
        console.error('[Skillup AppInit] Initialization error:', err);
    });

})();
