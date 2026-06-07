"""
cmd/run_skill.py — inject SKILL code into a Virtuoso CIW and wait for the result.

Usage:
    python3 skillup.py --cmd:run_skill --target=CDS.log --code='<expr>' [--timeout=30]
"""

import sys
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Allow importing from project root and app/skillbot
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.skillbot.inject.skillbot_inject import (
    find_all_ciw_windows,
    find_free_port,
    _write_and_load,
    _inject_text_to_ciw,
)


def _parse_args(args):
    params = {"target": None, "code": None, "timeout": 30}
    for arg in args:
        if arg.startswith("--target="):
            params["target"] = arg[len("--target="):]
        elif arg.startswith("--code="):
            params["code"] = arg[len("--code="):]
        elif arg.startswith("--timeout="):
            try:
                params["timeout"] = int(arg[len("--timeout="):])
            except ValueError:
                print(f"[error]invalid --timeout value: {arg}", file=sys.stderr, flush=True)
                return None
    return params


def _find_target_window(target):
    """Return window info dict for the given CDS.log name, or None."""
    windows = find_all_ciw_windows()
    if not windows:
        return None
    for w in windows:
        if target in w.get("title", ""):
            return w
    return None


# Minimal JSON-escape sufficient for SKILL sprintf output.
# Handles the characters that would break a JSON string literal.
_RS_JSON_ESCAPE_IL = r"""
procedure( _rsJsonEscape(s)
  let( (result len i ch)
    result = ""
    len = strlen(s)
    i = 1
    while( i <= len
      ch = substring(s i 1)
      cond(
        ( ch == "\\" result = strcat(result "\\\\") )
        ( ch == "\"" result = strcat(result "\\\"") )
        ( ch == "\n" result = strcat(result "\\n")  )
        ( ch == "\r" result = strcat(result "\\r")  )
        ( ch == "\t" result = strcat(result "\\t")  )
        ( t          result = strcat(result ch)     )
      )
      i = i + 1
    )
    result
  )
)
""".strip()


def _build_skill_wrapper(user_code, port):
    """Return self-contained SKILL code that runs user_code and POSTs the result.

    procedure() is defined at top level (before let), then let() executes the
    user code and sends the result back via curl.
    """
    return f"""{_RS_JSON_ESCAPE_IL}

let( (__rs_ret __rs_body)
  __rs_ret = errset( {user_code} t )
  if( __rs_ret != nil
    then
      __rs_body = sprintf(nil "{{\\\"ok\\\":true,\\\"result\\\":\\\"%s\\\"}}"
                  _rsJsonEscape(sprintf(nil "%L" car(__rs_ret))))
    else
      __rs_body = "{{\\\"ok\\\":false,\\\"result\\\":\\\"eval error\\\"}}"
  )
  system(sprintf(nil
    "curl -s --max-time 5 -X POST -H 'Content-Type: application/json' -d '%s' http://127.0.0.1:{port}/result &"
    __rs_body))
)
"""


class _ResultHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path == "/result":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
            except Exception:
                data = {"ok": False, "result": body.decode(errors="replace")}
            self.server._result = data
            self.server._event.set()
            self._respond(200, {"ok": True})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


_USAGE = """\
Usage: python3 skillup.py --cmd:run_skill --target=<CDS.log> --code=<expr> [--timeout=<sec>]

  --target=<CDS.log>   CDS.log filename identifying the Virtuoso CIW window (required)
  --code=<expr>        SKILL expression to evaluate (required)
  --timeout=<sec>      seconds to wait for result (default: 30)

Example:
  python3 skillup.py --cmd:run_skill --target='CDS.log' --code='printf("%L\\n" list(1 2 3))'
"""


def run(args):
    from lib.log import log, Color

    if not args or '--help' in args or '-h' in args:
        print(_USAGE, end='')
        return 0

    params = _parse_args(args)
    if params is None:
        return 1

    if not params["target"]:
        print("--target is required\n", file=sys.stderr, flush=True)
        print(_USAGE, end='', file=sys.stderr)
        return 1

    if not params["code"]:
        print("--code is required\n", file=sys.stderr, flush=True)
        print(_USAGE, end='', file=sys.stderr)
        return 1

    target = params["target"]
    code = params["code"]
    timeout = params["timeout"]

    # Find CIW window
    win = _find_target_window(target)
    if win is None:
        windows = find_all_ciw_windows()
        if not windows:
            print("CIW window not found. Is Virtuoso running?", file=sys.stderr, flush=True)
        else:
            print(f"CIW window '{target}' not found.", file=sys.stderr, flush=True)
        return 1

    log("info", message=f"CIW found: {win['title']!r} (window_id={win['window_id']:#x})")

    # Start ephemeral HTTP listener
    port = find_free_port()
    if not port:
        log("error", message="no free port available")
        return 1

    event = threading.Event()

    class _Server(HTTPServer):
        allow_reuse_address = True
        _result = None
        _event = event

    server = _Server(("127.0.0.1", port), _ResultHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    log("info", message=f"result listener on port {port}")

    # Build and inject SKILL wrapper
    skill_code = _build_skill_wrapper(code, port)
    tmp_dir = os.path.join("/tmp", "skillup")
    os.makedirs(tmp_dir, exist_ok=True)
    il_path = os.path.join(tmp_dir, "run_skill.il")
    with open(il_path, "w") as f:
        f.write(skill_code)
    inject_cmd = f'load("{il_path}")'

    log("info", message="injecting into CIW...")
    ok = _inject_text_to_ciw(inject_cmd, log_file=target, window_id=win["window_id"])
    if not ok:
        log("error", message="inject failed")
        server.shutdown()
        return 1

    # Wait for result
    log("info", message=f"waiting for result (timeout={timeout}s)...")
    received = event.wait(timeout=timeout)
    server.shutdown()

    if not received:
        log("error", message=f"timeout waiting for result ({timeout}s)")
        return 1

    result = server._result
    if result.get("ok"):
        print(f"{Color.YELLOW}result: {result.get('result', '')}{Color.RESET}")
    else:
        log("error", message=f"SKILL error: {result.get('result', '')}")
        return 1

    return 0
