# Skillup Test Guide

## Overview

This project includes a comprehensive unit test suite for the SKILL code analyzer. The tests validate detection of common programming errors including:

- Undeclared variables
- Parameter redeclarations
- Mismatched parentheses
- Mixed error scenarios

## Running Tests

### Run all tests

```bash
cd /home/work/code/skillup
python3 test_skillup.py
```

### Run specific test categories

```bash
# Run only valid code tests
python3 -m unittest test_skillup.TestValidSKILL

# Run only undeclared variable tests
python3 -m unittest test_skillup.TestUndeclaredVariables

# Run only redeclaration tests
python3 -m unittest test_skillup.TestParameterRedeclaration

# Run only parenthesis tests
python3 -m unittest test_skillup.TestParenthesisMismatch

# Run mixed error tests
python3 -m unittest test_skillup.TestMixedErrors
```

### Run individual test

```bash
python3 -m unittest test_skillup.TestValidSKILL.test_valid_basic
```

## Test Files

Test SKILL files are located in `test/` directory:

### Valid Code Tests (Should produce NO errors)

- **test_valid_basic.il** - Basic SKILL constructs
  - Global variables
  - Simple procedures with parameters
  - Let/prog variable declarations
  - Foreach loops
  - Conditional statements (if/when/cond)
  - Nested functions
  - Property access

- **test_valid_advanced.il** - Advanced SKILL constructs
  - Optional and key parameters
  - Prog blocks with return
  - For/while loops
  - Case/unless statements
  - Map and filter operations
  - Complex nested structures

- **test_valid_config.il** - Configuration-style patterns
  - Global configuration settings
  - List operations
  - Function composition
  - Property-based data access

### Error Detection Tests (Should produce errors)

- **test_error_undeclared.il** - Undeclared variable errors
  - Global scope undeclared variables
  - Undeclared in procedures
  - Undeclared in loops
  - Undeclared in conditionals
  - Property access on undeclared objects
  - Multiple undeclared in single expression

- **test_error_redeclaration.il** - Parameter redeclaration errors
  - Duplicate parameter names (not yet detected)
  - Parameters redeclared in let blocks ✓
  - Nested scope redeclarations ✓

- **test_error_parentheses.il** - Parenthesis mismatch errors
  - Missing closing parentheses
  - Extra closing parentheses
  - Nested expression mismatches

- **test_error_mixed.il** - Mixed error types
  - Combination of undeclared and redeclaration errors
  - Multiple error types in single file

## Test Results Summary

```
Test Category                     | Tests | Status
----------------------------------|-------|--------
Valid SKILL Code                  |   3   |   ✓
Undeclared Variables (Basic)      |   1   |   ✓
Undeclared Variables (Detailed)   |   1   |   ✓
Parameter Redeclaration (Basic)   |   1   |   ✓
Parameter Redeclaration (Detailed)|   1   |   ✓
Parenthesis Mismatch              |   1   |   ✓
Mixed Errors (Basic)              |   1   |   ✓
Mixed Errors (Detailed)           |   1   |   ✓
Existing Test Files               |   3   |   ✓
Cadence Samples                   |   1   |   ✓
----------------------------------|-------|--------
TOTAL                             |  14   |   ✓
```

### Detailed Validation Tests

The test suite now includes **detailed validation tests** that verify:

1. **Exact line numbers** - Each error occurs on the expected line
2. **Variable names** - The correct variable/parameter is reported
3. **Function context** - Errors are attributed to the correct function
4. **Error types** - Proper classification (undeclared, redeclaration, etc.)

### Expected Error Files (`.expected`)

Expected errors are stored in **separate `.expected` files** alongside test files:

**Format:** `line|func|type|var`

**Example** `test/test_error_undeclared.expected`:
```
# Expected errors for test_error_undeclared.il
# Format: line|func|type|var
5|None|undeclared|undeclaredVar
10|testUndeclared|undeclared|missingVariable
18|loopError|undeclared|total
```

**Benefits:**
- ✅ Easy to update without modifying Python code
- ✅ Clear separation of test data and test logic
- ✅ Human-readable format
- ✅ No `.expected` file = valid code (no errors expected)

## Understanding Test Output

### Successful test run:

```
test_valid_basic (__main__.TestValidSKILL)
Test basic valid SKILL constructs ... ok
```

### Failed test run:

```
test_undeclared_errors (__main__.TestUndeclaredVariables)
Test detection of undeclared variables ... FAIL

Expected at least 5 undeclared errors, found 3
```

## Test Implementation Details

### Test Framework

- Python's built-in `unittest` framework
- Subprocess execution of `skillup.py`
- Output parsing for error counting
- Category-based error classification

### Error Counting

The test suite counts errors by type:
- `undeclared` - Undeclared variable errors
- `redeclaration` - Parameter/variable redeclaration errors
- `parenthesis` - Parenthesis mismatch errors
- `total` - All errors

### Known Limitations

1. **Parameter duplicate detection**: The verifier currently does not detect duplicate parameters in function signatures (e.g., `procedure(f(x x))`). Only let-based redeclarations are detected.

2. **Global variables in functions**: Global variables are not automatically visible in function scopes. They must be passed as parameters or declared within the function.

3. **Parenthesis errors**: Severe parenthesis errors may cause early parser termination, preventing detection of other errors in the same file.

## Adding New Tests

### 1. Create a new test SKILL file

```bash
# For valid code (should have no errors)
vim test/test_valid_myfeature.il

# For error detection (should have specific errors)
vim test/test_error_myerror.il
```

### 2. Add test method to test_skillup.py

```python
def test_my_feature(self):
    """Test description"""
    test_file = str(Path(__file__).parent / "test" / "test_valid_myfeature.il")
    returncode, stdout, stderr = self.run_verifier(test_file)

    errors = self.count_errors(stdout)
    self.assertEqual(errors['total'], 0,
                    f"Expected no errors, but found {errors['total']}")
```

### 3. Run the new test

```bash
python3 test_skillup.py
```

## Integration with CI/CD

To integrate tests into a CI/CD pipeline:

```bash
#!/bin/bash
# run_tests.sh

cd /home/work/code/skillup
python3 test_skillup.py

if [ $? -eq 0 ]; then
    echo "All tests passed!"
    exit 0
else
    echo "Tests failed!"
    exit 1
fi
```

## Debugging Failed Tests

### 1. Run the specific test file manually

```bash
python3 skillup.py test/test_valid_basic.il
```

### 2. Check for syntax errors

Make sure the test SKILL file has valid syntax (balanced parentheses, proper let syntax, etc.)

### 3. Verify error expectations

Check if the test expectations match the actual verifier behavior:

```bash
# Count actual errors
python3 skillup.py test_file.il 2>&1 | grep -i error | wc -l
```

## Test Maintenance

- Keep test files focused on specific features
- Use descriptive comments in test SKILL files
- Update test expectations when verifier behavior changes
- Add regression tests for bugs found in production

## Contact

For questions or issues with the test suite, please check the project documentation or create an issue in the repository.
