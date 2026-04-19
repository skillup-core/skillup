"""
SkillBot App

Cadence Virtuoso SKILL debugging tool.

New architecture (no ipcBeginProcess):
  - F5 (debug_start): find CIW window via X11, start skillbot_inject.py subprocess
    on a free port, inject setup + transformed code into CIW.
  - CIW → Python: SKILL calls system("curl .../debug_break/<line>") etc.
  - Python → CIW: X11 keyboard injection via skillbot_inject.py.

skillbot.il only needs to be loaded once to define helper functions
(_sbB64Decode, _sbDbgBreak, _sbDbgEval, etc.).  No skillbotStart() call needed.
"""

import sys
import os
import json
import sqlite3
import subprocess
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.baseapp import BaseApp
from lib.appmgr import register_app_class
from lib.config import get_app_config

# SkillBook app IDs (for reading DB path from skillbook config)
_SKILLBOOK_APP_ID      = 'b00k5k1l'
_SKILLBOOK_APP_ID_NAME = 'skillbook'
_SKILLBOOK_APP_DIR     = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'skillbook')

IPC_SERVER_HOST = "127.0.0.1"

# Connection check interval (milliseconds) — kept for UI polling
CONNECTION_CHECK_INTERVAL_MS = 5000


def _ipc_post(port, path, data, timeout=35):
    from urllib.request import urlopen, Request
    from urllib.error import URLError
    try:
        body = json.dumps(data).encode()
        url  = f"http://{IPC_SERVER_HOST}:{port}{path}"
        req  = Request(url, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except URLError as e:
        return {"success": False, "error": f"IPC unreachable: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _ipc_get(port, path):
    from urllib.request import urlopen
    from urllib.error import URLError
    try:
        url = f"http://{IPC_SERVER_HOST}:{port}{path}"
        with urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


class SkillBotApp(BaseApp):

    def __init__(self, engine, context):
        super().__init__(engine, context)
        self._current_language = 'en'
        self._il_path = str(Path(__file__).parent / "skill" / "skillbot.il")
        self._debug_session = None   # active debug session dict or None
        self._ipc_proc      = None   # skillbot_inject.py subprocess
        self._ipc_port      = 0      # port skillbot_inject.py is listening on
        self._ipc_virt_pid  = 0      # virt_pid the current IPC process was started for

    def _ibus_suppress(self):
        """Suppress ibus restart during X11 inject to CIW.
        Returns engine.ibus_suppress() context manager, or a no-op fallback."""
        if self.engine and hasattr(self.engine, 'ibus_suppress'):
            return self.engine.ibus_suppress()
        from contextlib import nullcontext
        return nullcontext()

    # ──────────────────────────────────────────────────────────
    # CLI mode
    # ──────────────────────────────────────────────────────────

    def on_run_cli(self, args):
        print("SkillBot: CLI mode not yet implemented. Use --desktop mode.",
              file=sys.stderr)
        return 1

    # ──────────────────────────────────────────────────────────
    # Desktop mode initialization
    # ──────────────────────────────────────────────────────────

    def on_run_desktop_initialize(self):
        self.register_handlers({
            "get_status":             self._handle_get_status,
            "get_ipc_path":           self._handle_get_ipc_path,
            "get_skillbot_config":    self._handle_get_skillbot_config,
            "get_layout":             self._handle_get_layout,
            "save_layout":            self._handle_save_layout,
            "get_editor_prefs":       self._handle_get_editor_prefs,
            "save_editor_prefs":      self._handle_save_editor_prefs,
            "get_skill_syntax":       self._handle_get_skill_syntax,
            "run_code":               self._handle_run_code,
            "run_code_selected":      self._handle_run_code_selected,
            # Intellisense
            "intellisense_complete":  self._handle_intellisense_complete,
            "intellisense_signature": self._handle_intellisense_signature,
            # Debug
            "get_ciw_list":           self._handle_get_ciw_list,
            "debug_start":            self._handle_debug_start,
            "debug_start_selected":   self._handle_debug_start_selected,
            "debug_continue":         self._handle_debug_continue,
            "debug_next":             self._handle_debug_next,
            "debug_eval":             self._handle_debug_eval,
            "debug_stop":             self._handle_debug_stop,
            "debug_status":           self._handle_debug_status,
            "debug_update_bp":        self._handle_debug_update_bp,
            # File explorer
            "file_get_root":          self._handle_file_get_root,
            "file_set_root":          self._handle_file_set_root,
            "file_list_dir":          self._handle_file_list_dir,
            "file_read":              self._handle_file_read,
            "file_check_mtime":       self._handle_file_check_mtime,
            "file_save":              self._handle_file_save,
            "file_new_file":          self._handle_file_new_file,
            "file_rename":            self._handle_file_rename,
            "file_delete":            self._handle_file_delete,
            # Projects
            "project_list":           self._handle_project_list,
            "project_save":           self._handle_project_save,
            "project_delete":         self._handle_project_delete,
        })
        self._intellisense_init()
        return 0

    def on_close(self):
        session = self._debug_session
        self._debug_session = None

        if session:
            port = session.get('port')
            if port:
                try:
                    _ipc_post(port, "/debug/stop", {}, timeout=3)
                except Exception:
                    pass
            self._restore_original_files(session)
        self._stop_ipc_proc(graceful=False)

    # ──────────────────────────────────────────────────────────
    # IPC subprocess management
    # ──────────────────────────────────────────────────────────

    def _kill_orphan_ipc_procs(self):
        """Kill any skillbot_inject.py processes left over from previous sessions."""
        import signal
        ipc_script_name = os.path.join("skillbot", "inject", "skillbot_inject.py")
        try:
            for pid_str in os.listdir('/proc'):
                if not pid_str.isdigit():
                    continue
                try:
                    with open(f'/proc/{pid_str}/cmdline', 'rb') as f:
                        cmdline = f.read().replace(b'\x00', b' ').decode(errors='replace')
                    if ipc_script_name in cmdline:
                        os.kill(int(pid_str), signal.SIGKILL)
                        print(f"[SkillBot] Killed orphan IPC pid={pid_str}", file=sys.stderr)
                except Exception:
                    pass
        except Exception:
            pass

    def _start_ipc_proc(self, virt_pid=0, log_file=""):
        """Start skillbot_inject.py on a free port. Returns port or 0 on failure."""
        self._stop_ipc_proc(graceful=False)
        self._kill_orphan_ipc_procs()

        from app.skillbot.inject.skillbot_inject import find_free_port
        port = find_free_port()
        if not port:
            print("[SkillBot] No free port available", file=sys.stderr)
            return 0

        ipc_script = str(Path(__file__).parent / "inject" / "skillbot_inject.py")
        cmd = [sys.executable, ipc_script,
               "--port", str(port),
               "--virt-pid", str(virt_pid),
               "--log-file", log_file]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            print(f"[SkillBot] Failed to start IPC: {e}", file=sys.stderr)
            return 0

        # Forward IPC stderr to our stderr
        def _forward_stderr():
            for line in proc.stderr:
                print(line, end="", file=sys.stderr, flush=True)
        threading.Thread(target=_forward_stderr, daemon=True).start()

        # Wait until REST API is ready (up to 3 s)
        import time
        deadline = time.time() + 3.0
        while time.time() < deadline:
            r = _ipc_get(port, "/health")
            if r.get("status") == "ok":
                self._ipc_proc     = proc
                self._ipc_port     = port
                self._ipc_virt_pid = virt_pid
                print(f"[SkillBot] IPC ready on port {port}", file=sys.stderr)
                return port
            time.sleep(0.1)

        print(f"[SkillBot] IPC did not become ready on port {port}", file=sys.stderr)
        proc.terminate()
        return 0

    def _stop_ipc_proc(self, graceful=True):
        if self._ipc_proc:
            try:
                if graceful and self._ipc_port:
                    _ipc_post(self._ipc_port, "/debug/stop", {}, timeout=2)
            except Exception:
                pass
            try:
                self._ipc_proc.terminate()
                self._ipc_proc.wait(timeout=2)
            except Exception:
                try:
                    self._ipc_proc.kill()
                    self._ipc_proc.wait(timeout=1)
                except Exception:
                    pass
            self._ipc_proc     = None
            self._ipc_port     = 0
            self._ipc_virt_pid = 0

    def _ensure_ipc(self, virt_pid=0, log_file=""):
        """Return current IPC port, starting a new process if needed.

        If the existing IPC process was started for a different virt_pid,
        stop it and start a new one for the requested virt_pid.
        """
        if self._ipc_proc and self._ipc_proc.poll() is None and self._ipc_port:
            if virt_pid and self._ipc_virt_pid != virt_pid:
                # Different CIW selected — restart IPC for the new one
                self._stop_ipc_proc(graceful=False)
            else:
                return self._ipc_port
        return self._start_ipc_proc(virt_pid=virt_pid, log_file=log_file)

    # ──────────────────────────────────────────────────────────
    # Intellisense
    # ──────────────────────────────────────────────────────────

    def _intellisense_init(self):
        self._isk_db_path        = None
        self._isk_function_names = []
        self._isk_function_names_set = set()

        default_db   = os.path.join(_SKILLBOOK_APP_DIR, 'data', 'skillbook.db')
        db_path_tmpl = get_app_config(
            _SKILLBOOK_APP_ID, _SKILLBOOK_APP_ID_NAME,
            'skillbook.skillbook_db_path', default_db)
        db_path = db_path_tmpl.replace('${skillbook_app_dir}', _SKILLBOOK_APP_DIR)

        if not Path(db_path).exists():
            print(f"[SkillBot] Intellisense: skillbook DB not found at {db_path}",
                  file=sys.stderr)
            return

        self._isk_db_path = db_path
        try:
            conn   = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT function_name FROM functions ORDER BY function_name')
            self._isk_function_names     = [row[0] for row in cursor.fetchall()]
            self._isk_function_names_set = set(self._isk_function_names)
            conn.close()
            print(f"[SkillBot] Intellisense: {len(self._isk_function_names)} functions",
                  file=sys.stderr)
        except Exception as e:
            print(f"[SkillBot] Intellisense load failed: {e}", file=sys.stderr)

    def _handle_intellisense_complete(self, data, language):
        if not self._isk_db_path:
            return {'success': False, 'error': 'Intellisense DB not available'}
        q = data.get('q', '').strip()
        if not q:
            return {'success': True, 'results': []}
        limit   = data.get('limit', 20)
        q_lower = q.lower()
        prefix_hits = []
        contains_hits = []
        for name in self._isk_function_names:
            nl = name.lower()
            if nl.startswith(q_lower):
                prefix_hits.append(name)
            elif q_lower in nl:
                contains_hits.append(name)
            if len(prefix_hits) >= limit:
                break
        results_names = (prefix_hits + contains_hits)[:limit]
        results = []
        try:
            conn   = sqlite3.connect(self._isk_db_path)
            cursor = conn.cursor()
            for name in results_names:
                cursor.execute('''
                    SELECT s.signature_text
                    FROM function_signatures fs
                    JOIN signatures s ON fs.signature_id = s.id
                    JOIN functions f ON fs.function_id = f.id
                    WHERE f.function_name = ?
                    ORDER BY fs.position
                ''', (name,))
                sigs = [row[0] for row in cursor.fetchall()]
                results.append({'name': name, 'signatures': sigs})
            conn.close()
        except Exception as e:
            print(f"[SkillBot] intellisense complete error: {e}", file=sys.stderr)
            results = [{'name': n, 'signatures': []} for n in results_names]
        return {'success': True, 'results': results}

    def _handle_intellisense_signature(self, data, language):
        if not self._isk_db_path:
            return {'success': False, 'error': 'Intellisense DB not available'}
        name      = data.get('name', '').strip()
        arg_index = data.get('arg_index', 0)
        if not name:
            return {'success': False, 'error': 'name required'}
        try:
            from app.skillbook.skillbook import get_function_data
            func_data = get_function_data(self._isk_db_path, name, language_id=1)
        except Exception as e:
            return {'success': False, 'error': str(e)}
        if not func_data:
            return {'success': False, 'error': f'Function not found: {name}'}
        return {
            'success':    True,
            'name':       name,
            'signatures': func_data.get('signatures', []),
            'arguments':  func_data.get('arguments', []),
            'returns':    func_data.get('returns', []),
            'arg_index':  arg_index,
        }

    # ──────────────────────────────────────────────────────────
    # General handlers
    # ──────────────────────────────────────────────────────────

    def _handle_get_status(self, data, language):
        self._current_language = language
        ipc_alive = (self._ipc_proc is not None
                     and self._ipc_proc.poll() is None
                     and self._ipc_port != 0)
        return {
            "success":   True,
            "il_path":   self._il_path,
            "ipc_alive": ipc_alive,
            "ipc_port":  self._ipc_port,
        }

    def _handle_get_ipc_path(self, data, language):
        return {"success": True, "path": self._il_path}

    def _handle_get_skillbot_config(self, data, language):
        return {
            "success":                      True,
            "connection_check_interval_ms": CONNECTION_CHECK_INTERVAL_MS,
        }

    def _handle_get_layout(self, data, language):
        config = self.load_config({})
        return {"success": True, "layout": config.get("ui.layout", "bottom")}

    def _handle_save_layout(self, data, language):
        layout = data.get("layout", "bottom")
        config = self.load_config({})
        config["ui.layout"] = layout
        self.save_config(config)
        return {"success": True}

    def _handle_get_editor_prefs(self, data, language):
        config = self.load_config({})
        prefs = {
            "editor.font_size": int(config.get("editor.font_size", 16)),
        }
        return {"success": True, "prefs": prefs}

    def _handle_save_editor_prefs(self, data, language):
        prefs = data.get("prefs", {})
        config = self.load_config({})
        if "editor.font_size" in prefs:
            config["editor.font_size"] = int(prefs["editor.font_size"])
        self.save_config(config)
        return {"success": True}

    def _handle_get_skill_syntax(self, data, language):
        if not self._isk_db_path:
            return {"success": True, "builtins": []}
        try:
            conn   = sqlite3.connect(self._isk_db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT f.function_name
                FROM functions f
                JOIN function_sections fs ON f.id = fs.function_id
                WHERE fs.section_id IN (
                    SELECT id FROM sections
                    WHERE key IN ('skdevref','skipcref','sklangref','skoopref')
                )
                ORDER BY f.function_name
            ''')
            import re
            builtins = [row[0] for row in cursor.fetchall()
                        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_?!]*$', row[0])]
            conn.close()
            return {"success": True, "builtins": builtins,
                    "all_functions": self._isk_function_names}
        except Exception as e:
            print(f"[SkillBot] get_skill_syntax error: {e}", file=sys.stderr)
            return {"success": False, "builtins": [], "all_functions": []}

    # ──────────────────────────────────────────────────────────
    # Debug handlers
    # ──────────────────────────────────────────────────────────

    def _normalize_debug_files(self, data):
        """Normalize debug start payload to multi-file format.
        Accepts either 'files' array or legacy single 'code' string.
        """
        files = data.get("files")
        if files:
            return [f for f in files if f.get("code", "").strip()]
        # Legacy single-file compat
        code = data.get("code", "").strip()
        if not code:
            return []
        return [{"file_id": 0, "code": code, "breakpoints": data.get("breakpoints", [])}]

    def _handle_run_code(self, data, language):
        """Run IL tabs in CIW via load("...") injection (no debug instrumentation).

        Each IL tab is handled as follows:
          - untitled.il  → write content to /tmp/skillbot/run/<CDS.log>/run.il, inject load(...)
          - real path, dirty → write content to /tmp/skillbot/run/<CDS.log>/run.il, inject load(...)
          - real path, clean → inject load(path) directly
          - non-.il extension → skip
        """
        from app.skillbot.inject.skillbot_inject import find_all_ciw_windows

        files = data.get("files", [])
        if not files:
            return {"success": False, "error": "No files to run"}

        ciw_windows = find_all_ciw_windows()
        if not ciw_windows:
            return {"success": False, "error": "CIW window not found. Is Virtuoso running?"}

        # Multiple CIW windows: ask user to select
        if len(ciw_windows) > 1:
            return {
                "success": False,
                "error": "ciw_selection_needed",
                "ciw_windows": ciw_windows,
                "files": files,
            }

        return self._do_run_code(ciw_windows[0], files)

    def _handle_run_code_selected(self, data, language):
        """Called after user selects a CIW from the selection dialog (run mode)."""
        from app.skillbot.inject.skillbot_inject import find_all_ciw_windows

        window_id = data.get("window_id")
        files = data.get("files", [])
        if not files:
            return {"success": False, "error": "No files to run"}

        ciw_windows = find_all_ciw_windows()
        ciw = next((w for w in ciw_windows if w.get("window_id") == window_id), None)
        if ciw is None:
            if not ciw_windows:
                return {"success": False, "error": "CIW window not found. Is Virtuoso running?"}
            return {
                "success": False,
                "error": "ciw_selection_needed",
                "ciw_windows": ciw_windows,
                "files": files,
            }

        return self._do_run_code(ciw, files)

    def _do_run_code(self, ciw, files):
        """Execute run_code with a resolved CIW window."""
        import re as _re
        from pathlib import Path
        from app.skillbot.inject.skillbot_inject import _check_ciw_desktop, _inject_text_to_ciw

        ok, ciw_desktop, current_desktop = _check_ciw_desktop("", window_id=ciw.get("window_id"))
        if not ok:
            return {
                "success": False,
                "error": "ciw_wrong_desktop",
                "ciw_desktop":     ciw_desktop,
                "current_desktop": current_desktop,
            }

        # Extract CDS.log name from CIW title
        _m = _re.search(r'(CDS\.log(?:\.\d+)?)', str(ciw.get("title", "")))
        log_base = _m.group(1) if _m else "CDS.log"

        tmp_dir = Path("/tmp/skillbot/run") / log_base
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = str(tmp_dir / "run.il")

        window_id = ciw.get("window_id")
        ciw_info = {"window_id": window_id, "title": ciw.get("title", ""), "pid": ciw.get("pid")}

        for f in files:
            name    = f.get("name", "")
            path    = f.get("path") or None
            dirty   = f.get("dirty", False)
            content = f.get("content", "")

            # Skip non-.il files
            ext = Path(name).suffix.lower()
            if ext not in (".il", ".ils"):
                continue

            is_untitled = (path is None or name == "untitled.il")

            if is_untitled or dirty:
                # Write content to tmp file and load it
                with open(tmp_path, "w", encoding="utf-8") as fh:
                    fh.write(content)
                load_cmd = f'load("{tmp_path}")'
            else:
                # Clean saved file — load directly by path
                load_cmd = f'load("{path}")'

            print(f"[SkillBot] run: {load_cmd}", file=sys.stderr)
            with self._ibus_suppress():
                _inject_text_to_ciw(load_cmd, "", window_id=window_id)

        return {"success": True, "ciw_info": ciw_info}

    def _handle_get_ciw_list(self, data, language):
        """Return list of available CIW windows without starting a debug session."""
        from app.skillbot.inject.skillbot_inject import find_all_ciw_windows
        ciw_windows = find_all_ciw_windows()
        return {"success": True, "ciw_windows": ciw_windows}

    def _handle_debug_start(self, data, language):
        """F5: find CIW, start IPC subprocess, inject debug code.

        Request (multi-file): {
            files: [{file_id, name, path, code, breakpoints}, ...]
        }
        Request (legacy single-file): {
            code: "original SKILL code",
            breakpoints: [3, 5, 7],
        }
        """
        from app.skillbot.inject.skillbot_inject import find_all_ciw_windows

        files = self._normalize_debug_files(data)
        if not files:
            return {"success": False, "error": "Empty code"}

        # ── Find CIW window ──────────────────────────────────
        ciw_windows = find_all_ciw_windows()
        if not ciw_windows:
            return {"success": False,
                    "error": "CIW window not found. Is Virtuoso running?"}

        # Multiple CIW windows: ask user to select
        if len(ciw_windows) > 1:
            return {
                "success": False,
                "error": "ciw_selection_needed",
                "ciw_windows": ciw_windows,
                "files": files,
            }

        return self._do_debug_start(ciw_windows[0], files, data)

    def _handle_debug_start_selected(self, data, language):
        """Called after user selects a CIW from the selection dialog.

        Request: {
            window_id: int, title: str, pid: int,
            files: [{file_id, name, path, code, breakpoints}, ...]
        }
        """
        from app.skillbot.inject.skillbot_inject import find_all_ciw_windows

        window_id = data.get("window_id")
        files = self._normalize_debug_files(data)
        if not files:
            return {"success": False, "error": "Empty code"}

        # Re-fetch CIW list to get fresh data; match by window_id
        ciw_windows = find_all_ciw_windows()
        ciw_info = next((w for w in ciw_windows if w.get("window_id") == window_id), None)
        if ciw_info is None:
            # Previously selected CIW is gone (Virtuoso closed).
            # Fall back to CIW selection dialog instead of injecting into
            # a stale/reused window ID.
            if not ciw_windows:
                return {"success": False,
                        "error": "CIW window not found. Is Virtuoso running?"}
            return {
                "success": False,
                "error": "ciw_selection_needed",
                "ciw_windows": ciw_windows,
                "files": files,
            }

        return self._do_debug_start(ciw_info, files, data)

    def _do_debug_start(self, ciw_info, files, data):
        """Core debug start logic after CIW window is determined.

        Args:
            ciw_info: CIW window dict {window_id, title, pid}
            files: list of {file_id, name, path, code, breakpoints}
            data: original request data
        """
        from app.skillbot.debugger import transform_for_debug, has_entry_point
        from app.skillbot.inject.skillbot_inject import _check_ciw_desktop, _inject_text_to_ciw

        virt_pid = ciw_info.get("pid", 0)

        # Extract CDS.log name from CIW title (e.g. "CDS.log.1")
        import re as _re
        _m = _re.search(r'(CDS\.log(?:\.\d+)?)', str(ciw_info.get("title", "")))
        log_file = _m.group(1) if _m else ""

        # ── Check virtual desktop ────────────────────────────
        ok, ciw_desktop, current_desktop = _check_ciw_desktop(log_file, window_id=ciw_info.get("window_id"))
        if not ok:
            return {
                "success": False,
                "error": "ciw_wrong_desktop",
                "ciw_desktop":     ciw_desktop,
                "current_desktop": current_desktop,
            }

        # ── Inject load "skillbot.il" into selected CIW ──────
        inject_load = data.get("inject_load", True)
        if inject_load:
            load_cmd = f'load("{self._il_path}")'
            print(f"[SkillBot] Injecting: {load_cmd}", file=sys.stderr)
            with self._ibus_suppress():
                ok = _inject_text_to_ciw(load_cmd, log_file, window_id=ciw_info.get("window_id"))
            if not ok:
                # CIW window is gone (Virtuoso closed or wrong window).
                # Show fresh CIW selection dialog instead of continuing.
                print(f"[SkillBot] Injection failed — CIW window lost, re-prompting selection",
                      file=sys.stderr)
                from app.skillbot.inject.skillbot_inject import find_all_ciw_windows as _fcw
                ciw_windows = _fcw()
                if not ciw_windows:
                    return {"success": False,
                            "error": "CIW window not found. Is Virtuoso running?"}
                return {
                    "success": False,
                    "error": "ciw_selection_needed",
                    "ciw_windows": ciw_windows,
                    "files": files,
                }
            import time
            time.sleep(0.5)

        # ── Pre-load debug-disabled IL files ─────────────────
        # Tabs with "Allow Debugging" off are excluded from the debug session
        # but their functions must be defined in CIW before the main code runs.
        # Inject load("path") for each saved file so CIW loads them first.
        preload_paths = data.get("preload_paths", [])
        if preload_paths:
            import time as _time
            for fpath in preload_paths:
                if not fpath:
                    continue
                preload_cmd = f'load("{fpath}")'
                print(f"[SkillBot] Pre-loading: {preload_cmd}", file=sys.stderr)
                with self._ibus_suppress():
                    _inject_text_to_ciw(preload_cmd, log_file, window_id=ciw_info.get("window_id"))
                _time.sleep(0.3)

        # ── Start IPC subprocess ─────────────────────────────
        port = self._ensure_ipc(virt_pid=virt_pid, log_file=log_file)
        if not port:
            return {"success": False, "error": "Failed to start IPC process"}

        # ── Transform all files ──────────────────────────────
        file_data = {}  # file_id -> per-file debug info
        any_procedure = False
        any_entry_point = False
        entry_point_file_id = None

        for f in files:
            fid = f["file_id"]
            code = f["code"]
            bp = f.get("breakpoints", [])
            result = transform_for_debug(code, bp if bp else None, file_id=fid)
            has_procs = bool(result['procedure_ranges'])
            has_entry = has_entry_point(code)
            if has_procs:
                any_procedure = True
            if has_entry:
                any_entry_point = True
                entry_point_file_id = fid
            file_data[fid] = {
                'name':             f.get("name", ""),
                'path':             f.get("path"),
                'tab_id':           f.get("tab_id"),
                'original_code':    code,
                'transformed_code': result['code'],
                'setup_code':       result['setup'],
                'line_map':         result['line_map'],
                'insertable_lines': result['insertable_lines'],
                'user_breakpoints': bp[:] if bp else [],
                'procedure_ranges': result['procedure_ranges'],
                'total_lines':      result['total_lines'],
                'has_procedures':   has_procs,
                'has_entry_point':  has_entry,
            }

        if not any_procedure:
            return {"success": False, "error": "No procedure found to debug"}

        idle_mode = not any_entry_point
        timeout   = data.get("timeout", 300)

        # ── Combine setup code ───────────────────────────────
        setup_parts = []
        for fid in sorted(file_data.keys()):
            setup_parts.append(file_data[fid]['setup_code'])
        combined_setup = '\n'.join(setup_parts)

        # ── Combine transformed code ─────────────────────────
        # All files' procedure code comes first, entry-point code at the end.
        # This single combined code string gets sent to IPC for injection.
        code_parts = []
        code_entry = None
        for fid in sorted(file_data.keys()):
            fd = file_data[fid]
            if fid == entry_point_file_id:
                code_entry = fd['transformed_code']
            else:
                code_parts.append(fd['transformed_code'])
        # Append entry-point code last so procedure defs are loaded first
        if code_entry is not None:
            code_parts.append(code_entry)
        combined_code = '\n'.join(code_parts)

        self._debug_session = {
            'port':             port,
            'files':            file_data,
            'idle':             idle_mode,
            'current_file_id':  None,
            'current_line':     0,
            'ciw_info':         ciw_info,
            'log_file':         log_file,
        }

        # Build files_info for response
        files_info = [
            {"file_id": fid, "insertable_lines": fd['insertable_lines']}
            for fid, fd in sorted(file_data.items())
        ]

        def _bg():
            # Send all code to IPC in a single /debug/start call
            ipc_result = _ipc_post(port, "/debug/start", {
                "setup":   combined_setup,
                "code":    combined_code,
                "timeout": timeout,
                "idle":    idle_mode,
            }, timeout=timeout + 10)

            if self._debug_session is None:
                return

            if not ipc_result:
                session = self._debug_session
                self._debug_session = None
                self._restore_original_files(session)
                self.callJS("onDebugEvent", {"type": "error", "error": "IPC failed"})
                return

            if not ipc_result.get("success"):
                session = self._debug_session
                self._debug_session = None
                self._restore_original_files(session)
                self.callJS("onDebugEvent", {
                    "type":  "error",
                    "error": ipc_result.get("error", "Debug start failed"),
                })
                return

            status = ipc_result.get("status")

            if status == "idle":
                # Notify UI that procedures are loaded and we're waiting for a CIW call
                self.callJS("onDebugEvent", {
                    "type":       "idle",
                    "files_info": files_info,
                })
                # Now block waiting for the user to invoke a procedure from CIW
                ipc_result = _ipc_post(port, "/debug/wait_break",
                                       {"timeout": timeout}, timeout=timeout + 10)
                if self._debug_session is None:
                    return
                if not ipc_result or not ipc_result.get("success"):
                    session = self._debug_session
                    self._debug_session = None
                    self._restore_original_files(session)
                    self.callJS("onDebugEvent", {
                        "type":  "error",
                        "error": (ipc_result or {}).get("error", "IPC failed"),
                    })
                    return
                status = ipc_result.get("status")

            line    = ipc_result.get("line", 0)
            file_id = ipc_result.get("file_id", 0)
            output  = ipc_result.get("output", [])

            if self._debug_session:
                self._debug_session['current_line'] = line
                self._debug_session['current_file_id'] = file_id
            self.callJS("onDebugEvent", {
                "type":       "break" if status == "break" else "ended",
                "line":       line,
                "file_id":    file_id,
                "output":     output,
                "files_info": files_info,
            })
            if status == "ended":
                session = self._debug_session
                self._debug_session = None
                self._restore_original_files(session)

        threading.Thread(target=_bg, daemon=True).start()
        return {"success": True, "status": "starting",
                "files_info": files_info,
                "ciw_info": {"window_id": ciw_info.get("window_id"), "title": ciw_info.get("title", ""), "pid": ciw_info.get("pid", 0)}}

    def _handle_debug_continue(self, data, language):
        if not self._debug_session:
            return {"success": False, "error": "No active debug session"}
        port       = self._debug_session['port']
        file_data  = self._debug_session['files']

        def _bg():
            # Restore user breakpoints for all files
            from app.skillbot.debugger import build_breakpoint_update_code
            bp_parts = []
            for fid, fd in sorted(file_data.items()):
                bp = fd['user_breakpoints']
                if bp:
                    bp_parts.append(build_breakpoint_update_code(bp, fid))
            bp_code = '\n'.join(bp_parts)
            result = _ipc_post(port, "/debug/command",
                               {"cmd": "continue", "bp_code": bp_code, "timeout": 300},
                               timeout=310)
            self._on_debug_ipc_result(result)

        threading.Thread(target=_bg, daemon=True).start()
        return {"success": True, "status": "running"}

    def _handle_debug_next(self, data, language):
        if not self._debug_session:
            return {"success": False, "error": "No active debug session"}
        port      = self._debug_session['port']
        file_data = self._debug_session['files']

        from app.skillbot.debugger import build_next_step_code_multi
        files_insertable = {fid: fd['insertable_lines'] for fid, fd in file_data.items()}
        files_user_bp    = {fid: fd['user_breakpoints'] for fid, fd in file_data.items()}
        bp_code = build_next_step_code_multi(files_insertable, files_user_bp)

        def _bg():
            result = _ipc_post(port, "/debug/command",
                               {"cmd": "continue", "bp_code": bp_code, "timeout": 300},
                               timeout=310)
            self._on_debug_ipc_result(result)

        threading.Thread(target=_bg, daemon=True).start()
        return {"success": True, "status": "running"}

    def _on_debug_ipc_result(self, result):
        if self._debug_session is None:
            return
        if result and result.get("success"):
            line    = result.get("line", 0)
            file_id = result.get("file_id", 0)
            if self._debug_session:
                self._debug_session['current_line'] = line
                self._debug_session['current_file_id'] = file_id
            self.callJS("onDebugEvent", {
                "type":    "break" if result.get("status") == "break" else "ended",
                "line":    line,
                "file_id": file_id,
                "output":  result.get("output", []),
            })
            if result.get("status") == "ended":
                session = self._debug_session
                self._debug_session = None
                threading.Thread(target=self._restore_original_files, args=(session,), daemon=True).start()
        elif result:
            self.callJS("onDebugEvent", {
                "type":  "error",
                "error": result.get("error", "Unknown error"),
            })
        else:
            self.callJS("onDebugEvent", {"type": "error", "error": "IPC failed"})

    def _handle_debug_eval(self, data, language):
        if not self._debug_session:
            return {"success": False, "error": "No active debug session"}
        expr = data.get("expr", "").strip()
        if not expr:
            return {"success": False, "error": "Empty expression"}
        port = self._debug_session['port']

        def _bg():
            result = _ipc_post(port, "/debug/command",
                               {"cmd": "eval", "expr": expr}, timeout=15)
            self.callJS("onDebugEvalResult",
                        result or {"success": False, "error": "IPC failed"})

        threading.Thread(target=_bg, daemon=True).start()
        return {"success": True, "status": "pending"}

    def _extract_procedures_only(self, code: str) -> str:
        """Extract only procedure definitions from SKILL code.

        Returns a string containing only the procedure(...) blocks,
        stripping any top-level executable statements (entry points)
        that would run immediately on load().
        """
        from app.skillbot.debugger import _find_procedures, _strip_block_comments
        lines = code.split('\n')
        # Strip /* */ block comments before parsing so that procedure keywords
        # and parentheses inside comments do not produce false matches.
        parse_lines = _strip_block_comments(lines)
        procedures = _find_procedures(parse_lines)
        if not procedures:
            return code  # No procedures found; return as-is

        parts = []
        for p in procedures:
            # start_line and end_line are 1-based
            proc_lines = lines[p['start_line'] - 1 : p['end_line']]
            parts.append('\n'.join(proc_lines))
        return '\n\n'.join(parts)

    def _restore_original_files(self, session):
        """After debug ends, reload original (untransformed) code into Virtuoso.

        Writes a restore file containing only the procedure definitions from
        each open tab's original code, then load()s that file.  This avoids
        re-executing top-level entry-point code (e.g. main()) that would run
        immediately when the raw file is loaded.

        Restore file path: /tmp/skillbot/<log_base>_restore.il
        """
        from app.skillbot.inject.skillbot_inject import (
            _inject_text_to_ciw, _get_tmp_il_path)

        ciw_info = session.get('ciw_info', {})
        window_id = ciw_info.get('window_id') if ciw_info else None
        file_data = session.get('files', {})

        # Collect procedure-only code from all open tabs
        restore_parts = []
        for fid in sorted(file_data.keys()):
            fd = file_data[fid]
            original = fd.get('original_code', '').strip()
            if not original:
                continue
            procs_only = self._extract_procedures_only(original)
            if procs_only.strip():
                restore_parts.append(procs_only)

        if not restore_parts:
            print("[SkillBot] Restore: no procedures to restore", file=sys.stderr)
            return

        restore_code = '\n\n'.join(restore_parts)
        from app.skillbot.inject.skillbot_inject import _write_and_load as _wal
        session_log_file = session.get('log_file', '')
        cmd = _wal(restore_code, tag="restore", log_file=session_log_file)
        print(f"[SkillBot] Restoring procedures via {cmd}", file=sys.stderr)
        with self._ibus_suppress():
            _inject_text_to_ciw(cmd, log_file="", window_id=window_id)

    def _handle_debug_stop(self, data, language):
        if not self._debug_session:
            return {"success": True, "message": "No active session"}
        port = self._debug_session['port']
        session = self._debug_session
        result = _ipc_post(port, "/debug/stop", {})
        self._debug_session = None
        threading.Thread(target=self._restore_original_files, args=(session,), daemon=True).start()
        self.callJS("onDebugEvent", {"type": "stopped"})
        return result or {"success": True}

    def _handle_debug_status(self, data, language):
        if not self._debug_session:
            return {"success": True, "active": False}
        return {
            "success":         True,
            "active":          True,
            "line":            self._debug_session.get('current_line', 0),
            "file_id":         self._debug_session.get('current_file_id', 0),
            "files": {
                str(fid): {"insertable_lines": fd['insertable_lines'], "user_breakpoints": fd['user_breakpoints']}
                for fid, fd in self._debug_session.get('files', {}).items()
            },
        }

    def _handle_debug_update_bp(self, data, language):
        breakpoints = data.get("breakpoints", [])
        file_id = data.get("file_id", 0)
        if not self._debug_session:
            return {"success": False, "error": "No active debug session"}
        file_data = self._debug_session.get('files', {})
        fd = file_data.get(file_id)
        if fd:
            fd['user_breakpoints'] = breakpoints
        from app.skillbot.debugger import build_breakpoint_update_code
        bp_code = build_breakpoint_update_code(breakpoints, file_id)
        port    = self._debug_session['port']
        _ipc_post(port, "/debug/command", {"cmd": "update_bp", "code": bp_code})
        return {"success": True}

    # ──────────────────────────────────────────────────────────
    # File explorer handlers
    # ──────────────────────────────────────────────────────────

    def _handle_file_get_root(self, data, language):
        config = self.load_config({})
        root = config.get('explorer.root_dir', '')
        if not root or not Path(root).is_dir():
            root = str(Path.home())
        return {'success': True, 'path': root}

    def _handle_file_set_root(self, data, language):
        new_root = data.get('path', '')
        if not new_root or not Path(new_root).is_dir():
            return {'success': False, 'error': 'Invalid directory'}
        config = self.load_config({})
        config['explorer.root_dir'] = new_root
        self.save_config(config)
        return {'success': True, 'path': new_root}

    def _handle_file_list_dir(self, data, language):
        dir_path = data.get('path', '')
        if not dir_path:
            return {'files': [], 'error': 'No path provided'}
        try:
            entries = []
            with os.scandir(dir_path) as it:
                for entry in it:
                    if entry.name == '__pycache__':
                        continue
                    try:
                        stat = entry.stat()
                        entries.append({
                            'name':   entry.name,
                            'path':   entry.path,
                            'is_dir': entry.is_dir(),
                            'size':   0 if entry.is_dir() else stat.st_size,
                            'mtime':  int(stat.st_mtime),
                        })
                    except OSError:
                        pass
            entries.sort(key=lambda e: (not e['is_dir'], e['name'].lower()))
            return {'files': entries}
        except PermissionError as e:
            return {'files': [], 'error': f'Permission denied: {e}'}
        except OSError as e:
            return {'files': [], 'error': str(e)}

    def _handle_file_read(self, data, language):
        file_path = data.get('path', '')
        if not file_path:
            return {'error': 'No path provided'}
        try:
            p = Path(file_path)
            st = p.stat()
            if st.st_size > 10 * 1024 * 1024:
                return {'error': 'File too large to open (>10 MB)'}
            content = p.read_text(encoding='utf-8', errors='replace')
            return {'content': content, 'mtime': st.st_mtime}
        except OSError as e:
            return {'error': str(e)}

    def _handle_file_check_mtime(self, data, language):
        """Return current mtime for each requested path.

        Input:  { paths: [str] }
        Output: { mtimes: { path: float|null } }  — null if file missing
        """
        paths = data.get('paths', [])
        result = {}
        for p_str in paths:
            try:
                result[p_str] = Path(p_str).stat().st_mtime
            except OSError:
                result[p_str] = None
        return {'mtimes': result}

    def _handle_file_save(self, data, language):
        file_path = data.get('path', '')
        content   = data.get('content', '')
        if not file_path:
            return {'success': False, 'error': 'No path provided'}
        try:
            p = Path(file_path)
            p.write_text(content, encoding='utf-8')
            return {'success': True, 'mtime': p.stat().st_mtime}
        except OSError as e:
            return {'success': False, 'error': str(e)}

    def _handle_file_new_file(self, data, language):
        file_path = data.get('path', '')
        if not file_path:
            return {'success': False, 'error': 'No path provided'}
        p = Path(file_path)
        if p.exists():
            return {'success': False, 'error': 'File already exists'}
        try:
            p.touch()
            return {'success': True}
        except OSError as e:
            return {'success': False, 'error': str(e)}

    def _handle_file_rename(self, data, language):
        old_path = data.get('old_path', '')
        new_path = data.get('new_path', '')
        if not old_path or not new_path:
            return {'success': False, 'error': 'old_path and new_path required'}
        try:
            Path(old_path).rename(new_path)
            return {'success': True}
        except OSError as e:
            return {'success': False, 'error': str(e)}

    def _handle_file_delete(self, data, language):
        file_path = data.get('path', '')
        if not file_path:
            return {'success': False, 'error': 'No path provided'}
        p = Path(file_path)
        if p.is_dir():
            return {'success': False, 'error': 'Cannot delete directories'}
        try:
            p.unlink()
            return {'success': True}
        except OSError as e:
            return {'success': False, 'error': str(e)}

    # ──────────────────────────────────────────────────────────
    # Project handlers
    # ──────────────────────────────────────────────────────────

    def _projects_dir(self):
        data_dir = self.get_data_dir()
        p = Path(data_dir) / 'projects'
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _handle_project_list(self, data, language):
        try:
            index_file = self._projects_dir() / 'list.json'
            if not index_file.exists():
                return {'success': True, 'projects': []}
            projects = json.loads(index_file.read_text(encoding='utf-8'))
            return {'success': True, 'projects': projects}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _handle_project_save(self, data, language):
        """Create or update a project.

        Input: { id, name, description, files: [path, ...] }
        If id is empty/null, a new id is generated.
        """
        import uuid
        try:
            proj_id = data.get('id') or str(uuid.uuid4())[:8]
            name    = data.get('name', '').strip() or 'Untitled'
            desc    = data.get('description', '').strip()
            files   = data.get('files', [])

            # Load / update index
            index_file = self._projects_dir() / 'list.json'
            if index_file.exists():
                projects = json.loads(index_file.read_text(encoding='utf-8'))
            else:
                projects = []

            entry = {
                'id':          proj_id,
                'name':        name,
                'description': desc,
                'files':       files,
            }

            idx = next((i for i, p in enumerate(projects) if p['id'] == proj_id), None)
            if idx is None:
                projects.append(entry)
            else:
                projects[idx] = entry

            index_file.write_text(json.dumps(projects, ensure_ascii=False, indent=2),
                                  encoding='utf-8')
            return {'success': True, 'project': entry}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _handle_project_delete(self, data, language):
        try:
            proj_id = data.get('id', '')
            if not proj_id:
                return {'success': False, 'error': 'id required'}
            index_file = self._projects_dir() / 'list.json'
            if not index_file.exists():
                return {'success': True}
            projects = json.loads(index_file.read_text(encoding='utf-8'))
            projects = [p for p in projects if p['id'] != proj_id]
            index_file.write_text(json.dumps(projects, ensure_ascii=False, indent=2),
                                  encoding='utf-8')
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

register_app_class(SkillBotApp)
