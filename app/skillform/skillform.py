"""
Skill Form App

JSON Form Designer and Runner for SKILL automation.

- Runner: Load a JSON Schema form and collect user input, return result to SKILL
- Designer: Visually design JSON Schema forms and save as .json files

Usage
    desktop:
    python3 skillup.py --desktop --app:skillform

    standalone:
    python3 skillup.py --desktop --app:skillform --skillform-run=/tmp/form.json
"""

import os
import sys
import json
import socket
import threading
from typing import List, Optional, TYPE_CHECKING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.appmgr import AppContext, register_app_class
from lib.baseapp import BaseApp, BaseAppState
from lib import board as board_lib

if TYPE_CHECKING:
    from lib.webui import WebUIEngine


class SkillFormApp(BaseApp):
    """Skill Form Application - Form Designer and Runner"""

    def __init__(self, engine: Optional['WebUIEngine'], context: AppContext):
        super().__init__(engine, context)
        self._runner_process = None
        self._caller_conn = None      # TCP socket to parent caller process
        self._caller_thread = None

    def on_run_cli(self, args: List[str]) -> int:
        """CLI mode: run a form and print result as JSON to stdout"""
        schema_path = None
        request_id = None

        for arg in args:
            if arg.startswith('--schema='):
                schema_path = arg[9:]
            elif arg.startswith('--id='):
                request_id = arg[5:]

        if not schema_path:
            print('[error] Usage: --app:skillform --schema=<path.json> [--id=<request_id>]',
                  file=sys.stderr)
            return 1

        schema_path = os.path.expanduser(schema_path)
        if not os.path.exists(schema_path):
            print(f'[error] Schema file not found: {schema_path}', file=sys.stderr)
            return 1

        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
        except Exception as e:
            print(f'[error] Failed to load schema: {e}', file=sys.stderr)
            return 1

        print(json.dumps({'schema': schema, 'request_id': request_id}))
        return 0

    def on_run_desktop_initialize(self) -> int:
        """Desktop mode initialization"""
        config = self.load_config({
            'runner.last_schema': '',
            'designer.last_file': '',
            'general.board_dir': '',
        })
        self._board_config = config

        # Check if --skillform-run=<path> and/or --skillform-caller-port=<N> were passed via environment
        auto_run_path = None
        caller_port = None
        raw_args = os.environ.get('_SKILLUP_APP_ARGS')
        if raw_args:
            try:
                extra_args = json.loads(raw_args)
                for arg in extra_args:
                    if arg.startswith('--skillform-run='):
                        auto_run_path = arg[len('--skillform-run='):]
                    elif arg.startswith('--skillform-caller-port='):
                        caller_port = int(arg[len('--skillform-caller-port='):])
            except Exception:
                pass

        # Load auto-run schema if specified
        auto_run_schema = None
        if auto_run_path:
            auto_run_path = os.path.expanduser(auto_run_path)
            try:
                with open(auto_run_path, 'r', encoding='utf-8') as f:
                    auto_run_schema = json.load(f)
            except Exception as e:
                print(f'[warn ] --skillform-run: failed to load {auto_run_path}: {e}',
                      file=sys.stderr)

        # Load last designer file on startup
        last_file = config.get('designer.last_file', '')
        designer_schema = None
        if last_file:
            try:
                with open(last_file, 'r', encoding='utf-8') as f:
                    designer_schema = json.load(f)
            except Exception:
                last_file = ''

        # Load last runner schema on startup (only if not overridden by auto_run)
        last_runner_path = '' if auto_run_schema else config.get('runner.last_schema', '')
        last_runner_schema = None
        if last_runner_path and not auto_run_schema:
            try:
                resolved = board_lib.resolve_form_path(last_runner_path)
                if os.path.exists(resolved):
                    with open(resolved, 'r', encoding='utf-8') as f:
                        candidate = json.load(f)
                    # Skip board list forms (they contain board-type fields, not for standalone runner)
                    fields = candidate.get('fields', [])
                    if not any(fd.get('type') == 'board' for fd in fields):
                        last_runner_schema = candidate
                    else:
                        last_runner_path = ''
            except Exception:
                last_runner_path = ''

        self.state.update({
            'runner_schema': auto_run_schema or last_runner_schema,
            'runner_schema_path': auto_run_path if auto_run_schema else last_runner_path,
            'runner_result': None,
            'runner_waiting': auto_run_schema is not None,
            'designer_schema': designer_schema,
            'designer_file': last_file,
            'auto_run': auto_run_schema is not None,
        }, notify=False)

        self.register_handlers({
            # Runner handlers
            'runner_load_schema': self._handle_runner_load_schema,
            'runner_submit': self._handle_runner_submit,
            'runner_cancel': self._handle_runner_cancel,
            'runner_get_state': self._handle_runner_get_state,
            'runner_button_click': self._handle_runner_button_click,
            # Designer handlers
            'designer_load': self._handle_designer_load,
            'designer_save': self._handle_designer_save,
            'designer_get_state': self._handle_designer_get_state,
            'designer_run': self._handle_designer_run,
            'designer_run_standalone': self._handle_designer_run_standalone,
            'designer_prepare_code': self._handle_designer_prepare_code,
            'runner_poll': self._handle_runner_poll,
            # Standalone mode
            'standalone_close': self._handle_standalone_close,
            # Board handlers
            'board_list': self._handle_board_list,
            'board_get': self._handle_board_get,
            'board_read_detail_fields': self._handle_board_read_detail_fields,
        })

        # Connect to caller process if port was provided
        if caller_port:
            self._start_caller_connection(caller_port)

        return 0

    # -------------------------------------------------------------------------
    # Runner handlers
    # -------------------------------------------------------------------------

    def _handle_runner_load_schema(self, data: dict, language: str) -> dict:
        """Load a JSON Schema file for the runner"""
        path = data.get('path', '').strip()
        schema = data.get('schema', None)

        if schema is not None:
            # Schema provided directly (e.g., from SKILL via IPC)
            # notify=True so the runner iframe gets state_update even if it didn't trigger the call
            self.state.update({
                'runner_schema': schema,
                'runner_schema_path': '',
                'runner_result': None,
                'runner_waiting': True,
            }, notify=True)
            return {'success': True, 'schema': schema}

        if not path:
            return {'success': False, 'error': 'No path provided'}

        path = os.path.expanduser(path)
        path = board_lib.resolve_form_path(path)
        if not os.path.exists(path):
            return {'success': False, 'error': f'File not found: {path}'}

        try:
            with open(path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
        except Exception as e:
            return {'success': False, 'error': f'Failed to load schema: {e}'}

        self.state.update({
            'runner_schema': schema,
            'runner_schema_path': path,
            'runner_result': None,
            'runner_waiting': True,
        }, notify=False)

        # Save last used path, but skip board list forms
        is_board_list = any(fd.get('type') == 'board' for fd in schema.get('fields', []))
        if not is_board_list:
            from lib.config import save_config
            save_config(self.context.config_path, {'runner.last_schema': path})

        return {'success': True, 'schema': schema}

    def _handle_runner_button_click(self, data: dict, language: str) -> dict:
        """Button clicked in runner - forward event to caller, and handle board commands."""
        button_id = data.get('button_id', '')
        values = data.get('values', {})
        board_command = data.get('board_command', '')
        record_id = data.get('record_id', '')

        result = {'success': True}

        if board_command in ('POST', 'MODIFY', 'DELETE'):
            try:
                current_schema = self.state.get('runner_schema')
                form_id = ((current_schema or {}).get('docProps') or {}).get('formId', '')
                detail_path = self.state.get('runner_schema_path') or ''
                board_dir = board_lib.get_board_dir(self._board_config)
                is_sys = board_lib.is_under_system_dir(detail_path)
                db_path = board_lib.get_db_path(board_dir, is_sys)

                if board_command == 'POST':
                    new_id = board_lib.post_record(db_path, form_id, values)
                    result['board_ok'] = True
                    result['record_id'] = new_id
                elif board_command == 'MODIFY' and record_id:
                    board_lib.modify_record(db_path, record_id, values)
                    result['board_ok'] = True
                    result['record_id'] = record_id
                elif board_command == 'DELETE' and record_id:
                    board_lib.delete_record(db_path, record_id)
                    result['board_ok'] = True
            except Exception as e:
                print(f'[error] board command {board_command} failed: {e}', file=sys.stderr)
                result['board_ok'] = False
                result['error'] = str(e)

        self._send_to_caller({'type': 'button_click', 'button_id': button_id, 'values': values,
                              'board_command': board_command})
        return result

    def _send_to_caller(self, event: dict):
        """Send a JSON event to the parent caller process"""
        if not self._caller_conn:
            return
        try:
            self._caller_conn.sendall((json.dumps(event) + '\n').encode('utf-8'))
        except Exception as e:
            print(f'[warn ] caller send failed: {e}', file=sys.stderr)
            self._caller_conn = None

    def _start_caller_connection(self, port: int):
        """Connect to caller's TCP server and start listener thread"""
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect(('127.0.0.1', port))
            self._caller_conn = conn
        except Exception as e:
            print(f'[warn ] --skillform-caller-port: failed to connect to {port}: {e}',
                  file=sys.stderr)
            return

        self._send_to_caller({'type': 'ready'})

        def _reader():
            try:
                for line in conn.makefile('r', encoding='utf-8'):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    if msg.get('type') == 'close':
                        def _exit():
                            import time
                            time.sleep(0.05)
                            sys.exit(0)
                        threading.Thread(target=_exit, daemon=True).start()
                        return
                    elif msg.get('type') == 'set_values':
                        self.state.update({
                            'runner_set_values': msg.get('values', {}),
                            'runner_set_values_seq': self.state.get('runner_set_values_seq', 0) + 1,
                        }, notify=False)  # JS polls via runner_get_state; no cross-thread callJS needed
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        self._caller_thread = threading.Thread(target=_reader, daemon=True)
        self._caller_thread.start()

    def _handle_runner_submit(self, data: dict, language: str) -> dict:
        """User submitted the form - save result"""
        values = data.get('values', {})
        self.state.update({
            'runner_result': values,
            'runner_waiting': False,
        }, notify=False)
        return {'success': True}

    def _handle_runner_cancel(self, data: dict, language: str) -> dict:
        """User cancelled the form"""
        self.state.update({
            'runner_result': None,
            'runner_waiting': False,
        }, notify=False)
        return {'success': True}

    def _handle_runner_get_state(self, data: dict, language: str) -> dict:
        """Get current runner state"""
        return {
            'schema': self.state.get('runner_schema'),
            'schema_path': self.state.get('runner_schema_path'),
            'result': self.state.get('runner_result'),
            'waiting': self.state.get('runner_waiting'),
            'runner_schema_version': self.state.get('runner_schema_version', 0),
            'auto_run': self.state.get('auto_run', False),
            'set_values': self.state.get('runner_set_values'),
            'set_values_seq': self.state.get('runner_set_values_seq', -1),
        }

    # -------------------------------------------------------------------------
    # Designer handlers
    # -------------------------------------------------------------------------

    def _handle_designer_load(self, data: dict, language: str) -> dict:
        """Load a schema file into the designer"""
        path = data.get('path', '').strip()
        if not path:
            return {'success': False, 'error': 'No path provided'}

        path = os.path.expanduser(path)
        if not os.path.exists(path):
            # Return empty schema for new file
            self.state.update({
                'designer_schema': {},
                'designer_file': path,
            }, notify=False)
            return {'success': True, 'schema': {}, 'is_new': True}

        try:
            with open(path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
        except Exception as e:
            return {'success': False, 'error': f'Failed to load: {e}'}

        self.state.update({
            'designer_schema': schema,
            'designer_file': path,
        }, notify=False)

        from lib.config import save_config
        save_config(self.context.config_path, {'designer.last_file': path})

        return {'success': True, 'schema': schema}

    def _handle_designer_save(self, data: dict, language: str) -> dict:
        """Save schema JSON to file"""
        path = data.get('path', '').strip()
        schema = data.get('schema', None)

        if not path:
            return {'success': False, 'error': 'No path provided'}
        if schema is None:
            return {'success': False, 'error': 'No schema provided'}

        path = os.path.expanduser(path)

        try:
            schema = {'schemaVersion': 1, **schema}
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(schema, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return {'success': False, 'error': f'Failed to save: {e}'}

        self.state.update({'designer_file': path}, notify=False)

        from lib.config import save_config
        save_config(self.context.config_path, {'designer.last_file': path})

        return {'success': True}

    def _handle_designer_get_state(self, data: dict, language: str) -> dict:
        """Get current designer state"""
        return {
            'schema': self.state.get('designer_schema'),
            'file': self.state.get('designer_file'),
        }

    def _handle_designer_run(self, data: dict, language: str) -> dict:
        """Store form schema from designer so runner can load it"""
        schema = data.get('schema')
        if schema is None:
            return {'success': False, 'error': 'No schema provided'}
        version = self.state.get('runner_schema_version', 0) + 1
        self.state.update({
            'runner_schema': schema,
            'runner_schema_path': '',
            'runner_result': None,
            'runner_waiting': True,
            'runner_schema_version': version,
        }, notify=False)
        return {'success': True, 'version': version}

    def _handle_designer_run_standalone(self, data: dict, language: str) -> dict:
        """Save schema to temp file and launch a standalone runner subprocess"""
        import tempfile
        import subprocess as _subprocess
        import threading

        schema = data.get('schema')
        if schema is None:
            return {'success': False, 'error': 'No schema provided'}

        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', prefix='skillform_run_',
                dir=tempfile.gettempdir(), delete=False, encoding='utf-8'
            ) as f:
                json.dump(schema, f, ensure_ascii=False, indent=2)
                tmp_path = f.name
        except Exception as e:
            return {'success': False, 'error': f'Failed to write temp file: {e}'}

        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        skillup_py = os.path.join(script_dir, 'skillup.py')

        if self._runner_process and self._runner_process.poll() is None:
            try:
                self._runner_process.terminate()
                self._runner_process.wait(timeout=2)
            except Exception:
                try:
                    self._runner_process.kill()
                except Exception:
                    pass

        try:
            self._runner_process = _subprocess.Popen(
                [sys.executable, skillup_py, '--desktop', '--app:skillform',
                 f'--skillform-run={tmp_path}'],
                stdout=_subprocess.DEVNULL,
                stderr=_subprocess.DEVNULL,
            )
        except Exception as e:
            return {'success': False, 'error': f'Failed to launch runner: {e}'}

        def _cleanup_temp():
            self._runner_process.wait()
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        threading.Thread(target=_cleanup_temp, daemon=True).start()
        return {'success': True}

    def _handle_designer_prepare_code(self, data: dict, language: str) -> dict:
        import json as _json
        script_dir  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        skillup_py  = os.path.join(script_dir, 'skillup.py')
        libform_il  = os.path.join(script_dir, 'app', 'skillform', 'lib', 'skill', 'libform.il')
        executor_sh = os.path.normpath(os.path.join(script_dir, '..', 'skillup-tool', 'skillup-executor.sh'))

        has_executor = os.path.isfile(executor_sh)
        caller_il_name = 'caller_with_executor.il' if has_executor else 'caller.il'
        caller_il = os.path.join(script_dir, 'app', 'skillform', 'example', 'caller', 'skill', caller_il_name)

        schema = data.get('schema')
        form_path = '/tmp/skillform_sample.json'
        if schema:
            try:
                with open(form_path, 'w', encoding='utf-8') as f:
                    _json.dump(schema, f, ensure_ascii=False, indent=2)
            except Exception as e:
                return {'success': False, 'error': str(e)}

        return {
            'success': True,
            'skillup_py': skillup_py,
            'libform_il': libform_il,
            'caller_il': caller_il,
            'form_path': form_path,
            'has_executor': has_executor,
        }

    # -------------------------------------------------------------------------
    # Board handlers
    # -------------------------------------------------------------------------

    def _board_db_path(self, detail_form_path: str) -> str:
        board_dir = board_lib.get_board_dir(self._board_config)
        resolved = board_lib.resolve_form_path(detail_form_path) if detail_form_path else ''
        is_sys = board_lib.is_under_system_dir(resolved) if resolved else False
        return board_lib.get_db_path(board_dir, is_sys)

    def _handle_board_list(self, data: dict, language: str) -> dict:
        detail_form_path = board_lib.resolve_form_path(data.get('detail_form_path', ''))
        form_id = board_lib.read_form_id(detail_form_path) if detail_form_path else None
        if not form_id:
            current_schema = self.state.get('runner_schema')
            form_id = ((current_schema or {}).get('docProps') or {}).get('formId', '')
        if not form_id:
            return {'records': []}
        try:
            db_path = self._board_db_path(detail_form_path)
            records = board_lib.list_records(db_path, form_id)
            return {'records': records}
        except Exception as e:
            print(f'[error] board_list: {e}', file=sys.stderr)
            return {'records': [], 'error': str(e)}

    def _handle_board_read_detail_fields(self, data: dict, language: str) -> dict:
        """Read field ids from a detail form JSON without touching runner state."""
        SYSTEM_FIELDS = [
            {'id': '@created_at', 'label': '@created_at'},
            {'id': '@updated_at', 'label': '@updated_at'},
            {'id': '@record_id',  'label': '@record_id'},
        ]
        path = data.get('path', '').strip()
        if not path:
            return {'fields': [], 'system_fields': SYSTEM_FIELDS}
        resolved = board_lib.resolve_form_path(os.path.expanduser(path))
        if not os.path.exists(resolved):
            return {'fields': [], 'system_fields': SYSTEM_FIELDS, 'error': 'File not found'}
        try:
            with open(resolved, 'r', encoding='utf-8') as f:
                schema = json.load(f)
            fields = [
                {'id': fd['id'], 'label': fd.get('label', fd['id'])}
                for fd in schema.get('fields', [])
                if fd.get('type') not in ('button', 'separator', 'board') and fd.get('id')
            ]
            return {'fields': fields, 'system_fields': SYSTEM_FIELDS}
        except Exception as e:
            return {'fields': [], 'system_fields': SYSTEM_FIELDS, 'error': str(e)}

    def _handle_board_get(self, data: dict, language: str) -> dict:
        record_id = data.get('record_id', '')
        detail_form_path = board_lib.resolve_form_path(data.get('detail_form_path', ''))
        if not record_id:
            return {'record': None}
        try:
            db_path = self._board_db_path(detail_form_path)
            record = board_lib.get_record(db_path, record_id)
            return {'record': record}
        except Exception as e:
            print(f'[error] board_get: {e}', file=sys.stderr)
            return {'record': None, 'error': str(e)}

    def _handle_standalone_close(self, data: dict, language: str) -> dict:
        """Close the standalone window by terminating the subprocess"""
        import threading
        def _exit():
            import time
            time.sleep(0.1)  # allow response to be sent first
            sys.exit(0)
        threading.Thread(target=_exit, daemon=True).start()
        return {'success': True}

    def _handle_runner_poll(self, data: dict, language: str) -> dict:
        """Runner polls for schema updates. Returns schema only if version changed."""
        known_version = data.get('version', -1)
        current_version = self.state.get('runner_schema_version', 0)
        if known_version == current_version:
            return {'changed': False, 'version': current_version}
        return {
            'changed': True,
            'version': current_version,
            'schema': self.state.get('runner_schema'),
        }

    def on_close(self):
        """Called when window closes - notify caller, terminate runner subprocess"""
        self._send_to_caller({'type': 'window_closed'})
        if self._caller_conn:
            try:
                self._caller_conn.close()
            except Exception:
                pass
            self._caller_conn = None

        if self._runner_process and self._runner_process.poll() is None:
            try:
                self._runner_process.terminate()
                self._runner_process.wait(timeout=2)
            except Exception:
                try:
                    self._runner_process.kill()
                except Exception:
                    pass


register_app_class(SkillFormApp)
