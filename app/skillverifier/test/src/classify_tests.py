#!/usr/bin/env python3
"""
Classify test files into categories:
1. Valid files (no errors expected)
2. Files with intentional errors (need .expected)
3. Files with syntax errors in the test file itself (need fixing)
"""

import subprocess
import sys
from pathlib import Path

# Files that passed (already have .expected or truly valid)
passed_files = [
    'test_array.il',
    'test_arrow.il',
    'test_debug.il',
    'test_error_mixed.il',
    'test_error_redeclaration.il',
    'test_error_undeclared.il',
    'test_func3.il',
    'test_hotspot_simple.il',
    'test_if3.il',
    'test_if_in_proc.il',
    'test_if_prop.il',
    'test_if_simple.il',
    'test_keyword_args.il',
    'test_missing_paren.il',
    'test_multiline_cond.il',
    'test_nested.il',
    'test_nested_if.il',
    'test_prog.il',
    'test_question.il',
    'test_quote_backtick.il',
    'test_simple.il',
    'test_simple_multiline.il',
    'test_simple_paren.il',
    'test_two_funcs.il',
    'test_valid_advanced.il',
    'test_valid_basic.il',
    'test_valid_config.il',
    'test_verify.il',
]

failed_files = [
    'test_caseq.il',
    'test_corrected.il',
    'test_dot_and.il',
    'test_error_parentheses.il',
    'test_escape.il',
    'test_fixed.il',
    'test_func2.il',
    'test_if_2param.il',
    'test_if_assign.il',
    'test_if_syntax.il',
    'test_multiline_if.il',
    'test_nested_if2.il',
    'test_paren_fix.il',
    'test_prop_chain.il',
    'test_simple_if.il',
    'test_unary.il',
]

# Analyze each failed file
print("Classifying failed test files...")
print("="*80)

# Category 1: Files with bad let syntax that need fixing
bad_let_syntax = []
test_dir = Path(__file__).resolve().parent.parent / "files"
for filename in ['test_multiline_if.il', 'test_prop_chain.il', 'test_unary.il']:
    filepath = test_dir / filename
    if filepath.exists():
        with open(filepath, 'r') as f:
            content = f.read()
            if 'let((' in content and not 'let( ((' in content:
                bad_let_syntax.append(filename)

print("\nCategory 1: Files with bad let syntax (need fixing):")
print("  These use 'let((x 1) ...)' instead of 'let( ((x 1)) ...)'")
for f in bad_let_syntax:
    print(f"    - {f}")

# Category 2: Files that test error detection (need .expected files)
error_test_files = []
for filename in failed_files:
    if filename in bad_let_syntax:
        continue
    # Check if filename suggests it's testing errors or if it has obvious test errors
    if 'error' in filename or filename in ['test_caseq.il', 'test_escape.il',
                                             'test_if_assign.il', 'test_nested_if2.il',
                                             'test_simple_if.il', 'test_dot_and.il',
                                             'test_fixed.il', 'test_corrected.il',
                                             'test_func2.il', 'test_if_2param.il',
                                             'test_if_syntax.il']:
        error_test_files.append(filename)

print("\nCategory 2: Files testing error detection (need .expected files):")
for f in error_test_files:
    filepath = test_dir / f
    if filepath.exists():
        with open(filepath, 'r') as file:
            first_line = file.readline().strip()
            print(f"    - {f}")
            if first_line.startswith(';') or first_line.startswith('#'):
                print(f"        Comment: {first_line}")

print("\nCategory 3: Files that need investigation:")
need_investigation = [f for f in failed_files if f not in bad_let_syntax and f not in error_test_files]
for f in need_investigation:
    print(f"    - {f}")

print("\n" + "="*80)
print("Summary:")
print(f"  - Bad let syntax (need fixing): {len(bad_let_syntax)}")
print(f"  - Error test files (need .expected): {len(error_test_files)}")
print(f"  - Need investigation: {len(need_investigation)}")
