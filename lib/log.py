"""
Skillup Logging Utility

Simple logging functions for console output with color support.
"""

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


def log(msg_type: str, line: Optional[int] = None, message: Optional[str] = None,
        tag: Optional[str] = None, return_string: bool = False) -> Optional[str]:
    """
    Print formatted colored log message.

    Args:
        msg_type: Type of message (info, warn, error)
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
    """
    # Choose color based on message type
    if msg_type == "info":
        prefix_color = Color.GREEN
    elif msg_type == "warn":
        prefix_color = Color.YELLOW
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
    else:
        print(output)
        return None
