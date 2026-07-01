"""
SkillupAgent App

LLM-powered agent chat using a llamacpp server (OpenAI-compatible API).

Flow:
  1. Connect to llamacpp (/health check)
  2. Select CIW window (same as skillbot inject)
  3. Select agent (scanned from agent_dir/<name>/config.ini)
  4. Generate session UUID; load agent.py plugin if present
  5. Call agent.on_init(id, DDE, agent_dir) → optional model params
  6. Send system.txt as first user message — hidden from UI
  7. Chat: on_pre_req / on_post_req hooks wrap each LLM call
"""

import sys
import os
import json
import uuid
import threading
import configparser
import importlib.util
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.baseapp import BaseApp
from lib.appmgr import register_app_class

_APP_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_LLM_HOST = '127.0.0.1'
DEFAULT_LLM_PORT = 8080
DEFAULT_AGENT_DIR = os.path.join(_APP_DIR, 'data', 'agent')

CONFIG_DEFAULTS = {
    'llamacpp.host': DEFAULT_LLM_HOST,
    'llamacpp.port': str(DEFAULT_LLM_PORT),
    'agent.dir':     DEFAULT_AGENT_DIR,
}


def _llm_health(host, port):
    # Quick TCP precheck so a firewalled/unreachable host fails fast and the
    # whole sync handler stays well under the desktop's 5s response timeout.
    import socket, time
    print(f'[SkillupAgent] llm health check: {host}:{port}', file=sys.stderr, flush=True)
    t0 = time.time()
    try:
        with socket.create_connection((host, int(port)), timeout=1.5):
            pass
    except Exception as e:
        print(f'[warn ][SkillupAgent] llm tcp connect failed in {time.time()-t0:.2f}s: '
              f'{type(e).__name__}: {e}', file=sys.stderr, flush=True)
        return False

    from urllib.request import urlopen
    try:
        with urlopen(f'http://{host}:{port}/health', timeout=2) as r:
            data = json.loads(r.read())
            ok = data.get('status') in ('ok', 'no slot available', 'loading model')
            print(f'[SkillupAgent] llm /health ok in {time.time()-t0:.2f}s: status={data.get("status")!r}',
                  file=sys.stderr, flush=True)
            return ok
    except Exception:
        pass
    try:
        with urlopen(f'http://{host}:{port}/v1/models', timeout=2) as r:
            r.read()
            print(f'[SkillupAgent] llm /v1/models ok in {time.time()-t0:.2f}s',
                  file=sys.stderr, flush=True)
            return True
    except Exception as e:
        print(f'[warn ][SkillupAgent] llm http probe failed in {time.time()-t0:.2f}s: '
              f'{type(e).__name__}: {e}', file=sys.stderr, flush=True)
        return False


def _llm_chat(host, port, messages, model_params=None, timeout=120):
    """POST to /v1/chat/completions. Returns (content, error_str)."""
    import time
    from urllib.request import urlopen, Request
    from urllib.error import URLError
    url = f'http://{host}:{port}/v1/chat/completions'
    body_data = {'messages': messages, 'stream': False}
    if isinstance(model_params, dict):
        body_data.update(model_params)
    body = json.dumps(body_data).encode()
    req = Request(url, data=body, headers={'Content-Type': 'application/json'})
    print(f'[SkillupAgent] llm chat -> {host}:{port} msgs={len(messages)} bytes={len(body)}',
          file=sys.stderr, flush=True)
    t0 = time.time()
    try:
        with urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            content = data['choices'][0]['message']['content']
            print(f'[SkillupAgent] llm chat ok in {time.time()-t0:.2f}s: chars={len(content)}',
                  file=sys.stderr, flush=True)
            return content, None
    except URLError as e:
        print(f'[warn ][SkillupAgent] llm chat URLError in {time.time()-t0:.2f}s: {e}',
              file=sys.stderr, flush=True)
        return None, f'Connection error: {e}'
    except (KeyError, IndexError) as e:
        return None, f'Unexpected response format: {e}'
    except json.JSONDecodeError as e:
        return None, f'Response parse error: {e}'
    except Exception as e:
        print(f'[warn ][SkillupAgent] llm chat failed in {time.time()-t0:.2f}s: '
              f'{type(e).__name__}: {e}', file=sys.stderr, flush=True)
        return None, str(e)


def _load_agent_module(agent_dir):
    """Dynamically load agent.py from agent_dir. Returns module or None."""
    agent_py = Path(agent_dir) / 'agent.py'
    if not agent_py.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location('_skillupagent_plugin', str(agent_py))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f'[SkillupAgent] agent.py load error: {e}', file=sys.stderr)
        return None


# Real stdout, captured before any hook can redirect sys.stdout to stderr
# (see _call_hook below). The subprocess bridge (lib/comm.py) writes
# JSON-RPC frames straight to sys.stdout, so callJS() calls made from
# *inside* a hook (streaming sub-agent events) must go through this
# captured reference instead of the live sys.stdout, or they get silently
# swallowed as stderr log lines.
_REAL_STDOUT = sys.stdout


def _call_hook(mod, name, *args):
    """Call a hook function on the agent module. Returns its return value or None.
    stdout is redirected to stderr during the call so plain print() in agent.py is safe."""
    if mod is None:
        return None
    fn = getattr(mod, name, None)
    if fn is None:
        return None
    old_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        return fn(*args)
    except Exception as e:
        print(f'[SkillupAgent] hook {name} error: {e}', file=sys.stderr)
        return None
    finally:
        sys.stdout = old_stdout


LOG_PATH = '/tmp/skillup/skillupagent/log.txt'


LOG_OLD_PATH = '/tmp/skillup/skillupagent/log.old.txt'
LOG_MAX_BYTES = 1024 * 1024  # 1 MB


def _write_log(entry):
    """Append a JSON log entry to LOG_PATH. Rotates to log.old.txt when > 1 MB."""
    try:
        log_dir = os.path.dirname(LOG_PATH)
        os.makedirs(log_dir, exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) >= LOG_MAX_BYTES:
            os.replace(LOG_PATH, LOG_OLD_PATH)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as e:
        print(f'[SkillupAgent] log write error: {e}', file=sys.stderr)


class SkillupAgentApp(BaseApp):

    def __init__(self, engine, context):
        super().__init__(engine, context)
        self._llm_host     = DEFAULT_LLM_HOST
        self._llm_port     = DEFAULT_LLM_PORT
        self._agent_dir    = DEFAULT_AGENT_DIR
        self._conversation = []   # [{"role": ..., "content": ...}, ...]
        self._selected_ciw   = None
        self._selected_agent = None
        self._session_active = False
        self._session_id     = None
        self._agent_module   = None
        self._init_called    = False
        self._model_params   = {}
        self._agent_ctx      = {}
        # sub-agent sessions: agent_id -> {conversation, session_id, module,
        # model_params, agent_dir, name}. Isolated from the leader's own
        # session fields above; never read/written by the leader's _bg.
        self._subsessions    = {}
        # accumulator for the current on_post_req call: list of
        # {'agent_id', 'agent_name', 'turns'} dicts, one per call_subagent().
        self._subagent_turns = []

    # ── CLI ─────────────────────────────────────────────────────

    def on_run_cli(self, args):
        print('SkillupAgent: CLI mode not implemented. Use --desktop mode.',
              file=sys.stderr)
        return 1

    # ── Desktop init ─────────────────────────────────────────────

    def on_run_desktop_initialize(self):
        config = self.load_config(CONFIG_DEFAULTS)
        self._llm_host  = config.get('llamacpp.host', DEFAULT_LLM_HOST)
        self._llm_port  = int(config.get('llamacpp.port', DEFAULT_LLM_PORT))
        self._agent_dir = config.get('agent.dir', DEFAULT_AGENT_DIR)

        self.register_handlers({
            'agent_connect':     self._handle_connect,
            'agent_set_host':    self._handle_set_host,
            'agent_ciw_list':    self._handle_ciw_list,
            'agent_list':        self._handle_agent_list,
            'agent_start':       self._handle_agent_start,
            'agent_chat':        self._handle_chat,
            'agent_reset':       self._handle_reset,
            'agent_get_config':  self._handle_get_config,
            'agent_save_config': self._handle_save_config,
        })
        return 0

    def on_close(self):
        self._session_active = False
        self._conversation   = []
        self._call_on_exit()

    def _stream_callJS(self, action, data):
        """callJS() safe to call from inside a hook (i.e. while sys.stdout may
        be redirected to sys.stderr by _call_hook). Restores the real stdout
        for the duration of the call so subprocess-mode JSON-RPC notifications
        aren't misrouted to the stderr log stream."""
        cur = sys.stdout
        sys.stdout = _REAL_STDOUT
        try:
            self.callJS(action, data)
        finally:
            sys.stdout = cur

    # ── Default system prompt ─────────────────────────────────────

    _LANG_INSTRUCTION = {
        'ko': '항상 한국어로 답변하세요.',
        'en': 'Always respond in English.',
    }

    def _default_system_prompt(self, language):
        """Return the prefix prepended to every agent's system.txt."""
        parts = []
        lang_instruction = self._LANG_INSTRUCTION.get(language, '')
        if lang_instruction:
            parts.append(lang_instruction)
        return '\n\n'.join(parts)

    # ── DDE ──────────────────────────────────────────────────────

    def _make_agent_ctx(self, language='en', allow_subagent=True):
        """Build the agent context dict passed to agent.py hooks as 'agent'.

        allow_subagent=False omits 'call_subagent' from the context, which is
        how sub-agent nesting is capped at depth 1: a sub-agent's own hooks
        get call_skill/language only, so they cannot delegate further.
        """
        def call_skill(code):
            try:
                from app.skillbot.inject.skillbot_inject import (
                    _inject_text_to_ciw, _write_and_load)
                ciw = self._selected_ciw
                window_id = ciw.get('window_id') if ciw else None
                # Multi-line code goes through a temp file to avoid newlines
                # splitting the clipboard paste into multiple CIW inputs.
                if '\n' in code:
                    inject_str = _write_and_load(code, 'agent')
                else:
                    inject_str = code
                ok = _inject_text_to_ciw(inject_str, window_id=window_id)
                if not ok:
                    print('[SkillupAgent] call_skill: inject failed', file=sys.stderr)
                return ok
            except Exception as e:
                print(f'[SkillupAgent] call_skill error: {e}', file=sys.stderr)
                return False
        ctx = {'call_skill': call_skill, 'language': language}
        if allow_subagent:
            ctx['call_subagent'] = lambda agent_id, message, display=None: self._call_subagent(
                agent_id, message, language, display=display)
        return ctx

    # ── Sub-agent ────────────────────────────────────────────────

    def _call_subagent(self, agent_id, message, language, display=None):
        """Run one delegation turn against a sub-agent, isolated from the
        leader's own session fields (_conversation/_session_id/_agent_module/
        _model_params are never touched here).

        Sub-sessions persist per agent_id in self._subsessions for the
        lifetime of the leader session, so a second call_subagent() for the
        same agent_id continues that sub-agent's own conversation history
        (e.g. "change the width you just drew to 4").

        `display`, if given, is a human-readable version of `message` shown
        in the UI's streamed leader turn instead of the raw `message` text
        (which is often a compact key=value string meant for the sub-agent's
        LLM, not for display). The raw `message` is still what's actually
        sent to the sub-agent — `display` only affects rendering.

        Returns the sub-agent's response text, or None on failure.
        """
        agent_id = str(agent_id).strip()
        message = str(message)
        display_message = str(display) if display is not None else message

        agents = self._scan_agents(language)
        agent = next((a for a in agents if a['id'] == agent_id), None)
        if agent is None:
            print(f'[SkillupAgent] call_subagent: agent not found: {agent_id}', file=sys.stderr)
            return None

        sub = self._subsessions.get(agent_id)
        if sub is None:
            system_path = Path(agent['dir']) / 'system.txt'
            if not system_path.exists():
                print(f'[SkillupAgent] call_subagent: system.txt not found for {agent_id}',
                      file=sys.stderr)
                return None
            system_content = system_path.read_text(encoding='utf-8').strip()
            default_prompt = self._default_system_prompt(language)
            if default_prompt:
                system_content = default_prompt + '\n\n' + system_content

            sub_session_id = str(uuid.uuid4())
            # Sub-agent hooks get call_skill/language only — no call_subagent,
            # so delegation cannot recurse past depth 1.
            sub_ctx = self._make_agent_ctx(language, allow_subagent=False)
            sub_module = _load_agent_module(agent['dir'])

            raw = _call_hook(sub_module, 'on_init', sub_session_id, sub_ctx,
                              agent['dir'], system_content)
            if isinstance(raw, dict):
                sub_model_params = raw.get('hyperparameter', {})
                send_system = raw.get('system_prompt', system_content)
            else:
                sub_model_params = {}
                send_system = system_content

            init_messages = [{'role': 'user', 'content': send_system}]
            init_content, err = _llm_chat(
                self._llm_host, self._llm_port, init_messages,
                model_params=sub_model_params,
            )
            if err:
                print(f'[SkillupAgent] call_subagent: init failed for {agent_id}: {err}',
                      file=sys.stderr)
                return None

            sub = {
                'conversation': [
                    {'role': 'user',      'content': send_system},
                    {'role': 'assistant', 'content': init_content},
                ],
                'session_id':   sub_session_id,
                'module':       sub_module,
                'ctx':          sub_ctx,
                'model_params': sub_model_params,
                'agent_dir':    agent['dir'],
                'name':         agent['name'],
            }
            self._subsessions[agent_id] = sub

        turns = []

        pre_result = _call_hook(sub['module'], 'on_pre_req', sub['session_id'], sub['ctx'],
                                 list(sub['conversation']), message)
        send_message = pre_result.get('new_message', message) if isinstance(pre_result, dict) else message

        # Stream the leader→sub-agent turn as soon as it's known, before the
        # (potentially slow) LLM round-trip — this is what makes the leader
        # turn appear immediately instead of after the whole delegation
        # chain completes.
        leader_name = self._selected_agent['name'] if self._selected_agent else None
        self._stream_callJS('onAgentEvent', {
            'type':        'subagent_turn',
            'agent_id':    agent_id,
            'agent_name':  sub['name'],
            'leader_name': leader_name,
            'role':        'leader',
            'content':     display_message,
        })

        full_msgs = sub['conversation'] + [{'role': 'user', 'content': send_message}]
        content, err = _llm_chat(
            self._llm_host, self._llm_port, full_msgs,
            model_params=sub['model_params'],
        )
        if err:
            print(f'[SkillupAgent] call_subagent: chat failed for {agent_id}: {err}',
                  file=sys.stderr)
            return None

        sub['conversation'].append({'role': 'user',      'content': send_message})
        sub['conversation'].append({'role': 'assistant', 'content': content})

        post_result = _call_hook(sub['module'], 'on_post_req', sub['session_id'], sub['ctx'],
                                  list(sub['conversation']), content)
        display = post_result.get('response', content) if isinstance(post_result, dict) else content

        # Stream the sub-agent's reply the moment it's ready.
        self._stream_callJS('onAgentEvent', {
            'type':        'subagent_turn',
            'agent_id':    agent_id,
            'agent_name':  sub['name'],
            'leader_name': leader_name,
            'role':        'subagent',
            'content':     display,
        })

        turns.append({'role': 'leader',   'content': send_message})
        turns.append({'role': 'subagent', 'content': display})

        # Merge into any existing transcript entry for this agent_id within
        # the current on_post_req call, so repeated delegations in one turn
        # accumulate under a single subagents[] entry.
        existing = next((e for e in self._subagent_turns if e['agent_id'] == agent_id), None)
        if existing is not None:
            existing['turns'].extend(turns)
        else:
            self._subagent_turns.append({
                'agent_id':   agent_id,
                'agent_name': sub['name'],
                'turns':      turns,
            })

        return display

    def _call_on_exit(self):
        if self._init_called and self._agent_module is not None:
            _call_hook(self._agent_module, 'on_exit',
                       self._session_id, self._agent_ctx, list(self._conversation))
        self._init_called  = False
        self._agent_module = None
        self._model_params = {}
        self._session_id   = None
        self._agent_ctx    = {}

        for agent_id, sub in self._subsessions.items():
            _call_hook(sub['module'], 'on_exit', sub['session_id'], sub['ctx'],
                       list(sub['conversation']))
        self._subsessions    = {}
        self._subagent_turns = []

    # ── Connection check ─────────────────────────────────────────

    def _handle_connect(self, data, language):
        ok = _llm_health(self._llm_host, self._llm_port)
        return {
            'success': ok,
            'host':    self._llm_host,
            'port':    self._llm_port,
            'error':   None if ok else
                       f'Cannot reach llamacpp at {self._llm_host}:{self._llm_port}',
        }

    def _handle_set_host(self, data, language):
        host = str(data.get('host', DEFAULT_LLM_HOST)).strip()
        try:
            port = int(data.get('port', DEFAULT_LLM_PORT))
        except (TypeError, ValueError):
            return {'success': False, 'error': 'Invalid port'}
        if not host:
            return {'success': False, 'error': 'Host is required'}
        if not (1 <= port <= 65535):
            return {'success': False, 'error': 'Port must be 1-65535'}
        self._llm_host = host
        self._llm_port = port
        return {'success': True}

    # ── CIW list ─────────────────────────────────────────────────

    def _handle_ciw_list(self, data, language):
        try:
            from app.skillbot.inject.skillbot_inject import find_all_ciw_windows
            ciw_windows = find_all_ciw_windows()
        except Exception as e:
            print(f'[SkillupAgent] find_all_ciw_windows error: {e}', file=sys.stderr)
            return {'success': False, 'error': str(e), 'ciw_windows': []}
        return {'success': True, 'ciw_windows': ciw_windows}

    # ── Agent list ───────────────────────────────────────────────

    def _handle_agent_list(self, data, language):
        return {'success': True, 'agents': self._scan_agents(language)}

    _STAGING_UUID = '00000000-0000-0000-0000-000000000000'

    @staticmethod
    def _current_account_id():
        return os.environ.get('USER', os.environ.get('USERNAME', 'user'))

    def _scan_agents(self, language='en'):
        agents = []
        agent_dir = Path(self._agent_dir)
        if not agent_dir.is_dir():
            print(f'[SkillupAgent] agent dir not found: {agent_dir}', file=sys.stderr)
            return agents

        account_id = self._current_account_id()

        for subdir in sorted(agent_dir.iterdir()):
            if not subdir.is_dir():
                continue

            # Staging directory: only expose the current user's own staging agent,
            # skip all other accounts under the zero-UUID path.
            if subdir.name == self._STAGING_UUID:
                staging_agent_dir = subdir / account_id
                if not staging_agent_dir.is_dir():
                    continue
                self._try_append_agent(agents, staging_agent_dir, language, staging=True)
                continue

            config_file = subdir / 'config.ini'
            if not config_file.exists():
                continue
            self._try_append_agent(agents, subdir, language, staging=False)

        return agents

    def _try_append_agent(self, agents, subdir, language, staging=False):
        config_file = subdir / 'config.ini'
        if not config_file.exists():
            return
        try:
            cp = configparser.ConfigParser()
            cp.read(str(config_file), encoding='utf-8')
            agent_id    = cp.get('config', 'id', fallback=subdir.name)
            name        = cp.get('config', 'name', fallback=subdir.name)
            desc        = cp.get('config', f'desc.{language}', fallback=None) \
                          or cp.get('config', 'desc', fallback='')
            require_ciw = cp.getboolean('config', 'require_ciw', fallback=True)
            if staging:
                name = f'[WIP] {name}'
            agents.append({
                'id':          agent_id,
                'name':        name,
                'desc':        desc,
                'require_ciw': require_ciw,
                'dir':         str(subdir),
                'has_system':  (subdir / 'system.txt').exists(),
                'has_plugin':  (subdir / 'agent.py').exists(),
                'staging':     staging,
            })
        except Exception as e:
            print(f'[SkillupAgent] skip agent {subdir.name}: {e}', file=sys.stderr)

    # ── Session start ────────────────────────────────────────────

    def _handle_agent_start(self, data, language):
        """Start session: select CIW + agent, run plugin hooks, send system.txt."""
        ciw_info = data.get('ciw')
        agent_id = data.get('agent_id', '').strip()

        if not agent_id:
            return {'success': False, 'error': 'agent_id required'}

        agents = self._scan_agents(language)
        agent = next((a for a in agents if a['id'] == agent_id), None)
        if agent is None:
            return {'success': False, 'error': f'Agent not found: {agent_id}'}

        system_path = Path(agent['dir']) / 'system.txt'
        if not system_path.exists():
            return {'success': False, 'error': f'system.txt not found for agent: {agent_id}'}

        system_content = system_path.read_text(encoding='utf-8').strip()
        if not system_content:
            return {'success': False, 'error': 'system.txt is empty'}

        default_prompt = self._default_system_prompt(language)
        if default_prompt:
            system_content = default_prompt + '\n\n' + system_content

        # Tear down any previous session's plugin before starting a new one
        self._call_on_exit()

        self._selected_ciw   = ciw_info
        self._selected_agent = agent
        self._conversation   = []
        self._session_active = True
        self._session_id     = str(uuid.uuid4())
        self._agent_ctx      = self._make_agent_ctx(language)
        self._agent_module   = _load_agent_module(agent['dir'])

        session_id    = self._session_id
        agent_module  = self._agent_module
        agent_ctx     = self._agent_ctx
        agent_dir_str = agent['dir']

        log_enabled = bool(data.get('log', False))
        print(f'[SkillupAgent] starting session: agent={agent["name"]} id={session_id}',
              file=sys.stderr)

        def _bg():
            import datetime
            # on_init fires before system.txt so hyperparameter/system_prompt apply to first LLM call
            print(f'[SkillupAgent] on_init hook start', file=sys.stderr, flush=True)
            raw = _call_hook(agent_module, 'on_init', session_id, agent_ctx, agent_dir_str, system_content)
            print(f'[SkillupAgent] on_init hook done', file=sys.stderr, flush=True)
            self._init_called  = True
            if isinstance(raw, dict):
                self._model_params = raw.get('hyperparameter', {})
                send_system = raw.get('system_prompt', system_content)
            else:
                self._model_params = {}
                send_system = system_content
            if self._model_params:
                print(f'[SkillupAgent] hyperparameter from on_init: {self._model_params}',
                      file=sys.stderr)

            if log_enabled and send_system != system_content:
                _write_log({'time': datetime.datetime.now().isoformat(), 'event': 'system_prompt',
                            'original': system_content, 'modified': send_system})
            elif log_enabled:
                _write_log({'time': datetime.datetime.now().isoformat(), 'event': 'system_prompt',
                            'content': send_system})

            if not self._session_active:
                return

            messages = [{'role': 'user', 'content': send_system}]
            content, err = _llm_chat(
                self._llm_host, self._llm_port, messages,
                model_params=self._model_params,
            )

            if not self._session_active:
                return

            if err:
                print(f'[SkillupAgent] start error: {err}', file=sys.stderr)
                self._session_active = False
                self.callJS('onAgentEvent', {'type': 'start_error', 'error': err})
                return

            if log_enabled:
                _write_log({'time': datetime.datetime.now().isoformat(), 'event': 'system_response',
                            'content': content})

            # Keep hidden initialization turns in history for context
            self._conversation = [
                {'role': 'user',      'content': send_system},
                {'role': 'assistant', 'content': content},
            ]
            usage_path_lang = Path(agent_dir_str) / f'usage.{language}.txt'
            usage_path_base = Path(agent_dir_str) / 'usage.txt'
            if usage_path_lang.exists():
                usage_text = usage_path_lang.read_text(encoding='utf-8').strip()
            elif usage_path_base.exists():
                usage_text = usage_path_base.read_text(encoding='utf-8').strip()
            else:
                usage_text = None

            print('[SkillupAgent] agent ready', file=sys.stderr)
            self.callJS('onAgentEvent', {'type': 'ready', 'usage': usage_text})

        threading.Thread(target=_bg, daemon=True).start()
        return {'success': True, 'status': 'starting'}

    # ── Chat ─────────────────────────────────────────────────────

    def _handle_chat(self, data, language):
        if not self._session_active:
            return {'success': False, 'error': 'No active session'}
        message = data.get('message', '').strip()
        if not message:
            return {'success': False, 'error': 'Empty message'}
        log_enabled = bool(data.get('log', False))

        session_id   = self._session_id
        agent_module = self._agent_module
        agent_ctx    = self._agent_ctx
        model_params = self._model_params

        def _bg():
            import datetime

            msgs = list(self._conversation)  # snapshot — passed to on_pre_req
            result = _call_hook(agent_module, 'on_pre_req', session_id, agent_ctx, msgs, message)
            send_message = result.get('new_message', message) if isinstance(result, dict) else message

            if log_enabled:
                entry = {'time': datetime.datetime.now().isoformat(), 'event': 'new_message',
                         'original': message}
                if send_message != message:
                    entry['modified'] = send_message
                _write_log(entry)

            full_msgs = msgs + [{'role': 'user', 'content': send_message}]
            content, err = _llm_chat(
                self._llm_host, self._llm_port, full_msgs,
                model_params=model_params,
            )

            if not self._session_active:
                return

            if err:
                print(f'[SkillupAgent] chat error: {err}', file=sys.stderr)
                self.callJS('onAgentEvent', {'type': 'chat_error', 'error': err})
                return

            self._conversation.append({'role': 'user',      'content': send_message})
            self._conversation.append({'role': 'assistant', 'content': content})

            # Reset the accumulator so this turn's payload only carries
            # delegations made during this on_post_req call.
            self._subagent_turns = []
            result = _call_hook(agent_module, 'on_post_req', session_id, agent_ctx,
                                list(self._conversation), content)
            display = result.get('response', content) if isinstance(result, dict) else content
            subagent_turns = self._subagent_turns
            self._subagent_turns = []

            if log_enabled:
                entry = {'time': datetime.datetime.now().isoformat(), 'event': 'response',
                         'original': content}
                if display != content:
                    entry['modified'] = display
                _write_log(entry)

            # Sub-agent turns were already streamed live via 'subagent_turn'
            # events fired from inside on_post_req (_call_subagent). The
            # final 'response' event only carries a flag, not the full
            # transcript again, so the UI doesn't double-render it.
            event = {'type': 'response', 'content': display}
            if subagent_turns:
                event['had_subagents'] = True
            self.callJS('onAgentEvent', event)

        threading.Thread(target=_bg, daemon=True).start()
        return {'success': True, 'status': 'pending'}

    # ── Reset ────────────────────────────────────────────────────

    def _handle_reset(self, data, language):
        self._session_active = False
        self._conversation   = []
        self._selected_ciw   = None
        self._selected_agent = None
        self._call_on_exit()
        return {'success': True}

    # ── Config ───────────────────────────────────────────────────

    def _handle_get_config(self, data, language):
        config = self.load_config(CONFIG_DEFAULTS)
        return {
            'success':   True,
            'host':      config.get('llamacpp.host', DEFAULT_LLM_HOST),
            'port':      int(config.get('llamacpp.port', DEFAULT_LLM_PORT)),
            'agent_dir': config.get('agent.dir', DEFAULT_AGENT_DIR),
        }

    def _handle_save_config(self, data, language):
        config = self.load_config(CONFIG_DEFAULTS)
        if 'host' in data:
            config['llamacpp.host'] = str(data['host']).strip()
        if 'port' in data:
            config['llamacpp.port'] = str(int(data['port']))
        if 'agent_dir' in data:
            config['agent.dir'] = str(data['agent_dir']).strip()
        self.save_config(config)
        self._llm_host  = config.get('llamacpp.host', DEFAULT_LLM_HOST)
        self._llm_port  = int(config.get('llamacpp.port', DEFAULT_LLM_PORT))
        self._agent_dir = config.get('agent.dir', DEFAULT_AGENT_DIR)
        return {'success': True}


register_app_class(SkillupAgentApp)
