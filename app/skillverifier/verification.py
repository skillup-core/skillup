"""
Skillup Skill Verifier - Verification Logic

This module handles the verification execution logic.
"""

import os
import sys


def format_log_message(msg_type, line=None, func_name=None, error_text=None,
                       error_code=None, code_id=None):
    """Format log message with ANSI color codes matching terminal output"""
    # ANSI color codes
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'

    if msg_type == "info":
        prefix_color = GREEN
    elif msg_type == "warn":
        prefix_color = YELLOW
    else:
        prefix_color = RED

    output = f"{prefix_color}[{msg_type:5s}]{RESET}"

    if code_id is not None:
        code_letter = code_id[0] if code_id else ""
        code_number = code_id[1:] if len(code_id) > 1 else ""
        formatted_code = f"{code_letter}{code_number.zfill(2)}"

        if code_letter == 'W':
            code_color = YELLOW
        else:
            code_color = RED

        output += f"{code_color}[{formatted_code}]{RESET} "

    if line is not None:
        output += f"line {YELLOW}{line}{RESET}, "

    if func_name is not None:
        output += f"in function {YELLOW}{func_name}{RESET}, "

    if error_text is not None:
        output += f"{error_text}"
        if error_code is not None:
            output += f", {RED}{error_code}{RESET}"

    return output


def run_verification(verification_state, paths: list, define_file: str, data_db: str, language: str = 'en'):
    """
    Run verification in background thread.

    Args:
        verification_state: VerificationState instance to update
        paths: List of file/directory paths to verify
        define_file: Path to define file (optional)
        data_db: Path to database file (optional)
        language: UI language ('en' or 'ko')
    """
    # Import verification functions from skillverifier core
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, script_dir)

    from app.skillverifier.core import (
        parse_define_file,
        DefinitionDatabase
    )
    from app.skillverifier.skillverifier import (
        collect_files,
        verify_file
    )

    verification_state.reset()

    def add_log(msg_type, line=None, func_name=None, error_text=None,
                error_code=None, code_id=None):
        """Add formatted log entry"""
        msg = format_log_message(msg_type, line, func_name, error_text, error_code, code_id)
        verification_state.add_log(msg_type, msg)

    try:
        # Expand ~ in file paths
        if define_file:
            define_file = os.path.expanduser(define_file)
            if not os.path.exists(define_file):
                if language == 'ko':
                    error_msg = f"Define 파일이 존재하지 않습니다: {define_file}"
                else:
                    error_msg = f"Define file does not exist: {define_file}"
                add_log('error', error_text=error_msg)
                verification_state.set_error(error_msg)
                return

        if data_db:
            data_db = os.path.expanduser(data_db)
            if not os.path.exists(data_db):
                if language == 'ko':
                    error_msg = f"데이터 데이터베이스가 존재하지 않습니다: {data_db}"
                else:
                    error_msg = f"Data database does not exist: {data_db}"
                add_log('error', error_text=error_msg)
                verification_state.set_error(error_msg)
                return

        # Expand ~ in paths
        expanded_paths = [os.path.expanduser(p) for p in paths]

        # Collect files
        files = collect_files(expanded_paths)

        if not files:
            if language == 'ko':
                error_msg = "검증할 .il 파일을 찾을 수 없습니다"
            else:
                error_msg = "No .il files found to verify"
            add_log('error', error_text=error_msg)
            verification_state.set_error(error_msg)
            return

        # Set total count
        verification_state.set('total', len(files))

        if language == 'ko':
            add_log('info', error_text=f'{len(files)}개의 파일을 검증합니다')
        else:
            add_log('info', error_text=f'Found {len(files)} files to verify')

        # Parse define file
        defined_variables = set()
        defined_functions = set()

        if define_file:
            defined_variables, defined_functions = parse_define_file(define_file)
            if defined_variables is not None and defined_functions is not None:
                total_defs = len(defined_variables) + len(defined_functions)
                add_log('info', error_text=f'loaded {total_defs} definitions from {define_file}')

        # Load database if --data option provided
        if data_db:
            add_log('info', error_text=f'using database: {data_db}')

            db = DefinitionDatabase(data_db)
            try:
                db.connect()
                db.create_schema()

                cursor = db.conn.cursor()

                # Load all functions
                cursor.execute('''
                    SELECT DISTINCT d.name
                    FROM definitions d
                    JOIN definition_types dt ON d.type_id = dt.type_id
                    WHERE dt.type_name = 'function'
                ''')
                for row in cursor.fetchall():
                    defined_functions.add(row[0])

                # Load all variables
                cursor.execute('''
                    SELECT DISTINCT d.name
                    FROM definitions d
                    JOIN definition_types dt ON d.type_id = dt.type_id
                    WHERE dt.type_name = 'variable'
                ''')
                for row in cursor.fetchall():
                    defined_variables.add(row[0])

                db.disconnect()

                total_db_defs = len(defined_functions) + len(defined_variables)
                add_log('info', error_text=f'loaded {total_db_defs} definitions from database')

            except Exception as e:
                add_log('error', error_text=f'failed to load database: {str(e)}')
                db.disconnect()

        # Verify files
        results = []
        total_errors = 0

        for i, filepath in enumerate(files):
            # Verify the file (silent=True to avoid duplicate logging)
            error_count, errors, source_code = verify_file(filepath, defined_variables, defined_functions, silent=True)
            total_errors += error_count

            # Collect all logs for this file
            file_logs = []

            # Add file verification start log
            file_logs.append({
                'type': 'info',
                'message': format_log_message('info', error_text=f'verify {filepath}')
            })

            # Add all error/warning logs for this file
            for err in errors:
                err_type = err.get('type', 'error')
                msg = format_log_message(
                    err_type,
                    line=err.get('line'),
                    func_name=err.get('function'),
                    error_text=err.get('message'),
                    error_code=err.get('code'),
                    code_id=err.get('error_code')
                )
                file_logs.append({'type': err_type, 'message': msg})

            # Prepare result
            result = {
                'filepath': filepath,
                'errors': errors,
                'source': source_code
            }
            results.append(result)

            # BATCH UPDATE: progress + logs + result in single notification (3 → 1 per file)
            verification_state.update_file_batch(filepath, i + 1, file_logs, result)

        # Complete
        if language == 'ko':
            add_log('info', error_text=f'검증 완료: {len(files)}개 파일, {total_errors}개 에러')
        else:
            add_log('info', error_text=f'Verification complete: {len(files)} files, {total_errors} errors')

        verification_state.complete(results)

    except Exception as e:
        error_msg = f'Verification error: {str(e)}'
        add_log('error', error_text=error_msg)
        verification_state.set_error(error_msg)
