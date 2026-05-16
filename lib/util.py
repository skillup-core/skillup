"""
Skillup Utility Functions

Provides utility functions for common operations like opening URLs in Firefox.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from lib.config import get_desktop_config


def browse_firefox(url_or_path: str, firefox_path: Optional[str] = None) -> bool:
    """
    Open a URL or local file path in Firefox.

    Supports:
    - HTTP/HTTPS URLs (e.g., https://example.com)
    - Local file paths (e.g., /path/to/file.html)
    - Local file paths with bookmarks (e.g., /path/to/file.html#section)

    Args:
        url_or_path: URL or local file path to open
        firefox_path: Optional explicit Firefox executable path.
                     If not provided, uses config value from general.firefox (default: "firefox")

    Returns:
        bool: True if Firefox was launched successfully, False otherwise

    Configuration:
        - Key: general.firefox
        - Default: "firefox" (PATH resolution)
        - Can be set to absolute path like "/usr/bin/firefox" or "/opt/firefox/firefox"

    Examples:
        # Open URL
        browse_firefox("https://example.com")

        # Open local file
        browse_firefox("/home/user/doc.html")

        # Open local file with bookmark
        browse_firefox("/home/user/doc.html#chapter2")

        # Explicit Firefox path
        browse_firefox("https://example.com", firefox_path="/opt/firefox/firefox")
    """
    try:
        # Get Firefox path from config if not provided explicitly
        if firefox_path is None:
            firefox_path = get_desktop_config('general.firefox', default='firefox')

        # For local file paths, check if file exists (excluding bookmark)
        if not _is_url(url_or_path):
            file_path = _extract_file_path(url_or_path)
            if not Path(file_path).exists():
                print(f"[error][Util] File not found: {file_path}", file=sys.stderr, flush=True)
                return False

            # Extract bookmark from original path if present
            bookmark = ''
            if '#' in url_or_path:
                bookmark = url_or_path.split('#', 1)[1]

            # Convert to file:// URL for Firefox
            file_url = Path(file_path).resolve().as_uri()

            # Append bookmark if it was present
            if bookmark:
                url_or_path = f"{file_url}#{bookmark}"
            else:
                url_or_path = file_url

        # Launch Firefox
        subprocess.Popen(
            [firefox_path, url_or_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Detach from parent process
        )

        return True

    except FileNotFoundError:
        print(f"[error][Util] Firefox not found: {firefox_path}", file=sys.stderr, flush=True)
        return False
    except Exception as e:
        print(f"[error][Util] Failed to launch Firefox: {e}", file=sys.stderr, flush=True)
        return False


def _is_url(path_or_url: str) -> bool:
    """
    Check if a string is a URL (starts with http://, https://, etc.).

    Args:
        path_or_url: String to check

    Returns:
        bool: True if it's a URL, False if it's a file path
    """
    return path_or_url.startswith(('http://', 'https://', 'ftp://', 'ftps://'))


def _extract_file_path(path_with_bookmark: str) -> str:
    """
    Extract file path from a string that may contain a bookmark (#...).

    Args:
        path_with_bookmark: File path possibly containing bookmark (e.g., "/path/to/file.html#section")

    Returns:
        str: File path without the bookmark
    """
    if '#' in path_with_bookmark:
        return path_with_bookmark.split('#', 1)[0]
    return path_with_bookmark
