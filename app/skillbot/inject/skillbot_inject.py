"""
SkillBot Debug IPC Service

Exposes a REST API that:
 - Receives debug events from Virtuoso CIW via curl callbacks:
     GET /debug_break/<line>        — breakpoint hit
     GET /debug_end[?result=<val>]  — procedure returned
     POST /debug_eval_result        — eval result from _sbDbgEval()
 - Injects commands back into CIW via xdotool (clipboard paste + key events).

No stdin/stdout IPC (ipcBeginProcess) is used.

Usage:
    python3 skillbot_inject.py --port PORT --log-file PATH [--virt-pid PID]

The port is chosen by skillbot.py and passed as --port.
"""

import sys
import os
import json
import threading
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Set by main() so handlers and _log() can use them
_ipc_virt_pid = 0
_ipc_log_file = ""
_ipc_assigned_port = 0   # REST API port this process is listening on


def _log(msg, level="info"):
    prefix = "[error]" if level == "error" else "[warn ]" if level == "warn" else ""
    print(f"{prefix}[SkillBot IPC] {msg}", file=sys.stderr, flush=True)


# ─── File-based code injection ───────────────────────────────────────────────

def _get_tmp_log_base():
    """Return the CDS.log variant name (e.g. 'CDS.log' or 'CDS.log.1').

    Uses _ipc_log_file basename if available, otherwise falls back to the
    CIW window title to extract the CDS.log variant name.
    """
    log_base = None

    if _ipc_log_file:
        log_base = os.path.basename(_ipc_log_file)

    if not log_base:
        # Try to extract from cached CIW window title
        if _ciw_win_cache:
            try:
                title = _ciw_win_cache.get_wm_name()
                if title:
                    import re
                    m = re.search(r'(CDS\.log(?:\.\d+)?)', str(title))
                    if m:
                        log_base = m.group(1)
            except Exception:
                pass

    if not log_base:
        log_base = "CDS.log"

    return log_base


def _get_tmp_il_path():
    """Return the path to /tmp/skillbot/<log_base>.il for file-based injection.

    Kept for backward compatibility (restore path derivation).
    """
    log_base = _get_tmp_log_base()
    tmp_dir = os.path.join("/tmp", "skillbot")
    os.makedirs(tmp_dir, exist_ok=True)
    return os.path.join(tmp_dir, log_base + ".il")


def _write_and_load(code, tag="code", log_file=None):
    """Write SKILL code to a temp file and return a load() command.

    Writes the code to /tmp/skillbot/debug/<CDS.log name>/<tag>.il and
    returns load("...") to minimize data injected via clipboard/X11.

    e.g. /tmp/skillbot/debug/CDS.log.1/setup.il
         /tmp/skillbot/debug/CDS.log.1/code.il

    log_file: optional CDS.log name override (used when called from main process
              which doesn't have _ipc_log_file set)
    """
    if log_file:
        import re as _re
        m = _re.search(r'(CDS\.log(?:\.\d+)?)', log_file)
        log_base = m.group(1) if m else log_file
    else:
        log_base = _get_tmp_log_base()
    tmp_dir = os.path.join("/tmp", "skillbot", "debug", log_base)
    os.makedirs(tmp_dir, exist_ok=True)
    il_path = os.path.join(tmp_dir, f"{tag}.il")

    with open(il_path, 'w') as f:
        f.write(code)
    _log(f"wrote {len(code)} bytes to {il_path}")
    return f'load("{il_path}")'


# ─── xdotool path ─────────────────────────────────────────────────────────────

# Prefer the bundled xdotool binary; fall back to system-installed one.
_XDOTOOL = os.path.join(os.path.dirname(__file__), '..', 'bin', 'xdotool')
if not os.path.isfile(_XDOTOOL):
    _XDOTOOL = 'xdotool'


# ─── X11 CIW window detection ─────────────────────────────────────────────────

# Cached CIW window (avoids repeated window tree traversal)
_ciw_win_cache = None


def _find_by_pid(d, pid):
    """Find top-level X11 window by _NET_WM_PID atom."""
    try:
        from Xlib import Xatom
        root = d.screen().root
        client_list_atom = d.intern_atom('_NET_CLIENT_LIST')
        pid_atom = d.intern_atom('_NET_WM_PID')
        prop = root.get_full_property(client_list_atom, Xatom.WINDOW)
        if not prop:
            return None
        for wid in prop.value:
            try:
                w = d.create_resource_object('window', wid)
                p = w.get_full_property(pid_atom, Xatom.CARDINAL)
                if p and p.value[0] == pid:
                    return w
            except Exception:
                pass
    except Exception:
        pass
    return None


def _find_ciw_window(d, log_file=""):
    """Find the CIW window by title containing a CDS.log variant.

    Returns the first matching X window, or None.
    """
    candidates = []
    if log_file:
        base = os.path.basename(log_file)
        if base not in candidates:
            candidates.append(base)
    for suffix in ("", ".1", ".2", ".3", ".4", ".5"):
        name = "CDS.log" + suffix
        if name not in candidates:
            candidates.append(name)

    root = d.screen().root

    def _search_tree(window, title_substring):
        try:
            name = window.get_wm_name()
            if name and title_substring in str(name):
                return window
        except Exception:
            pass
        try:
            for child in window.query_tree().children:
                result = _search_tree(child, title_substring)
                if result:
                    return result
        except Exception:
            pass
        return None

    for title_sub in candidates:
        win = _search_tree(root, title_sub)
        if win:
            return win
    return None


def find_all_ciw_windows():
    """Return list of all CIW windows found via X11.

    Each entry: {"window_id": int, "title": str, "pid": int}
    Used by skillbot.py to let the user select which CIW to connect to.
    """
    results = []
    try:
        from Xlib import display as _display, Xatom
        disp_name = os.environ.get('DISPLAY', ':0')
        d = _display.Display(disp_name)
    except Exception:
        return results

    try:
        root = d.screen().root
        client_list_atom = d.intern_atom('_NET_CLIENT_LIST')
        pid_atom = d.intern_atom('_NET_WM_PID')
        prop = root.get_full_property(client_list_atom, Xatom.WINDOW)
        if not prop:
            d.close()
            return results

        for wid in prop.value:
            try:
                w = d.create_resource_object('window', wid)
                name = w.get_wm_name()
                if name and 'CDS.log' in str(name):
                    pid = 0
                    p = w.get_full_property(pid_atom, Xatom.CARDINAL)
                    if p:
                        pid = p.value[0]
                    results.append({"window_id": wid, "title": str(name), "pid": pid})
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            d.close()
        except Exception:
            pass
    return results



def _check_ciw_desktop(log_file="", window_id=None):
    """Check that the CIW window is on the same OS virtual desktop.

    Returns (ok, ciw_desktop, current_desktop).
    ok=True means check passed or could not be determined.
    If window_id is provided, checks that specific window directly.
    """
    try:
        from Xlib import display as _display, Xatom
    except ImportError:
        return True, None, None

    try:
        disp_name = os.environ.get('DISPLAY', ':0')
        d = _display.Display(disp_name)
    except Exception:
        return True, None, None

    try:
        root = d.screen().root

        current_desktop_atom = d.intern_atom('_NET_CURRENT_DESKTOP')
        cur_prop = root.get_full_property(current_desktop_atom, Xatom.CARDINAL)
        current_desktop = cur_prop.value[0] if cur_prop else None

        ciw_win = None
        if window_id is not None:
            try:
                ciw_win = d.create_resource_object('window', window_id)
            except Exception:
                ciw_win = None

        if ciw_win is None:
            client_list_atom = d.intern_atom('_NET_CLIENT_LIST')
            prop = root.get_full_property(client_list_atom, Xatom.WINDOW)
            if not prop:
                d.close()
                return True, None, None

            # If log_file given, match by exact basename (e.g. "CDS.log.1")
            log_basename = os.path.basename(log_file) if log_file else None

            for wid in prop.value:
                try:
                    w = d.create_resource_object('window', wid)
                    name = w.get_wm_name()
                    if not name:
                        continue
                    name_str = str(name)
                    if log_basename:
                        if log_basename in name_str:
                            ciw_win = w
                            break
                    elif 'CDS.log' in name_str:
                        ciw_win = w
                        break
                except Exception:
                    pass

        if not ciw_win:
            d.close()
            return True, None, None

        ciw_desktop_atom = d.intern_atom('_NET_WM_DESKTOP')
        ciw_prop = ciw_win.get_full_property(ciw_desktop_atom, Xatom.CARDINAL)
        ciw_desktop = ciw_prop.value[0] if ciw_prop else None

        d.close()

        if current_desktop is not None and ciw_desktop is not None and ciw_desktop != current_desktop:
            return False, ciw_desktop, current_desktop
        return True, ciw_desktop, current_desktop
    except Exception:
        try:
            d.close()
        except Exception:
            pass
        return True, None, None


def _xdotool(*args, input_data=None, timeout=5):
    """Run xdotool with the given arguments. Returns (returncode, stdout, stderr)."""
    import subprocess as _sp
    cmd = [_XDOTOOL] + list(args)
    result = _sp.run(cmd, input=input_data, capture_output=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def _set_clipboard(text):
    """Set X11 CLIPBOARD to text via python-xlib SelectionOwner.

    Spawns a daemon thread that serves SelectionRequest events for up to 5 s,
    which is enough time for a single Ctrl+V paste to complete.
    Returns True if ownership was acquired, False otherwise.
    """
    try:
        from Xlib import X, display as _display, Xatom
    except ImportError:
        return False
    try:
        cd = _display.Display(os.environ.get('DISPLAY', ':0'))
    except Exception:
        return False

    CLIPBOARD   = cd.intern_atom('CLIPBOARD')
    UTF8_STRING = cd.intern_atom('UTF8_STRING')
    TARGETS     = cd.intern_atom('TARGETS')
    text_bytes  = text.encode('utf-8')

    screen = cd.screen()
    try:
        owner = screen.root.create_window(
            0, 0, 1, 1, 0, screen.root_depth, X.InputOutput, X.CopyFromParent)
        owner.set_selection_owner(CLIPBOARD, X.CurrentTime)
        cd.flush()
    except Exception:
        cd.close()
        return False

    if cd.get_selection_owner(CLIPBOARD) != owner:
        owner.destroy()
        cd.close()
        return False

    def _serve():
        from Xlib.protocol import event as _ev
        import time as _t
        try:
            deadline = _t.time() + 5.0
            while _t.time() < deadline:
                while cd.pending_events():
                    e = cd.next_event()
                    if e.type == X.SelectionRequest:
                        prop = e.property if e.property != X.NONE else e.target
                        if e.target in (UTF8_STRING, Xatom.STRING):
                            e.requestor.change_property(prop, UTF8_STRING, 8, text_bytes)
                        elif e.target == TARGETS:
                            e.requestor.change_property(
                                prop, Xatom.ATOM, 32, [TARGETS, UTF8_STRING])
                        else:
                            prop = X.NONE
                        reply = _ev.SelectionNotify(
                            time=e.time, requestor=e.requestor,
                            selection=e.selection, target=e.target, property=prop)
                        e.requestor.send_event(reply)
                        cd.flush()
                    elif e.type == X.SelectionClear:
                        return
                _t.sleep(0.02)
        except Exception:
            pass
        finally:
            try:
                owner.destroy()
                cd.close()
            except Exception:
                pass

    threading.Thread(target=_serve, daemon=True).start()
    return True


def _is_wayland():
    """Return True if running under Wayland (XWayland bridge)."""
    return bool(os.environ.get('WAYLAND_DISPLAY'))


# Modifier keycodes (Shift_L/R, Control_L/R, Alt_L, Super_L/R)
_MODIFIER_KEYCODES = (50, 62, 37, 105, 64, 108, 133, 134)


def _wait_modifiers_released(timeout=1.5):
    """Block until all modifier keys are physically released, or timeout.

    Uses XQueryKeymap to poll the real keyboard state.  This ensures that
    hotkey modifiers (e.g. Shift from Shift+F5) are fully released before
    xdotool key events are sent, preventing unintended key combinations.
    """
    import time as _t
    try:
        from Xlib import display as _display
        d = _display.Display(os.environ.get('DISPLAY', ':0'))
    except Exception:
        _t.sleep(0.2)  # fallback
        return
    try:
        deadline = _t.time() + timeout
        while _t.time() < deadline:
            km = d.query_keymap()
            if not any(km[kc >> 3] & (1 << (kc & 7)) for kc in _MODIFIER_KEYCODES):
                return
            _t.sleep(0.02)
        _log("modifier keys still held after timeout — proceeding anyway", "warn")
    except Exception:
        _t.sleep(0.2)
    finally:
        try:
            d.close()
        except Exception:
            pass


# Sentinel: None = unchecked, True = permission granted, False = never granted
_xdotool_permitted = None


def _wait_for_xdotool_permission(timeout_sec=60):
    """On Wayland, xdotool blocks (hangs) until the user clicks Allow in the
    'Remote Interaction' dialog.  If the user clicks Cancel xdotool keeps
    blocking indefinitely; if Allow is clicked it completes immediately.

    Strategy: run `xdotool key 0x0` (no-op keysym, sends no actual key events)
    with a short per-attempt timeout.
    - Completes within timeout  → user clicked Allow → permission granted.
    - subprocess.TimeoutExpired → still waiting (dialog open or cancelled).
    Poll until total timeout_sec elapses, then raise RuntimeError.

    0x0 is used instead of a real key (e.g. 'shift') to avoid the
    keydown-without-keyup stuck-modifier bug when the process is killed while
    the Wayland permission dialog is still pending.
    """
    global _xdotool_permitted
    if _xdotool_permitted:
        return True

    import subprocess as _sp
    import time as _time

    _log("Wayland detected — waiting for 'Allow Remote Interaction' approval "
         f"(timeout {timeout_sec}s) ...")

    deadline = _time.time() + timeout_sec
    probe_timeout = 2.0  # seconds per attempt before treating as "still pending"
    while _time.time() < deadline:
        try:
            # 0x0 keysym: xdotool accepts it but sends no key events — safe to
            # kill at any point without leaving a modifier stuck in X11.
            _xdotool('key', '0x0', timeout=probe_timeout)
            # Completed within timeout → Allow was clicked
            _xdotool_permitted = True
            _log("xdotool permission granted")
            return True
        except _sp.TimeoutExpired as e:
            # Still blocking — kill the hung probe process and retry
            try:
                e.process.kill()
                e.process.wait()
            except Exception:
                pass
            # no sleep needed: the probe itself consumed probe_timeout seconds

    raise RuntimeError(
        "Wayland 'Allow Remote Interaction' was not approved within "
        f"{timeout_sec} seconds — debug session cancelled.")


def _inject_text_to_ciw(text, log_file="", window_id=None):
    """Inject text followed by Enter into the Virtuoso CIW input field via xdotool.

    Window detection uses python-xlib (PID-based then title-based search) to
    identify the correct CIW window among multiple candidates — the same logic
    as before.  All key events and clipboard operations use xdotool.

    If window_id is provided, that specific X11 window is used directly.

    Returns True on success, False if CIW not found.
    """
    import time as _time

    _log(f"inject: {text!r}")

    # On Wayland, xdotool requires user approval via 'Allow Remote Interaction'
    # dialog before it can send key events.  Block until approved or timeout.
    if _is_wayland():
        try:
            _wait_for_xdotool_permission()
        except RuntimeError as e:
            _log(str(e), "error")
            return False

    try:
        from Xlib import display as _display
    except ImportError:
        _log("FAIL: python-xlib not installed", "error")
        return False

    try:
        disp_name = os.environ.get('DISPLAY', ':0')
        d = _display.Display(disp_name)
    except Exception as e:
        _log(f"FAIL: Cannot connect to X display: {e}", "error")
        return False

    global _ciw_win_cache

    # If a specific window_id is given, use it directly (skip cache logic)
    if window_id:
        try:
            _w = d.create_resource_object('window', window_id)
            _name = _w.get_wm_name()  # validate it's alive
            if _name and 'CDS.log' in str(_name):
                _ciw_win_cache = _w
            else:
                _log(f"window {window_id:#x} no longer a CIW (name={_name!r}), ignoring", "warn")
                _ciw_win_cache = None
        except Exception:
            _ciw_win_cache = None

    if _ciw_win_cache is None or window_id is None:
        # Validate cache
        if _ciw_win_cache is not None:
            try:
                _ciw_win_cache.get_wm_name()
            except Exception:
                _ciw_win_cache = None

        if _ciw_win_cache is None:
            if _ipc_virt_pid:
                _ciw_win_cache = _find_by_pid(d, _ipc_virt_pid)
            if _ciw_win_cache is None:
                _ciw_win_cache = _find_ciw_window(d, log_file)

    d.close()

    ciw_win = _ciw_win_cache
    if not ciw_win:
        _log("FAIL: CIW window not found", "error")
        return False

    _log(f"CIW window: {ciw_win.id:#x}")

    # Wait until the user has physically released all modifier keys (Shift, Ctrl,
    # Alt, Super) before injecting key events.  This prevents the hotkey used to
    # trigger inject (e.g. Shift+F5 for debug-stop, F5 for debug-start) from
    # being still held when xdotool sends ctrl+a / ctrl+v, which would produce
    # unintended key combinations in the target window.
    _wait_modifiers_released(timeout=1.5)
    _time.sleep(0.05)  # brief settle after release

    # Set clipboard via python-xlib SelectionOwner (no external tools needed).
    # '\n' is included so ctrl+v delivers text + newline atomically; the
    # separate Return key is kept as a fallback in case the terminal strips \n.
    if not _set_clipboard(text + '\n'):
        _log("FAIL: could not set clipboard", "error")
        return False

    # Save current focus so we can restore it after inject.
    prev_win = None
    try:
        from Xlib import display as _dfocus
        _df = _dfocus.Display(os.environ.get('DISPLAY', ':0'))
        prev_win = _df.get_input_focus().focus
        _df.close()
    except Exception:
        pass

    # Focus CIW via `xdotool windowfocus --sync`.
    # --sync makes xdotool wait until the compositor confirms the focus change,
    # which is more reliable on XWayland than sending a raw _NET_ACTIVE_WINDOW
    # ClientMessage (which the compositor may silently ignore).
    import subprocess as _sp
    env = dict(os.environ, XMODIFIERS='')
    try:
        rc = _sp.run(
            [_XDOTOOL, 'windowfocus', '--sync', str(ciw_win.id)],
            env=env, capture_output=True, timeout=3
        ).returncode
        if rc != 0:
            _log(f"windowfocus returned {rc} — aborting inject", "error")
            return False
    except _sp.TimeoutExpired:
        _log("windowfocus timed out — aborting inject", "error")
        return False
    except Exception as e:
        _log(f"windowfocus error: {e} — aborting inject", "error")
        return False
    _time.sleep(0.15)

    # Key events via xdotool (avoids ibus 1.5.3 spurious-newline bug).
    # XMODIFIERS="" and env are already set above; reuse them here.
    def _xdt(*args):
        _sp.run([_XDOTOOL] + list(args), env=env,
                capture_output=True, timeout=5)

    _xdt('key', '--clearmodifiers', 'ctrl+u', 'ctrl+v')
    _time.sleep(0.05)
    _xdt('key', '--clearmodifiers', 'Return')
    _time.sleep(0.05)

    # Restore focus to the previously active window via xdotool windowfocus.
    if prev_win is not None:
        try:
            _sp.run(
                [_XDOTOOL, 'windowfocus', '--sync', str(prev_win.id)],
                env=env, capture_output=True, timeout=3
            )
        except Exception:
            pass

    _log(f"inject done")
    return True


# ─── Shared state ─────────────────────────────────────────────────────────────

class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        # Debug state
        self.debug_active = False
        self.debug_break_event = threading.Event()
        self.debug_break_line = 0
        self.debug_break_file_id = 0
        self.debug_output = []

    # Debug state management
    def debug_start(self):
        with self.lock:
            self.debug_active = True
            self.debug_break_event.clear()
            self.debug_break_line = 0
            self.debug_break_file_id = 0
            self.debug_output = []

    def debug_stop(self):
        with self.lock:
            self.debug_active = False
            self.debug_break_event.set()  # unblock any waiter
            self.debug_break_line = 0
            self.debug_break_file_id = 0
            self.debug_output = []

    def debug_on_break(self, line_num, file_id=0):
        with self.lock:
            self.debug_break_line = line_num
            self.debug_break_file_id = file_id
            output = list(self.debug_output)
            self.debug_output = []
        self.debug_break_event.set()
        return output

    def debug_add_output(self, text):
        with self.lock:
            self.debug_output.append(text)

    def debug_wait_for_break(self, timeout=300):
        return self.debug_break_event.wait(timeout=timeout)

    def debug_wait_for_next_break(self, timeout=300):
        """Wait for the next break event (idle mode: already injected, waiting for CIW call)."""
        return self.debug_break_event.wait(timeout=timeout)

state = SharedState()


# ─── REST API ─────────────────────────────────────────────────────────────────

class ApiHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        # /health
        if self.path == "/health":
            self._json({"status": "ok", "virt_pid": _ipc_virt_pid,
                        "log_file": _ipc_log_file, "port": _ipc_assigned_port})

        # /debug_break/<fileId>/<line> or /debug_break/<line> (backward compat)
        elif self.path.startswith("/debug_break/"):
            try:
                parts = self.path[len("/debug_break/"):].split("/")
                if len(parts) == 2:
                    file_id, line_num = int(parts[0]), int(parts[1])
                else:
                    file_id, line_num = 0, int(parts[0])
            except ValueError:
                file_id, line_num = 0, 0
            state.debug_on_break(line_num, file_id)
            _log(f"debug_break file_id={file_id} line={line_num}")
            self._json({"ok": True})

        # /debug_end  — SKILL signals procedure returned (optionally ?result=...)
        elif self.path.startswith("/debug_end"):
            state.debug_on_break(-1)  # -1 = ended
            _log("debug_end")
            self._json({"ok": True})

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body)
        except Exception:
            self._json({"error": "bad request"}, 400)
            return

        # /debug_eval_result  — _sbDbgEval() sends result back
        if self.path == "/debug_eval_result":
            with state.lock:
                ev = getattr(state, '_pending_eval_event', None)
                state._pending_eval_result = {
                    "success": req.get("success", False),
                    "result":  req.get("result", ""),
                }
                state._pending_eval_event = None
            if ev:
                ev.set()
            self._json({"ok": True})

        # /debug/start  — start a debug session (inject setup + code into CIW)
        elif self.path == "/debug/start":
            self._handle_debug_start(req)

        # /debug/command  — continue / next / eval / update_bp
        elif self.path == "/debug/command":
            self._handle_debug_command(req)

        # /debug/wait_break  — block until next _sbDbgBreak() arrives (idle mode)
        elif self.path == "/debug/wait_break":
            self._handle_debug_wait_break(req)

        # /debug/stop  — abort debug session
        elif self.path == "/debug/stop":
            self._handle_debug_stop(req)

        # /debug/status
        elif self.path == "/debug/status":
            with state.lock:
                self._json({"success": True, "active": state.debug_active,
                            "line": state.debug_break_line})

        else:
            self._json({"error": "not found"}, 404)

    def _handle_debug_start(self, req):
        """Inject setup code and transformed debug code into CIW.

        Flow (normal mode):
          1. Inject setup code (set __sbk_bp, __sbk_ln, __sbPort) via CIW.
          2. Inject transformed code wrapped in begin()..._sbCurl("/debug_end").
          3. Wait for first /debug_break or /debug_end curl callback.

        Flow (idle mode — procedure-only code with no entry point):
          1. Inject setup code via CIW.
          2. Inject transformed code as-is (no begin() wrapper, no _sbCurl("/debug_end")).
             The procedures are just defined in Virtuoso; no execution happens yet.
          3. Return immediately with status="idle".
          4. Python then calls /debug/wait_break to wait for the user to invoke a
             procedure from the CIW, which triggers _sbDbgBreak() callbacks normally.
        """
        setup_code  = req.get("setup", "")
        debug_code  = req.get("code", "")
        timeout     = req.get("timeout", 300)
        idle        = req.get("idle", False)

        if not debug_code:
            self._json({"success": False, "error": "empty debug code"})
            return

        state.debug_start()

        # Inject setup code (breakpoint list + port for curl callbacks)
        if setup_code:
            full_setup = f"begin(\n{setup_code}\n__sbPort = {_ipc_assigned_port}\n)"
            skill_call = _write_and_load(full_setup, "setup")
            if not _inject_text_to_ciw(skill_call, _ipc_log_file):
                state.debug_stop()
                self._json({"success": False,
                            "error": "Setup inject failed — CIW not responding"})
                return
            import time as _t
            _t.sleep(0.5)

        if idle:
            # Idle mode: inject procedure definitions only, return immediately.
            # No begin() wrapper, no _sbCurl("/debug_end") — procedures are defined
            # and ready; execution happens when the user calls them from CIW.
            skill_call = _write_and_load(debug_code, "code")
            if not _inject_text_to_ciw(skill_call, _ipc_log_file):
                state.debug_stop()
                self._json({"success": False,
                            "error": "Code inject failed — CIW not responding"})
                return
            self._json({"success": True, "status": "idle"})
            return

        # Normal mode: wrap in begin() and append _sbCurl("/debug_end") so Python
        # is notified when all code finishes executing.
        wrapped = "begin(\n" + debug_code + "\n_sbCurl(\"/debug_end\")\n)"
        skill_call = _write_and_load(wrapped, "code")
        if not _inject_text_to_ciw(skill_call, _ipc_log_file):
            state.debug_stop()
            self._json({"success": False,
                        "error": "Code inject failed — CIW not responding"})
            return

        # Wait for first break or end
        if not state.debug_wait_for_break(timeout=timeout):
            state.debug_stop()
            self._json({"success": False, "error": "debug timeout — no break received"})
            return

        with state.lock:
            line    = state.debug_break_line
            file_id = state.debug_break_file_id
            output  = list(state.debug_output)

        if line == -1:
            state.debug_stop()
            self._json({"success": True, "status": "ended", "line": 0, "file_id": file_id, "output": output})
        else:
            self._json({"success": True, "status": "break", "line": line, "file_id": file_id, "output": output})

    def _handle_debug_command(self, req):
        """Handle a command while paused at a breakpoint.

        Commands: continue | eval | update_bp
        """
        cmd     = req.get("cmd", "")
        timeout = req.get("timeout", 300)

        if not state.debug_active:
            self._json({"success": False, "error": "no active debug session"})
            return

        if cmd == "eval":
            expr = req.get("expr", "")
            if not expr:
                self._json({"success": False, "error": "empty expression"})
                return
            # eval uses _sbDbgEval which still needs base64 for the expression
            import base64 as _b64
            b64_expr   = _b64.b64encode(expr.encode()).decode()
            skill_call = f'_sbDbgEval("{b64_expr}")'

            eval_event = threading.Event()
            with state.lock:
                state._pending_eval_event  = eval_event
                state._pending_eval_result = None

            if not _inject_text_to_ciw(skill_call, _ipc_log_file):
                self._json({"success": False,
                            "error": "X11 injection failed — CIW not responding"})
                return

            if not eval_event.wait(timeout=10):
                self._json({"success": False, "error": "eval timeout"})
                return

            with state.lock:
                resp = state._pending_eval_result
            self._json(resp or {"success": False, "error": "no response"})
            return

        if cmd == "update_bp":
            bp_code = req.get("code", "")
            if bp_code:
                skill_call = _write_and_load(bp_code, "bp")
                _inject_text_to_ciw(skill_call, _ipc_log_file)
            self._json({"success": True})
            return

        if cmd in ("continue", "next"):
            # Optional bp update first (fire-and-forget, best-effort)
            bp_code = req.get("bp_code", "")
            if bp_code:
                import time as _t
                skill_call = _write_and_load(bp_code, "bp")
                _inject_text_to_ciw(skill_call, _ipc_log_file)
                _t.sleep(0.1)

            state.debug_break_event.clear()

            if not _inject_text_to_ciw("continue()", _ipc_log_file):
                self._json({"success": False,
                            "error": "X11 injection failed — CIW not responding"})
                return

            if not state.debug_break_event.wait(timeout=timeout):
                state.debug_stop()
                self._json({"success": False, "error": "timeout waiting for break"})
                return

            with state.lock:
                line    = state.debug_break_line
                file_id = state.debug_break_file_id
                output  = list(state.debug_output)

            if line == -1:
                state.debug_stop()
                self._json({"success": True, "status": "ended", "line": 0, "file_id": file_id, "output": output})
            else:
                self._json({"success": True, "status": "break", "line": line, "file_id": file_id, "output": output})
            return

        self._json({"success": False, "error": f"unknown command: {cmd}"})

    def _handle_debug_wait_break(self, req):
        """Wait for the next _sbDbgBreak() or /debug_end callback (idle mode).

        Called by Python after injecting procedure-only code in idle mode.
        Blocks until the user invokes a procedure from CIW, which triggers
        the breakpoint guards normally.
        """
        timeout = req.get("timeout", 300)
        if not state.debug_active:
            self._json({"success": False, "error": "no active debug session"})
            return

        if not state.debug_wait_for_next_break(timeout=timeout):
            state.debug_stop()
            self._json({"success": False, "error": "idle timeout — no call received"})
            return

        with state.lock:
            line    = state.debug_break_line
            file_id = state.debug_break_file_id
            output  = list(state.debug_output)

        if line == -1:
            state.debug_stop()
            self._json({"success": True, "status": "ended", "line": 0, "file_id": file_id, "output": output})
        else:
            self._json({"success": True, "status": "break", "line": line, "file_id": file_id, "output": output})

    def _handle_debug_stop(self, req):
        if state.debug_active:
            _inject_text_to_ciw("debugQuit()", _ipc_log_file)
            state.debug_stop()
        self._json({"success": True})

    def _json(self, obj, code=200):
        data = json.dumps(obj, separators=(',', ':')).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def find_free_port(start=18770, end=18800):
    """Find a free TCP port in the given range."""
    import socket
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return None


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0,
                        help="REST API port to listen on (0 = auto-select)")
    parser.add_argument("--virt-pid", type=int, default=0,
                        help="Virtuoso process PID (optional, used for window lookup)")
    parser.add_argument("--log-file", type=str, default="",
                        help="Virtuoso CIW log file path (optional, improves window lookup)")
    args = parser.parse_args()

    global _ipc_virt_pid, _ipc_log_file, _ipc_assigned_port
    _ipc_virt_pid = args.virt_pid
    _ipc_log_file = args.log_file

    port = args.port or find_free_port()
    if not port:
        _log("No free port available", "error")
        sys.exit(1)

    _ipc_assigned_port = port

    class ReuseHTTPServer(ThreadingMixIn, HTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = ReuseHTTPServer(("127.0.0.1", port), ApiHandler)
    _log(f"IPC server ready on port {port} (virt_pid={_ipc_virt_pid})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
