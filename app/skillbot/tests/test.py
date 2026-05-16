#!/usr/bin/env python3
"""
Skillbot Debugger Transform Test Runner

Usage:
    python3 test.py testcase.txt
"""

import sys
import os
import re

# Allow importing debugger from parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from app.skillbot.debugger import transform_for_debug


def parse_testcases(path):
    """Parse testcase.txt and return list of (name, description, input, output)."""
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    cases = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')

        # Skip comment-only lines and blank lines between cases
        if line.startswith(';') or line.strip() == '':
            i += 1
            continue

        # Match [testcaseNN] description
        m = re.match(r'^\[(\w+)\]\s*(.*)', line)
        if not m:
            i += 1
            continue

        name = m.group(1)
        description = m.group(2).strip()
        i += 1

        # Skip comment lines after header
        while i < len(lines) and lines[i].startswith(';'):
            i += 1

        # Read INPUT:
        if i >= len(lines) or lines[i].strip() != 'INPUT:':
            print(f'[WARN] {name}: expected INPUT: after header, got: {lines[i].strip()!r}')
            i += 1
            continue
        i += 1

        input_lines = []
        while i < len(lines):
            l = lines[i].rstrip('\n')
            if l.strip() == 'OUTPUT:':
                break
            input_lines.append(l)
            i += 1

        if i >= len(lines):
            print(f'[WARN] {name}: no OUTPUT: found')
            continue
        i += 1  # skip OUTPUT:

        output_lines = []
        while i < len(lines):
            l = lines[i].rstrip('\n')
            # Next test case or EOF
            if re.match(r'^\[(\w+)\]', l):
                break
            # Blank line after output block signals end (allow trailing blank)
            output_lines.append(l)
            i += 1

        # Strip trailing blank lines from output
        while output_lines and output_lines[-1].strip() == '':
            output_lines.pop()
        while input_lines and input_lines[-1].strip() == '':
            input_lines.pop()

        cases.append((name, description, '\n'.join(input_lines), '\n'.join(output_lines)))

    return cases


def run_tests(path):
    cases = parse_testcases(path)
    if not cases:
        print('No test cases found.')
        return 1

    passed = 0
    failed = 0

    for name, description, input_code, expected_output in cases:
        result = transform_for_debug(input_code)
        actual_output = result['code']

        if actual_output == expected_output:
            print(f'  PASS  [{name}] {description}')
            passed += 1
        else:
            print(f'  FAIL  [{name}] {description}')
            # Show diff
            exp_lines = expected_output.splitlines()
            act_lines = actual_output.splitlines()
            max_lines = max(len(exp_lines), len(act_lines))
            diff_shown = False
            for i in range(max_lines):
                e = exp_lines[i] if i < len(exp_lines) else '<missing>'
                a = act_lines[i] if i < len(act_lines) else '<missing>'
                if e != a:
                    if not diff_shown:
                        print(f'        --- expected')
                        print(f'        +++ actual')
                        diff_shown = True
                    print(f'        line {i+1}:')
                    print(f'          - {e!r}')
                    print(f'          + {a!r}')
            failed += 1

    total = passed + failed
    print()
    print(f'Result: {passed}/{total} passed', end='')
    if failed == 0:
        print('  ALL PASSED')
    else:
        print(f'  {failed} FAILED')

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f'Usage: python3 {sys.argv[0]} testcase.txt')
        sys.exit(1)

    sys.exit(run_tests(sys.argv[1]))
