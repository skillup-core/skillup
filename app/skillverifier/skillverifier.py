"""
Skill Verifier App

SKILL Code Verifier for Cadence Virtuoso
Parses SKILL code into AST (Abstract Syntax Tree)

Usage:
    skillup.py --app:skillverifier [OPTIONS] <file1.il> <file2.il> <dir1> <dir2>...

    Arguments:
        <file.il>    Individual .il files to verify
        <dir>        Directories to scan recursively for all .il files

Options:
    --define=<path>    Path to define file containing predefined functions/variables
                       Define file format:
                       - [VARIABLE] section for variable names
                       - [FUNCTION] section for function names
                       - Comments: # (line comment), /* */ (block comment)

    --build=<db>       Build mode: Parse files and store definitions in SQLite database
                       - Supports incremental builds (SHA256 hash comparison)
                       - Skips unchanged files automatically
                       - NFS-safe with WAL mode and locking

    --data=<db>        Query mode: Use database to skip undefined function/variable errors
                       - Functions/variables defined in database won't trigger errors
                       - Useful for cross-file references

Environment Variables:
    SKILLVERIFIER_DEFINE        Path to define file (overridden by --define option)
                                Example: export SKILLVERIFIER_DEFINE="~/define.txt"
    SKILLVERIFIER_VSCODE        Path to VSCode executable (for opening files from web UI)
                                Example: export SKILLVERIFIER_VSCODE="/usr/bin/code"

Examples:
    # Verify single file
    python3 skillup.py --app:skillverifier test.il

    # Verify multiple files with define file
    python3 skillup.py --app:skillverifier --define=defs.txt file1.il file2.il

    # Verify all .il files in directory
    python3 skillup.py --app:skillverifier /path/to/skill/code

    # Build database from files
    python3 skillup.py --app:skillverifier --build=myproject.db file1.il file2.il

    # Verify using database for cross-file references
    python3 skillup.py --app:skillverifier --data=myproject.db newfile.il
"""

import os
import sys
from typing import List, Set, Optional, Tuple, TYPE_CHECKING

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import base app and context
from lib.appmgr import AppContext, register_app_class
from lib.baseapp import BaseApp, BaseAppState

# Import core verification library from local core module
from .core import (
    parse_define_file,
    print_message,
    DefinitionDatabase,
    Tokenizer,
    Parser,
    FunctionDef,
    Assignment,
    collect_files,
    verify_file
)

# Type hints only (not imported at runtime)
if TYPE_CHECKING:
    from lib.webui import WebUIEngine


class VerificationState(BaseAppState):
    """Custom state with domain-specific methods for verification"""

    def set(self, key: str, value, notify: bool = False):
        """Override to disable default state_update notifications"""
        # Only update data without triggering parent's state_update event
        # notify parameter is ignored - we use onVerifierStateUpdate instead
        with self.condition:
            self._data[key] = value
            self.condition.notify_all()

    def update(self, updates: dict, notify: bool = False):
        """Override to disable default state_update notifications"""
        # Only update data without triggering parent's state_update event
        # notify parameter is ignored - we use onVerifierStateUpdate instead
        with self.condition:
            self._data.update(updates)
            self.condition.notify_all()

    def reset(self):
        """Reset state for new verification (preserves form inputs)"""
        with self.condition:
            # Preserve form input values
            files_input = self._data.get('files_input', '')
            define_file_input = self._data.get('define_file_input', '')
            data_db_input = self._data.get('data_db_input', '')

            # Reset verification state
            self._data = {
                'running': True,
                'progress': 0,
                'total': 0,
                'current_file': '',
                'logs': [],
                'results': [],
                'error': None,
                # Preserve form inputs
                'files_input': files_input,
                'define_file_input': define_file_input,
                'data_db_input': data_db_input
            }
            self.condition.notify_all()

        # Notify UI of reset
        self.app.notify_state_change('onVerifierStateUpdate', self.get_status())

    def add_log(self, log_type: str, message: str):
        """Add log entry with automatic notification"""
        with self.condition:
            logs = self._data.get('logs', [])
            logs.append({'type': log_type, 'message': message})
            self._data['logs'] = logs[-1000:]  # Keep last 1000
            self.condition.notify_all()

        # Notify UI with full status
        self.app.notify_state_change('onVerifierStateUpdate', self.get_status())

    def add_logs_batch(self, logs: list):
        """Add multiple logs at once (single notification)"""
        with self.condition:
            current_logs = self._data.get('logs', [])
            current_logs.extend(logs)
            self._data['logs'] = current_logs[-1000:]
            self.condition.notify_all()

        self.app.notify_state_change('onVerifierStateUpdate', self.get_status())

    def update_progress(self, current_file: str, progress: int):
        """Update progress and notify"""
        with self.condition:
            self._data['current_file'] = current_file
            self._data['progress'] = progress
            self.condition.notify_all()

        self.app.notify_state_change('onVerifierStateUpdate', self.get_status())

    def add_result(self, result: dict):
        """Add verification result"""
        with self.condition:
            results = self._data.get('results', [])
            results.append(result)
            self._data['results'] = results
            self.condition.notify_all()

        self.app.notify_state_change('onVerifierStateUpdate', self.get_status())

    def update_file_batch(self, current_file: str, progress: int, logs: list, result: dict, throttle_interval: int = 10):
        """Batch update: progress + logs + result with throttled notifications

        Args:
            current_file: Current file being processed
            progress: Current progress count
            logs: Logs for this file
            result: Result for this file
            throttle_interval: Send full update every N files (default: 10)
        """
        with self.condition:
            # Update progress
            self._data['current_file'] = current_file
            self._data['progress'] = progress

            # Add logs
            current_logs = self._data.get('logs', [])
            current_logs.extend(logs)
            self._data['logs'] = current_logs[-1000:]

            # Add result
            results = self._data.get('results', [])
            results.append(result)
            self._data['results'] = results

            self.condition.notify_all()

        # THROTTLING: Only send full update every Nth file to reduce overhead
        total = self._data.get('total', 0)
        if progress == 1 or progress == total or progress % throttle_interval == 0:
            self.app.notify_state_change('onVerifierStateUpdate', self.get_status())

    def set_error(self, error: str):
        """Set error state"""
        with self.condition:
            self._data['error'] = error
            self._data['running'] = False
            self.condition.notify_all()

        self.app.notify_state_change('onVerifierStateUpdate', self.get_status())

    def complete(self, results: list):
        """Mark verification as complete"""
        with self.condition:
            self._data['results'] = results
            self._data['running'] = False
            self.condition.notify_all()

        self.app.notify_state_change('onVerifierStateUpdate', self.get_status())

    def get_status(self) -> dict:
        """Get complete status snapshot"""
        with self.lock:
            return {
                'running': self._data.get('running', False),
                'progress': self._data.get('progress', 0),
                'total': self._data.get('total', 0),
                'current_file': self._data.get('current_file', ''),
                'logs': list(self._data.get('logs', [])),
                'results': list(self._data.get('results', [])),
                'error': self._data.get('error'),
                # Include form inputs from config
                'files_input': self._data.get('files_input', ''),
                'define_file_input': self._data.get('define_file_input', ''),
                'data_db_input': self._data.get('data_db_input', ''),
                # Aliases for frontend compatibility
                'processed_files': self._data.get('progress', 0),
                'total_files': self._data.get('total', 0)
            }

    def save_inputs(self, files_input: str, define_file_input: str, data_db_input: str):
        """Save form inputs (also persist to config)"""
        with self.lock:
            self._data['files_input'] = files_input
            self._data['define_file_input'] = define_file_input
            self._data['data_db_input'] = data_db_input

        # Save to config file
        from lib.config import save_config
        save_config(self.app.context.config_path, {
            'verify.files_input': files_input,
            'verify.define_file_input': define_file_input,
            'verify.data_db_input': data_db_input
        })

    def get_new_logs(self, last_count: int) -> tuple:
        """Get new logs since last_count"""
        with self.lock:
            logs = self._data.get('logs', [])
            new_logs = logs[last_count:]
            return (new_logs, len(logs))


class SkillVerifierApp(BaseApp):
    """Skill Verifier Application"""

    def __init__(self, engine: Optional['WebUIEngine'], context: AppContext):
        """
        Initialize Skill Verifier app.

        Args:
            engine: WebUI engine (None in CLI mode)
            context: App execution context
        """
        super().__init__(engine, context)

    def create_state(self) -> VerificationState:
        """Override to provide custom state class"""
        return VerificationState(self)

    def get_menu_items(self) -> List[dict]:
        """Return left menu items for desktop mode"""
        return [
            {'id': 'dashboard', 'name': 'Dashboard'},
            {'id': 'verify', 'name': 'File Verify'},
            {'id': 'results', 'name': 'Results'},
        ]

    def on_menu_click(self, menu_id: str):
        """Handle menu click event"""
        pass

    def on_close(self):
        """Cleanup when app is closed"""
        # Reset state to clear all previous results and logs
        if self._state is not None:
            with self._state.condition:
                self._state._data = {
                    'running': False,
                    'progress': 0,
                    'total': 0,
                    'current_file': '',
                    'logs': [],
                    'results': [],
                    'error': None,
                    # Preserve form inputs
                    'files_input': self._state._data.get('files_input', ''),
                    'define_file_input': self._state._data.get('define_file_input', ''),
                    'data_db_input': self._state._data.get('data_db_input', '')
                }
                self._state.condition.notify_all()

    def on_run_cli(self, args: List[str]) -> int:
        """
        Run in CLI mode.

        Args:
            args: Command line arguments

        Returns:
            Exit code (0 = success, 1 = error)
        """

        # Parse arguments
        define_file = None
        build_db = None
        data_db = None
        paths = []

        for arg in args:
            if arg.startswith('--define='):
                define_file = arg[9:]
            elif arg.startswith('--build='):
                build_db = arg[8:]
            elif arg.startswith('--data='):
                data_db = arg[7:]
            elif not arg.startswith('--'):
                paths.append(arg)

        # Check environment variable if --define not provided
        if not define_file:
            define_file = os.environ.get('SKILLUP_DEFINE')

        # Expand ~ in file paths
        if define_file:
            define_file = os.path.expanduser(define_file)
        if build_db:
            build_db = os.path.expanduser(build_db)
        if data_db:
            data_db = os.path.expanduser(data_db)

        # Collect all files
        files = collect_files(paths)

        if not files:
            print_message("error", error_text="No .il files found")
            return 1

        # BUILD MODE
        if build_db:
            print_message("info", error_text=f"build mode: storing definitions in {build_db}")
            db = DefinitionDatabase(build_db)

            try:
                db.connect()
                db.create_schema()

                built_count = 0
                skipped_count = 0
                total_funcs = 0
                total_vars = 0

                for filepath in files:
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()

                        tokenizer = Tokenizer(content)
                        tokens = tokenizer.tokenize()
                        parser = Parser(tokens)
                        ast = parser.parse()

                        functions = {}
                        variables = {}

                        for node in ast:
                            if isinstance(node, FunctionDef):
                                functions[node.name] = node.line
                            elif isinstance(node, Assignment) and hasattr(node, 'var') and isinstance(node.var, str):
                                variables[node.var] = node.line

                        result = db.add_definitions(filepath, functions, variables)

                        if result['built']:
                            built_count += 1
                            total_funcs += result['added_functions']
                            total_vars += result['added_variables']
                            status = "new" if result['reason'] == 'new' else "modified"
                            print_message("info", error_text=f"{filepath}: {status} ({result['added_functions']} functions, {result['added_variables']} variables)")
                        else:
                            skipped_count += 1

                    except Exception as e:
                        print_message("error", error_text=f"{filepath}: failed to parse: {e}")
                        continue

                print_message("info", error_text=f"build complete: {built_count} files built, {skipped_count} files skipped (unchanged)")
                print_message("info", error_text=f"total: {total_funcs} functions, {total_vars} variables")

                stats = db.get_database_stats()
                size_mb = stats['total_size_bytes'] / (1024 * 1024)
                print_message("info", error_text=f"database size: {size_mb:.2f} MB, fragmentation: {stats['fragmentation_percent']:.1f}%")

            finally:
                db.close()

            return 0

        # NORMAL VERIFY MODE
        defined_variables: Set[str] = set()
        defined_functions: Set[str] = set()

        if define_file:
            defined_variables, defined_functions = parse_define_file(define_file)
            if defined_variables is None or defined_functions is None:
                return 1
            if defined_variables or defined_functions:
                total_defs = len(defined_variables) + len(defined_functions)
                print_message("info", error_text=f"loaded {total_defs} definitions ({len(defined_variables)} variables, {len(defined_functions)} functions) from {define_file}")

        # Load database if --data option provided
        if data_db:
            print_message("info", error_text=f"using database: {data_db}")
            db = DefinitionDatabase(data_db)
            try:
                db.connect()
                db.create_schema()

                cursor = db.conn.cursor()

                cursor.execute('''
                    SELECT DISTINCT d.name
                    FROM definitions d
                    JOIN definition_types dt ON d.type_id = dt.type_id
                    WHERE dt.type_name = 'function'
                ''')
                for row in cursor.fetchall():
                    defined_functions.add(row[0])

                cursor.execute('''
                    SELECT DISTINCT d.name
                    FROM definitions d
                    JOIN definition_types dt ON d.type_id = dt.type_id
                    WHERE dt.type_name = 'variable'
                ''')
                for row in cursor.fetchall():
                    defined_variables.add(row[0])

                total_db_defs = len(defined_functions) + len(defined_variables)
                print_message("info", error_text=f"loaded {total_db_defs} definitions from database")

            except Exception as e:
                print_message("error", error_text=f"failed to load database: {str(e)}")

            finally:
                db.close()

        # Verify files
        total_errors = 0

        for filepath in files:
            error_count, errors, source_code = verify_file(filepath, defined_variables, defined_functions)
            total_errors += error_count

        return 0 if total_errors == 0 else 1

    def on_run_desktop_initialize(self) -> int:
        """
        Desktop mode initialization hook.

        Called in subprocess before JSON-RPC loop starts.
        Override to perform desktop-specific initialization.

        Returns:
            Exit code (0 = success)
        """
        # Import verification handlers
        from .verification import run_verification
        self.run_verification = run_verification

        # Load saved config and initialize state
        config = self.load_config({
            'verify.files_input': '',
            'verify.define_file_input': '',
            'verify.data_db_input': ''
        })

        # Initialize state with config values
        self.state.update({
            'files_input': config.get('verify.files_input', ''),
            'define_file_input': config.get('verify.define_file_input', ''),
            'data_db_input': config.get('verify.data_db_input', ''),
            'running': False,
            'progress': 0,
            'total': 0,
            'logs': [],
            'results': []
        }, notify=False)

        # Register handlers
        self.register_handlers({
            'verify': self._handle_verify,
            'verify_status': self._handle_verify_status,
            'verify_stream': self._handle_verify_stream,
            'save_verify_inputs': self._handle_save_verify_inputs,
            'open_vscode': self._handle_open_vscode
        })

        return 0

    def _handle_verify(self, data: dict, language: str) -> dict:
        """Start verification"""
        import os
        import threading
        from lib.msgbox import show as msgbox_show

        paths = data.get('paths', [])
        define_file = data.get('define_file', '')
        data_db = data.get('data_db', '')

        if not paths:
            return {'success': False, 'error': 'No paths provided'}

        # Validate file paths
        invalid_paths = []
        for path in paths:
            if not os.path.exists(path):
                invalid_paths.append(path)

        if invalid_paths:
            # Show error message box (language auto-detected from desktop config)
            if len(invalid_paths) == 1:
                msgbox_show(
                    {"en": "File Not Found", "ko": "파일을 찾을 수 없음"},
                    {"en": f"The file does not exist:\n{invalid_paths[0]}",
                     "ko": f"다음 파일이 존재하지 않습니다:\n{invalid_paths[0]}"}
                )
            else:
                file_list = '\n'.join(invalid_paths)
                msgbox_show(
                    {"en": "Files Not Found", "ko": "파일을 찾을 수 없음"},
                    {"en": f"The following files do not exist:\n{file_list}",
                     "ko": f"다음 파일들이 존재하지 않습니다:\n{file_list}"}
                )
            return {'success': False, 'error': 'Invalid file paths'}

        # Save inputs to config before starting verification
        files_input = ', '.join(paths) if isinstance(paths, list) else str(paths)
        self.state.save_inputs(files_input, define_file, data_db)

        # Start verification in background thread
        verify_thread = threading.Thread(
            target=self.run_verification,
            args=(self.state, paths, define_file, data_db, language),
            daemon=True
        )
        verify_thread.start()

        return {'success': True, 'message': 'Verification started'}

    def _handle_verify_status(self, data: dict, language: str) -> dict:
        """Get current verification status"""
        status = self.state.get_status()
        return status

    def _handle_verify_stream(self, data: dict, language: str) -> dict:
        """SSE stream for verification status updates (event-driven)"""
        # Get last log count from client
        last_log_count = data.get('last_log_count', 0)
        wait = data.get('wait', False)

        # If wait=True, block until state changes
        if wait:
            self.state.wait_for_change(timeout=30.0)

        # Return current status with incremental updates
        new_logs, total_log_count = self.state.get_new_logs(last_log_count)
        status = self.state.get_status()

        # Debug log
        if status['results']:
            from lib.log import log
            log("info", message=f"Sending results count: {len(status['results'])}, running: {status['running']}", tag="sse")

        return {
            'running': status['running'],
            'progress': status['progress'],
            'total': status['total'],
            'current_file': status['current_file'],
            'new_logs': new_logs,
            'total_log_count': total_log_count,
            'results': status['results'],  # Always include results
            'error': status['error']
        }

    def _handle_save_verify_inputs(self, data: dict, language: str) -> dict:
        """Save verification form inputs"""
        self.state.save_inputs(
            data.get('files_input', ''),
            data.get('define_file_input', ''),
            data.get('data_db_input', '')
        )
        return {'success': True}

    def _handle_open_vscode(self, data: dict, language: str) -> dict:
        """Open file in VSCode"""
        import subprocess

        filepath = data.get('filepath', '')
        line = data.get('line', 1)

        if not filepath:
            return {'success': False, 'error': 'No filepath provided'}

        try:
            # Use code command with goto line option
            cmd = ['code', '--goto', f'{filepath}:{line}']
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {'success': True}
        except FileNotFoundError:
            return {'success': False, 'error': 'VSCode (code) command not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Register this app class
register_app_class(SkillVerifierApp)
