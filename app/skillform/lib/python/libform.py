"""
libform.py - SkillForm Python caller library

Stdlib-only. Launches a skillform GUI and delivers button events
to a callback function.

Usage:
    from libform import SkillForm

    def on_event(form, ev):
        print(ev)
        if ev.get('type') == 'button_click' and ev['button_id'] == 'ok':
            form.close()

    SkillForm('myform.json').run(on_event)
"""

import os
import json
import socket
import subprocess
import sys
from pathlib import Path

# ANSI color codes
_GREEN  = '\033[32m'
_YELLOW = '\033[33m'
_RED    = '\033[31m'
_BLUE   = '\033[34m'
_RESET  = '\033[0m'

def _log(level, msg):
    if level == 'info':
        level_str = f'{_GREEN}[info]{_RESET}'
    elif level == 'warn':
        level_str = f'{_YELLOW}[warn]{_RESET}'
    else:
        level_str = f'{_RED}[error]{_RESET}'
    print(f'{level_str}{_BLUE}[skillform]{_RESET} {msg}', file=sys.stderr)


def _find_skillup_py(start=None):
    """Walk up from start (default: this file) to find skillup.py"""
    path = Path(start or __file__).resolve()
    for parent in path.parents:
        candidate = parent / 'skillup.py'
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        'skillup.py not found. Set skillup_py= explicitly or run from inside the repo.')


class SkillForm:
    """
    Launch a skillform GUI window and receive button events.

    Parameters
    ----------
    form_path : str
        Path to the JSON form schema file.
    skillup_py : str, optional
        Path to skillup.py. Auto-detected from this file's location if omitted.
    """

    def __init__(self, form_path, skillup_py=None):
        self.form_path = os.path.abspath(form_path)
        self.skillup_py = skillup_py or _find_skillup_py()
        self._srv = None
        self._conn = None
        self._proc = None

    def run(self, on_event):
        """
        Open the form window and block until the connection closes.

        on_event(form, ev) is called for each event from the GUI:
          - ev['type'] == 'ready'          -- window is up
          - ev['type'] == 'button_click'   -- button pressed
              ev['button_id']              -- field id of the button
              ev['values']                 -- dict of all form field values
          - ev['type'] == 'window_closed'  -- user closed the window

        Call form.close() inside on_event to send a close command to the GUI.
        """
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(('127.0.0.1', 0))
        self._srv.listen(1)
        port = self._srv.getsockname()[1]

        _log('info', f'launching skillform on port {port}: {os.path.basename(self.form_path)}')
        self._proc = subprocess.Popen(
            [sys.executable, self.skillup_py,
             '--desktop', '--app:skillform',
             f'--skillform-run={self.form_path}',
             f'--skillform-caller-port={port}'],
            stdout=subprocess.DEVNULL,
            stderr=None,  # inherit stderr so [warn]/[error] messages reach console
        )

        try:
            self._srv.settimeout(30)
            self._conn, _ = self._srv.accept()
            self._srv.settimeout(None)
            _log('info', 'connected')
        except socket.timeout:
            self._cleanup()
            _log('error', 'skillform did not connect within 30 seconds')
            raise TimeoutError('skillform did not connect within 30 seconds')

        try:
            for line in self._conn.makefile('r', encoding='utf-8'):
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                on_event(self, ev)
        finally:
            self._cleanup()

    def save_values(self, values: dict, path: str):
        """Save form field values to a JSON file."""
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(values, f, ensure_ascii=False, indent=2)
            _log('info', f'saved to {path}')
        except Exception as e:
            _log('warn', f'save_values failed: {e}')

    def load_values(self, path: str) -> dict:
        """Load form field values from a JSON file. Returns {} if file missing."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                values = json.load(f)
            _log('info', f'loaded from {path}')
            return values
        except FileNotFoundError:
            _log('warn', f'no saved file: {path}')
            return {}
        except Exception as e:
            _log('warn', f'load_values failed: {e}')
            return {}

    def set_values(self, values: dict):
        """Send updated field values to the form window."""
        if self._conn:
            try:
                self._conn.sendall((json.dumps({'type': 'set_values', 'values': values}) + '\n').encode('utf-8'))
            except Exception:
                _log('warn', 'set_values send failed')

    def close(self):
        """Send close command to the form window."""
        if self._conn:
            try:
                self._conn.sendall(b'{"type":"close"}\n')
                _log('info', 'close sent')
            except Exception:
                _log('warn', 'close send failed (connection already closed?)')

    def _cleanup(self):
        for obj in (self._conn, self._srv):
            if obj:
                try:
                    obj.close()
                except Exception:
                    pass
        self._conn = None
        self._srv = None
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
