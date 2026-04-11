#!/usr/bin/env python3
"""
Unit tests for skillup.py

This test suite validates the SKILL code analyzer by testing all .il files
in the test/files/ directory. Each file becomes an individual test case.
"""

import unittest
import subprocess
import sys
import os
import glob
import re
from pathlib import Path


class SkillupTestCase(unittest.TestCase):
    """Base class for skillup tests"""

    @staticmethod
    def run_verifier(test_file):
        """Run skillup.py on a test file and return the result."""
        verifier_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "skillup.py"

        # Special handling for test_define2.il - set environment variable
        env = os.environ.copy()
        if 'test_define2.il' in test_file:
            define_file = Path(test_file).parent / "test_define.txt"
            env['SKILLUP_DEFINE'] = str(define_file)
        else:
            # Clear the environment variable for other tests
            env.pop('SKILLUP_DEFINE', None)

        result = subprocess.run(
            [sys.executable, str(verifier_path), '--app:skillverifier', test_file],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        return result.returncode, result.stdout, result.stderr

    @staticmethod
    def load_expected_errors(test_file):
        """Load expected errors from .expected file."""
        expected_file = test_file.replace('.il', '.expected')
        if not os.path.exists(expected_file):
            return None

        expected = []
        with open(expected_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split('|')
                if len(parts) != 4:
                    continue

                error = {
                    'line': int(parts[0]),
                    'func': None if parts[1] == 'None' else parts[1],
                    'type': parts[2],
                    'var': parts[3]
                }
                expected.append(error)

        return expected

    @staticmethod
    def parse_errors(output):
        """Parse detailed error information from verifier output."""
        errors = []
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

        for line in output.split('\n'):
            # Check for both [error] and [warn] tags (note: tags may have trailing spaces)
            if '[error' not in line and '[warn' not in line:
                continue

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

            # Parse error type and variable name
            if 'undefined function call' in clean_line.lower():
                error['type'] = 'undeclared(function)'
                var_match = re.search(r',\s+(\S+)\s*$', clean_line)
                if var_match:
                    error['var'] = var_match.group(1)
            elif 'undeclared variable' in clean_line.lower():
                error['type'] = 'undeclared(variable)'
                var_match = re.search(r',\s+(\S+)\s*$', clean_line)
                if var_match:
                    error['var'] = var_match.group(1)
            elif 'declaring parameters as local variable' in clean_line.lower() or 'redeclar' in clean_line.lower():
                error['type'] = 'redeclaration'
                var_match = re.search(r',\s+(\S+)\s*$', clean_line)
                if var_match:
                    error['var'] = var_match.group(1)
            elif 'assignment in condition' in clean_line.lower():
                error['type'] = 'assignment'
                var_match = re.search(r',\s+(\S+)\s*$', clean_line)
                if var_match:
                    error['var'] = var_match.group(1)
                else:
                    error['var'] = '='
            elif 'constant' in clean_line.lower() and 'variable name position' in clean_line.lower():
                error['type'] = 'constant_binding'
                var_match = re.search(r',\s+(\S+)\s*$', clean_line)
                if var_match:
                    error['var'] = var_match.group(1)
            elif 'missing opening parenthesis' in clean_line.lower():
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
            elif 'if statement' in clean_line.lower() and 'syntax error' in clean_line.lower():
                error['type'] = 'if_syntax'
                error['var'] = 'if'
            elif 'parameter declaration' in clean_line.lower() and 'without @optional or @key' in clean_line.lower():
                error['type'] = 'parameter_syntax'
                error['var'] = 'param'
            elif 'non-identifier in variable binding' in clean_line.lower():
                error['type'] = 'binding_syntax'
                # Extract last value after last comma (e.g., "(123...)")
                parts = clean_line.split(',')
                if len(parts) > 1:
                    error['var'] = parts[-1].strip()
                else:
                    error['var'] = 'binding'
            elif 'invalid cond clause syntax' in clean_line.lower():
                error['type'] = 'cond_syntax'
                error['var'] = 'cond'
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
                var_match = re.search(r'syntax error[^,]*,\s+(\S+)\s*$', clean_line)
                if var_match:
                    error['var'] = var_match.group(1)
                else:
                    error['var'] = 'syntax'

            if error['line'] is not None:
                errors.append(error)

        return errors

    def verify_with_expected(self, test_file, stdout):
        """Universal validation method that uses .expected file if present."""
        expected = self.load_expected_errors(test_file)

        if expected is None:
            # No .expected file means this should be valid code with no errors
            errors = self.parse_errors(stdout)
            self.assertEqual(len(errors), 0,
                           f"No .expected file found (expecting valid code), but found {len(errors)} errors")
            return

        # .expected file exists - perform detailed validation
        parsed_errors = self.parse_errors(stdout)

        # Group by error type
        actual_by_type = {}
        for e in parsed_errors:
            if e['type'] not in actual_by_type:
                actual_by_type[e['type']] = []
            actual_by_type[e['type']].append(e)

        expected_by_type = {}
        for e in expected:
            if e['type'] not in expected_by_type:
                expected_by_type[e['type']] = []
            expected_by_type[e['type']].append(e)

        # Verify each error type
        for error_type in set(list(actual_by_type.keys()) + list(expected_by_type.keys())):
            actual_errors = actual_by_type.get(error_type, [])
            expected_errors = expected_by_type.get(error_type, [])

            self.assertEqual(len(actual_errors), len(expected_errors),
                           f"Error type '{error_type}': expected {len(expected_errors)} errors, found {len(actual_errors)}")

            # Match each expected error to exactly one actual error
            matched_actual_indices = set()
            for exp in expected_errors:
                matching_indices = [
                    i for i, e in enumerate(actual_errors)
                    if e['line'] == exp['line']
                    and e['var'] == exp['var']
                    and e['func'] == exp['func']
                    and i not in matched_actual_indices
                ]

                self.assertTrue(len(matching_indices) > 0,
                              f"Expected error not found: line {exp['line']}, {error_type}, {exp['var']}")

                matched_actual_indices.add(matching_indices[0])


def create_test_method(test_file):
    """Dynamically create a test method for a given test file."""
    def test_method(self):
        filename = os.path.basename(test_file)
        returncode, stdout, stderr = self.run_verifier(test_file)
        try:
            self.verify_with_expected(test_file, stdout)
            # Green color for OK
            print(f"  \033[92m[OK]\033[0m files/{filename}")
        except AssertionError as e:
            # Red color for NG
            print(f"  \033[91m[NG]\033[0m files/{filename}")
            raise

    return test_method


# Dynamically generate test class with one test method per file
def load_tests(loader, tests, pattern):
    """Dynamically create test cases for all .il files in test/files/"""
    suite = unittest.TestSuite()

    # Find all test files
    test_dir = Path(__file__).resolve().parent.parent / "files"
    test_files = sorted(glob.glob(str(test_dir / "*.il")))

    if not test_files:
        return suite

    # Print header
    print("\nChecking test files...")

    # Create a dynamic test class
    test_class_dict = {}

    for test_file in test_files:
        filename = os.path.basename(test_file)
        # Create a valid test method name
        test_name = f"test_{filename.replace('.il', '').replace('-', '_')}"
        test_class_dict[test_name] = create_test_method(test_file)

    # Create the test class
    DynamicTestClass = type('TestAllFiles', (SkillupTestCase,), test_class_dict)

    # Add all tests to the suite
    for test_name in sorted(test_class_dict.keys()):
        suite.addTest(DynamicTestClass(test_name))

    # Print summary after all tests
    with_expected = sum(1 for f in test_files if os.path.exists(f.replace('.il', '.expected')))
    without_expected = len(test_files) - with_expected

    def print_summary():
        print(f"\nTested {len(test_files)} total files:")
        print(f"  - {with_expected} files with .expected (error validation)")
        print(f"  - {without_expected} files without .expected (valid code)")

    # Store the summary function to be called later
    DynamicTestClass._print_summary = staticmethod(print_summary)

    return suite


if __name__ == '__main__':
    # Run tests with minimal verbosity
    runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, 'w'))
    result = runner.run(load_tests(None, None, None))

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    # Green color for numbers
    tests_run_colored = f"\033[92m{result.testsRun}\033[0m"
    successes_colored = f"\033[92m{result.testsRun - len(result.failures) - len(result.errors)}\033[0m"

    # Red color for failures/errors if > 0, otherwise green
    failures_count = len(result.failures)
    errors_count = len(result.errors)
    failures_colored = f"\033[91m{failures_count}\033[0m" if failures_count > 0 else f"\033[92m{failures_count}\033[0m"
    errors_colored = f"\033[91m{errors_count}\033[0m" if errors_count > 0 else f"\033[92m{errors_count}\033[0m"

    print(f"Tests run: {tests_run_colored}")
    print(f"Successes: {successes_colored}")
    print(f"Failures: {failures_colored}")
    print(f"Errors: {errors_colored}")
    print("="*70)

    if result.wasSuccessful():
        print("\n✓ All tests passed successfully!")
    else:
        print("\n✗ Some tests failed!")
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}")
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}")

    sys.exit(0 if result.wasSuccessful() else 1)
