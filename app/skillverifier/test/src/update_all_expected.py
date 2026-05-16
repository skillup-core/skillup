#!/usr/bin/env python3
"""Update/create .expected files for all test files that have errors"""

import subprocess
import sys
import re
from pathlib import Path

test_dir = Path(__file__).resolve().parent.parent / "files"
verifier = Path(__file__).resolve().parent.parent.parent / "skillup.py"

# Get all .il files
all_il_files = sorted(test_dir.glob("*.il"))

print(f"Checking {len(all_il_files)} test files...")
print("="*80)

files_with_errors = []
files_without_errors = []

for filepath in all_il_files:
    filename = filepath.name

    # Run verifier
    result = subprocess.run(
        [sys.executable, str(verifier), str(filepath)],
        capture_output=True,
        text=True,
        timeout=10
    )

    # Count errors
    error_lines = [line for line in result.stdout.split('\n') if '[error]' in line.lower()]

    if error_lines:
        files_with_errors.append(filename)
    else:
        files_without_errors.append(filename)

print(f"\nFiles WITH errors (need .expected): {len(files_with_errors)}")
for f in files_with_errors:
    print(f"  - {f}")

print(f"\nFiles WITHOUT errors (valid code): {len(files_without_errors)}")
for f in files_without_errors:
    expected_file = test_dir / f.replace('.il', '.expected')
    if expected_file.exists():
        print(f"  - {f} [HAS .expected - should remove it!]")
    else:
        print(f"  - {f}")

print("\n" + "="*80)
print("Now generating .expected files for files with errors...")
print("="*80)

for filename in files_with_errors:
    filepath = test_dir / filename
    expected_path = test_dir / filename.replace('.il', '.expected')

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
        if '[error]' not in line:
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

        # Parse error type and variable name - FIXED to handle "undefined function call"
        if 'undefined function call' in clean_line.lower():
            error['type'] = 'undeclared(function)'
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
            var_match = re.search(r',\s+(\S+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
            else:
                error['var'] = '='
        elif 'paren' in clean_line.lower() or 'mismatch' in clean_line.lower():
            error['type'] = 'parenthesis'
            error['var'] = 'parenthesis'
        elif 'syntax error' in clean_line.lower():
            error['type'] = 'syntax'
            var_match = re.search(r'syntax error[^,]*,\s+(\S+)\s*$', clean_line)
            if var_match:
                error['var'] = var_match.group(1)
            else:
                error['var'] = 'syntax'

        if error['line'] is not None and error['type'] is not None and error['var'] is not None:
            errors.append(error)

    # Write .expected file
    if errors:
        with open(expected_path, 'w') as f:
            f.write("# Expected errors for " + filename + "\n")
            f.write("# Format: line|func|type|var\n")
            f.write("#\n")
            for err in errors:
                func_str = err['func'] if err['func'] else 'None'
                f.write(f"{err['line']}|{func_str}|{err['type']}|{err['var']}\n")

        print(f"\n[OK] {filename}")
        print(f"     Created/Updated {expected_path.name} with {len(errors)} expected errors")
    else:
        print(f"\n[SKIP] {filename} - no parseable errors")

print("\n" + "="*80)
print("Update complete!")
