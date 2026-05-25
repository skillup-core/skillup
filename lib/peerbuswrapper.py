"""
PeerbusWrapper — desktop/app-side client for the peerbus daemon.

Usage:
    from lib.peerbuswrapper import PeerbusWrapper

    wrapper = PeerbusWrapper()
    wrapper.register(desktop_id, app_id='chat', callback_port=17450)
    wrapper.on_message(lambda send_id, from_uid, from_ip, app_id, msg_type, payload: ...)
    result = wrapper.post('bob', 'chat', {'text': 'hello'})
    wrapper.unregister(desktop_id)
"""

import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, List, Optional
from urllib.parse import urlparse


def _get_sock_path() -> str:
    from lib.config import get_config_home
    return os.path.join(get_config_home(), 'peerbus', 'daemon.sock')


# ---------------------------------------------------------------------------
# HTTP over Unix domain socket
# ---------------------------------------------------------------------------

class _UnixSocketConnection(http.client.HTTPConnection):
    """HTTPConnection that connects to a Unix domain socket instead of TCP."""

    def __init__(self, sock_path: str):
        # host value is irrelevant for unix socket but HTTPConnection requires it
        super().__init__('localhost')
        self._sock_path = sock_path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self._sock_path)
        self.sock = s


def _unix_request(sock_path: str, method: str, path: str,
                  body: Optional[bytes] = None,
                  timeout: float = 10.0) -> Any:
    """Send a single HTTP request over a Unix domain socket. Returns parsed JSON."""
    conn = _UnixSocketConnection(sock_path)
    conn.timeout = timeout
    headers = {}
    if body is not None:
        headers['Content-Type'] = 'application/json'
        headers['Content-Length'] = str(len(body))
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    if resp.status >= 400:
        raise RuntimeError(f"peerbus REST {path} error {resp.status}: {data}")
    return json.loads(data) if data else None


# ---------------------------------------------------------------------------
# PeerbusWrapper
# ---------------------------------------------------------------------------

class PeerbusWrapper:
    """Desktop process-side wrapper around the peerbus daemon Unix socket API."""

    def __init__(self, sock_path: Optional[str] = None,
                 log_fn: Optional[Callable] = None):
        self._sock_path = sock_path or _get_sock_path()
        self._log_fn = log_fn
        self._message_callbacks: List[Callable] = []
        self._result_callbacks: List[Callable] = []
        self._callback_server: Optional[HTTPServer] = None
        self._callback_port: Optional[int] = None
        self._callback_thread: Optional[threading.Thread] = None
        self._desktop_id: Optional[str] = None
        self._app_id: Optional[str] = None
        self._registered_uptime: Optional[int] = None

    def _log(self, msg: str) -> None:
        if self._log_fn:
            self._log_fn(msg)
        else:
            print(f"[peerbus] {msg}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Daemon lifecycle
    # ------------------------------------------------------------------

    def _ensure_daemon(self) -> None:
        """Confirm daemon socket is live; start daemon via subprocess if not."""
        if os.path.exists(self._sock_path):
            # Socket file exists but daemon may have crashed without cleanup
            try:
                _unix_request(self._sock_path, 'GET', '/status', timeout=1)
                return  # daemon is alive
            except Exception:
                # Stale sock file from crashed daemon — remove and respawn
                try:
                    os.unlink(self._sock_path)
                except OSError:
                    pass

        skillup_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        peerbus_script = os.path.join(skillup_root, 'peerbus', 'peerbus.py')

        uid = self._get_uid()
        nfs_dir = self._get_nfs_dir(skillup_root)

        self._log(f"daemon not found, starting (uid={uid}, nfs_dir={nfs_dir})")

        proc = subprocess.Popen(
            [sys.executable, peerbus_script, '--uid', uid, '--nfs-dir', nfs_dir],
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=skillup_root,
        )
        self._log(f"daemon process spawned (subprocess PID: {proc.pid})")

        deadline = time.time() + 10
        while time.time() < deadline:
            time.sleep(0.2)
            if proc.poll() is not None:
                stderr_out = proc.stderr.read().decode(errors='replace').strip()
                raise RuntimeError(
                    f"peerbus daemon exited (code {proc.returncode}): {stderr_out}"
                )
            if os.path.exists(self._sock_path):
                self._log(f"daemon ready (sock: {self._sock_path})")
                return
        stderr_out = ''
        try:
            proc.kill()
            stderr_out = proc.stderr.read().decode(errors='replace').strip()
        except Exception:
            pass
        raise RuntimeError(
            f"peerbus daemon failed to start within 10 seconds: {stderr_out}"
        )

    def _is_daemon_alive(self) -> bool:
        if not os.path.exists(self._sock_path):
            return False
        try:
            _unix_request(self._sock_path, 'GET', '/status', timeout=2)
            return True
        except Exception:
            return False

    def _get_uid(self) -> str:
        import getpass
        return getpass.getuser()

    def _get_nfs_dir(self, skillup_root: str) -> str:
        from lib.config import _get_default_config_path, _expand_config_value
        import configparser

        default_path = _get_default_config_path()
        if default_path and os.path.exists(default_path):
            ini_dir = os.path.dirname(os.path.abspath(default_path))
            cp = configparser.ConfigParser()
            cp.read(default_path)
            raw = cp.get('desktop', 'general.peer_bus_nfs_dir', fallback=None)
            if raw:
                return _expand_config_value(raw, ini_dir)

        return os.path.join(skillup_root, 'desktop', 'peerbus', 'data')

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, desktop_id: str, app_id: str, callback_port: int = 0) -> int:
        """Start daemon if needed, start callback server, register desktop.

        Pass callback_port=0 (default) to let the OS assign a free port.
        Returns the actual port the callback server is listening on.
        """
        self._desktop_id = desktop_id
        self._app_id = app_id
        self._ensure_daemon()
        actual_port = self._start_callback_server(callback_port)
        self._post_json('/desktops/register', {
            'desktop_id':    desktop_id,
            'app_id':        app_id,
            'callback_port': actual_port,
        })
        try:
            status = _unix_request(self._sock_path, 'GET', '/status', timeout=2)
            self._registered_uptime = status.get('uptime')
        except Exception:
            self._registered_uptime = None
        return actual_port

    def unregister(self, desktop_id: str) -> None:
        self._delete(f'/desktops/{desktop_id}')
        self._stop_callback_server()

    def ensure_registered(self) -> None:
        """Re-register if daemon restarted since last register (uptime reset).

        Call once at app startup after register(). If the daemon was restarted
        (e.g. build update) between register() and this call, uptime will be
        lower than recorded — re-register to restore message delivery.
        """
        if self._registered_uptime is None:
            return
        if not self._desktop_id or not self._app_id or not self._callback_port:
            return
        try:
            status = _unix_request(self._sock_path, 'GET', '/status', timeout=2)
            current_uptime = status.get('uptime', 0)
        except Exception:
            return
        if current_uptime < self._registered_uptime:
            self._log(
                f"daemon restarted detected (uptime {self._registered_uptime}s -> "
                f"{current_uptime}s), re-registering desktop_id={self._desktop_id}"
            )
            try:
                self._post_json('/desktops/register', {
                    'desktop_id':    self._desktop_id,
                    'app_id':        self._app_id,
                    'callback_port': self._callback_port,
                })
                self._registered_uptime = current_uptime
            except Exception as e:
                self._log(f"re-register failed: {e}")

    # ------------------------------------------------------------------
    # Callback server (daemon -> desktop push)
    # ------------------------------------------------------------------

    def _start_callback_server(self, port: int) -> int:
        """Start the callback HTTP server. Returns the actual listening port."""
        if self._callback_server is not None:
            return self._callback_port
        wrapper = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def _read_body(self) -> dict:
                length = int(self.headers.get('Content-Length', 0))
                return json.loads(self.rfile.read(length)) if length else {}

            def _send_ok(self):
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')

            def do_POST(self):
                body   = self._read_body()
                parsed = urlparse(self.path)

                if parsed.path == '/message':
                    event = body.get('event')
                    if event == 'daemon_restarting':
                        threading.Thread(
                            target=wrapper._handle_daemon_restarting,
                            daemon=True).start()
                    else:
                        for cb in list(wrapper._message_callbacks):
                            try:
                                cb(
                                    body.get('send_id'),
                                    body.get('from_uid'),
                                    body.get('from_ip'),
                                    body.get('app_id'),
                                    body.get('msg_type'),
                                    body.get('payload'),
                                )
                            except Exception:
                                pass
                elif parsed.path == '/result':
                    for cb in list(wrapper._result_callbacks):
                        try:
                            cb(
                                body.get('send_id'),
                                body.get('status'),
                                body.get('result'),
                            )
                        except Exception:
                            pass
                self._send_ok()

        # port=0 lets the OS assign a free port, avoiding TOCTOU races.
        self._callback_server = HTTPServer(('127.0.0.1', port), Handler)
        self._callback_port   = self._callback_server.server_address[1]
        self._callback_thread = threading.Thread(
            target=self._callback_server.serve_forever, daemon=True)
        self._callback_thread.start()
        return self._callback_port

    def _stop_callback_server(self) -> None:
        if self._callback_server:
            self._callback_server.shutdown()
            self._callback_server = None

    def _handle_daemon_restarting(self) -> None:
        """Wait for daemon to come back up, then re-register."""
        time.sleep(3)
        deadline = time.time() + 15
        while time.time() < deadline:
            if os.path.exists(self._sock_path):
                try:
                    if self._desktop_id and self._app_id and self._callback_port:
                        self._post_json('/desktops/register', {
                            'desktop_id':    self._desktop_id,
                            'app_id':        self._app_id,
                            'callback_port': self._callback_port,
                        })
                    return
                except Exception:
                    pass
            time.sleep(0.5)

    # ------------------------------------------------------------------
    # Message send
    # ------------------------------------------------------------------

    def post(self, to_uid: str, app_id: str, payload: dict,
             to_ip: Optional[str] = None,
             target_mode: str = 'SINGLE',
             desktop_id: Optional[str] = None,
             wait_for: str = 'delivered',
             timeout_ms: int = 5000,
             queue_offline: bool = False) -> dict:
        return self._send_msg('postmessage', to_uid, app_id, payload,
                              to_ip, target_mode, desktop_id, wait_for, timeout_ms,
                              queue_offline)

    def send(self, to_uid: str, app_id: str, payload: dict,
             to_ip: Optional[str] = None,
             target_mode: str = 'SINGLE',
             desktop_id: Optional[str] = None,
             wait_for: str = 'delivered',
             timeout_ms: int = 5000,
             queue_offline: bool = False) -> dict:
        return self._send_msg('sendmessage', to_uid, app_id, payload,
                              to_ip, target_mode, desktop_id, wait_for, timeout_ms,
                              queue_offline)

    def _send_msg(self, msg_type: str, to_uid: str, app_id: str, payload: dict,
                  to_ip: Optional[str], target_mode: str,
                  desktop_id: Optional[str],
                  wait_for: str, timeout_ms: int,
                  queue_offline: bool = False) -> dict:
        send_id = str(uuid.uuid4())
        body: dict = {
            'send_id':       send_id,
            'to_uid':        to_uid,
            'app_id':        app_id,
            'target_mode':   target_mode,
            'desktop_id':    desktop_id,
            'msg_type':      msg_type,
            'payload':       payload,
            'wait_for':      wait_for,
            'timeout_ms':    timeout_ms,
            'queue_offline': queue_offline,
        }
        if to_ip is not None:
            body['to_ip'] = to_ip
        # allow extra 3s for daemon overhead on top of the requested timeout
        http_timeout = max(timeout_ms / 1000.0 + 3, 10)
        try:
            return self._post_json('/send', body, timeout=http_timeout)
        except Exception:
            self._ensure_daemon()
            return self._post_json('/send', body, timeout=http_timeout)

    # ------------------------------------------------------------------
    # Peer list
    # ------------------------------------------------------------------

    def get_peers(self) -> list:
        return self._get_json('/peers')

    def get_presence(self, peers: list) -> list:
        """Check presence for specific (uid, ip) pairs without a full scandir.

        peers: [{'uid': 'alice', 'ip': '1.1.1.1'}, ...]
        return: [{'uid', 'ip', 'tcp_port', 'online', 'ts'}, ...]
        """
        if not peers:
            return []
        param = ','.join(f"{p['uid']}@{p['ip']}" for p in peers)
        return self._get_json(f'/presence?peers={param}')

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_message(self, callback: Callable) -> None:
        """Register callback(send_id, from_uid, from_ip, app_id, msg_type, payload)."""
        self._message_callbacks.append(callback)

    def on_result(self, callback: Callable) -> None:
        """Register callback(send_id, status, result)."""
        self._result_callbacks.append(callback)

    # ------------------------------------------------------------------
    # HTTP helpers (Unix socket)
    # ------------------------------------------------------------------

    def _post_json(self, path: str, body: dict, timeout: float = 10.0) -> Any:
        data = json.dumps(body).encode()
        return _unix_request(self._sock_path, 'POST', path, body=data, timeout=timeout)

    def _get_json(self, path: str) -> Any:
        return _unix_request(self._sock_path, 'GET', path, timeout=5)

    def _delete(self, path: str) -> None:
        try:
            _unix_request(self._sock_path, 'DELETE', path, timeout=0.3)
        except Exception:
            pass
