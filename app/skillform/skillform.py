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
from typing import List, Optional, TYPE_CHECKING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.appmgr import AppContext, register_app_class
from lib.baseapp import BaseApp, BaseAppState

if TYPE_CHECKING:
    from lib.webui import WebUIEngine


class SkillFormApp(BaseApp):
    """Skill Form Application - Form Designer and Runner"""

    def __init__(self, engine: Optional['WebUIEngine'], context: AppContext):
        super().__init__(engine, context)

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
        })

        # Check if --skillform-run=<path> was passed via environment
        auto_run_path = None
        raw_args = os.environ.get('_SKILLUP_APP_ARGS')
        if raw_args:
            try:
                extra_args = json.loads(raw_args)
                for arg in extra_args:
                    if arg.startswith('--skillform-run='):
                        auto_run_path = arg[len('--skillform-run='):]
                        break
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

        self.state.update({
            'runner_schema': auto_run_schema,
            'runner_schema_path': auto_run_path if auto_run_schema else config.get('runner.last_schema', ''),
            'runner_result': None,
            'runner_waiting': auto_run_schema is not None,
            'designer_schema': None,
            'designer_file': config.get('designer.last_file', ''),
            'auto_run': auto_run_schema is not None,
        }, notify=False)

        self.register_handlers({
            # Runner handlers
            'runner_load_schema': self._handle_runner_load_schema,
            'runner_submit': self._handle_runner_submit,
            'runner_cancel': self._handle_runner_cancel,
            'runner_get_state': self._handle_runner_get_state,
            # Designer handlers
            'designer_load': self._handle_designer_load,
            'designer_save': self._handle_designer_save,
            'designer_get_state': self._handle_designer_get_state,
            'designer_run': self._handle_designer_run,
            'runner_poll': self._handle_runner_poll,
            # Standalone mode
            'standalone_close': self._handle_standalone_close,
        })

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

        # Save last used path
        from lib.config import save_config
        save_config(self.context.config_path, {'runner.last_schema': path})

        return {'success': True, 'schema': schema}

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


register_app_class(SkillFormApp)
