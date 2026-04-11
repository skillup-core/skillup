#!/usr/bin/env python3
"""
Generic Subprocess Entry Point for Desktop Apps

This script reads app.ini to dynamically load handler modules and run as subprocess.
It communicates with the desktop process via JSON-RPC over stdin/stdout.

Usage:
    From app directory: python3 ../../lib/comm.py

    The script will:
    1. Detect the app directory from its parent path
    2. Read app.ini to get subprocess configuration
    3. Dynamically import handler_module and state_module
    4. Run JSON-RPC loop for communication with desktop
"""

import sys
import json
import os
import re
from configparser import ConfigParser
from importlib import import_module


class SubprocessBridge:
    """
    Bridge object that mimics QWebChannel bridge for subprocess mode.
    Forwards callJS requests to desktop via JSON-RPC notifications.
    """

    def callJS(self, function_name, json_args):
        """Send callJS notification to desktop process"""
        send_notification('callJS', {
            'function_name': function_name,
            'json_args': json_args
        })


def send_response(response_id, result=None, error=None):
    """Send JSON-RPC response to stdout"""
    response = {
        'jsonrpc': '2.0',
        'id': response_id
    }

    if error:
        response['error'] = {
            'code': -32603,
            'message': str(error)
        }
    else:
        response['result'] = result or {}

    # Write to stdout with newline
    print(json.dumps(response), flush=True)


def send_notification(method, params=None):
    """Send JSON-RPC notification (no response expected) to stdout"""
    notification = {
        'jsonrpc': '2.0',
        'method': method,
        'params': params or {}
    }

    # Write to stdout with newline
    print(json.dumps(notification), flush=True)


def validate_module_name(name):
    """
    Validate module name for security.
    Only allow alphanumeric characters and underscores.
    Reject any path traversal attempts.
    """
    if not name:
        return False

    # Only allow safe characters: letters, numbers, underscore
    if not re.match(r'^[a-zA-Z0-9_]+$', name):
        return False

    # Reject path traversal patterns
    if '..' in name or '/' in name or '\\' in name:
        return False

    return True


def load_app_config(app_dir):
    """
    Load app.ini from app directory and return configuration.

    Returns:
        tuple: (app_id, app_id_name, app_name, main_script)
    """
    config_path = os.path.join(app_dir, 'app.ini')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"app.ini not found in {app_dir}")

    config = ConfigParser()
    config.read(config_path, encoding='utf-8')

    # Get app metadata
    app_id = config.get('app', 'id', fallback='unknown')
    app_id_name = config.get('app', 'id_name', fallback=None)
    app_name = config.get('app', 'name', fallback='Unknown App')
    main_script = config.get('app', 'main', fallback='main.py')

    # Validate app_id for security (used in module path)
    if not validate_module_name(app_id):
        raise ValueError(f"Invalid app ID in app.ini: {app_id}")

    return app_id, app_id_name, app_name, main_script


# Global app instance for callpython_handler to access
_app_instance = None

# License check — called once after ping response
_license_checked = False

def _check_license_once():
    """
    License enforcement — runs after ping so desktop receives pong first.
    LIC_DATE_START, LIC_DATE_END, LIC_MAX_USERS, LIC_TYPE are injected by
    PyInit_comm() into the 'comm' module from comm_license.inc constants.
      LIC_TYPE: 1=free, 2=enterprise, 3=master
    """
    global _license_checked
    if _license_checked:
        return
    _license_checked = True

    import comm as _comm
    lic_type      = _comm.LIC_TYPE        # 1=free, 2=enterprise, 3=master
    date_start    = _comm.LIC_DATE_START
    date_end      = _comm.LIC_DATE_END
    max_users     = _comm.LIC_MAX_USERS

    # @master: no restrictions
    if lic_type == 3:
        return

    # Date check (enterprise only)
    if lic_type == 2:
        import time as _t
        _now = _t.localtime()
        today = _now.tm_year * 10000 + (_now.tm_mon * 100) + _now.tm_mday
        if today < date_start or today > date_end:
            sys.exit(1)

    # User count check
    if max_users != -1:
        import __main__ as _m
        _count_fn = getattr(_m, 'count_activated_users', None)
        _path_fn  = getattr(_m, 'get_default_account_db_path', None)
        if _count_fn and _path_fn:
            cnt = _count_fn(_path_fn())
            if cnt != -2 and cnt > max_users:
                sys.exit(1)


def main():
    """
    Main subprocess entry point.
    Detects app directory, loads configuration, and runs JSON-RPC loop.
    """
    global _app_instance

    # Detect app directory from script location
    # Expected: lib/comm.py is executed from app/appname/ directory
    # or passed app directory as first argument
    if len(sys.argv) > 1:
        app_dir = os.path.abspath(sys.argv[1])
    else:
        # Assume current directory is app directory
        app_dir = os.getcwd()

    # Add project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        # Load app configuration
        app_id, app_id_name, app_name, main_script = load_app_config(app_dir)

        print(f"[{app_name} Process] Started", file=sys.stderr, flush=True)
        print(f"[{app_name} Process] App ID: {app_id}", file=sys.stderr, flush=True)

        # Import main app module (this auto-registers the app class)
        main_module_path = main_script.replace('.py', '')
        app_dir_name = os.path.basename(app_dir)
        main_module_name = f"app.{app_dir_name}.{main_module_path}"
        print(f"[{app_name} Process] Loading main module: {main_module_name}", file=sys.stderr, flush=True)

        main_mod = import_module(main_module_name)

        # Get the registered app class
        from lib.appmgr import get_app_class
        app_class = get_app_class(main_mod)

        if app_class is None:
            raise ValueError(f"No app class registered in {main_module_name}")

        # Create app instance
        from lib.appmgr import AppContext
        from lib.config import get_app_config_path

        config_path = get_app_config_path(app_id, app_id_name)
        context = AppContext(mode='desktop', args=[], config_path=config_path, app_id=app_id)

        print(f"[{app_name} Process] Creating app instance: {app_class.__name__}", file=sys.stderr, flush=True)
        _app_instance = app_class(engine=None, context=context)

        # Inject subprocess bridge for real-time updates
        bridge = SubprocessBridge()

        # Create a minimal engine-like object for callJS support
        class BridgeEngine:
            def __init__(self, bridge):
                self.bridge = bridge

            def callJS(self, action, data):
                # Convert data to JSON string for callJS
                import json
                json_args = json.dumps(data) if data else '{}'
                self.bridge.callJS(action, json_args)

        # Directly assign engine (replaces None from BaseApp.__init__)
        _app_instance.engine = BridgeEngine(bridge)

        # Call on_run_desktop_initialize
        print(f"[{app_name} Process] Calling on_run_desktop_initialize", file=sys.stderr, flush=True)
        try:
            exit_code = _app_instance.on_run_desktop_initialize()
            if exit_code != 0:
                print(f"[error][{app_name} Process] on_run_desktop_initialize failed with exit code {exit_code}",
                      file=sys.stderr, flush=True)
                sys.exit(exit_code)
        except Exception as e:
            print(f"[error][{app_name} Process] on_run_desktop_initialize raised exception: {e}",
                  file=sys.stderr, flush=True)
            sys.exit(1)

        print(f"[{app_name} Process] Initialization complete", file=sys.stderr, flush=True)

    except Exception as e:
        print(f"[error][Process] Fatal error during initialization: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    # Main JSON-RPC loop
    try:
        # Read requests from stdin line by line
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                # Parse JSON-RPC request
                request = json.loads(line)

                # Validate request
                if 'jsonrpc' not in request or request['jsonrpc'] != '2.0':
                    send_response(request.get('id', None), error='Invalid JSON-RPC version')
                    continue

                if 'method' not in request:
                    send_response(request.get('id', None), error='Missing method')
                    continue

                method = request['method']
                params = request.get('params', {})
                request_id = request.get('id', 1)

                # Handle shutdown request
                if method == 'shutdown':
                    send_response(request_id, result={'success': True})
                    print(f"[{app_name} Process] Shutdown requested", file=sys.stderr, flush=True)
                    break

                # Handle ping request
                if method == 'ping':
                    send_response(request_id, result={'pong': True})
                    # License check runs after ping so subprocess is alive
                    # when desktop receives pong. Violation causes exit(1).
                    _check_license_once()
                    continue

                # Get language from params or use default
                language = params.get('language', 'en')

                # Call app's on_handler
                result = _app_instance.on_handler(method, params, language)

                # Send response
                send_response(request_id, result=result)

            except json.JSONDecodeError as e:
                send_response(None, error=f'Invalid JSON: {str(e)}')
            except Exception as e:
                print(f"[error][{app_name} Process] Error handling request: {e}", file=sys.stderr, flush=True)
                send_response(request.get('id', None) if 'request' in locals() else None, error=str(e))

    except KeyboardInterrupt:
        print(f"[warn ][{app_name} Process] Interrupted", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[error][{app_name} Process] Fatal error: {e}", file=sys.stderr, flush=True)
    finally:
        if _app_instance is not None:
            try:
                _app_instance.on_close()
            except Exception as e:
                print(f"[error][{app_name} Process] on_close error: {e}", file=sys.stderr, flush=True)
        print(f"[{app_name} Process] Exiting", file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
