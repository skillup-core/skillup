"""
Skillup App Launcher

Handles app loading and execution in both CLI and desktop modes.
"""

import os
import sys
import importlib.util
from typing import Dict, Any, Optional, List
from enum import Enum

from .log import log


# Global registry for app classes
_registered_app_classes = {}


def register_app_class(app_class):
    """
    Register an app class for discovery.

    This should be called at module level in each app's main script.

    Args:
        app_class: The app class to register (must inherit from BaseApp)

    Example:
        from lib.appmgr import register_app_class

        class MyApp(BaseApp):
            ...

        register_app_class(MyApp)
    """
    # Get the module name from the class
    module_name = app_class.__module__
    _registered_app_classes[module_name] = app_class


class AppMode(Enum):
    """Application execution mode"""
    DESKTOP = "desktop"
    CLI = "cli"
    UNKNOWN = "unknown"


def get_app_mode() -> AppMode:
    """
    Get current app execution mode from environment variable.

    Returns:
        AppMode enum value
    """
    mode = os.environ.get('_SKILLUP_APP_MODE', '').lower()

    if mode == 'desktop':
        return AppMode.DESKTOP
    elif mode == 'cli':
        return AppMode.CLI
    else:
        return AppMode.UNKNOWN


class AppContext:
    """Context passed to app when launched"""

    def __init__(self, mode: str, args: List[str], config_path: str, app_id: str = None):
        """
        Initialize app context.

        Args:
            mode: Execution mode ('cli' or 'desktop')
            args: Command line arguments
            config_path: Path to app config file
            app_id: App ID (8-char hex, optional)
        """
        self.mode = mode
        self.args = args
        self.config_path = config_path
        self.app_id = app_id


def load_app_module(app_id: str):
    """
    Load app module dynamically.

    Args:
        app_id: App ID (directory name under app/)

    Returns:
        Loaded module or None if not found
    """
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_dir = os.path.join(script_dir, 'app', app_id)

    # Check app.ini for main entry point
    app_ini_path = os.path.join(app_dir, 'app.ini')
    main_file = 'main.py'  # default

    if os.path.exists(app_ini_path):
        from configparser import ConfigParser
        config = ConfigParser()
        config.read(app_ini_path, encoding='utf-8')
        main_file = config.get('app', 'main', fallback='main.py')

    main_py = os.path.join(app_dir, main_file)

    if not os.path.exists(main_py):
        log("error", message=f"App not found: {app_id} (looking for {main_file})")
        return None

    try:
        # Use actual filename (without .py) as module name for consistency with comm.py
        main_module_path = main_file.replace('.py', '')
        module_name = f"app.{app_id}.{main_module_path}"

        spec = importlib.util.spec_from_file_location(module_name, main_py)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        log("error", message=f"Failed to load app {app_id}: {e}")
        return None


def get_app_class(module):
    """
    Get App class from module.

    Looks up the registered app class. The app must have called
    register_app_class() at module level.

    Args:
        module: Loaded app module

    Returns:
        App class or None if not registered
    """
    module_name = module.__name__
    return _registered_app_classes.get(module_name)


def run_app_cli(app_id: str, args: List[str]) -> int:
    """
    Run app in CLI mode.

    Args:
        app_id: App ID (can be either id or id_name)
        args: Command line arguments

    Returns:
        Exit code
    """
    # Set environment variable to indicate CLI mode
    os.environ['_SKILLUP_APP_MODE'] = 'cli'

    # Import from config module (UI-independent)
    from .config import get_app_config_path
    from configparser import ConfigParser

    module = load_app_module(app_id)
    if module is None:
        return 1

    app_class = get_app_class(module)
    if app_class is None:
        log("error", message=f"App class not found in {app_id}")
        return 1

    # Read app.ini to get id and id_name
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_ini_path = os.path.join(script_dir, 'app', app_id, 'app.ini')

    app_real_id = app_id
    app_id_name = None

    if os.path.exists(app_ini_path):
        config = ConfigParser()
        config.read(app_ini_path, encoding='utf-8')
        app_real_id = config.get('app', 'id', fallback=app_id)
        app_id_name = config.get('app', 'id_name', fallback=None)

    config_path = get_app_config_path(app_real_id, app_id_name)
    context = AppContext(mode='cli', args=args, config_path=config_path, app_id=app_real_id)

    try:
        app = app_class(engine=None, context=context)
        return app.on_run_cli(args)
    except Exception as e:
        log("error", message=f"App error: {e}")
        return 1


def list_apps() -> List[Dict[str, Any]]:
    """
    List all available apps.

    Returns:
        List of app info dictionaries
    """
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_dir = os.path.join(script_dir, 'app')

    apps = []

    if not os.path.exists(app_dir):
        return apps

    for item in os.listdir(app_dir):
        item_path = os.path.join(app_dir, item)
        if os.path.isdir(item_path):
            ini_path = os.path.join(item_path, 'app.ini')
            main_py = os.path.join(item_path, 'main.py')

            if os.path.exists(ini_path) and os.path.exists(main_py):
                apps.append({
                    'id': item,
                    'path': item_path,
                    'has_ini': True,
                    'has_main': True
                })

    return apps
