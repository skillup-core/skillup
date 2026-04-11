"""
Skillup WebUI Engine

Common web engine for apps and desktop.
Provides HTTP server, Qt WebEngine integration, and message passing.
"""

import os
import sys
import json
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from contextlib import contextmanager
from typing import Dict, Any, Callable, Optional, Tuple

# Import configuration functions from separate config module
from .config import (
    get_desktop_config_path,
    get_app_config_path,
    load_config,
    save_config
)


# ============================================================================
# Utility Functions
# ============================================================================

def find_free_port() -> int:
    """Find a free port on localhost"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def load_static_files(web_dir: str) -> Dict[str, Tuple[bytes, str]]:
    """
    Load all static files from web directory into memory.

    Args:
        web_dir: Path to web directory

    Returns:
        dict: {relative_path: (content_bytes, content_type)}
    """
    static_files = {}

    if not os.path.exists(web_dir):
        return static_files

    content_types = {
        '.js': 'application/javascript',
        '.css': 'text/css',
        '.map': 'application/json',
        '.html': 'text/html',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.ttf': 'font/ttf',
        '.eot': 'application/vnd.ms-fontobject',
        '.json': 'application/json'
    }

    binary_extensions = {'.png', '.jpg', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.eot'}

    for root, dirs, files in os.walk(web_dir):
        for filename in files:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, web_dir)

            ext = os.path.splitext(filename)[1].lower()
            content_type = content_types.get(ext, 'application/octet-stream')

            try:
                if ext in binary_extensions:
                    with open(filepath, 'rb') as f:
                        content = f.read()
                else:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read().encode('utf-8')

                key = rel_path.replace(os.sep, '/')
                static_files[key] = (content, content_type)
            except Exception:
                pass

    return static_files


# ============================================================================
# ANSI Color Codes
# ============================================================================

class Color:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    GRAY = '\033[90m'
    RESET = '\033[0m'


# Import log function from lib.log
from lib.log import log


# ============================================================================
# WebUI Engine
# ============================================================================

class WebUIEngine:
    """
    Common web engine for apps and desktop.

    Provides:
    - HTTP server for serving HTML/CSS/JS
    - Qt WebEngine integration
    - Message passing between Python and JavaScript
    - Configuration management
    """

    def __init__(self, app_id: Optional[str] = None, title: str = "Skillup"):
        """
        Initialize WebUI Engine.

        Args:
            app_id: App ID for configuration (None for desktop)
            title: Window title
        """
        self.app_id = app_id
        self.title = title
        self.server = None
        self.port = None
        self.static_files = {}
        self.message_handlers = {}
        self.qt_app = None
        self.view = None
        self.bridge = None  # QWebChannel bridge
        self._lock = threading.Lock()
        self._status = {}

    def register_handler(self, handler_name: str, handler: Callable):
        """
        Register a message handler for JavaScript->Python communication.

        Args:
            handler_name: Handler name to handle
            handler: Callback function(data) -> response
        """
        self.message_handlers[handler_name] = handler

    def callJS(self, action: str, data: Dict[str, Any]):
        """
        Send a message to JavaScript.

        If a detached window page is active, runs JS directly on that page via
        runJavaScript() so that the correct window context receives the call.
        Otherwise uses QWebChannel bridge signal (fast path) or pending messages.

        Args:
            action: Action name
            data: Data to send
        """
        import json

        # JS snippet: call function directly if in window scope,
        # or forward to visible iframe via postMessage (for detached desktop.html pages).
        args_json = json.dumps(json.dumps(data))
        js = (f"(function(){{var _fn='{action}',_args=JSON.parse({args_json});"
              f"if(typeof window[_fn]==='function'){{window[_fn](_args);}}"
              f"else{{var _if=document.querySelector('#app-content iframe.iframe-visible')||document.querySelector('iframe');"
              f"if(_if&&_if.contentWindow){{_if.contentWindow.postMessage({{action:'callJS',functionName:_fn,args:_args}},'*');}}"
              f"else{{console.warn('[callJS] no target for:',_fn);}}"
              f"}}}})()")

        # If detached window(s) are active, run JS directly in those pages (main thread via signal).
        detached_pages = getattr(self, '_detached_pages', {})
        detached_page = getattr(self, '_detached_page', None)
        popup_windows = getattr(self, '_popup_windows', {})

        if detached_pages and self.bridge:
            for uk in list(detached_pages.keys()):
                self.bridge.runJSInPopup.emit(uk, js)
            return

        # Legacy: single _detached_page (no _detached_pages dict)
        if detached_page is not None and self.bridge:
            self.bridge.runJSInPopup.emit('__detached__', js)
            return

        # If popup windows exist, run JS in all visible popups and skip the bridge
        # signal (which would incorrectly target the main desktop window).
        if self.bridge and popup_windows:
            for url_key in list(popup_windows):
                self.bridge.runJSInPopup.emit(url_key, js)
            return

        # Use QWebChannel bridge signal (desktop.html receives and forwards to visible iframe)
        if self.bridge:
            try:
                self.bridge.callJS.emit(action, json.dumps(data))
                return
            except Exception:
                pass  # Fallback to pending messages

        # Fallback: Store in pending messages for SSE
        with self._lock:
            self._status['pending_messages'] = self._status.get('pending_messages', [])
            self._status['pending_messages'].append({'action': action, 'data': data})

    def get_config(self, key: str, default=None):
        """Get configuration value"""
        if self.app_id:
            config_path = get_app_config_path(self.app_id)
        else:
            config_path = get_desktop_config_path()

        config = load_config(config_path)
        return config.get(key, default)

    def set_config(self, key: str, value):
        """Set configuration value"""
        if self.app_id:
            config_path = get_app_config_path(self.app_id)
        else:
            config_path = get_desktop_config_path()

        save_config(config_path, {key: value})

    def load_html(self, html_path: str):
        """
        Load HTML file in the web view.

        Args:
            html_path: Path to HTML file
        """
        if self.view:
            try:
                from PySide2.QtCore import QUrl  # type: ignore
            except ImportError:
                from PySide6.QtCore import QUrl  # type: ignore
            url = f"http://localhost:{self.port}/{html_path}"
            self.view.load(QUrl(url))

    def add_static_files(self, web_dir: str, prefix: str = ""):
        """
        Add static files from a directory.

        Args:
            web_dir: Path to web directory
            prefix: URL prefix for files
        """
        files = load_static_files(web_dir)
        for key, value in files.items():
            if prefix:
                self.static_files[f"{prefix}/{key}"] = value
            else:
                self.static_files[key] = value

    def create_handler(self, index_html_generator: Optional[Callable] = None):
        """
        Create HTTP request handler class.

        Args:
            index_html_generator: Function to generate index.html content

        Returns:
            Handler class
        """
        engine = self

        class WebUIHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                parsed_path = urlparse(self.path)
                path = parsed_path.path

                # Serve qwebchannel.js from Qt installation
                if path == '/qtwebchannel/qwebchannel.js':
                    # Try to find qwebchannel.js in Qt installation
                    qwebchannel_content = None
                    try:
                        # Try PySide2 first
                        try:
                            from PySide2.QtCore import QLibraryInfo  # type: ignore
                            qt_data_path = QLibraryInfo.location(QLibraryInfo.DataPath)
                        except (ImportError, AttributeError):
                            # PySide6
                            from PySide6.QtCore import QLibraryInfo  # type: ignore
                            qt_data_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.DataPath)

                        qwebchannel_path = os.path.join(qt_data_path, 'resources', 'qtwebchannel', 'qwebchannel.js')
                        if os.path.exists(qwebchannel_path):
                            with open(qwebchannel_path, 'r', encoding='utf-8') as f:
                                qwebchannel_content = f.read()
                    except Exception:
                        pass

                    if qwebchannel_content:
                        self.send_response(200)
                        self.send_header('Content-type', 'application/javascript')
                        self.send_header('Cache-Control', 'max-age=3600')
                        self.end_headers()
                        try:
                            self.wfile.write(qwebchannel_content.encode('utf-8'))
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return
                    else:
                        # Fallback: minimal inline implementation
                        self.send_response(200)
                        self.send_header('Content-type', 'application/javascript')
                        self.send_header('Cache-Control', 'max-age=3600')
                        self.end_headers()
                        # Minimal shim that uses qrc:// directly
                        fallback_js = "console.warn('Using qrc:// fallback - load from qrc:///qtwebchannel/qwebchannel.js instead');"
                        try:
                            self.wfile.write(fallback_js.encode('utf-8'))
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return

                # Handle SSE streams
                if path.startswith('/sse/'):
                    action = path[5:]  # Remove '/sse/'

                    if action in engine.message_handlers:
                        self.send_response(200)
                        self.send_header('Content-type', 'text/event-stream')
                        self.send_header('Cache-Control', 'no-cache')
                        self.send_header('Connection', 'keep-alive')
                        self.end_headers()

                        try:
                            last_log_count = 0

                            # Send initial state immediately
                            result = engine.message_handlers[action]({'last_log_count': last_log_count, 'wait': False})
                            sse_data = f"data: {json.dumps(result)}\n\n"
                            self.wfile.write(sse_data.encode('utf-8'))
                            self.wfile.flush()

                            if 'total_log_count' in result:
                                last_log_count = result['total_log_count']

                            # Event-driven loop: wait for state changes
                            while result.get('running', False):
                                # Wait for next update (blocking with timeout)
                                result = engine.message_handlers[action]({'last_log_count': last_log_count, 'wait': True})

                                # Send SSE message
                                sse_data = f"data: {json.dumps(result)}\n\n"
                                self.wfile.write(sse_data.encode('utf-8'))
                                self.wfile.flush()

                                # Update last log count
                                if 'total_log_count' in result:
                                    last_log_count = result['total_log_count']

                            # Send final state with results
                            final_result = engine.message_handlers[action]({'last_log_count': last_log_count, 'wait': False})
                            sse_data = f"data: {json.dumps(final_result)}\n\n"
                            self.wfile.write(sse_data.encode('utf-8'))
                            self.wfile.flush()

                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return

                # Serve index HTML
                if path == '/' or path == '/index.html':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()

                    if index_html_generator:
                        html_content = index_html_generator()
                    else:
                        html_content = "<html><body><h1>No content</h1></body></html>"

                    try:
                        self.wfile.write(html_content.encode('utf-8'))
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return

                # Serve static files
                file_key = path.lstrip('/')
                if file_key in engine.static_files:
                    content, content_type = engine.static_files[file_key]
                    self.send_response(200)
                    self.send_header('Content-type', content_type)
                    self.send_header('Cache-Control', 'max-age=3600')
                    self.end_headers()
                    try:
                        self.wfile.write(content)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return

                # 404
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                parsed_path = urlparse(self.path)
                path = parsed_path.path

                # Handle API calls
                if path.startswith('/api/'):
                    # Parse request body
                    content_length = int(self.headers.get('Content-Length', 0))
                    if content_length > 0:
                        body = self.rfile.read(content_length)
                        try:
                            data = json.loads(body.decode('utf-8'))
                        except json.JSONDecodeError:
                            data = {}
                    else:
                        data = {}

                    # Check for app-specific callPython route: /api/callPython/<guid>/<handler_name>
                    if path.startswith('/api/callPython/'):
                        # Extract guid and handler_name from path
                        route_parts = path[16:].split('/', 1)  # Remove '/api/callPython/'
                        if len(route_parts) == 2:
                            guid, handler_name = route_parts
                            # Add route info to data for handler
                            data['_route_info'] = {'guid': guid, 'handler_name': handler_name}
                            # Use special 'callPython' handler
                            handler_name = 'callPython'
                        else:
                            self.send_response(400)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({'error': 'Invalid callPython route'}).encode('utf-8'))
                            return
                    else:
                        # Regular API call: /api/<handler_name>
                        handler_name = path[5:]  # Remove '/api/'

                    if handler_name in engine.message_handlers:
                        try:
                            result = engine.message_handlers[handler_name](data)
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps(result or {}).encode('utf-8'))
                        except Exception as e:
                            self.send_response(500)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
                    else:
                        self.send_response(404)
                        self.end_headers()
                    return

                self.send_response(404)
                self.end_headers()

        return WebUIHandler

    def start_server(self, handler_class=None, index_html_generator: Optional[Callable] = None):
        """
        Start HTTP server.

        Args:
            handler_class: Custom handler class (optional)
            index_html_generator: Function to generate index.html
        """
        self.port = find_free_port()

        if handler_class is None:
            handler_class = self.create_handler(index_html_generator)

        self.server = HTTPServer(('localhost', self.port), handler_class)

        server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        server_thread.start()

        return f"http://localhost:{self.port}/"

    def create_bridge(self):
        """
        Create QWebChannel bridge for direct JavaScript ↔ Python communication.

        Returns:
            PythonBridge instance
        """
        # Try PySide2 first, fallback to PySide6
        try:
            from PySide2.QtCore import QObject, Slot, Signal  # type: ignore
        except ImportError:
            try:
                from PySide6.QtCore import QObject, Slot, Signal  # type: ignore
            except ImportError:
                log("error", message="PySide2 or PySide6 is required for QWebChannel")
                return None

        # Create PythonBridge class dynamically
        engine = self

        class PythonBridge(QObject):
            """Bridge for QWebChannel - enables direct JavaScript ↔ Python calls"""

            # Signals: Python → JavaScript events
            messageReceived = Signal(str, str)  # (type, message)
            callJS = Signal(str, str)  # (function_name, json_args) - Python → JavaScript function call
            openWindow = Signal(str, str, str)  # (url, title, mode) - open new window from main thread
            focusWindow = Signal(str)  # (url_prefix) - focus existing popup window
            detachToNewWindow = Signal(str, str, str)  # (url_key, title, desktop_url)
            runJSInPopup = Signal(str, str)  # (url_key, js_code) - run JS in a popup window page

            def __init__(self):
                super().__init__()

            @Slot(str, str, result=str)
            def callPython(self, action, json_data):
                """
                Main entry point from JavaScript.

                Args:
                    action: Handler name (e.g., 'verify', 'getInfo')
                    json_data: JSON string of data from JavaScript

                Returns:
                    JSON string of result
                """
                import json

                try:
                    # Parse JSON data
                    try:
                        data = json.loads(json_data) if json_data else {}
                    except json.JSONDecodeError:
                        data = {}

                    # Route to handler
                    if action in engine.message_handlers:
                        result = engine.message_handlers[action](data)
                        return json.dumps(result or {})
                    else:
                        return json.dumps({'error': f'Unknown handler: {action}'})

                except Exception as e:
                    return json.dumps({'error': str(e)})

            @Slot(str)
            def log(self, message):
                """Log message from JavaScript to Python console"""
                from lib.log import log as log_func
                log_func("info", message=message, tag="js")

        return PythonBridge()

    def run_qt(self, url: Optional[str] = None):
        """
        Run Qt WebEngine with the given URL.

        Args:
            url: URL to load (default: server URL)
        """
        # Try PySide2 first, fallback to PySide6
        pyside_version = None
        try:
            from PySide2.QtWidgets import QApplication  # type: ignore
            from PySide2.QtWebEngineWidgets import QWebEngineView  # type: ignore
            from PySide2.QtCore import QUrl, qInstallMessageHandler  # type: ignore
            from PySide2.QtGui import QFontDatabase  # type: ignore
            from PySide2.QtWebChannel import QWebChannel  # type: ignore
            pyside_version = 2
        except ImportError:
            try:
                from PySide6.QtWidgets import QApplication  # type: ignore
                from PySide6.QtWebEngineWidgets import QWebEngineView  # type: ignore
                from PySide6.QtCore import QUrl, qInstallMessageHandler  # type: ignore
                from PySide6.QtGui import QFontDatabase  # type: ignore
                from PySide6.QtWebChannel import QWebChannel  # type: ignore
                pyside_version = 6
            except ImportError:
                log("error", message="PySide2 or PySide6 is required for desktop mode")
                sys.exit(1)

        # Set up Qt environment
        os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
        os.environ['QT_QUICK_BACKEND'] = 'software'
        os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu'
        os.environ['QT_LOGGING_RULES'] = 'default.warning=false'
        os.environ['QT_QPA_PLATFORMTHEME'] = ''
        os.environ['QT_STYLE_OVERRIDE'] = 'Fusion'
        os.environ['QT_IM_MODULE'] = 'ibus'
        if 'XMODIFIERS' not in os.environ:
            os.environ['XMODIFIERS'] = '@im=ibus'

        # Detect ibus version for CentOS 7.4 workaround (ibus <= 1.5.3)
        ibus_needs_restart = False
        if sys.platform == 'linux':
            try:
                import subprocess as _sp
                _ibus_out = _sp.check_output(['ibus', 'version'], stderr=_sp.DEVNULL, timeout=3).decode().strip()
                _ibus_ver_str = _ibus_out.split()[-1] if _ibus_out else ''
                _ibus_ver = tuple(int(x) for x in _ibus_ver_str.split('.')) if _ibus_ver_str else (0,)
                if _ibus_ver <= (1, 5, 3):
                    ibus_needs_restart = True
            except Exception:
                pass

        # Shared state: last IME mode reported by JavaScript
        ibus_last_ime_active = [False]

        # Flag to suppress ibus restart during X11 inject (e.g. F5 debug).
        # When inject activates CIW window, Qt fires ApplicationInactive which
        # would trigger ibus restart, disrupting the X11 key injection.
        self._ibus_suppress_restart = False
        self._ibus_restart_pending = False

        @contextmanager
        def _ibus_suppress_ctx():
            self._ibus_suppress_restart = True
            self._ibus_restart_pending = False
            try:
                yield
            finally:
                self._ibus_suppress_restart = False
                if self._ibus_restart_pending:
                    self._ibus_restart_pending = False
                    try:
                        import subprocess as _sp
                        _sp.Popen(['ibus', 'restart'], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                    except Exception:
                        pass
        self.ibus_suppress = _ibus_suppress_ctx

        def handle_ibus_notify_korean(data):
            ibus_last_ime_active[0] = bool(data.get('ime_active', False))
            return {'success': True}

        # Always register handlers (JS calls unconditionally); only ibus_needs_restart
        # gates the actual restart logic in applicationStateChanged / restart_request.
        self.register_handler('ibus_notify_korean', handle_ibus_notify_korean)
        self.register_handler('ibus_restart_request', lambda data: {'success': True})

        # Set platform-specific QT_QPA_PLATFORM
        if sys.platform == 'linux':
            os.environ['QT_QPA_PLATFORM'] = 'xcb'
        elif sys.platform == 'win32':
            os.environ['QT_QPA_PLATFORM'] = 'windows'
        elif sys.platform == 'darwin':
            os.environ['QT_QPA_PLATFORM'] = 'cocoa'
        # Other platforms: let Qt auto-detect

        qInstallMessageHandler(lambda mode, context, message: None)

        engine_ref = self

        # Custom WebEngineView
        class CustomWebEngineView(QWebEngineView):
            def contextMenuEvent(self, event):
                pass

            def focusInEvent(self, event):
                super().focusInEvent(event)
                # Reset IM context on focus-in to restore Korean input
                # after switching back from GTK apps (gedit, gnome-terminal)
                app = QApplication.instance()
                if app and app.inputMethod():
                    app.inputMethod().reset()

            def closeEvent(self, event):
                # If this is the main window, close all popup windows and quit
                if self is engine_ref.view:
                    if hasattr(engine_ref, '_popup_windows'):
                        for w in list(engine_ref._popup_windows.values()):
                            try:
                                w.close()
                            except Exception:
                                pass
                    super().closeEvent(event)
                    engine_ref.qt_app.quit()
                else:
                    # Popup window closed: remove from tracking dict
                    if hasattr(engine_ref, '_popup_windows'):
                        stale = [k for k, v in engine_ref._popup_windows.items() if v is self]
                        for k in stale:
                            del engine_ref._popup_windows[k]
                    super().closeEvent(event)

            def dragEnterEvent(self, event):
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                else:
                    super().dragEnterEvent(event)

            def dragMoveEvent(self, event):
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                else:
                    super().dragMoveEvent(event)

            def dropEvent(self, event):
                mime = event.mimeData()
                if mime.hasUrls():
                    event.acceptProposedAction()
                    paths = [url.toLocalFile() for url in mime.urls() if url.toLocalFile()]
                    if paths:
                        import json as _json
                        pos = event.pos()
                        script = """
(function() {{
    var paths = {paths};
    var x = {x}, y = {y};
    var target = document.elementFromPoint(x, y) || document.body;
    target.dispatchEvent(new CustomEvent('nativeFileDrop', {{
        detail: {{ paths: paths, x: x, y: y }},
        bubbles: true, cancelable: false
    }}));
    Array.from(document.querySelectorAll('iframe')).forEach(function(fr) {{
        try {{ fr.contentWindow.postMessage({{ type: 'nativeFileDrop', paths: paths }}, '*'); }} catch(e) {{}}
    }});
}})();
""".format(paths=_json.dumps(paths), x=pos.x(), y=pos.y())
                        self.page().runJavaScript(script)
                else:
                    super().dropEvent(event)

        # Enable console message logging
        if pyside_version == 2:
            from PySide2.QtWebEngineWidgets import QWebEnginePage  # type: ignore
        else:
            from PySide6.QtWebEngineCore import QWebEnginePage  # type: ignore

        class ConsolePage(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
                # Map Qt console level to message type
                # level is an enum, need to compare with enum values
                if level == QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
                    msg_type = "info"
                elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
                    msg_type = "warn"
                elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    msg_type = "error"
                else:
                    # Fallback to info for unknown levels
                    msg_type = "info"

                # Format: [info ][web] message (or [error][web], [warn ][web])
                location = f" (line {lineNumber})" if lineNumber else ""
                log(msg_type, message=f"{message}{location}", tag="web")


        self.qt_app = QApplication(sys.argv)

        # ibus 1.5.3 workaround: GTK apps steal ibus input context from Qt.
        # On focus loss with Korean active, restart ibus immediately.
        # On focus loss with English active, defer restart until user presses
        # a Korean toggle key (Shift+Space / Hangul), triggered from JS.
        if ibus_needs_restart:
            try:
                from PySide2.QtCore import Qt as _Qt  # type: ignore
            except ImportError:
                from PySide6.QtCore import Qt as _Qt  # type: ignore

            ibus_focus_lost = [False]

            def _on_app_state_changed(state):
                if state == _Qt.ApplicationInactive:
                    ibus_focus_lost[0] = True
                    if ibus_last_ime_active[0]:
                        if self._ibus_suppress_restart:
                            self._ibus_restart_pending = True
                        else:
                            try:
                                import subprocess as _sp
                                _sp.Popen(['ibus', 'restart'], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                            except Exception:
                                pass

            def handle_ibus_restart_request(data):
                if ibus_focus_lost[0]:
                    try:
                        import subprocess as _sp
                        _sp.Popen(['ibus', 'restart'], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                        ibus_focus_lost[0] = False
                    except Exception:
                        pass
                return {'success': True}

            self.register_handler('ibus_restart_request', handle_ibus_restart_request)
            self.qt_app.applicationStateChanged.connect(_on_app_state_changed)

        # Load fonts
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)

        from glob import glob as find_files
        font_extensions = ['*.ttf', '*.otf', '*.TTF', '*.OTF']
        for extension in font_extensions:
            for font_path in find_files(os.path.join(parent_dir, '**', extension), recursive=True):
                try:
                    QFontDatabase.addApplicationFont(font_path)
                except Exception:
                    pass

        self.view = CustomWebEngineView()

        # Set custom page with console logging
        console_page = ConsolePage(self.view)
        self.view.setPage(console_page)

        self.view.setWindowTitle(self.title)
        self.view.resize(1000, 720)

        # Set minimum window size to prevent resizing to (0,0)
        try:
            from PySide2.QtCore import QSize  # type: ignore
        except ImportError:
            from PySide6.QtCore import QSize  # type: ignore
        self.view.setMinimumSize(QSize(1000, 720))

        # Notify callback if set (e.g., for setting dialog parent)
        if hasattr(self, 'on_view_created') and callable(self.on_view_created):
            self.on_view_created(self.view)

        # Enable developer tools (F12 or right-click -> Inspect)
        if pyside_version == 2:
            from PySide2.QtWebEngineWidgets import QWebEngineSettings  # type: ignore
        else:
            from PySide6.QtWebEngineCore import QWebEngineSettings  # type: ignore

        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        # Enable developer tools
        try:
            if hasattr(QWebEngineSettings.WebAttribute, 'DeveloperExtrasEnabled'):
                settings.setAttribute(QWebEngineSettings.WebAttribute.DeveloperExtrasEnabled, True)
        except Exception:
            pass

        # Set up QWebChannel for direct JavaScript ↔ Python communication
        self.bridge = self.create_bridge()
        if self.bridge:
            channel = QWebChannel(self.view.page())
            channel.registerObject('bridge', self.bridge)
            self.view.page().setWebChannel(channel)
            log("info", message="QWebChannel enabled for fast JavaScript <-> Python communication", tag="qt")

            # Connect openWindow signal to slot running in main thread
            if not hasattr(self, '_popup_windows'):
                self._popup_windows = {}  # {url_prefix: view}

            _popup_counter = [0]

            def _do_open_window(w_url, w_title, w_mode='true'):
                try:
                    new_view = CustomWebEngineView()
                    new_page = ConsolePage(new_view)
                    new_view.setPage(new_page)
                    new_view.setWindowTitle(w_title)
                    new_view.resize(1200, 800)
                    new_view.setMinimumSize(QSize(600, 400))
                    # Apply same settings as main window
                    new_settings = new_view.settings()
                    new_settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                    new_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                    try:
                        if hasattr(QWebEngineSettings.WebAttribute, 'DeveloperExtrasEnabled'):
                            new_settings.setAttribute(QWebEngineSettings.WebAttribute.DeveloperExtrasEnabled, True)
                    except Exception:
                        pass
                    new_view.load(QUrl(w_url))
                    new_view.show()
                    # Track popup windows:
                    # - single/single_open mode: key by URL path for focus-reuse
                    # - true mode: key by unique counter (multiple windows allowed)
                    from urllib.parse import urlparse
                    parsed = urlparse(w_url)
                    if w_mode in ('single', 'single_open'):
                        url_key = parsed.scheme + '://' + parsed.netloc + parsed.path
                    else:
                        _popup_counter[0] += 1
                        url_key = f"__popup_{_popup_counter[0]}"
                    self._popup_windows[url_key] = new_view
                    log("info", message=f"Popup window opened: {w_url}", tag="qt")
                except Exception as e:
                    log("error", message=f"Popup window failed: {e}", tag="qt")

            def _do_focus_window(url_prefix):
                try:
                    view = self._popup_windows.get(url_prefix)
                    if view and view.isVisible():
                        view.raise_()
                        view.activateWindow()
                        log("info", message=f"Popup window focused: {url_prefix}", tag="qt")
                    else:
                        # Remove stale entry
                        if url_prefix in self._popup_windows:
                            del self._popup_windows[url_prefix]
                except Exception as e:
                    log("error", message=f"focus_window failed: {e}", tag="qt")

            def _do_detach_to_new_window(url_key, w_title, desktop_url):
                """Move current main page (with app-standalone CSS already applied) to a new
                standalone window, then reload main view with desktop URL."""
                try:
                    old_page = engine_ref.view.page()

                    # New standalone window takes the current page as-is
                    new_view = CustomWebEngineView()
                    new_view.setPage(old_page)
                    new_view.setWindowTitle(w_title)
                    new_view.resize(engine_ref.view.size())
                    new_view.setMinimumSize(QSize(600, 400))

                    # Track the detached page so callJS() can inject JS directly
                    # into this window's context via runJavaScript().
                    # Use a dict keyed by url_key to support multiple detached windows.
                    if not hasattr(engine_ref, '_detached_pages'):
                        engine_ref._detached_pages = {}
                    engine_ref._detached_pages[url_key] = old_page
                    # Legacy single-page ref: point to the most-recently-detached page
                    engine_ref._detached_page = old_page

                    new_view.show()
                    self._popup_windows[url_key] = new_view

                    # When the detached window closes, clear the page ref and notify app.
                    _orig_close = new_view.__class__.closeEvent
                    def _detached_close(self_view, event, _uk=url_key):
                        engine_ref._detached_pages.pop(_uk, None)
                        # Clear legacy ref only if it points to this page
                        if engine_ref._detached_page is old_page:
                            engine_ref._detached_page = None
                        if hasattr(engine_ref, '_on_detached_close_cb') and engine_ref._on_detached_close_cb:
                            try:
                                engine_ref._on_detached_close_cb()
                            except Exception:
                                pass
                            engine_ref._on_detached_close_cb = None
                        _orig_close(self_view, event)
                    new_view.closeEvent = _detached_close.__get__(new_view, new_view.__class__)

                    # Give main view a fresh page, re-register bridge, reload desktop
                    fresh_page = ConsolePage(engine_ref.view)
                    engine_ref.view.setPage(fresh_page)
                    channel = QWebChannel(fresh_page)
                    channel.registerObject('bridge', engine_ref.bridge)
                    fresh_page.setWebChannel(channel)
                    s = engine_ref.view.settings()
                    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                    try:
                        if hasattr(QWebEngineSettings.WebAttribute, 'DeveloperExtrasEnabled'):
                            s.setAttribute(QWebEngineSettings.WebAttribute.DeveloperExtrasEnabled, True)
                    except Exception:
                        pass
                    engine_ref.view.load(QUrl(desktop_url))
                    log("info", message=f"Detached page to new window: {url_key}", tag="qt")
                except Exception as e:
                    log("error", message=f"detach_to_new_window failed: {e}", tag="qt")

            def _do_run_js_in_popup(url_key, js_code):
                """Run JS in a specific popup window page (must run on main thread)."""
                try:
                    if url_key == '__detached__':
                        page = getattr(engine_ref, '_detached_page', None)
                        if page:
                            page.runJavaScript(js_code)
                        return
                    # Check _detached_pages dict first (multi-detach support)
                    detached_pages = getattr(engine_ref, '_detached_pages', {})
                    if url_key in detached_pages:
                        page = detached_pages[url_key]
                        if page:
                            page.runJavaScript(js_code)
                        return
                    view = self._popup_windows.get(url_key)
                    if view and view.isVisible():
                        view.page().runJavaScript(js_code)
                except Exception as e:
                    log("error", message=f"runJSInPopup failed: {e}", tag="qt")

            self.bridge.openWindow.connect(_do_open_window)
            self.bridge.focusWindow.connect(_do_focus_window)
            self.bridge.detachToNewWindow.connect(_do_detach_to_new_window)
            self.bridge.runJSInPopup.connect(_do_run_js_in_popup)

        if url is None:
            url = f"http://localhost:{self.port}/"

        # Hide window initially to prevent flicker during page load
        # Show after first paint is complete
        def on_load_finished(success):
            if success:
                self.view.show()

        self.view.loadFinished.connect(on_load_finished)
        self.view.load(QUrl(url))

        if pyside_version == 6:
            exit_code = self.qt_app.exec()
        else:
            exit_code = self.qt_app.exec_()

        # Cleanup
        if self.server:
            self.server.shutdown()
            self.server.server_close()

        return exit_code

    def detach_to_new_window(self, url: str, title: str, desktop_url: str, multi: bool = False):
        """Move main page to a new standalone window; reload main with desktop_url.

        Args:
            multi: If True, assign a unique counter-based key (allows multiple detached windows).
                   If False (default), key by URL path (single-window semantics).
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if multi:
            if not hasattr(self, '_detach_counter'):
                self._detach_counter = 0
            self._detach_counter += 1
            url_key = f"__detach_{self._detach_counter}"
        else:
            url_key = parsed.scheme + '://' + parsed.netloc + parsed.path
        if self.bridge:
            self.bridge.detachToNewWindow.emit(url_key, title, desktop_url)
        else:
            log("error", message="detach_to_new_window: bridge not available", tag="qt")

    def open_window(self, url: str, title: str = "Skillup", mode: str = "true"):
        """
        Open a new Qt WebEngine window. Emits signal to run in main thread.
        Safe to call from any thread.
        """
        log("info", message=f"open_window: emitting signal url={url}", tag="qt")
        if self.bridge:
            self.bridge.openWindow.emit(url, title, mode)
        else:
            log("error", message="open_window: bridge not available", tag="qt")

    def focus_window(self, url: str) -> bool:
        """
        Focus an existing popup window matching the URL (path only, ignoring query string).
        Returns True if a live window was found and focused, False otherwise.
        Safe to call from any thread.
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        url_key = parsed.scheme + '://' + parsed.netloc + parsed.path

        if not hasattr(self, '_popup_windows'):
            return False

        view = self._popup_windows.get(url_key)
        if view is None:
            return False

        # Check visibility synchronously (must be called from main thread in Qt,
        # but isVisible() is generally safe to read from other threads in practice).
        # Emit focus signal to handle activation on main thread.
        try:
            if view.isVisible():
                if self.bridge:
                    self.bridge.focusWindow.emit(url_key)
                return True
            else:
                del self._popup_windows[url_key]
                return False
        except Exception:
            return False

    def shutdown(self):
        """Shutdown the engine"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
