# Skillup Test Files

This directory contains unit test SKILL files for the skillup project.

## Directory Structure

```
test/
├── README.md                      - This file
├── test_valid_basic.il            - Valid: Basic SKILL constructs
├── test_valid_advanced.il         - Valid: Advanced features
├── test_valid_config.il           - Valid: Configuration patterns
├── test_error_undeclared.il       - Error: Undeclared variables
├── test_error_redeclaration.il    - Error: Parameter redeclarations
├── test_error_parentheses.il      - Error: Mismatched parentheses
└── test_error_mixed.il            - Error: Mixed error types
```

## Valid Test Files

These files contain syntactically and semantically correct SKILL code. They should produce **no errors** when analyzed.

### test_valid_basic.il
Tests basic SKILL language features:
- Global variable assignments
- Simple procedures with parameters
- `let` blocks with local variables
- `foreach` loops
- Conditional statements (`if`, `when`, `cond`)
- Nested functions
- Property access operators (`~>`, `->`)

### test_valid_advanced.il
Tests advanced SKILL features:
- Optional parameters (`@optional`)
- Key parameters (`@key`)
- `prog` blocks with `return`
- `for` and `while` loops
- `case` and `unless` statements
- Map and filter patterns using `foreach`
- Complex nested structures
- Multiple return points

### test_valid_config.il
Tests configuration-style code patterns:
- Global configuration variables
- List operations
- Property-based data access
- Procedure composition

## Error Test Files

These files intentionally contain errors to verify the verifier's detection capabilities.

### Expected Error Files (`.expected`)

Each error test file has a corresponding `.expected` file that defines the exact errors that should be detected:

- **test_error_undeclared.expected** - 8 expected undeclared variable errors
- **test_error_redeclaration.expected** - 2 expected redeclaration errors
- **test_error_mixed.expected** - 7 expected errors (mixed types)

**Format:** `line|func|type|var`
- `line`: Line number where error occurs
- `func`: Function name (or `None` for global scope)
- `type`: Error type (`undeclared`, `redeclaration`, etc.)
- `var`: Variable/parameter name

**Example:**
```
# Expected errors for test_error_undeclared.il
5|None|undeclared|undeclaredVar
10|testUndeclared|undeclared|missingVariable
```

**Note:** If a test file has NO `.expected` file, it is treated as a valid file (no errors expected).

## Error Test Files

### test_error_undeclared.il
Contains **8 undeclared variable errors**:
1. Undeclared in global scope
2. Undeclared in procedure
3. Undeclared in loop (accumulator not declared)
4. Undeclared in conditional
5. Property access on undeclared object
6. Multiple undeclared in single expression (3 variables)

### test_error_redeclaration.il
Contains **parameter redeclaration errors**:
- Parameters redeclared in `let` blocks (detected ✓)
- Duplicate parameter names in signatures (not yet detected)
- Nested scope redeclarations

Note: Currently only let-based redeclarations are detected.

### test_error_parentheses.il
Contains **parenthesis mismatch errors**:
- Missing closing parentheses
- Extra closing parentheses
- Mismatched in nested expressions

### test_error_mixed.il
Contains **multiple error types**:
- Undeclared variables (5 errors)
- Parameter redeclarations (1 error)
- Combination of different error patterns

## Running Individual Test Files

To manually verify a test file:

```bash
# Valid files - should produce no errors
python3 skillup.py test/test_valid_basic.il
python3 skillup.py test/test_valid_advanced.il
python3 skillup.py test/test_valid_config.il

# Error files - should detect errors
python3 skillup.py test/test_error_undeclared.il
python3 skillup.py test/test_error_redeclaration.il
python3 skillup.py test/test_error_parentheses.il
python3 skillup.py test/test_error_mixed.il
```

## Test File Naming Convention

- `test_valid_*.il` - Files that should pass verification (no errors)
- `test_error_*.il` - Files that should produce specific errors

## Adding New Test Files

When adding new test files:

1. Follow the naming convention above
2. Add clear comments explaining the test purpose
3. For error files, document expected errors in comments
4. Update `test_skillup.py` with corresponding test methods
5. Update this README with the new file description

## Notes

- All test files use independent naming (no Cadence-specific terminology)
- Test files are designed to be self-documenting with comments
- Each test file focuses on a specific feature or error type
- Files are kept small and focused for easy maintenance

## See Also

- [TEST_GUIDE.md](../TEST_GUIDE.md) - Complete testing documentation
- [test_skillup.py](../test_skillup.py) - Python unit test framework
- [run_tests.sh](../run_tests.sh) - Test runner script
