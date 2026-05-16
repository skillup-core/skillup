#!/usr/bin/env python3
"""Generate .expected files for error test cases"""

import subprocess
import sys
import re
from pathlib import Path

error_test_files = [
    'test_caseq.il',
    'test_code.il',
    'test_cond_invalid.il',
    'test_corrected.il',
    'test_dot_and.il',
    'test_error_parentheses.il',
    'test_escape.il',
    'test_fixed.il',
    'test_func2.il',
    'test_if_2param.il',
    'test_if_assign.il',
    'test_if_syntax.il',
    'test_nested_if2.il',
    'test_simple_if.il',
]

test_dir = Path(__file__).resolve().parent.parent / "files"
verifier = Path(__file__).resolve().parent.parent.parent / "skillup.py"

print(f"Generating .expected files for {len(error_test_files)} test files...")
print("="*80)

for filename in error_test_files:
    filepath = test_dir / filename
    expected_path = test_dir / filename.replace('.il', '.expected')

    if not filepath.exists():
        print(f"\n[SKIP] {filename} - file not found")
        continue

    # Run verifier
    result = subprocess.run(
        [sys.executable, str(verifier), str(filepath)],
        capture_output=True,
        text=True,
        timeout=10
    )

    # Parse errors from output
    errors = []
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    for line in result.stdout.split('\n'):
        if '[error]' not in line and '[warn' not in line:
            continue

        # Strip ANSI codes
        clean_line = ansi_escape.sub('', line)

        error = {'line': None, 'func': None, 'type': None, 'var': None}

        # Parse line number
        line_match = re.search(r'line\s+(\d+)', clean_line)
        if line_match:
            error['line'] = int(line_match.group(1))

        # Parse function name
        func_match = re.search(r'in function\s+(\w+)', clean_line)
        if func_match:
            error['func'] = func_match.group(1)
        else:
            error['func'] = None

        # Parse error type and variable name
        if 'undefined function call' in clean_line.lower():
            error['type'] = 'undeclared(function)'
            # Variable/function name is typically at the end after last comma
            var_match = re.search(r',\s+(\w+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
        elif 'undeclared variable' in clean_line.lower():
            error['type'] = 'undeclared(variable)'
            var_match = re.search(r',\s+(\w+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
        elif 'declaring parameters as local variable' in clean_line.lower() or 'redeclar' in clean_line.lower():
            error['type'] = 'redeclaration'
            var_match = re.search(r',\s+(\w+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
        elif 'assignment in condition' in clean_line.lower():
            error['type'] = 'assignment'
            # Assignment errors show = at the end
            var_match = re.search(r',\s+(\S+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
            else:
                error['var'] = '='
        elif 'invalid cond clause syntax' in clean_line.lower():
            error['type'] = 'cond_syntax'
            error['var'] = 'cond'
        elif 'constant (number or string) in variable name position' in clean_line.lower():
            error['type'] = 'constant_binding'
            var_match = re.search(r',\s+(\S+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
        elif 'function definition missing opening parenthesis' in clean_line.lower():
            error['type'] = 'function_syntax'
            # Extract last value after last comma (e.g., "procedure (")
            parts = clean_line.split(',')
            if len(parts) > 1:
                last_part = parts[-1].strip()
                # Extract just the keyword (e.g., "procedure" from "procedure (")
                keyword_match = re.search(r'(\w+)', last_part)
                error['var'] = keyword_match.group(1) if keyword_match else last_part
            else:
                error['var'] = 'function'
        elif 'multiple expressions require' in clean_line.lower() and 'then' in clean_line.lower():
            error['type'] = 'if_syntax'
            error['var'] = 'if'
        elif 'parameter declaration with' in clean_line.lower() and 'without @optional' in clean_line.lower():
            error['type'] = 'parameter_syntax'
            error['var'] = 'param'
        elif 'non-identifier in variable binding position' in clean_line.lower():
            error['type'] = 'binding_syntax'
            # Extract last value after last comma (e.g., "(123...)")
            parts = clean_line.split(',')
            if len(parts) > 1:
                error['var'] = parts[-1].strip()
            else:
                error['var'] = 'binding'
        elif 'function parameter must be a symbol' in clean_line.lower():
            error['type'] = 'parameter_symbol'
            # Extract last value after last comma (e.g., "1", "string", etc.)
            var_match = re.search(r',\s+(\S+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
            else:
                error['var'] = 'parameter'
        elif 'paren' in clean_line.lower() or 'mismatch' in clean_line.lower():
            error['type'] = 'parenthesis'
            error['var'] = 'parenthesis'
        elif 'syntax error' in clean_line.lower():
            error['type'] = 'syntax'
            # Get the error token if present
            var_match = re.search(r'syntax error[^,]*,\s+(\S+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
            else:
                error['var'] = 'syntax'

        if error['line'] is not None and error['type'] is not None and error['var'] is not None:
            errors.append(error)

    if not errors:
        print(f"\n[SKIP] {filename} - no parseable errors found")
        continue

    # Write .expected file
    with open(expected_path, 'w') as f:
        f.write("# Expected errors for " + filename + "\n")
        f.write("# Format: line|func|type|var\n")
        f.write("#\n")
        for err in errors:
            func_str = err['func'] if err['func'] else 'None'
            f.write(f"{err['line']}|{func_str}|{err['type']}|{err['var']}\n")

    print(f"\n[OK] {filename}")
    print(f"     Created {expected_path.name} with {len(errors)} expected errors")
    for err in errors:
        func_str = f"in {err['func']}" if err['func'] else "global"
        print(f"       - Line {err['line']}, {func_str}: {err['type']} - {err['var']}")

print("\n" + "="*80)
print("Generation complete!")
