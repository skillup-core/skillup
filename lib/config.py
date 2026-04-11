"""
Skillup Configuration Management

Handles configuration file loading and saving for apps and desktop.
This module is UI-independent and can be used in both CLI and desktop modes.
"""

import os
import sys
from typing import Dict, Any, Optional


def get_config_home() -> str:
    """
    Get the configuration directory path.

    Priority:
    1. SKILLUP_CONFIG_HOME environment variable
    2. XDG_CONFIG_HOME/skillup
    3. ~/.config/skillup (default)

    Returns:
        str: Absolute path to config directory
    """
    config_home = os.environ.get('SKILLUP_CONFIG_HOME')
    if config_home:
        return os.path.expanduser(config_home)

    xdg_config = os.environ.get('XDG_CONFIG_HOME')
    if xdg_config:
        return os.path.join(os.path.expanduser(xdg_config), 'skillup')

    return os.path.expanduser('~/.config/skillup')


def get_desktop_config_path() -> str:
    """Get the path to the desktop config.ini file"""
    config_home = get_config_home()
    return os.path.join(config_home, 'desktop', 'config.ini')


def get_app_config_path(app_id: str, app_id_name: str = None) -> str:
    """
    Get the path to an app's config.ini file

    Args:
        app_id: App ID (8-char hex)
        app_id_name: Human-readable app name (optional, for path readability)

    Returns:
        Path in format: ~/.config/skillup/app/{id_name}-{id}/config.ini
        If id_name not provided, uses just {id}
    """
    config_home = get_config_home()

    if app_id_name:
        app_dir = f"{app_id_name}-{app_id}"
    else:
        app_dir = app_id

    return os.path.join(config_home, 'app', app_dir, 'config.ini')


def get_app_data_path(app_id: str, app_id_name: str = None) -> str:
    """
    Get the path to an app's data directory.

    This directory is for persistent app data (e.g., history, cache files)
    that should survive configuration resets.

    Args:
        app_id: App ID (8-char hex)
        app_id_name: Human-readable app name (optional, for path readability)

    Returns:
        Path in format: ~/.config/skillup/app/{id_name}-{id}/data/
        If id_name not provided, uses just {id}/data/
        Directory is created automatically if it does not exist.
    """
    config_path = get_app_config_path(app_id, app_id_name)
    data_dir = os.path.join(os.path.dirname(config_path), 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def load_config(config_path: str, defaults: Optional[Dict[str, Any]] = None, app_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from flat key=value file (no section headers).

    IMPORTANT: When calling from BaseApp subclasses, use self.load_config() instead!
    This ensures app_id is automatically passed for SKILLUP_DEFAULT_CONFIG support.

    Args:
        config_path: Path to config.ini file
        defaults: Default values if config doesn't exist
        app_id: App ID or 'desktop' for section filtering in SKILLUP_DEFAULT_CONFIG
                WARNING: If app_id is None, SKILLUP_DEFAULT_CONFIG will be ignored!
                - For apps: Use self.load_config() in BaseApp subclasses (auto-passes app_id)
                - For desktop: Must pass app_id='desktop' explicitly
                - For system code: Must pass app_id explicitly

    Returns:
        dict: Configuration dictionary

    Usage:
        # ✅ CORRECT - In BaseApp subclass
        class MyApp(BaseApp):
            def on_run_desktop_initialize(self):
                config = self.load_config({'my.setting': 'default'})

        # ✅ CORRECT - In desktop code
        from lib.config import load_config
        config = load_config(path, defaults, app_id='desktop')

        # ❌ WRONG - In BaseApp subclass (SKILLUP_DEFAULT_CONFIG ignored!)
        class MyApp(BaseApp):
            def on_run_desktop_initialize(self):
                from lib.config import load_config
                config = load_config(self.context.config_path, defaults)  # Missing app_id!
    """
    config = defaults.copy() if defaults else {}

    # Apply SKILLUP_DEFAULT_CONFIG overrides to defaults
    default_config_path = _get_default_config_path()
    if default_config_path and app_id:
        config = _apply_default_config_overrides(config, default_config_path, app_id)

    if not os.path.exists(config_path):
        return config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments (# or ;)
                if not line or line.startswith('#') or line.startswith(';'):
                    continue

                # Parse key = value
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()

    except Exception:
        pass

    return config


def _get_default_config_path() -> Optional[str]:
    """
    Get the path to the default configuration override file.

    Priority:
    1. SKILLUP_DEFAULT_CONFIG environment variable (if set)
    2. skillup_default_config.ini in skillup.py parent directory (if exists)
    3. None (use hardcoded defaults)

    Returns:
        str: Absolute path to default config file, or None if not found
    """
    # Check environment variable first
    env_path = os.environ.get('SKILLUP_DEFAULT_CONFIG')
    if env_path:
        return env_path

    # Check for skillup_default_config.ini in skillup.py parent directory
    # skillup.py is at /home/work/code/skillup/skillup.py
    # its parent directory is /home/work/code/
    skillup_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Parent of skillup/
    local_config = os.path.join(skillup_root, 'skillup_default_config.ini')
    if os.path.exists(local_config):
        return local_config

    return None


def _expand_config_value(value: str, ini_dir: str) -> str:
    """
    Expand variables in a config value.

    Supported variables:
    - ${ini_dir}: Directory containing the default config file
    - ${ENV_VAR}: Any environment variable

    Args:
        value: Raw config value string
        ini_dir: Directory of the default config file (for ${ini_dir})

    Returns:
        str: Value with variables expanded
    """
    import re

    def replace_var(m):
        name = m.group(1)
        if name == 'ini_dir':
            return ini_dir
        return os.environ.get(name, m.group(0))  # Leave unexpanded if env var not found

    return re.sub(r'\$\{([^}]+)\}', replace_var, value)


def _apply_default_config_overrides(config: Dict[str, Any], default_config_path: str, app_id: str) -> Dict[str, Any]:
    """
    Apply overrides from SKILLUP_DEFAULT_CONFIG file.

    The default config file uses INI format with sections:
    - [desktop] for desktop configuration
    - [app_id] for app-specific configuration (e.g., [550e8400])

    Values support variable expansion:
    - ${ini_dir}: Directory containing the default config file
    - ${ENV_VAR}: Any environment variable

    Args:
        config: Current configuration (with hardcoded defaults)
        default_config_path: Path to SKILLUP_DEFAULT_CONFIG file or skillup_default_config.ini
        app_id: App ID or 'desktop' to determine which section to use

    Returns:
        dict: Configuration with overrides applied
    """
    if not os.path.exists(default_config_path):
        # Only exit if path came from environment variable (explicit user request)
        env_path = os.environ.get('SKILLUP_DEFAULT_CONFIG')
        if env_path:
            print(f"[error][Config] SKILLUP_DEFAULT_CONFIG file not found: {default_config_path}", file=sys.stderr)
            sys.exit(1)
        # Otherwise, silently skip (local config file doesn't exist, which is fine)
        return config

    ini_dir = os.path.dirname(os.path.abspath(default_config_path))

    try:
        current_section = None
        target_section = app_id  # Either 'desktop' or app ID like '550e8400'

        with open(default_config_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#') or line.startswith(';'):
                    continue

                # Parse section header [section_name]
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1].strip()
                    continue

                # Parse key = value only if we're in a section AND it's the target section
                if current_section is not None and current_section == target_section and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = _expand_config_value(value.strip(), ini_dir)

    except Exception:
        pass

    return config


def get_app_config(app_id: str, app_id_name: str, key: str, default: Any = None) -> Any:
    """
    Get another app's configuration value.

    Useful when one app needs to read settings from another app.
    For example, skillbot reading skillbook's DB path.

    Args:
        app_id: Target app's 8-char hex ID (e.g., 'b00k5k1l')
        app_id_name: Target app's human-readable name (e.g., 'skillbook')
        key: Configuration key (e.g., 'skillbook.skillbook_db_path')
        default: Default value if key doesn't exist

    Returns:
        Configuration value or default
    """
    config_path = get_app_config_path(app_id, app_id_name)
    config = load_config(config_path, app_id=app_id)
    return config.get(key, default)


def get_desktop_config(key: str, default: Any = None) -> Any:
    """
    Get desktop configuration value.

    Args:
        key: Configuration key in format "section.key" (e.g., "general.language")
        default: Default value if key doesn't exist

    Returns:
        Configuration value or default
    """
    config_path = get_desktop_config_path()
    config = load_config(config_path, defaults={'general.language': 'en'}, app_id='desktop')
    return config.get(key, default)


def save_config(config_path: str, config: Dict[str, Any]):
    """
    Save configuration to flat key=value file (no section headers).

    Args:
        config_path: Path to config.ini file
        config: Configuration dictionary
    """
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            for key, value in sorted(config.items()):
                f.write(f'{key} = {value}\n')
    except Exception:
        pass
