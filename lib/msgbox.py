#!/usr/bin/env python3
"""
Message Box Utility

Provides a simple show() function to display message dialogs.
Automatically detects subprocess/desktop context and routes accordingly.

Usage:
    from lib.msgbox import show as msgbox_show

    # Simple string
    msgbox_show("Error", "File not found")

    # Multi-language dict (auto-detects desktop language)
    msgbox_show(
        {"en": "Error", "ko": "오류"},
        {"en": "File not found", "ko": "파일을 찾을 수 없습니다"}
    )

Setup (for in-process desktop mode):
    from lib.msgbox import set_engine
    set_engine(webui_engine)  # Call once during desktop initialization
"""

import sys
import json
import os


# Module-level engine reference for in-process desktop mode
_engine = None


def set_engine(engine):
    """
    Register the WebUI engine for in-process desktop mode.
    Call this once during desktop initialization so that show()
    can route messages via QWebChannel bridge.

    Args:
        engine: WebUIEngine instance (must have .bridge attribute)
    """
    global _engine
    _engine = engine


def _get_text(text_value, language=None):
    """
    Extract language-specific text from string or dict.

    Args:
        text_value: Either a string or dict like {"en": "...", "ko": "..."}
        language: Current language ('en' or 'ko'), or None to use desktop config

    Returns:
        str: The appropriate text for the current language
    """
    if isinstance(text_value, str):
        return text_value
    elif isinstance(text_value, dict):
        # If language is explicitly provided, use it
        if language and language in text_value:
            return text_value[language]

        # Otherwise, use desktop config language
        try:
            from lib.config import get_desktop_config
            desktop_lang = get_desktop_config('general.language', 'en')
            if desktop_lang in text_value:
                return text_value[desktop_lang]
        except Exception:
            pass

        # Fallback to 'en', then any available
        return text_value.get('en', next(iter(text_value.values()), ''))
    else:
        return str(text_value)


def _is_subprocess():
    """
    Detect if running in subprocess mode.

    Returns:
        bool: True if running as subprocess, False if running in desktop
    """
    # Check if we're running as subprocess by looking for JSON-RPC environment
    # In subprocess mode, stdout is used for JSON-RPC communication
    # We can detect this by checking if SKILLUP_SUBPROCESS env var is set
    # or by checking if parent process is desktop

    # Simple heuristic: if stdin is connected to a pipe (not a tty), we're likely a subprocess
    return not sys.stdin.isatty()


def _send_notification(method, params=None):
    """
    Send JSON-RPC notification to desktop process (subprocess mode).

    Args:
        method: Method name
        params: Parameters dict
    """
    notification = {
        'jsonrpc': '2.0',
        'method': method,
        'params': params or {}
    }

    # Write to stdout with newline
    print(json.dumps(notification), flush=True)


def confirm(title, text, callback, language=None):
    """
    Display a Yes/No confirm dialog and invoke callback with result.

    In in-process desktop mode, sends 'showConfirmBox' event to JavaScript.
    JavaScript is expected to show a confirm dialog and call Python back
    with the result via the registered 'confirm_result' handler.

    This function is fire-and-forget from Python's perspective.
    The callback is stored and invoked when JavaScript responds.

    Args:
        title: Dialog title (string or dict with 'en'/'ko' keys)
        text: Dialog message (string or dict with 'en'/'ko' keys)
        callback: Function(confirmed: bool) called with True (Yes) or False (No)
        language: Current language ('en' or 'ko'), or None to use desktop config

    Note:
        Subprocess mode is not supported for confirm dialogs since it requires
        a two-way communication channel. In subprocess mode, this logs a warning.

    Example:
        def on_confirm(confirmed):
            if confirmed:
                do_delete()

        confirm("Delete", "Are you sure?", on_confirm)
    """
    import uuid

    title_text = _get_text(title, language)
    message_text = _get_text(text, language)
    confirm_id = str(uuid.uuid4())

    if _is_subprocess():
        print(f"[warn ][msgbox] confirm() is not supported in subprocess mode", file=sys.stderr, flush=True)
        return

    if _engine and _engine.bridge:
        # Store callback for later invocation
        _pending_confirms[confirm_id] = callback
        _engine.bridge.callJS.emit('showConfirmBox', json.dumps({
            'confirm_id': confirm_id,
            'title': title_text,
            'text': message_text
        }))
    else:
        print(f"[warn ][msgbox] confirm() called but no engine available: {title_text}: {message_text}", file=sys.stderr, flush=True)


def handle_confirm_result(confirm_id, confirmed):
    """
    Called by desktop when user responds to a confirm dialog.

    Args:
        confirm_id: The ID returned in showConfirmBox event
        confirmed: True if user clicked Yes, False if No
    """
    callback = _pending_confirms.pop(confirm_id, None)
    if callback:
        try:
            callback(confirmed)
        except Exception as e:
            print(f"[error][msgbox] confirm callback error: {e}", file=sys.stderr, flush=True)


# Pending confirm callbacks: {confirm_id: callback}
_pending_confirms = {}


def show(title, text, language=None):
    """
    Display a message box dialog.

    This function works in all contexts:
    - Subprocess mode: sends JSON-RPC notification to desktop via stdout
    - In-process desktop mode: calls JavaScript showMessageBox via QWebChannel bridge
    - Fallback: prints to stderr if no bridge available

    Args:
        title: Dialog title (string or dict with 'en'/'ko' keys)
        text: Dialog message (string or dict with 'en'/'ko' keys)
        language: Current language ('en' or 'ko'), or None to use desktop config

    Example:
        # Simple string
        show("Error", "File not found")

        # Multi-language dict (uses desktop language if language=None)
        show(
            {"en": "Error", "ko": "오류"},
            {"en": "File not found", "ko": "파일을 찾을 수 없습니다"}
        )

        # Multi-language dict with explicit language
        show(
            {"en": "Error", "ko": "오류"},
            {"en": "File not found", "ko": "파일을 찾을 수 없습니다"},
            language='ko'
        )
    """
    # Extract language-specific text
    title_text = _get_text(title, language)
    message_text = _get_text(text, language)

    if _is_subprocess():
        # Subprocess mode: send notification to desktop
        _send_notification('msgbox', {
            'title': title_text,
            'text': message_text
        })
    elif _engine and _engine.bridge:
        # In-process desktop mode: call JavaScript directly via bridge
        _engine.bridge.callJS.emit('showMessageBox', json.dumps({
            'title': title_text,
            'text': message_text
        }))
    else:
        # Fallback: print to stderr
        print(f"[msgbox] {title_text}: {message_text}", file=sys.stderr, flush=True)
