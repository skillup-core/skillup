"""
Skillup Logging Utility

Simple logging functions for console output with color support.
"""

import os
import re
from typing import Optional


class Color:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


# ============================================================================
# Verbose mode (debug level enabled when True)
# ============================================================================

_verbose = False


def set_verbose(enabled: bool):
    global _verbose
    _verbose = enabled


def is_verbose() -> bool:
    return _verbose


# ============================================================================
# File logging state (lazy-initialized, module-level cache)
# ============================================================================

_file_log_initialized = False
_file_log_path: Optional[str] = None  # None means disabled


def _init_file_log():
    """Lazy-initialize file logging from desktop config."""
    global _file_log_initialized, _file_log_path
    _file_log_initialized = True

    try:
        from lib.config import get_desktop_config
        log_dir = get_desktop_config('general.user_log_dir', '').strip()
        if not log_dir:
            return

        user_name = os.environ.get('USER', os.environ.get('USERNAME', 'user'))
        user_log_dir = os.path.join(log_dir, user_name)
        os.makedirs(user_log_dir, exist_ok=True)
        _file_log_path = os.path.join(user_log_dir, 'log.txt')
    except Exception:
        pass


_ANSI_ESCAPE = re.compile(r'\033\[[0-9;]*m')

_LOG_ROTATE_BYTES = 256 * 1024  # 256 KB

_APP_USAGE_ROTATE_BYTES = 10 * 1024 * 1024  # 10 MB


def _format_duration(seconds: float) -> str:
    """Format duration: under 1 min -> Xs, under 1 hour -> Xmin, else HH:MM"""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m = s // 60
    if m < 60:
        return f"{m}min"
    return f"{m // 60:02d}:{m % 60:02d}"


def write_app_usage(account: str, appname: str, duration_seconds: float):
    """
    Append one app-usage record to {user_log_dir}/.stat/app-usage.txt.
    Rotates to app-usage.txt.old when the file exceeds 10 MB.
    """
    try:
        from lib.config import get_desktop_config
        log_dir = get_desktop_config('general.user_log_dir', '').strip()
        if not log_dir:
            return

        stat_dir = os.path.join(log_dir, '.stat')
        os.makedirs(stat_dir, exist_ok=True)
        usage_path = os.path.join(stat_dir, 'app-usage.txt')

        from datetime import datetime
        timestamp = datetime.now().strftime('[%y%m%d_%H:%M:%S]')
        duration_str = _format_duration(duration_seconds)
        line = f"{timestamp} account={account}, appname={appname}, duration={duration_str}"

        try:
            import fcntl
            lock_path = usage_path + '.lock'
            with open(lock_path, 'a') as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    try:
                        size = os.path.getsize(usage_path)
                    except OSError:
                        size = 0
                    if size >= _APP_USAGE_ROTATE_BYTES:
                        os.replace(usage_path, usage_path + '.old')
                    with open(usage_path, 'a', encoding='utf-8') as f:
                        f.write(line + '\n')
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
        except Exception:
            pass
    except Exception:
        pass


def _write_to_file(plain_line: str):
    """Append one log line to the user log file, rotating if over 4 KB."""
    if _file_log_path is None:
        return
    try:
        import fcntl
        lock_path = _file_log_path + '.lock'
        with open(lock_path, 'a') as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                # Rotate if log.txt >= 4 KB
                try:
                    size = os.path.getsize(_file_log_path)
                except OSError:
                    size = 0

                if size >= _LOG_ROTATE_BYTES:
                    old_path = _file_log_path[:-4] + '.old.txt'  # log.old.txt
                    os.replace(_file_log_path, old_path)

                with open(_file_log_path, 'a', encoding='utf-8') as f:
                    f.write(plain_line + '\n')
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
    except Exception:
        pass


def log(msg_type: str, line: Optional[int] = None, message: Optional[str] = None,
        tag: Optional[str] = None, return_string: bool = False) -> Optional[str]:
    """
    Print formatted colored log message.

    Args:
        msg_type: Type of message (info, warn, error, debug)
        line: Optional line number
        message: Log message text
        tag: Optional tag displayed in gray after msg_type (e.g., "web", "js", "qt")
        return_string: If True, return the formatted string instead of printing

    Returns:
        Formatted string if return_string=True, otherwise None

    Examples:
        log("info", message="Server started")
        log("warn", line=42, message="Deprecated function used")
        log("error", message="Failed to load file", tag="io")
        log("debug", message="Init complete", tag="web")
    """
    # debug messages are suppressed unless verbose mode is enabled
    if msg_type == "debug" and not _verbose:
        return None

    # Choose color based on message type
    if msg_type == "info":
        prefix_color = Color.GREEN
    elif msg_type == "warn":
        prefix_color = Color.YELLOW
    elif msg_type == "debug":
        prefix_color = Color.GRAY
    else:  # error
        prefix_color = Color.RED

    # Build output string
    output = f"{prefix_color}[{msg_type:5s}]{Color.RESET}"

    # Add tag if provided (e.g., [web])
    if tag is not None:
        output += f"{Color.GRAY}[{tag}]{Color.RESET}"

    # Add line number if provided
    if line is not None:
        output += f" line {Color.YELLOW}{line}{Color.RESET}:"

    # Add message
    if message is not None:
        if line is not None:
            output += f" {message}"
        else:
            output += f" {message}"

    # Return or print
    if return_string:
        return output

    print(output)

    # File logging (lazy init, strip ANSI, write with lock+rotation)
    if not _file_log_initialized:
        _init_file_log()
    if _file_log_path is not None:
        from datetime import datetime
        timestamp = datetime.now().strftime('[%y%m%d_%H:%M:%S]')
        _write_to_file(timestamp + ' ' + _ANSI_ESCAPE.sub('', output))

    return None
