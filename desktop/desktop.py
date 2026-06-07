"""
Skillup Desktop Manager

Manages the desktop environment, app loading, and app lifecycle.
"""

import os
import base64
import json
import configparser
import secrets
import subprocess
import sys
import re
import time
from typing import Dict, List, Any, Optional

from lib.webui import WebUIEngine
from lib.config import (
    get_config_home,
    get_desktop_config_path,
    load_config,
    save_config
)
from lib.log import log, write_app_usage
from desktop.account import (
    get_default_account_db_path,
    init_db,
    get_account,
    get_account_photo,
    upsert_account,
    clear_account_photo,
)
from desktop.group import (
    init_group_db,
    create_group,
    get_group,
    list_groups,
    update_group,
    delete_group,
    get_group_members,
    add_member,
    remove_member,
    grant_admin,
    revoke_admin,
    request_join,
    list_join_requests,
    list_all_pending_join_requests,
    approve_join_request,
    reject_join_request,
    get_group_image,
    _is_member,
)


# ============================================================================
# Hotkey Management Utilities
# ============================================================================

def detect_desktop_environment():
    """
    Detect the current desktop environment (GNOME, KDE, XFCE)

    Returns:
        str: 'gnome', 'kde', 'xfce', or 'unknown'
    """
    # Check XDG_CURRENT_DESKTOP first
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()

    if 'gnome' in desktop:
        return 'gnome'
    elif 'kde' in desktop or 'plasma' in desktop:
        return 'kde'
    elif 'xfce' in desktop:
        return 'xfce'

    # Fallback: Check DESKTOP_SESSION
    session = os.environ.get('DESKTOP_SESSION', '').lower()

    if 'gnome' in session:
        return 'gnome'
    elif 'kde' in session or 'plasma' in session:
        return 'kde'
    elif 'xfce' in session:
        return 'xfce'

    return 'unknown'


def get_current_python_command():
    """
    Get the full command to run current skillup.py with --desktop

    Returns:
        str: Command string like 'bash /path/to/skillup-executor.sh --desktop'
             or 'python3 /path/to/skillup.py --desktop' if executor not found
    """
    skillup_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    executor = os.path.join(skillup_root, '..', 'skillup-tool', 'skillup-executor.sh')
    executor = os.path.abspath(executor)
    if os.path.isfile(executor):
        return f"bash {executor} --desktop"
    python_exe = sys.executable
    script_path = os.path.join(skillup_root, 'skillup.py')
    return f"{python_exe} {script_path} --desktop"


def parse_hotkey_to_gsettings(key_string):
    """
    Convert hotkey string to gsettings format

    Args:
        key_string: Key combination like 'CTRL, ALT, s' or 'CTRL, SHIFT, F1'

    Returns:
        str: gsettings format like '<Primary><Alt>s' or '<Primary><Shift>F1'
    """
    parts = [p.strip().upper() for p in key_string.split(',')]

    result = ''
    for part in parts:
        if part == 'CTRL' or part == 'CONTROL':
            result += '<Primary>'
        elif part == 'ALT':
            result += '<Alt>'
        elif part == 'SHIFT':
            result += '<Shift>'
        elif part == 'SUPER' or part == 'WIN':
            result += '<Super>'
        else:
            # This is the actual key (last part)
            result += part.lower()

    return result


def check_hotkey_registered(key_combination='<Primary><Alt>s'):
    """
    Check if hotkey is currently registered in the system

    Args:
        key_combination: Key combination in gsettings format (e.g., '<Primary><Alt>s')

    Returns:
        dict: {'registered': bool, 'command': str or None}
    """
    desktop = detect_desktop_environment()

    if desktop == 'gnome':
        try:
            # Get list of custom keybindings
            result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return {'registered': False, 'command': None}

            # Parse output like: ['/org/gnome/.../', '/org/gnome/.../']
            output = result.stdout.strip()
            if output == '@as []' or output == '[]':
                return {'registered': False, 'command': None}

            # Extract paths
            paths = re.findall(r"'([^']+)'", output)

            # Check each custom keybinding
            for path in paths:
                # Get binding
                binding_result = subprocess.run(
                    ['gsettings', 'get', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}', 'binding'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if binding_result.returncode != 0:
                    continue

                binding = binding_result.stdout.strip().strip("'")

                # Check if this is our hotkey
                if binding == key_combination:
                    # Get command
                    command_result = subprocess.run(
                        ['gsettings', 'get', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}', 'command'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    if command_result.returncode == 0:
                        command = command_result.stdout.strip().strip("'")
                        # Check if command contains 'skillup'
                        if 'skillup' in command:
                            return {'registered': True, 'command': command}

            return {'registered': False, 'command': None}

        except Exception:
            return {'registered': False, 'command': None}

    elif desktop == 'kde':
        # KDE stores shortcuts in kglobalshortcutsrc
        try:
            config_file = os.path.expanduser('~/.config/kglobalshortcutsrc')
            if not os.path.exists(config_file):
                return {'registered': False, 'command': None}

            # Parse KDE config file to find our shortcut
            # This is a simplified check - full implementation would need proper INI parsing
            with open(config_file, 'r') as f:
                content = f.read()
                if 'skillup' in content.lower():
                    return {'registered': True, 'command': 'unknown'}

            return {'registered': False, 'command': None}

        except Exception:
            return {'registered': False, 'command': None}

    elif desktop == 'xfce':
        # XFCE stores shortcuts in xfce4-keyboard-shortcuts.xml
        try:
            config_file = os.path.expanduser('~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-keyboard-shortcuts.xml')
            if not os.path.exists(config_file):
                return {'registered': False, 'command': None}

            # Parse XML file
            with open(config_file, 'r') as f:
                content = f.read()
                if 'skillup' in content.lower():
                    return {'registered': True, 'command': 'unknown'}

            return {'registered': False, 'command': None}

        except Exception:
            return {'registered': False, 'command': None}

    return {'registered': False, 'command': None}


def register_hotkey(key_combination='<Primary><Alt>s'):
    """
    Register global hotkey in the system

    Args:
        key_combination: Key combination in gsettings format

    Returns:
        dict: {'success': bool, 'message': str}
    """
    desktop = detect_desktop_environment()
    command = get_current_python_command()

    if desktop == 'gnome':
        try:
            # Get current custom keybindings
            result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return {'success': False, 'message': 'Failed to read gsettings'}

            output = result.stdout.strip()

            # Parse existing paths
            if output == '@as []' or output == '[]':
                paths = []
            else:
                paths = re.findall(r"'([^']+)'", output)

            # Find available slot
            slot = 0
            base_path = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom'
            while f"{base_path}{slot}/" in paths:
                slot += 1

            new_path = f"{base_path}{slot}/"
            paths.append(new_path)

            # Format paths for gsettings
            paths_str = '[' + ', '.join(f"'{p}'" for p in paths) + ']'

            # Set custom-keybindings list
            subprocess.run(
                ['gsettings', 'set', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings', paths_str],
                timeout=5
            )

            # Set name
            subprocess.run(
                ['gsettings', 'set', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{new_path}', 'name', 'Skillup Desktop'],
                timeout=5
            )

            # Set command
            subprocess.run(
                ['gsettings', 'set', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{new_path}', 'command', command],
                timeout=5
            )

            # Set binding
            subprocess.run(
                ['gsettings', 'set', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{new_path}', 'binding', key_combination],
                timeout=5
            )

            return {'success': True, 'message': 'Hotkey registered successfully'}

        except Exception as e:
            return {'success': False, 'message': f'Failed to register hotkey: {str(e)}'}

    elif desktop == 'kde':
        return {'success': False, 'message': 'KDE hotkey registration not yet implemented. Please register manually in System Settings.'}

    elif desktop == 'xfce':
        return {'success': False, 'message': 'XFCE hotkey registration not yet implemented. Please register manually in Settings.'}

    else:
        return {'success': False, 'message': f'Unsupported desktop environment: {desktop}'}


def unregister_hotkey(key_combination='<Primary><Alt>s'):
    """
    Unregister global hotkey from the system

    Args:
        key_combination: Key combination in gsettings format

    Returns:
        dict: {'success': bool, 'message': str, 'old_command': str or None}
    """
    desktop = detect_desktop_environment()

    if desktop == 'gnome':
        try:
            # Get current custom keybindings
            result = subprocess.run(
                ['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return {'success': False, 'message': 'Failed to read gsettings', 'old_command': None}

            output = result.stdout.strip()

            # Parse existing paths
            if output == '@as []' or output == '[]':
                return {'success': False, 'message': 'No custom keybindings found', 'old_command': None}

            paths = re.findall(r"'([^']+)'", output)

            # Find and remove our keybinding
            old_command = None
            removed_path = None

            for path in paths:
                # Get binding
                binding_result = subprocess.run(
                    ['gsettings', 'get', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}', 'binding'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if binding_result.returncode != 0:
                    continue

                binding = binding_result.stdout.strip().strip("'")

                # Check if this is our hotkey
                if binding == key_combination:
                    # Get command before removing
                    command_result = subprocess.run(
                        ['gsettings', 'get', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}', 'command'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    if command_result.returncode == 0:
                        old_command = command_result.stdout.strip().strip("'")

                    removed_path = path
                    break

            if removed_path is None:
                return {'success': False, 'message': 'Hotkey not found', 'old_command': None}

            # Remove from paths list
            paths.remove(removed_path)

            # Update custom-keybindings list
            if paths:
                paths_str = '[' + ', '.join(f"'{p}'" for p in paths) + ']'
            else:
                paths_str = '@as []'

            subprocess.run(
                ['gsettings', 'set', 'org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings', paths_str],
                timeout=5
            )

            # Reset the removed path's settings (cleanup)
            subprocess.run(
                ['gsettings', 'reset', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{removed_path}', 'name'],
                timeout=5,
                stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ['gsettings', 'reset', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{removed_path}', 'command'],
                timeout=5,
                stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ['gsettings', 'reset', f'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{removed_path}', 'binding'],
                timeout=5,
                stderr=subprocess.DEVNULL
            )

            return {'success': True, 'message': 'Hotkey unregistered successfully', 'old_command': old_command}

        except Exception as e:
            return {'success': False, 'message': f'Failed to unregister hotkey: {str(e)}', 'old_command': None}

    elif desktop == 'kde':
        return {'success': False, 'message': 'KDE hotkey unregistration not yet implemented. Please unregister manually in System Settings.', 'old_command': None}

    elif desktop == 'xfce':
        return {'success': False, 'message': 'XFCE hotkey unregistration not yet implemented. Please unregister manually in Settings.', 'old_command': None}

    else:
        return {'success': False, 'message': f'Unsupported desktop environment: {desktop}', 'old_command': None}




# ============================================================================
# Wayland IME Warning Detection
# ============================================================================

def _is_redhat8() -> bool:
    try:
        with open('/etc/redhat-release', 'r') as f:
            content = f.read()
        return 'release 8' in content
    except Exception:
        return False


def _has_ibus_korean() -> bool:
    try:
        result = subprocess.run(
            ['ibus', 'list-engine'],
            capture_output=True, text=True, timeout=3
        )
        return 'hangul' in result.stdout.lower() or 'korean' in result.stdout.lower()
    except Exception:
        return False


def should_show_wayland_ime_warning() -> bool:
    if os.environ.get('XDG_SESSION_TYPE', '').lower() != 'wayland':
        return False
    if not _is_redhat8():
        return False
    if not _has_ibus_korean():
        return False
    return True


# ============================================================================
# App Metadata
# ============================================================================

def validate_app_id(app_id: str) -> bool:
    """
    Validate app ID format.

    Requirements:
    - Exactly 8 characters
    - Only alphanumeric (a-z, A-Z, 0-9)

    Args:
        app_id: App ID to validate

    Returns:
        True if valid, False otherwise
    """
    if not app_id:
        return False

    if len(app_id) != 8:
        return False

    if not app_id.isalnum():
        return False

    return True


class AppInfo:
    """Application metadata from app.ini"""

    def __init__(self, dir_name: str, app_dir: str):
        """
        Initialize AppInfo

        Args:
            dir_name: App directory name (e.g., 'skillverifier')
            app_dir: Full path to app directory
        """
        self.dir_name = dir_name  # Directory name (for loading modules)
        self.id = ""  # Unique ID (8-char hex) - PRIMARY KEY
        self.id_name = ""  # Human-readable name (same as dir_name usually)
        self.dir = app_dir
        self.name = ""
        self.name_ko = ""
        self.version = "1.0.0"
        self.description = ""
        self.description_ko = ""
        self.icon = "icon.svg"
        self.main = None  # Main script for subprocess mode
        self.new_window = 'false'  # 'false', 'true', or 'single'
        self.menu_items = []

        self._load_ini()

    def _load_ini(self):
        """Load app.ini file"""
        ini_path = os.path.join(self.dir, 'app.ini')
        if not os.path.exists(ini_path):
            return

        try:
            parser = configparser.ConfigParser()
            parser.read(ini_path, encoding='utf-8')

            if parser.has_section('app'):
                # New ID scheme: id (8-char alphanumeric) is PRIMARY KEY
                self.id = parser.get('app', 'id', fallback='')

                # Validate app ID format
                if not validate_app_id(self.id):
                    log("error", message=f"Invalid app ID '{self.id}' in {self.dir_name}: must be exactly 8 alphanumeric characters")
                    self.id = ''  # Clear invalid ID

                # id_name is for human readability (config path, etc.)
                self.id_name = parser.get('app', 'id_name', fallback=self.dir_name)
                self.name = parser.get('app', 'name', fallback=self.id_name)
                self.name_ko = parser.get('app', 'name_ko', fallback=self.name)
                self.version = parser.get('app', 'version', fallback='1.0.0')
                self.description = parser.get('app', 'description', fallback='')
                self.description_ko = parser.get('app', 'description_ko', fallback=self.description)
                self.icon = parser.get('app', 'icon', fallback='icon.svg')
                self.main = parser.get('app', 'main', fallback=None)
                new_window_val = parser.get('app', 'new_window', fallback='false').strip().lower()
                if new_window_val in ('true', 'false', 'single'):
                    self.new_window = new_window_val
                else:
                    self.new_window = 'false'

            if parser.has_section('menu'):
                items_str = parser.get('menu', 'items', fallback='')
                if items_str:
                    item_ids = [x.strip() for x in items_str.split(',')]
                    for item_id in item_ids:
                        name = parser.get('menu', f'{item_id}.name', fallback=item_id)
                        name_ko = parser.get('menu', f'{item_id}.name_ko', fallback=name)
                        self.menu_items.append({
                            'id': item_id,
                            'name': name,
                            'name_ko': name_ko
                        })

        except Exception as e:
            log("warn", message=f"Failed to load app.ini for {self.id}: {e}")

    def get_name(self, language: str = 'en') -> str:
        """Get localized app name"""
        if language == 'ko' and self.name_ko:
            return self.name_ko
        return self.name

    def get_description(self, language: str = 'en') -> str:
        """Get localized description"""
        if language == 'ko' and self.description_ko:
            return self.description_ko
        return self.description

    def get_icon_path(self) -> str:
        """Get full path to icon file"""
        return os.path.join(self.dir, self.icon)

    def to_dict(self, language: str = 'en') -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,  # 8-char hex ID for URL routing
            'id_name': self.id_name,  # Human-readable name
            'name': self.get_name(language),
            'version': self.version,
            'description': self.get_description(language),
            'icon': self.icon,
            'new_window': self.new_window,
            'menu_items': [
                {
                    'id': item['id'],
                    'name': item['name_ko'] if language == 'ko' else item['name']
                }
                for item in self.menu_items
            ]
        }


# ============================================================================
# Image Utilities
# ============================================================================

def _resize_image_helper(photo_bytes: bytes, mime: str, width: int, height: int) -> Optional[bytes]:
    """
    Resize image to width x height (square crop from center).
    Requires Pillow (PIL). Returns None if PIL is not available.
    """
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(photo_bytes)).convert('RGB')

        # Center-crop to square first
        w, h = img.size
        min_side = min(w, h)
        left = (w - min_side) // 2
        top = (h - min_side) // 2
        img = img.crop((left, top, left + min_side, top + min_side))

        # Resize to target
        img = img.resize((width, height), Image.LANCZOS)

        # Encode back
        buf = io.BytesIO()
        fmt = 'JPEG' if 'jpeg' in mime or 'jpg' in mime else 'PNG'
        img.save(buf, format=fmt, quality=85)
        return buf.getvalue()
    except ImportError:
        # PIL not available - return original as fallback for small size
        return photo_bytes
    except Exception:
        return None


# ============================================================================
# Desktop Manager
# ============================================================================

class DesktopManager:
    """
    Desktop manager for the Skillup framework.

    Handles:
    - App discovery and loading
    - Desktop UI rendering
    - App lifecycle management
    - Settings and configuration
    """

    def __init__(self):
        self.engine = WebUIEngine(app_id=None, title="Skillup Desktop")

        # Register engine for lib.msgbox (in-process desktop mode)
        from lib.msgbox import set_engine
        set_engine(self.engine)

        self.apps: Dict[str, AppInfo] = {}
        self.current_app: Optional[str] = None
        self.language = 'en'
        self.theme = 'default'

        # Random GUID mapping: {app_id: {random_prefix: original_guid}}
        # This prevents cross-app attacks by making GUIDs session-specific
        self.app_guid_mapping: Dict[str, Dict[str, str]] = {}

        # App subprocess management: {app_id: subprocess.Popen}
        self.app_processes: Dict[str, Any] = {}

        # Set of app_ids currently being stopped (prevents restart during shutdown)
        self.app_processes_stopping: set = set()

        # True once desktop is shutting down — blocks any new subprocess starts
        self._is_shutting_down: bool = False

        # Set of app_ids that already logged a binary-not-found error (suppress repeats)
        self._binary_not_found_logged: set = set()

        # Subprocess response queues: {app_id: {request_id: queue}}
        self.subprocess_response_queues: Dict[str, Dict[int, Any]] = {}
        self.subprocess_request_id_counter: int = 0

        # Extra CLI args to inject into specific app subprocesses on first launch
        # {app_id: [arg, ...]}  — set by run() for auto-launched apps
        self._auto_launch_extra_args: Dict[str, List[str]] = {}

        # Initial menu to open for the auto-launched app (None = first menu)
        self._auto_launch_menu: Optional[str] = None

        # True when running in standalone app mode (no desktop shell)
        self._standalone_mode: bool = False

        # In-process app instances: {app_id: app_instance} (for legacy mode)
        self._app_instances: Dict[str, Any] = {}

        # App start timestamps for usage tracking: {app_id: monotonic time}
        self._app_start_times: Dict[str, float] = {}

        # Build update detection: snapshot of (version, build, date) at startup
        self._startup_build_info: Optional[tuple] = self._read_build_info()
        self._update_detected: bool = False

        # Skilltalk alerts buffered before desktop_ready fires (QWebChannel not yet connected)
        self._pending_st_alerts: list = []
        self._desktop_js_ready: bool = False
        self._pending_st_alerts_lock = __import__('threading').Lock()
        # command_result payloads received while skilltalk subprocess was not running
        self._pending_command_results: list = []
        self._pending_command_results_lock = __import__('threading').Lock()

        self._discover_apps()
        self._load_settings()
        self._setup_handlers()

    def _start_peerbus_daemon(self) -> None:
        """Ensure the peerbus daemon singleton is running. Non-fatal if it fails."""
        try:
            from lib.peerbuswrapper import PeerbusWrapper
            import lib.config as _cfg

            def _peerbus_log(msg: str) -> None:
                log("info", message=f"peerbus {msg}", tag="desktop")

            wrapper = PeerbusWrapper(log_fn=_peerbus_log)
            wrapper._ensure_daemon()
            pid_path = os.path.join(_cfg.get_config_home(), 'peerbus', 'daemon.pid')
            try:
                pid = int(open(pid_path).read().strip())
            except Exception:
                pid = '?'
            log("info", message=f"peerbus daemon running checked (PID: {pid})", tag="desktop")
        except Exception as e:
            log("warn", message=f"peerbus daemon could not start: {e}", tag="desktop")

        # Option B: desktop registers as skilltalk proxy so it can receive
        # skilltalk messages and show alerts even when skilltalk is not running.
        try:
            import uuid as _uuid
            from lib.peerbuswrapper import PeerbusWrapper

            def _st_log(msg: str) -> None:
                log("info", message=f"peerbus[skilltalk] {msg}", tag="desktop")

            self._skilltalk_peerbus = PeerbusWrapper(log_fn=_st_log)
            self._skilltalk_desktop_id = str(_uuid.uuid4())
            self._skilltalk_peerbus.on_message(self._on_skilltalk_peerbus_message)
            _st_port = self._skilltalk_peerbus.register(
                self._skilltalk_desktop_id,
                app_id='skilltalk',
                callback_port=0,
            )
            log("info", message=f"desktop registered as skilltalk peerbus proxy (port={_st_port})", tag="desktop")
        except Exception as e:
            log("warn", message=f"skilltalk peerbus proxy could not start: {e}", tag="desktop")
            self._skilltalk_peerbus = None
            self._skilltalk_desktop_id = None

    def _on_skilltalk_peerbus_message(self, send_id, from_uid, from_ip, app_id, msg_type, payload) -> None:
        """Handle skilltalk peerbus messages in desktop (Option B proxy)."""
        if not payload or app_id != 'skilltalk':
            return
        action = payload.get('action')
        if action not in ('new_chat', 'room_created', 'command_result'):
            return

        if action == 'command_result':
            st_process = self.app_processes.get('sk1llt4k')
            st_running = st_process is not None and st_process.poll() is None
            if not st_running:
                with self._pending_command_results_lock:
                    self._pending_command_results.append(payload)
            return

        if action == 'room_created':
            created_by = payload.get('created_by', '')
            if created_by == self.current_user:
                return
            chatroom_id = payload.get('chatroom_id')
            st_process = self.app_processes.get('sk1llt4k')
            st_running = st_process is not None and st_process.poll() is None
            if not st_running:
                try:
                    self.engine.broadcast_callJS('onRoomCreated', {
                        'chatroom_id': chatroom_id,
                        'created_by': created_by,
                    })
                except Exception:
                    pass
                alert_data = {
                    'app_id': 'skilltalk',
                    'chatroom_id': chatroom_id,
                    'message': f'{created_by}: 새 채팅방에 초대되었습니다.',
                }
                with self._pending_st_alerts_lock:
                    if not self._desktop_js_ready:
                        self._pending_st_alerts.append(alert_data)
                        return
                try:
                    self.engine.broadcast_callJS('onSkilltalkAlert', alert_data)
                except Exception as e:
                    log("warn", message=f"skilltalk room_created alert failed: {e}", tag="desktop")
            return

        chatroom_id = payload.get('chatroom_id')
        chat_id = payload.get('chat_id')
        sender_uid = from_uid or payload.get('sender_uid', '')
        if sender_uid == self.current_user:
            return

        st_process = self.app_processes.get('sk1llt4k')
        st_running = st_process is not None and st_process.poll() is None
        if not st_running:
            # Subprocess is gone — push onChatNew to any open popup windows
            # and show a topbar alert.  chat.html handles alert when running.
            try:
                self.engine.broadcast_callJS('onChatNew', {
                    'chatroom_id': chatroom_id,
                    'chat_id': chat_id,
                })
            except Exception as e:
                log("warn", message=f"skilltalk onChatNew broadcast failed: {e}", tag="desktop")

            preview = payload.get('preview', '')
            message = f'{sender_uid}: {preview}' if sender_uid else preview
            alert_data = {
                'app_id': 'skilltalk',
                'chatroom_id': chatroom_id,
                'chat_id': chat_id,
                'message': message,
            }
            with self._pending_st_alerts_lock:
                if not self._desktop_js_ready:
                    self._pending_st_alerts.append(alert_data)
                    return
            try:
                self.engine.broadcast_callJS('onSkilltalkAlert', alert_data)
            except Exception as e:
                log("warn", message=f"skilltalk alert dispatch failed: {e}", tag="desktop")

    def _read_build_info(self) -> Optional[tuple]:
        """Read (version, build, date) from buildinfo.ini. Returns None on failure."""
        try:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            buildinfo_path = os.path.join(script_dir, 'buildinfo.ini')
            cfg = configparser.ConfigParser()
            cfg.read(buildinfo_path, encoding='utf-8')
            return (
                cfg.get('buildinfo', 'version', fallback=''),
                cfg.get('buildinfo', 'build', fallback=''),
                cfg.get('buildinfo', 'date', fallback=''),
            )
        except Exception:
            return None

    def _check_build_update(self):
        """Poll buildinfo.ini; if changed, notify all windows and subprocesses."""
        if self._update_detected:
            return
        current = self._read_build_info()
        if current is None or self._startup_build_info is None:
            return
        if current == self._startup_build_info:
            return

        self._update_detected = True
        log("info", message="Build update detected, notifying all windows", tag="desktop")

        # Notify main desktop window via bridge signal
        if self.engine.bridge:
            try:
                self.engine.bridge.callJS.emit('showUpdateOverlay', '{}')
            except Exception:
                pass

        # Inject overlay directly into popup/detach windows (they have no showUpdateOverlay)
        _inject_js = (
            "(function(){"
            "if(document.getElementById('_su_update_overlay'))return;"
            "var d=document.createElement('div');"
            "d.id='_su_update_overlay';"
            "d.style='position:fixed;top:0;left:0;width:100%;height:100%;"
            "background:rgba(0,0,0,0.75);z-index:2147483647;"
            "display:flex;align-items:center;justify-content:center;"
            "pointer-events:all;font-family:sans-serif;';"
            "d.innerHTML='<div style=\"background:#20242b;border:1px solid #373c47;"
            "border-radius:12px;padding:32px 36px;min-width:320px;max-width:440px;"
            "text-align:center;box-shadow:0 8px 40px rgba(0,0,0,0.5);\">"
            "<div style=\"font-size:32px;margin-bottom:16px;\">&#x21BA;</div>"
            "<div style=\"font-size:15px;font-weight:600;color:#eceef2;margin-bottom:10px;\">"
            "업데이트 감지 / Update Available</div>"
            "<div style=\"font-size:13px;color:#a0a0b0;margin-bottom:6px;\">"
            "Skillup이 업데이트되었습니다. 메인 창에서 재시작하세요.</div>"
            "<div style=\"font-size:12px;color:#e07b39;\">"
            "작업 중인 내용이 손상될 수 있습니다.</div>"
            "</div>';"
            "document.body.appendChild(d);"
            "})()"
        )
        if self.engine.bridge:
            popup_windows = getattr(self.engine, '_popup_windows', {})
            for url_key in list(popup_windows):
                try:
                    self.engine.bridge.runJSInPopup.emit(url_key, _inject_js)
                except Exception:
                    pass
            detached_pages = getattr(self.engine, '_detached_pages', {})
            for uk in list(detached_pages.keys()):
                try:
                    self.engine.bridge.runJSInPopup.emit(uk, _inject_js)
                except Exception:
                    pass

        # Notify subprocess apps via JSON-RPC notification (fire-and-forget)
        for app_id, process in list(self.app_processes.items()):
            if process.poll() is not None:
                continue
            try:
                notification = json.dumps({
                    'jsonrpc': '2.0',
                    'method': 'show_update_overlay',
                    'params': {}
                }) + '\n'
                process.stdin.write(notification)
                process.stdin.flush()
            except Exception as e:
                log("warn", message=f"Failed to notify subprocess {app_id} of update: {e}", tag="desktop")

    def _discover_apps(self):
        """Discover all apps in the app directory"""
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_dir = os.path.join(script_dir, 'app')

        if not os.path.exists(app_dir):
            return

        for item in os.listdir(app_dir):
            item_path = os.path.join(app_dir, item)
            if os.path.isdir(item_path):
                ini_path = os.path.join(item_path, 'app.ini')
                if os.path.exists(ini_path):
                    app_info = AppInfo(item, item_path)
                    # Use app ID as key (not directory name)
                    if app_info.id:
                        self.apps[app_info.id] = app_info
                    else:
                        log("warn", message=f"App {item} has no ID, skipping")

    def _load_settings(self):
        """Load desktop settings"""
        config_path = get_desktop_config_path()
        config = load_config(config_path, {
            'general.language': 'en',
            'general.theme': 'default',
            'general.account_type': 'sqlite',
            'general.account_db': '',
            'general.board_dir': '',
            'layout.app_order': '',
            'hotkey.key': 'CTRL, ALT, s',
            'hotkey.last_cmd': '',
            'notice.wayland_ime_dismissed_time': '0'
        }, app_id='desktop')
        self._desktop_config = config

        self.language = config['general.language']
        self.theme = config['general.theme']
        self.app_order = config['layout.app_order']
        self.hotkey_key = config['hotkey.key']
        self.hotkey_last_cmd = config['hotkey.last_cmd']
        self._load_wayland_ime_dismissed_time()
        self.account_type = config.get('general.account_type', 'sqlite').strip()

        # Account DB path: used when account_type == 'sqlite'
        account_db_config = config.get('general.account_db', '').strip()
        self.account_db_path = account_db_config if account_db_config else get_default_account_db_path()

        # Initialize account backend
        if self.account_type == 'sqlite':
            try:
                init_db(self.account_db_path)
            except Exception as e:
                log("warn", message=f"Failed to initialize account DB: {e}", tag="desktop")
        else:
            log("warn", message=f"Unsupported account_type '{self.account_type}', falling back to sqlite", tag="desktop")
            self.account_type = 'sqlite'
            try:
                init_db(self.account_db_path)
            except Exception as e:
                log("warn", message=f"Failed to initialize account DB: {e}", tag="desktop")

        # Initialize group tables in the same DB
        try:
            init_group_db(self.account_db_path)
        except Exception as e:
            log("warn", message=f"Failed to initialize group DB: {e}", tag="desktop")

        # Determine current user from $USER env
        self.current_user = os.environ.get('USER', os.environ.get('USERNAME', 'user'))

    def _load_wayland_ime_dismissed_time(self):
        """Load wayland IME dismissed timestamp, handling migration from old boolean format"""
        # Try new timestamp format first
        time_str = self._desktop_config.get('notice.wayland_ime_dismissed_time', '0').strip()
        try:
            self.wayland_ime_dismissed_time = int(time_str)
        except (ValueError, TypeError):
            self.wayland_ime_dismissed_time = 0

        # If timestamp is 0, check for old boolean format for backward compatibility
        if self.wayland_ime_dismissed_time == 0:
            old_dismissed = self._desktop_config.get('notice.wayland_ime_dismissed', 'false').strip().lower() == 'true'
            if old_dismissed:
                self.wayland_ime_dismissed_time = int(time.time())

    def _is_wayland_ime_dismissed_within_week(self) -> bool:
        """Check if wayland IME dialog was dismissed within the last 7 days"""
        if self.wayland_ime_dismissed_time == 0:
            return False
        current_time = int(time.time())
        week_in_seconds = 7 * 24 * 60 * 60
        return (current_time - self.wayland_ime_dismissed_time) < week_in_seconds

    def _save_settings(self, hotkey_last_cmd=None, wayland_ime_dismissed=None):
        """Save desktop settings"""
        config_path = get_desktop_config_path()
        settings = {
            'general.language': self.language,
            'general.theme': self.theme,
            'layout.app_order': self.app_order,
            'hotkey.key': self.hotkey_key
        }

        if hotkey_last_cmd is not None:
            settings['hotkey.last_cmd'] = hotkey_last_cmd
            self.hotkey_last_cmd = hotkey_last_cmd

        if wayland_ime_dismissed is not None:
            settings['notice.wayland_ime_dismissed_time'] = str(wayland_ime_dismissed)
            self.wayland_ime_dismissed_time = wayland_ime_dismissed

        save_config(config_path, settings)

    def _generate_randomized_id(self, app_id: str) -> Optional[str]:
        """
        Generate a randomized ID for an app.
        Format: {random_prefix}_{original_id}

        IMPORTANT: This generates a session-specific ID that remains constant
        throughout the process lifetime. Each app gets one ID per session.

        Args:
            app_id: App ID (8-char hex)

        Returns:
            Randomized ID or None if app not found
        """
        if app_id not in self.apps:
            return None

        # Check if ID already exists for this app (return existing one)
        if app_id in self.app_guid_mapping and self.app_guid_mapping[app_id]:
            # Return existing ID (first one in the mapping)
            existing_prefix = list(self.app_guid_mapping[app_id].keys())[0]
            existing_id = self.app_guid_mapping[app_id][existing_prefix]
            return f"{existing_prefix}_{existing_id}"

        app_info = self.apps[app_id]
        original_id = app_info.id

        if not original_id:
            return None

        # Generate random prefix (4-digit number) - ONLY ONCE PER SESSION
        random_prefix = secrets.randbelow(10000)
        randomized_id = f"{random_prefix}_{original_id}"

        # Store mapping
        if app_id not in self.app_guid_mapping:
            self.app_guid_mapping[app_id] = {}

        self.app_guid_mapping[app_id][str(random_prefix)] = original_id

        return randomized_id

    def _validate_randomized_id(self, randomized_id: str) -> Optional[str]:
        """
        Validate a randomized ID and return the app_id if valid.

        Args:
            randomized_id: ID with random prefix (e.g., "5631_550e8400")

        Returns:
            app_id (8-char hex) if valid, None otherwise
        """
        try:
            # Split prefix and ID
            parts = randomized_id.split('_', 1)
            if len(parts) != 2:
                return None

            random_prefix, original_id = parts

            # Find matching app
            for app_id, prefix_mapping in self.app_guid_mapping.items():
                if random_prefix in prefix_mapping:
                    if prefix_mapping[random_prefix] == original_id:
                        return app_id

            return None

        except Exception:
            return None

    def _start_app_process(self, app_id: str) -> bool:
        """
        Start an app as a subprocess.

        Args:
            app_id: The app identifier

        Returns:
            True if started successfully, False otherwise
        """
        if self._is_shutting_down or app_id in self.app_processes_stopping:
            return False

        if app_id in self.app_processes:
            # App already running
            process = self.app_processes[app_id]
            if process.poll() is None:  # Still running
                return True
            else:
                # Process died, remove it
                del self.app_processes[app_id]
                if self._is_shutting_down or app_id in self.app_processes_stopping:
                    return False

        # Get app directory
        if app_id not in self.apps:
            log("error", message=f"App not found: {app_id}", tag="desktop")
            return False

        app_info = self.apps[app_id]
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_dir = os.path.join(script_dir, 'app', app_info.dir_name)

        # Check if app uses subprocess mode (app.ini [app] subprocess = true)
        app_ini_path = os.path.join(app_dir, 'app.ini')

        from configparser import ConfigParser
        config = ConfigParser()
        config.read(app_ini_path, encoding='utf-8')

        if not config.getboolean('app', 'subprocess', fallback=False):
            # App doesn't use subprocess mode, return False to allow in-process handling
            return False

        # Use comm.abi3.so Python extension module
        comm_so = os.path.join(script_dir, 'lib', 'comm.abi3.so')

        if not os.path.exists(comm_so):
            if app_id not in self._binary_not_found_logged:
                log("error", message="lib/comm.abi3.so not found", tag="desktop")
                self._binary_not_found_logged.add(app_id)
            return False

        cmd = [
            sys.executable, '-c',
            f'import sys, importlib.util; '
            f'spec = importlib.util.spec_from_file_location("comm", {repr(comm_so)}); '
            f'mod = importlib.util.module_from_spec(spec); '
            f'spec.loader.exec_module(mod); '
            f'sys.argv = ["comm", {repr(app_dir)}]; mod.main()'
        ]

        # Start subprocess with app directory as argument
        try:
            # Prepare environment with app mode indicator
            env = os.environ.copy()
            env['_SKILLUP_APP_MODE'] = 'desktop'
            # Forward verbose flag to subprocess
            from lib.log import is_verbose
            if is_verbose():
                env['_SKILLUP_VERBOSE'] = '1'
            # Forward extra launch args as JSON via environment variable
            extra_args = self._auto_launch_extra_args.pop(app_id, None)
            if extra_args:
                env['_SKILLUP_APP_ARGS'] = json.dumps(extra_args)

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                env=env
            )

            self.app_processes[app_id] = process

            # Start thread to read stderr and forward to console
            import threading
            def read_stderr():
                try:
                    for line in process.stderr:
                        line = line.rstrip()
                        # Parse log level from message prefix
                        if line.startswith('[error]'):
                            log("error", message=line[7:].lstrip(), tag=app_id)
                        elif line.startswith('[warn ]'):
                            log("warn", message=line[7:].lstrip(), tag=app_id)
                        elif line.startswith('[debug]'):
                            log("debug", message=line[7:].lstrip(), tag=app_id)
                        else:
                            log("info", message=line, tag=app_id)
                except Exception:
                    pass

            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()

            # Initialize response queue for this app
            if app_id not in self.subprocess_response_queues:
                self.subprocess_response_queues[app_id] = {}

            # Start thread to read stdout (both responses and notifications)
            def read_stdout():
                import queue
                try:
                    while True:
                        line = process.stdout.readline()
                        if not line:
                            break

                        try:
                            msg = json.loads(line)

                            # Check if this is a notification (no 'id' field)
                            if 'id' not in msg:
                                # Handle notification (e.g., callJS, msgbox)
                                method = msg.get('method')
                                params = msg.get('params', {})

                                if method == 'callJS':
                                    function_name = params.get('function_name')
                                    json_args = params.get('json_args')
                                    broadcast = params.get('broadcast', False)
                                    if function_name:
                                        try:
                                            data = json.loads(json_args) if json_args else {}
                                        except Exception:
                                            data = {}
                                        if broadcast:
                                            self.engine.broadcast_callJS(function_name, data)
                                        else:
                                            # Route through engine.callJS() so popup/detach windows
                                            # are handled correctly (runJSInPopup signal).
                                            self.engine.callJS(function_name, data)
                                elif method == 'msgbox':
                                    # Handle msgbox notification from subprocess
                                    title = params.get('title', 'Message')
                                    text = params.get('text', '')
                                    # Call JavaScript to show message box
                                    if self.engine.bridge:
                                        self.engine.bridge.callJS.emit('showMessageBox', json.dumps({
                                            'title': title,
                                            'text': text
                                        }))
                            else:
                                # This is a response to a request
                                request_id = msg.get('id')
                                if request_id in self.subprocess_response_queues.get(app_id, {}):
                                    # Put response in queue
                                    self.subprocess_response_queues[app_id][request_id].put(msg)
                        except Exception as e:
                            log("error", message=f"Error parsing stdout message: {e}", tag="desktop")
                except Exception as e:
                    log("error", message=f"Error reading stdout: {e}", tag="desktop")
                finally:
                    # In standalone mode, quit the Qt app when the subprocess exits
                    if self._standalone_mode and hasattr(self.engine, 'qt_app') and self.engine.qt_app:
                        try:
                            self.engine.qt_app.quit()
                        except Exception:
                            pass

            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stdout_thread.start()

            # Verify the subprocess is alive and responding with a ping
            ping_ok = False
            try:
                ping_result = self._call_app_subprocess(app_id, 'ping', {})
                ping_ok = ping_result.get('pong') is True
            except Exception:
                pass

            if not ping_ok:
                log("error", message=f"Subprocess for app {app_id} did not respond to ping — killing", tag="desktop")
                process.kill()
                process.wait()
                del self.app_processes[app_id]
                return False

            # Wait briefly for post-ping checks (e.g. license validation) to complete
            import time as _time
            _time.sleep(0.3)
            if process.poll() is not None:
                log("error", message=f"Subprocess for app {app_id} exited after ping (exit code {process.returncode})", tag="desktop")
                del self.app_processes[app_id]
                return False

            log("info", message=f"Started subprocess for app: {app_id} (PID: {process.pid})", tag="desktop")

            if app_id == 'sk1llt4k':
                self._flush_pending_command_results(app_id)

            return True

        except Exception as e:
            log("error", message=f"Failed to start subprocess for {app_id}: {e}", tag="desktop")
            return False

    def _flush_pending_command_results(self, app_id: str) -> None:
        """Deliver buffered command_result payloads to the (re)started skilltalk subprocess."""
        with self._pending_command_results_lock:
            pending = list(self._pending_command_results)
            self._pending_command_results.clear()
        if not pending:
            return
        log("info", message=f"flushing {len(pending)} pending command_result(s) to subprocess", tag="desktop")
        for payload in pending:
            try:
                self._call_app_subprocess(app_id, 'st_deliver_command_result', payload)
            except Exception as e:
                log("warn", message=f"flush command_result failed: {e}", tag="desktop")

    def _record_app_usage(self, app_id: str):
        """Write one app-usage entry if a start time was recorded for app_id."""
        import time as _time
        start = self._app_start_times.pop(app_id, None)
        if start is None:
            return
        duration = _time.monotonic() - start
        appname = self.apps[app_id].id_name if app_id in self.apps else app_id
        try:
            write_app_usage(self.current_user, appname, duration)
        except Exception:
            pass

    def _stop_app_process(self, app_id: str):
        """Stop an app subprocess"""
        if app_id not in self.app_processes:
            return

        process = self.app_processes[app_id]
        self.app_processes_stopping.add(app_id)

        try:
            # Send shutdown command via JSON-RPC (fire-and-forget, do not wait for response)
            # Using _call_app_subprocess would block for up to 5s waiting for a response
            # that may never arrive if the process exits immediately after handling shutdown.
            try:
                self.subprocess_request_id_counter += 1
                request_id = self.subprocess_request_id_counter
                request = json.dumps({
                    'jsonrpc': '2.0',
                    'method': 'shutdown',
                    'params': {},
                    'id': request_id
                }) + '\n'
                process.stdin.write(request)
                process.stdin.flush()
            except Exception:
                pass

            # Poll until the process exits (it calls _exit(0) immediately after shutdown).
            # Use short sleep intervals instead of process.wait(timeout=N) to minimize delay.
            import time as _time
            deadline = _time.monotonic() + 0.3
            while process.poll() is None and _time.monotonic() < deadline:
                _time.sleep(0.01)

            # Ensure the process is dead regardless
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        except Exception as e:
            log("error", message=f"Error stopping app {app_id}: {e}", tag="desktop")
            process.kill()

        finally:
            self.app_processes_stopping.discard(app_id)
            del self.app_processes[app_id]
            log("info", message=f"Stopped subprocess for app: {app_id}", tag="desktop")

    def _call_app_subprocess(self, app_id: str, handler_name: str, data: dict) -> dict:
        """
        Call app subprocess via JSON-RPC.

        Args:
            app_id: App identifier
            handler_name: Handler name
            data: Request data

        Returns:
            Response dictionary
        """
        if app_id not in self.app_processes:
            return {'success': False, 'error': 'App subprocess not running'}

        process = self.app_processes[app_id]

        # Check if process is still alive
        if process.poll() is not None:
            del self.app_processes[app_id]
            return {'success': False, 'error': 'App subprocess died'}

        try:
            import queue

            # Generate unique request ID
            self.subprocess_request_id_counter += 1
            request_id = self.subprocess_request_id_counter

            # Create response queue for this request
            response_queue = queue.Queue()
            if app_id not in self.subprocess_response_queues:
                self.subprocess_response_queues[app_id] = {}
            self.subprocess_response_queues[app_id][request_id] = response_queue

            # Create JSON-RPC request
            request = {
                'jsonrpc': '2.0',
                'method': handler_name,
                'params': data,
                'id': request_id
            }

            # Send request
            request_json = json.dumps(request) + '\n'
            process.stdin.write(request_json)
            process.stdin.flush()

            # Wait for response (with timeout)
            try:
                response = response_queue.get(timeout=5.0)
            except queue.Empty:
                return {'success': False, 'error': 'Subprocess response timeout'}
            finally:
                # Clean up queue
                if request_id in self.subprocess_response_queues.get(app_id, {}):
                    del self.subprocess_response_queues[app_id][request_id]

            # Check for JSON-RPC error
            if 'error' in response:
                return {'success': False, 'error': response['error'].get('message', 'Unknown error')}

            # Get result
            result = response.get('result', {})

            return result

        except Exception as e:
            log("error", message=f"Error calling app subprocess {app_id}: {e}", tag="desktop")
            return {'success': False, 'error': f'Subprocess communication error: {str(e)}'}

    def _setup_handlers(self):
        """Setup message handlers for API calls"""
        # Module-level image resize helper (used inside handler closures)
        _resize_image = _resize_image_helper

        def handle_init_app_guid(data):
            """Initialize app ID with random prefix"""
            # JavaScript sends app_id which is actually the ID from URL path
            app_id = data.get('app_id')
            path = data.get('path', '')

            if not app_id:
                return {'success': False, 'error': 'No app_id provided'}

            # Generate randomized ID
            randomized_id = self._generate_randomized_id(app_id)

            if not randomized_id:
                return {'success': False, 'error': f'App not found or no ID: {app_id}'}

            return {
                'success': True,
                'app_id': app_id,
                'randomized_guid': randomized_id  # Keep 'randomized_guid' for JS compatibility
            }

        def handle_callpython_route(data):
            """
            Route /api/callPython/<id>/<handler_name> requests to app-specific handlers

            This is a special handler that intercepts callPython routes and delegates
            to the appropriate app's handler module (either subprocess or in-process).
            """
            # Extract ID and handler_name from the special '_route_info' key
            route_info = data.get('_route_info', {})
            randomized_id = route_info.get('guid')  # Keep 'guid' key for compatibility
            handler_name = route_info.get('handler_name')

            if not randomized_id or not handler_name:
                return {'success': False, 'error': 'Invalid callPython route'}

            # Validate ID and get app_id
            app_id = self._validate_randomized_id(randomized_id)

            if not app_id:
                return {'success': False, 'error': 'Invalid or expired ID'}

            # Get app info
            app_info = self.apps.get(app_id)
            if not app_info:
                return {'success': False, 'error': f'App not found: {app_id}'}

            # Check if app requires subprocess mode
            app_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', app_info.dir_name)
            from configparser import ConfigParser as _ConfigParser
            _cfg = _ConfigParser()
            _cfg.read(os.path.join(app_dir, 'app.ini'), encoding='utf-8')
            requires_subprocess = _cfg.getboolean('app', 'subprocess', fallback=False)

            # Try subprocess communication first
            started = self._start_app_process(app_id)

            if started:
                # Use subprocess communication (JSON-RPC)
                return self._call_app_subprocess(app_id, handler_name, data)

            if requires_subprocess:
                # subprocess mode is required but failed to start — do not fall back
                return {'success': False, 'error': f'App subprocess failed to start: {app_id}'}

            # Fall back to in-process handler (legacy mode)
            try:
                # Try to get or create app instance
                if app_id not in self._app_instances:
                    # Create app instance for in-process mode
                    from lib.appmgr import load_app_module, get_app_class, AppContext
                    from lib.config import get_app_config_path

                    # Load app module (use dir_name for loading)
                    app_module = load_app_module(app_info.dir_name)
                    app_class = get_app_class(app_module)

                    if app_class is None:
                        return {'success': False, 'error': f'App class not found for: {app_id}'}

                    # Get config path using id and id_name
                    config_path = get_app_config_path(app_info.id, app_info.id_name)

                    context = AppContext(mode='desktop', args=[], config_path=config_path, app_id=app_info.id)
                    app_instance = app_class(engine=self.engine, context=context)

                    # Initialize app
                    ret = app_instance.on_run_desktop_initialize()
                    if ret and ret != 0:
                        return {'success': False, 'error': f'App initialization failed (exit code {ret})'}

                    # Register app's handlers into engine so QWebChannel can route them
                    self._register_app_handlers_to_engine(app_instance)

                    # Store instance for reuse (key is app_id)
                    self._app_instances[app_id] = app_instance

                # Call app's on_handler
                app_instance = self._app_instances[app_id]
                return app_instance.on_handler(handler_name, data, self.language)

            except Exception as e:
                import traceback
                traceback.print_exc()
                return {'success': False, 'error': f'Handler error: {str(e)}'}

        def handle_get_apps(data):
            """Get list of all apps"""
            app_list = []

            # Get app order from instance variable (kept in sync with config)
            app_order = [x.strip() for x in self.app_order.split(',') if x.strip()]

            # Sort apps by order
            sorted_app_ids = []
            for app_id in app_order:
                if app_id in self.apps:
                    sorted_app_ids.append(app_id)

            # Add remaining apps not in order
            for app_id in self.apps:
                if app_id not in sorted_app_ids:
                    sorted_app_ids.append(app_id)

            for app_id in sorted_app_ids:
                app_info = self.apps[app_id]
                d = app_info.to_dict(self.language)
                process = self.app_processes.get(app_id)
                d['running'] = process is not None and process.poll() is None
                app_list.append(d)

            return {'apps': app_list}

        def handle_get_config(data):
            """Get desktop configuration"""
            # Read build info from buildinfo.ini
            version = ''
            build = ''
            build_date = ''
            try:
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                buildinfo_path = os.path.join(script_dir, 'buildinfo.ini')
                _cfg = configparser.ConfigParser()
                _cfg.read(buildinfo_path, encoding='utf-8')
                _ver = _cfg.get('buildinfo', 'version', fallback='')
                _date = _cfg.get('buildinfo', 'date', fallback='')
                _build = _cfg.get('buildinfo', 'build', fallback='')
                version = _ver
                if _date and len(_date) == 8:
                    build_date = f'{_date[:4]}/{_date[4:6]}/{_date[6:]}'
                elif _date:
                    build_date = _date
                build = _build
            except Exception:
                pass
            # Consume auto_launch_menu once (reset after first read)
            auto_launch_menu = self._auto_launch_menu
            self._auto_launch_menu = None
            # Check if wayland IME warning should be shown
            show_wayland_ime_warning = (
                not self._is_wayland_ime_dismissed_within_week() and should_show_wayland_ime_warning()
            )
            return {
                'language': self.language,
                'theme': self.theme,
                'auto_launch_app': self.current_app,
                'auto_launch_menu': auto_launch_menu,
                'version': version,
                'build': build,
                'build_date': build_date,
                'show_wayland_ime_warning': show_wayland_ime_warning
            }

        def handle_set_config(data):
            """Set desktop configuration"""
            if 'language' in data:
                self.language = data['language']
            if 'theme' in data:
                self.theme = data['theme']
            if 'app_order' in data:
                self.app_order = data['app_order']
            wayland_dismissed = None
            if 'wayland_ime_dismissed_time' in data:
                wayland_dismissed = int(data['wayland_ime_dismissed_time'])
            elif 'wayland_ime_dismissed' in data:
                # Backward compatibility: convert old boolean to timestamp
                wayland_dismissed = int(time.time()) if bool(data['wayland_ime_dismissed']) else 0
            self._save_settings(wayland_ime_dismissed=wayland_dismissed)
            return {'success': True}

        def handle_launch_app(data):
            """Launch an app"""
            app_id = data.get('app_id')
            if not app_id or app_id not in self.apps:
                return {'success': False, 'error': f'App not found: {app_id}'}

            # If app requires subprocess, verify it starts successfully before launching
            app_info = self.apps[app_id]
            script_dir = os.path.dirname(os.path.abspath(__file__))
            app_dir = os.path.join(script_dir, '..', 'app', app_info.dir_name)
            from configparser import ConfigParser as _CP
            _cfg = _CP()
            _cfg.read(os.path.join(app_dir, 'app.ini'), encoding='utf-8')
            if _cfg.getboolean('app', 'subprocess', fallback=False):
                if not self._start_app_process(app_id):
                    return {'success': False, 'error': f'Failed to start subprocess for app: {app_id}'}

            self.current_app = app_id
            import time as _time
            self._app_start_times[app_id] = _time.monotonic()
            return {'success': True, 'app_id': app_id}

        def handle_close_app(data):
            """Close current app (or specific app by app_id) and return to desktop"""
            app_id = data.get('app_id') if data else None
            target_app = app_id or self.current_app

            if target_app:
                # Record app usage duration
                self._record_app_usage(target_app)

                # Call on_close for in-process app instances
                if target_app in self._app_instances:
                    try:
                        app_instance = self._app_instances[target_app]
                        app_instance.on_close()
                    except Exception as e:
                        log("error", message=f"Error calling on_close for {target_app}: {e}", tag="desktop")

                # Stop app subprocess if running
                self._stop_app_process(target_app)

            # Only clear current_app if closing the current one
            if not app_id or app_id == self.current_app:
                self.current_app = None
            return {'success': True}

        def handle_get_app_icon(data):
            """Get app icon content"""
            app_id = data.get('app_id')
            if app_id and app_id in self.apps:
                icon_path = self.apps[app_id].get_icon_path()
                if os.path.exists(icon_path):
                    try:
                        with open(icon_path, 'r', encoding='utf-8') as f:
                            return {'icon': f.read(), 'type': 'svg'}
                    except Exception:
                        pass
            return {'icon': None}

        def handle_get_app_content(data):
            """Get app view HTML path"""
            app_id = data.get('app_id')
            view_id = data.get('view_id', 'dashboard')
            if app_id and app_id in self.apps:
                app_info = self.apps[app_id]
                # Check for individual view file first
                view_path = os.path.join(app_info.dir, 'web', f'{view_id}.html')
                if os.path.exists(view_path):
                    return {'path': f'/app/{app_id}/{view_id}.html', 'exists': True, 'type': 'view'}
                # Fallback to content.html
                content_path = os.path.join(app_info.dir, 'web', 'content.html')
                if os.path.exists(content_path):
                    return {'path': f'/app/{app_id}/content.html', 'exists': True, 'type': 'content'}
            return {'path': None, 'exists': False}

        def handle_browse_path(data):
            """Browse directory contents for web-based file dialog"""
            try:
                dir_path = data.get('path', os.path.expanduser("~"))
                dir_path = os.path.expanduser(dir_path)
                dir_path = os.path.normpath(dir_path)

                if not os.path.isdir(dir_path):
                    return {'success': False, 'error': 'Not a directory'}

                entries = []
                try:
                    items = os.listdir(dir_path)
                except PermissionError:
                    return {'success': True, 'path': dir_path, 'entries': [], 'error': 'Permission denied'}

                for name in sorted(items, key=lambda x: x.lower()):
                    if name.startswith('.'):
                        continue
                    full = os.path.join(dir_path, name)
                    is_dir = os.path.isdir(full)
                    entries.append({'name': name, 'is_dir': is_dir})

                # Sort: directories first, then files, each alphabetically
                entries.sort(key=lambda e: (0 if e['is_dir'] else 1, e['name'].lower()))

                return {'success': True, 'path': dir_path, 'entries': entries}

            except Exception as e:
                log("error", message=f"Browse path error: {e}", tag="desktop")
                return {'success': False, 'error': str(e)}

        def handle_hotkey_status(data):
            """Get hotkey status"""
            try:
                desktop = detect_desktop_environment()
                gsettings_key = parse_hotkey_to_gsettings(self.hotkey_key)
                status = check_hotkey_registered(gsettings_key)

                return {
                    'registered': status['registered'],
                    'command': status['command'],
                    'desktop': desktop,
                    'key': self.hotkey_key
                }
            except Exception as e:
                log("error", message=f"Error getting hotkey status: {e}", tag="desktop")
                return {
                    'registered': False,
                    'command': None,
                    'desktop': 'unknown',
                    'key': self.hotkey_key
                }

        def handle_toggle_hotkey(data):
            """Toggle hotkey registration"""
            try:
                enable = data.get('enable', False)
                gsettings_key = parse_hotkey_to_gsettings(self.hotkey_key)

                if enable:
                    # Register hotkey
                    result = register_hotkey(gsettings_key)
                    if result['success'] and self.hotkey_last_cmd:
                        # Clear last_cmd after successful registration
                        self._save_settings(hotkey_last_cmd='')
                    return result
                else:
                    # Unregister hotkey
                    result = unregister_hotkey(gsettings_key)
                    if result['success'] and result['old_command']:
                        # Save old command before unregistration
                        self._save_settings(hotkey_last_cmd=result['old_command'])
                    return {
                        'success': result['success'],
                        'message': result['message']
                    }

            except Exception as e:
                log("error", message=f"Error toggling hotkey: {e}", tag="desktop")
                return {'success': False, 'message': f'Error: {str(e)}'}

        def handle_msgbox(data):
            """Show message box dialog"""
            try:
                title = data.get('title', 'Message')
                text = data.get('text', '')

                # Call JavaScript to show Bootstrap modal
                if self.engine.bridge:
                    self.engine.bridge.callJS.emit('showMessageBox', json.dumps({
                        'title': title,
                        'text': text
                    }))

                return {'success': True}
            except Exception as e:
                log("error", message=f"Message box error: {e}", tag="desktop")
                return {'success': False, 'error': str(e)}

        def handle_get_account(data):
            """Get current user account info"""
            user_id = self.current_user
            account = get_account(self.account_db_path, user_id)
            if account is None:
                # Return defaults without creating a DB record
                return {
                    'success': True,
                    'id': user_id,
                    'name': user_id,
                    'has_photo': False,
                }
            return {
                'success': True,
                'id': account['id'],
                'name': account['name'],
                'has_photo': account['has_photo'],
            }

        def handle_get_account_photo(data):
            """Get user avatar photo as base64 data URI"""
            size = data.get('size', 'small')  # 'small' or 'full'
            user_id = data.get('user_id') or self.current_user
            photo_bytes, mime = get_account_photo(self.account_db_path, user_id, size)
            if photo_bytes:
                b64 = base64.b64encode(photo_bytes).decode('ascii')
                return {
                    'success': True,
                    'data_uri': f'data:{mime};base64,{b64}'
                }
            return {'success': True, 'data_uri': None}

        def handle_save_account(data):
            """Save account name and/or photo"""
            user_id = self.current_user
            name = data.get('name')
            photo_data_uri = data.get('photo')  # base64 data URI or None

            photo_bytes = None
            photo_small_bytes = None
            photo_mime = None

            if photo_data_uri:
                # Parse data URI: data:<mime>;base64,<data>
                try:
                    if photo_data_uri.startswith('data:'):
                        header, b64data = photo_data_uri.split(',', 1)
                        mime_part = header.split(';')[0]
                        photo_mime = mime_part[5:]  # strip 'data:'
                        photo_bytes = base64.b64decode(b64data)

                        # Generate small version (64x64) using PIL if available
                        photo_small_bytes = _resize_image(photo_bytes, photo_mime, 64, 64)
                except Exception as e:
                    log("warn", message=f"Failed to parse photo data: {e}", tag="desktop")

            ok = upsert_account(
                self.account_db_path, user_id,
                name=name,
                photo=photo_bytes,
                photo_small=photo_small_bytes,
                photo_mime=photo_mime
            )
            return {'success': ok}

        def handle_clear_account_photo(data):
            """Remove custom photo (revert to default)"""
            user_id = self.current_user
            ok = clear_account_photo(self.account_db_path, user_id)
            return {'success': ok}

        # ---- Group handlers ------------------------------------------------

        def handle_list_groups(data):
            user_id = self.current_user
            groups = list_groups(self.account_db_path, user_id=user_id)
            return {'success': True, 'groups': groups}

        def handle_browse_groups(data):
            user_id = self.current_user
            groups = list_groups(self.account_db_path, user_id=None)
            from desktop.account import _get_connection
            from pathlib import Path
            pending_set = set()
            if Path(self.account_db_path).exists():
                try:
                    conn = _get_connection(self.account_db_path)
                    try:
                        rows = conn.execute(
                            "SELECT group_id FROM group_join_requests WHERE user_id = ?",
                            (user_id,)
                        ).fetchall()
                        pending_set = {r['group_id'] for r in rows}
                    finally:
                        conn.close()
                except Exception:
                    pass
            for g in groups:
                g['is_member'] = _is_member(self.account_db_path, g['id'], user_id)
                g['request_pending'] = g['id'] in pending_set
            return {'success': True, 'groups': groups}

        def handle_create_group(data):
            name = (data.get('name') or '').strip()
            if not name:
                return {'success': False, 'error': 'name_required'}
            description = (data.get('description') or '').strip()[:150]
            join_policy = data.get('join_policy', 'free')
            if join_policy == 'all_user':
                all_user = True
                join_policy = 'free'
            else:
                all_user = bool(data.get('all_user', False))
                if join_policy not in ('free', 'approve'):
                    join_policy = 'free'
            config = {'join_policy': join_policy}
            group_id = create_group(
                self.account_db_path, self.current_user, name,
                description=description, all_user=all_user, config=config
            )
            if group_id is None:
                return {'success': False, 'error': 'create_failed'}
            return {'success': True, 'group_id': group_id}

        def handle_get_group(data):
            group_id = data.get('group_id', '')
            grp = get_group(self.account_db_path, group_id)
            if grp is None:
                return {'success': False, 'error': 'not_found'}
            members = get_group_members(self.account_db_path, group_id)
            return {'success': True, 'group': grp, 'members': members}

        def handle_update_group(data):
            group_id = data.get('group_id', '')
            name = data.get('name')
            description = data.get('description')
            if description is not None:
                description = description.strip()[:150]
            all_user = data.get('all_user')
            join_policy = data.get('join_policy')

            config = None
            if join_policy is not None:
                if join_policy not in ('free', 'approve'):
                    return {'success': False, 'error': 'invalid_join_policy'}
                grp = get_group(self.account_db_path, group_id)
                if grp is None:
                    return {'success': False, 'error': 'not_found'}
                config = grp.get('config', {}) or {}
                config['join_policy'] = join_policy

            image_bytes = None
            image_small_bytes = None
            image_mime = None
            image_data_uri = data.get('image')
            if image_data_uri and image_data_uri.startswith('data:'):
                try:
                    header, b64data = image_data_uri.split(',', 1)
                    mime_part = header.split(';')[0]
                    image_mime = mime_part[5:]
                    image_bytes = base64.b64decode(b64data)
                    image_small_bytes = _resize_image(image_bytes, image_mime, 64, 64)
                except Exception as e:
                    log("warn", message=f"Failed to parse group image: {e}", tag="desktop")

            ok = update_group(
                self.account_db_path, group_id, self.current_user,
                name=name if name is not None else None,
                description=description,
                all_user=bool(all_user) if all_user is not None else None,
                config=config,
                image=image_bytes,
                image_small=image_small_bytes,
                image_mime=image_mime,
            )
            return {'success': ok, 'error': None if ok else 'update_failed'}

        def handle_delete_group(data):
            group_id = data.get('group_id', '')
            ok = delete_group(self.account_db_path, group_id, self.current_user)
            return {'success': ok, 'error': None if ok else 'delete_failed'}

        def handle_get_group_image(data):
            group_id = data.get('group_id', '')
            size = data.get('size', 'small')
            img_bytes, mime = get_group_image(self.account_db_path, group_id, size)
            if img_bytes:
                b64 = base64.b64encode(img_bytes).decode('ascii')
                return {'success': True, 'data_uri': f'data:{mime};base64,{b64}'}
            return {'success': True, 'data_uri': None}

        def handle_search_users(data):
            query = (data.get('query') or '').strip()
            if not query:
                return {'success': True, 'users': []}
            try:
                from desktop.account import _get_connection
                conn = _get_connection(self.account_db_path)
                try:
                    like = '%' + query + '%'
                    rows = conn.execute(
                        "SELECT id, name FROM accounts WHERE activated=1 "
                        "AND (id LIKE ? OR name LIKE ?) ORDER BY id LIMIT 20",
                        (like, like)
                    ).fetchall()
                    users = [{'id': r['id'], 'name': r['name']} for r in rows]
                    return {'success': True, 'users': users}
                finally:
                    conn.close()
            except Exception:
                return {'success': True, 'users': []}

        def handle_group_add_member(data):
            group_id = data.get('group_id', '')
            target = data.get('user_id', '')
            return add_member(self.account_db_path, group_id, self.current_user, target)

        def handle_group_remove_member(data):
            group_id = data.get('group_id', '')
            target = data.get('user_id', self.current_user)
            return remove_member(self.account_db_path, group_id, self.current_user, target)

        def handle_group_grant_admin(data):
            group_id = data.get('group_id', '')
            target = data.get('user_id', '')
            return grant_admin(self.account_db_path, group_id, self.current_user, target)

        def handle_group_revoke_admin(data):
            group_id = data.get('group_id', '')
            target = data.get('user_id', '')
            return revoke_admin(self.account_db_path, group_id, self.current_user, target)

        def handle_group_request_join(data):
            group_id = data.get('group_id', '')
            return request_join(self.account_db_path, group_id, self.current_user)

        def handle_group_list_requests(data):
            group_id = data.get('group_id', '')
            reqs = list_join_requests(self.account_db_path, group_id)
            return {'success': True, 'requests': reqs}

        def handle_group_approve_request(data):
            group_id = data.get('group_id', '')
            target = data.get('user_id', '')
            return approve_join_request(self.account_db_path, group_id, self.current_user, target)

        def handle_group_reject_request(data):
            group_id = data.get('group_id', '')
            target = data.get('user_id', '')
            return reject_join_request(self.account_db_path, group_id, self.current_user, target)

        self.engine.register_handler('init_app_guid', handle_init_app_guid)
        self.engine.register_handler('callPython', handle_callpython_route)
        self.engine.register_handler('get_apps', handle_get_apps)
        self.engine.register_handler('get_config', handle_get_config)
        self.engine.register_handler('set_config', handle_set_config)
        self.engine.register_handler('launch_app', handle_launch_app)
        self.engine.register_handler('close_app', handle_close_app)
        self.engine.register_handler('get_app_icon', handle_get_app_icon)
        self.engine.register_handler('get_app_content', handle_get_app_content)
        self.engine.register_handler('browse_path', handle_browse_path)
        self.engine.register_handler('hotkey_status', handle_hotkey_status)
        self.engine.register_handler('toggle_hotkey', handle_toggle_hotkey)
        def handle_confirm_result(data):
            """Handle Yes/No response from confirm dialog (for lib/msgbox.py confirm())"""
            try:
                from lib.msgbox import handle_confirm_result as msgbox_handle_confirm
                confirm_id = data.get('confirm_id', '')
                confirmed = bool(data.get('confirmed', False))
                msgbox_handle_confirm(confirm_id, confirmed)
                return {'success': True}
            except Exception as e:
                log("error", message=f"Confirm result error: {e}", tag="desktop")
                return {'success': False, 'error': str(e)}

        def handle_open_window(data):
            url = data.get('url', '')
            title = data.get('title', 'Skillup')
            mode = data.get('mode', 'true')  # 'true', 'single', or 'single_open'
            width = int(data.get('width', 0))
            height = int(data.get('height', 0))
            min_w = int(data.get('min_w', 0))
            min_h = int(data.get('min_h', 0))
            if not url:
                return {'success': False}
            full_url = f"http://localhost:{self.engine.port}/{url.lstrip('/')}"
            if mode in ('single', 'single_open'):
                focused = self.engine.focus_window(full_url)
                if focused:
                    return {'success': True, 'focused': True}
                if mode == 'single':
                    # focus-only: do not open new window, let caller decide
                    return {'success': True, 'focused': False}
            self.engine.open_window(full_url, title, mode, width, height, min_w, min_h)
            return {'success': True, 'focused': False}

        def handle_detach_to_new_window(data):
            url = data.get('url', '')
            title = data.get('title', 'Skillup')
            multi = bool(data.get('multi', False))
            if not url:
                return {'success': False}
            full_url = f"http://localhost:{self.engine.port}/{url.lstrip('/')}"
            desktop_url = f"http://localhost:{self.engine.port}/"

            # Compute url_key the same way detach_to_new_window() does,
            # so we can register a per-window close callback keyed by it.
            from urllib.parse import urlparse as _urlparse
            _parsed = _urlparse(full_url)
            if multi:
                if not hasattr(self.engine, '_detach_counter'):
                    self.engine._detach_counter = 0
                _next_key = f"__detach_{self.engine._detach_counter + 1}"
            else:
                _next_key = _parsed.scheme + '://' + _parsed.netloc + _parsed.path

            # Register a per-window close callback so on_close() fires for the
            # correct app when each detached window is individually closed.
            _detach_app_id = self.current_app

            def _on_detached_close(_aid=_detach_app_id):
                if _aid and _aid in self._app_instances:
                    try:
                        self._app_instances[_aid].on_close()
                    except Exception as e:
                        log("error", message=f"Error calling on_close after detach for {_aid}: {e}", tag="desktop")

            if not hasattr(self.engine, '_on_detached_close_cbs'):
                self.engine._on_detached_close_cbs = {}
            self.engine._on_detached_close_cbs[_next_key] = _on_detached_close

            self.engine.detach_to_new_window(full_url, title, desktop_url, multi=multi, app_id=_detach_app_id or '')
            return {'success': True}

        def handle_desktop_ready(data):
            """
            Called by desktop JavaScript when the UI is fully loaded and ready.
            Checks pending group join requests for the current admin user, then
            triggers on_skillup_started() on all non-subprocess in-process apps.
            """
            pending = list_all_pending_join_requests(
                self.account_db_path, self.current_user
            )
            if pending:
                self.engine.callJS('showGroupJoinRequests', {'requests': pending})
            self._fire_skillup_started()
            # Flush any skilltalk alerts that arrived before QWebChannel was ready.
            with self._pending_st_alerts_lock:
                self._desktop_js_ready = True
                pending_alerts = list(self._pending_st_alerts)
                self._pending_st_alerts.clear()
            for alert_data in pending_alerts:
                try:
                    self.engine.broadcast_callJS('onSkilltalkAlert', alert_data)
                except Exception as e:
                    log("warn", message=f"skilltalk alert replay failed: {e}", tag="desktop")
            return {'success': True}

        self.engine.register_handler('open_window', handle_open_window)
        self.engine.register_handler('detach_to_new_window', handle_detach_to_new_window)
        self.engine.register_handler('msgbox', handle_msgbox)
        self.engine.register_handler('confirm_result', handle_confirm_result)
        self.engine.register_handler('get_account', handle_get_account)
        self.engine.register_handler('get_account_photo', handle_get_account_photo)
        self.engine.register_handler('save_account', handle_save_account)
        self.engine.register_handler('clear_account_photo', handle_clear_account_photo)
        self.engine.register_handler('desktop_ready', handle_desktop_ready)
        self.engine.register_handler('list_groups', handle_list_groups)
        self.engine.register_handler('browse_groups', handle_browse_groups)
        self.engine.register_handler('create_group', handle_create_group)
        self.engine.register_handler('get_group', handle_get_group)
        self.engine.register_handler('update_group', handle_update_group)
        self.engine.register_handler('delete_group', handle_delete_group)
        self.engine.register_handler('get_group_image', handle_get_group_image)
        self.engine.register_handler('group_add_member', handle_group_add_member)
        self.engine.register_handler('group_remove_member', handle_group_remove_member)
        self.engine.register_handler('group_grant_admin', handle_group_grant_admin)
        self.engine.register_handler('group_revoke_admin', handle_group_revoke_admin)
        self.engine.register_handler('group_request_join', handle_group_request_join)
        self.engine.register_handler('group_list_requests', handle_group_list_requests)
        self.engine.register_handler('group_approve_request', handle_group_approve_request)
        self.engine.register_handler('group_reject_request', handle_group_reject_request)
        self.engine.register_handler('search_users', handle_search_users)

        # Suggest board: expose list.json path so JS can open it in skillform runner
        try:
            from desktop.board.suggest.board import LIST_FORM_PATH as _suggest_list_form_path
            from lib.board import make_board_info as _make_board_info
            def _suggest_board_info(data):
                return _make_board_info(_suggest_list_form_path)
            self.engine.register_handler('suggest_board_info', _suggest_board_info)
        except Exception as _e:
            log("warn", message=f"Suggest board unavailable: {_e}", tag="desktop")

        def handle_restart_after_update(data):
            """Restart skillup via a detached shell script that waits for this process to exit."""
            import tempfile, stat
            parent_pid = os.getpid()
            python_exe = sys.executable

            skillup_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            executor = os.path.abspath(os.path.join(skillup_root, '..', 'skillup-tool', 'skillup-executor.sh'))

            if os.path.isfile(executor):
                launch_cmd = f'bash {executor} --desktop'
            else:
                skillup_py = os.path.join(skillup_root, 'skillup.py')
                launch_cmd = f'"{python_exe}" "{skillup_py}" --desktop'

            script = (
                '#!/bin/bash\n'
                f'while kill -0 {parent_pid} 2>/dev/null; do sleep 0.3; done\n'
                f'{launch_cmd}\n'
            )

            try:
                fd, script_path = tempfile.mkstemp(prefix='skillup_restart_', suffix='.sh')
                try:
                    with os.fdopen(fd, 'w') as f:
                        f.write(script)
                    os.chmod(script_path, stat.S_IRWXU)
                    subprocess.Popen(
                        ['bash', script_path],
                        start_new_session=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    os.unlink(script_path)
                    raise
            except Exception as e:
                log("warn", message=f"Failed to write restart script: {e}", tag="desktop")
                return {'success': False}

            # Quit Qt on the main thread via QMetaObject.invokeMethod (thread-safe)
            bridge = self.engine.bridge
            if bridge:
                try:
                    try:
                        from PySide2.QtCore import QMetaObject, Qt as _Qt  # type: ignore
                    except ImportError:
                        from PySide6.QtCore import QMetaObject, Qt as _Qt  # type: ignore
                    QMetaObject.invokeMethod(bridge, '_do_quit', _Qt.QueuedConnection)
                except Exception as e:
                    log("warn", message=f"invokeMethod failed: {e}", tag="desktop")
                    bridge.quitApp.emit()
            return {'success': True}

        self.engine.register_handler('restart_after_update', handle_restart_after_update)

    def _register_app_handlers_to_engine(self, app_instance):
        """
        Register an in-process app's handlers directly into the engine's
        message_handlers so that QWebChannel callPython() can route to them
        without going through the GUID-based REST API route.

        Each handler is wrapped to inject the current language.
        """
        for handler_name, handler_fn in app_instance._handlers.items():
            # Capture variables in closure
            def make_wrapper(fn):
                def wrapper(data):
                    return fn(data, self.language)
                return wrapper
            self.engine.register_handler(handler_name, make_wrapper(handler_fn))

    def _fire_skillup_started(self):
        """
        Fire on_skillup_started() on all non-subprocess in-process apps
        that implement the method.

        Called once after the desktop UI reports it is fully loaded.
        Apps that want startup behavior (e.g. daily fortune dialog) implement
        on_skillup_started() in their app class.
        """
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for app_id, app_info in self.apps.items():
            app_dir = os.path.join(script_dir, 'app', app_info.dir_name)
            app_ini_path = os.path.join(app_dir, 'app.ini')

            from configparser import ConfigParser as _CP
            _cfg = _CP()
            _cfg.read(app_ini_path, encoding='utf-8')

            # Only trigger for non-subprocess (in-process) apps
            if _cfg.getboolean('app', 'subprocess', fallback=False):
                continue

            # Lazily instantiate the app if not already created
            if app_id not in self._app_instances:
                try:
                    from lib.appmgr import load_app_module, get_app_class, AppContext
                    from lib.config import get_app_config_path

                    app_module = load_app_module(app_info.dir_name)
                    app_class = get_app_class(app_module)

                    if app_class is None:
                        continue

                    config_path = get_app_config_path(app_info.id, app_info.id_name)
                    context = AppContext(
                        mode='desktop', args=[],
                        config_path=config_path, app_id=app_info.id
                    )
                    app_instance = app_class(engine=self.engine, context=context)
                    ret = app_instance.on_run_desktop_initialize()
                    if ret and ret != 0:
                        continue
                    self._register_app_handlers_to_engine(app_instance)
                    self._app_instances[app_id] = app_instance
                except Exception as e:
                    log("error", message=f"Failed to initialize app {app_id} for startup: {e}",
                        tag="desktop")
                    continue

            app_instance = self._app_instances.get(app_id)
            if app_instance is None:
                continue

            if not hasattr(app_instance, 'on_skillup_started'):
                continue

            try:
                app_instance.on_skillup_started()
            except Exception as e:
                log("error", message=f"Error in on_skillup_started for {app_id}: {e}",
                    tag="desktop")

    def _generate_desktop_html(self) -> str:
        """Generate desktop HTML content"""
        desktop_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(desktop_dir, 'web', 'desktop.html')

        if not os.path.exists(html_path):
            raise FileNotFoundError(f"Desktop HTML not found: {html_path}")

        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _find_app_by_id_or_guid(self, identifier: str) -> Optional[str]:
        """
        Find app by ID or directory name.

        Args:
            identifier: App ID (8-char hex) or directory name (for backward compat)

        Returns:
            App ID if found, None otherwise
        """
        # Check if it's a direct app ID match
        if identifier in self.apps:
            return identifier

        # Check if it's a directory name match (backward compatibility)
        for app_id, app_info in self.apps.items():
            if app_info.dir_name == identifier or app_info.id_name == identifier:
                return app_id

        return None

    def run(self, auto_launch_app: str = None, app_extra_args: list = None):
        """
        Run the desktop.

        Args:
            auto_launch_app: App ID or GUID to launch automatically
            app_extra_args: Extra CLI args forwarded to the auto-launched app subprocess
        """
        # Resolve auto_launch_app (could be ID or GUID)
        auto_launch_app_id = None
        if auto_launch_app:
            auto_launch_app_id = self._find_app_by_id_or_guid(auto_launch_app)
            if not auto_launch_app_id:
                log("error", message=f"Auto-launch app not found: {auto_launch_app}")
                return 1

        # Load static files (desktop/common/ -> /common/ URL)
        desktop_dir = os.path.dirname(os.path.abspath(__file__))
        common_dir = os.path.join(desktop_dir, 'common')
        self.engine.add_static_files(common_dir, prefix='common')

        # desktop/web/script/ -> /desktop-web-script/ URL
        js_dir = os.path.join(desktop_dir, 'web', 'script')
        if os.path.exists(js_dir):
            self.engine.add_static_files(js_dir, prefix='desktop-web-script')

        # desktop/web/css/ -> /desktop-web-css/ URL
        css_dir = os.path.join(desktop_dir, 'web', 'css')
        if os.path.exists(css_dir):
            self.engine.add_static_files(css_dir, prefix='desktop-web-css')

        # desktop/help/data/ -> /desktop-help-data/ URL
        help_data_dir = os.path.join(desktop_dir, 'help', 'data')
        if os.path.exists(help_data_dir):
            self.engine.add_static_files(help_data_dir, prefix='desktop-help-data')

        # Add app static files
        for app_id, app_info in self.apps.items():
            # Add icon
            icon_path = app_info.get_icon_path()
            if os.path.exists(icon_path):
                ext = os.path.splitext(icon_path)[1].lower()
                content_type = 'image/svg+xml' if ext == '.svg' else 'image/png'
                try:
                    with open(icon_path, 'rb') as f:
                        self.engine.static_files[f'app/{app_id}/icon{ext}'] = (f.read(), content_type)
                except Exception:
                    pass

            # Add all files from app's web folder (recursive)
            web_dir = os.path.join(app_info.dir, 'web')
            if os.path.exists(web_dir):
                self.engine.add_static_files(web_dir, prefix=f'app/{app_id}')

        # Start server
        url = self.engine.start_server(index_html_generator=self._generate_desktop_html)
        log("info", message=f"Desktop running at {url}")

        # Start peerbus daemon in background so it doesn't block app subprocess startup
        import threading as _threading
        _threading.Thread(target=self._start_peerbus_daemon, daemon=True).start()

        # Detect standalone app mode (skip desktop shell entirely)
        # Currently supports --skillform-run=<path> → open runner.html directly
        standalone_url = None
        if auto_launch_app_id and app_extra_args:
            for _arg in app_extra_args:
                if _arg.startswith('--skillform-run='):
                    schema_path = os.path.expanduser(_arg[len('--skillform-run='):])
                    self._auto_launch_extra_args[auto_launch_app_id] = app_extra_args
                    self.current_app = auto_launch_app_id
                    self._standalone_mode = True
                    self._start_app_process(auto_launch_app_id)
                    _standalone_lang = 'en'
                    for _a in app_extra_args:
                        if _a.startswith('--lang='):
                            _standalone_lang = _a[len('--lang='):]
                    standalone_url = f'app/{auto_launch_app_id}/runner.html?standalone=1&lang={_standalone_lang}'
                    break

        if standalone_url:
            # Standalone mode: open app page directly, no desktop shell
            load_url = url.rstrip('/') + '/' + standalone_url
            log("info", message=f"Standalone mode: {load_url}")
        else:
            load_url = url
            # Handle auto-launch inside desktop shell
            if auto_launch_app_id:
                self.current_app = auto_launch_app_id
                log("info", message=f"Auto-launching app: {auto_launch_app_id}")
                if app_extra_args:
                    self._auto_launch_extra_args[auto_launch_app_id] = app_extra_args

        # Register QTimer for build update polling (60s interval)
        def _setup_update_timer(qt_app):
            try:
                try:
                    from PySide2.QtCore import QTimer  # type: ignore
                except ImportError:
                    from PySide6.QtCore import QTimer  # type: ignore
                timer = QTimer()
                timer.timeout.connect(self._check_build_update)
                timer.start(60000)
                self._update_timer = timer
            except Exception as e:
                log("warn", message=f"Failed to start update timer: {e}", tag="desktop")

        self.engine._qt_ready_callbacks.append(_setup_update_timer)

        # Run Qt
        try:
            return self.engine.run_qt(load_url)
        finally:
            # Record usage for any apps still open at shutdown
            for app_id in list(self._app_start_times.keys()):
                self._record_app_usage(app_id)

            # Call on_close for all in-process app instances
            for app_id, app_instance in list(self._app_instances.items()):
                try:
                    app_instance.on_close()
                except Exception as e:
                    log("error", message=f"Error calling on_close for {app_id}: {e}", tag="desktop")
            # Clean up all app subprocesses
            self._is_shutting_down = True
            log("info", message="Shutting down app subprocesses...")
            for app_id in list(self.app_processes.keys()):
                self._stop_app_process(app_id)


def run_desktop(auto_launch_app: str = None, app_extra_args: list = None, verbose: bool = False) -> int:
    """
    Run the Skillup Desktop.

    Args:
        auto_launch_app: App ID to launch automatically
        app_extra_args: Extra CLI args to pass to the auto-launched app subprocess
        verbose: Enable debug-level logging

    Returns:
        Exit code
    """
    if verbose:
        from lib.log import set_verbose
        set_verbose(True)
    manager = DesktopManager()
    return manager.run(auto_launch_app, app_extra_args=app_extra_args)
