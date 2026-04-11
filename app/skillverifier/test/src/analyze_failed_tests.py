#!/usr/bin/env python3
"""Analyze all failed test files and generate report"""

import subprocess
import sys
from pathlib import Path

failed_files = [
    'test_caseq.il',
    'test_corrected.il',
    'test_dot_and.il',
    'test_error_parentheses.il',
    'test_escape.il',
    'test_fixed.il',
    'test_func2.il',
    'test_func3.il',
    'test_if3.il',
    'test_if_2param.il',
    'test_if_assign.il',
    'test_if_prop.il',
    'test_if_simple.il',
    'test_if_syntax.il',
    'test_missing_paren.il',
    'test_multiline_cond.il',
    'test_multiline_if.il',
    'test_nested_if.il',
    'test_nested_if2.il',
    'test_paren_fix.il',
    'test_prop_chain.il',
    'test_simple_if.il',
    'test_simple_paren.il',
    'test_unary.il',
]

test_dir = Path(__file__).resolve().parent.parent / "files"
verifier = Path(__file__).resolve().parent.parent.parent / "skillup.py"

print(f"Analyzing {len(failed_files)} failed test files...")
print("="*80)

for filename in failed_files:
    filepath = test_dir / filename
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

    # Count errors
    error_lines = [line for line in result.stdout.split('\n') if '[error]' in line.lower()]
    error_count = len(error_lines)

    print(f"\n{'='*80}")
    print(f"File: {filename}")
    print(f"Errors found: {error_count}")
    print(f"{'-'*80}")

    # Show first few lines of the file
    with open(filepath, 'r') as f:
        content = f.read()
        lines = content.split('\n')[:10]
        print("First 10 lines:")
        for i, line in enumerate(lines, 1):
            print(f"  {i:2}: {line}")

    print(f"{'-'*80}")
    print("Errors:")
    for line in error_lines:
        # Remove ANSI color codes
        import re
        clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)
        print(f"  {clean_line}")

print("\n" + "="*80)
print(f"Analysis complete. Reviewed {len(failed_files)} files.")
