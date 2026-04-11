# CLAUDE.md - Skill Verifier App

This file provides guidance to Claude Code when working with the Skill Verifier application.

## App Overview

**Skill Verifier** is a static analyzer for Cadence Virtuoso SKILL code. It detects common programming errors including undeclared variables, parameter redeclarations, and mismatched parentheses. The app runs in both CLI mode and as part of the Skillup Desktop platform.

### Key Features

- **Static Analysis**: Detects undeclared variables, undefined functions, parameter redeclaration, mismatched parentheses, and assignments in conditionals
- **Database Support**: Incremental builds with SQLite for large projects (NFS-safe with WAL mode)
- **Cross-File Analysis**: Reference database for multi-file projects to avoid false positives
- **Define Files**: Support for predefined functions/variables via configuration files
- **Multi-Mode Operation**:
  - CLI mode for command-line verification
  - Desktop mode with interactive web UI
  - Dashboard with real-time progress tracking

## File Structure

```
app/skillverifier/
├── app.ini                   # App metadata and configuration
├── skillverifier.py         # Main app entry point (App class)
├── core.py                  # Core verification engine (5500+ lines)
├── verification.py          # Verification workflow coordination
├── state.py                 # Shared state for UI communication
├── callpython_handler.py    # JavaScript↔Python communication handler
└── web/                     # Web UI files
    ├── dashboard.html       # Main dashboard
    ├── verify.html         # File verification interface
    └── results.html        # Results viewer
```

## Running the Verifier

### CLI Mode

```bash
# Basic usage
python3 skillup.py <skill_file.il>

# Verify multiple files and directories
python3 skillup.py file1.il file2.il src/

# Use define file for predefined functions/variables
python3 skillup.py --define="define.txt" test.il

# Build database from project files
python3 skillup.py --build=project.db src/*.il lib/*.il

# Verify using database (skip errors for cross-file references)
python3 skillup.py --data=project.db test.il
```

### Desktop Mode

```bash
# Start desktop and open skillverifier app
python3 skillup.py --desktop --app:skillverifier

# Or select from desktop sidebar
python3 skillup.py --desktop
```

## Command-Line Options

### `--define=<path>`
Path to define file containing predefined functions and variables.

Define file format:
- `[VARIABLE]` section for variable names
- `[FUNCTION]` section for function names
- Comments: `#` (line comment), `/* */` (block comment)

Alternative: Set `SKILLUP_DEFINE` environment variable.

### `--build=<db>`
Build mode: Parse files and store definitions in SQLite database.
- Supports incremental builds (SHA256 hash comparison)
- Skips unchanged files automatically
- NFS-safe with WAL mode and locking

### `--data=<db>`
Query mode: Use database to skip undefined function/variable errors.
- Functions/variables defined in database won't trigger errors
- Useful for cross-file references in large projects

## Core Architecture

The verifier is implemented in [core.py](core.py) (~5500 lines) with these main components:

### Error Codes ([core.py:28-74](core.py#L28-L74))

```python
class Code(Enum):
    # Warnings
    W1 = undefined_function
    W2 = undeclared_variable
    W3 = assignment_in_condition

    # Errors
    E1 = parameter_redeclaration
    E2 = function_missing_paren
    E3 = if_missing_then_else
    E4 = mismatched_parentheses
    E5 = parameter_pair_without_key
    E6 = non_identifier_in_binding
    E7 = constant_in_variable_position
    E8 = invalid_cond_clause
    E9 = parameter_not_symbol
```

### Definition Database ([core.py:80-300](core.py#L80-L300))

SQLite database for cross-file references:
- Build mode: Parse files and store definitions
- Query mode: Look up definitions to skip undefined errors
- Incremental builds with SHA256 hash comparison
- NFS-safe with WAL mode and locking
- Auto-VACUUM for maintenance

### Lexer

Tokenizes SKILL source code:
- Handles SKILL-specific syntax: property operators (`~>`, `->`, `.`), symbols (`'`), strings, numbers, identifiers
- Tracks line and column positions for error reporting
- Supports both line comments (`;`) and block comments (`/* */`)

### Parser ([core.py:1137+](core.py#L1137))

Two-pass parsing to support forward function references:
- **First pass**: Collects all top-level function names
- **Second pass**: Full semantic analysis with scope tracking
- **Critical**: Maintains `overall_paren_count` to track parenthesis balance across the entire file

### Scope Management

Manages lexical scoping with parent scope chain:
- Tracks variables, parameters, and functions separately
- Supports nested scopes (functions, let/prog blocks, loops)
- Function-level scope lookup for forward references

## Key Parsing Functions

- **`_parse_function_def()`**: Handles `procedure`, `defun`, `nprocedure` in both forms:
  - `(procedure name(...) body)` - with_paren=True
  - `procedure(name(...) body)` - with_paren=False

- **`_parse_var_decl()`**: Handles `let`, `prog` variable declarations with various binding forms

- **`_parse_loop()`**: Handles `foreach`, `for`, `while`, `forall`, `setof` with loop variable scoping

- **`_parse_conditional()`**: Handles `if`, `when`, `unless`, `cond`, `case`

- **`_parse_expr()`**: Recursive expression parsing that handles all SKILL expressions

## Parenthesis Counting Critical Details

**IMPORTANT**: The parenthesis counting system uses two mechanisms:

1. **`overall_paren_count`**: Global counter tracking all parentheses in the file
   - Incremented when opening `(` is encountered and counted
   - Decremented when closing `)` is consumed
   - Must be 0 at end of file for valid syntax

2. **`depth`**: Local counter within parsing functions
   - Tracks nesting depth relative to current context
   - Used to determine when to exit a function/let/loop body

**Key Pattern**: When `_parse_expr()` is called to handle a `(...)` expression, it manages both counters internally. Do NOT increment `depth` before calling `_parse_expr()` on a `LPAREN` token.

**Common Bug Pattern to Avoid**:
```python
# WRONG - double counts depth
elif t.type == 'LPAREN':
    depth += 1
    self._parse_expr()  # _parse_expr already handles the expression

# CORRECT
elif t.type == 'LPAREN':
    self._parse_expr()  # Let _parse_expr handle everything
```

## SKILL Language Support

The parser recognizes SKILL-specific constructs:

- **Function forms**: Both `(procedure name() body)` and `procedure(name() body)`
- **Parameter modifiers**: `@optional`, `@key`
- **Property operators**: `obj~>prop`, `obj->prop`, `obj.prop`
- **Variable bindings**: Both `((var1 val1) var2)` (mixed) and `(var1 var2)` (uninitialized)
- **Builtin functions**: Extensive list including HNL (Hierarchical Netlist) driver functions
- **Forward references**: Functions can be called before definition (two-pass parsing)

## Known Edge Cases

1. **Multiline variable lists**: Variable declarations can span multiple lines
   ```skill
   let( ( var1 var2 var3
          var4 var5 ) ...)
   ```

2. **Empty function bodies**: Valid SKILL syntax
   ```skill
   procedure(fn() ())  ; Empty body with ()
   ```

3. **Nested function definitions**: Functions can be defined inside other functions

4. **Property chains**: Only the base object needs to be declared
   ```skill
   obj~>first~>second  ; Only 'obj' is checked
   ```

## Desktop Integration

### App Class ([skillverifier.py](skillverifier.py))

```python
class App:
    def __init__(self, engine, context):
        # Initialize app with WebUI engine and context

    def run_cli(self, args):
        # CLI mode implementation
        # Parses args, runs verification, returns exit code

    def get_menu_items(self):
        # Return menu items for desktop sidebar
        return [
            {'id': 'dashboard', 'name': 'Dashboard'},
            {'id': 'verify', 'name': 'File Verify'},
            {'id': 'results', 'name': 'Results'},
        ]
```

### JavaScript Communication (handlers in App class)

Handlers are registered in the App class using `register_handlers()`:
```python
def on_run_desktop_initialize(self):
    self.register_handlers({
        'verify': self._handle_verify,
        'verify_status': self._handle_verify_status,
        'verify_stream': self._handle_verify_stream
    })
    return 0

def _handle_verify(self, data: dict, language: str) -> dict:
    # Start verification in background thread
    # Update state with progress
    return {'success': True}
```

### Shared State (built-in BaseAppState)

Thread-safe state object for UI updates is built into BaseApp:
```python
class VerificationState:
    def __init__(self):
        self.files = []
        self.progress = 0
        self.results = []
        self.lock = threading.Lock()
```

## Web UI Pages

### Dashboard ([web/dashboard.html](web/dashboard.html))
- Overview of verification status
- Quick access to recent results
- Real-time progress tracking

### File Verify ([web/verify.html](web/verify.html))
- File selection interface
- Define file configuration
- Database options (build/query)
- Start verification button

### Results ([web/results.html](web/results.html))
- Interactive results viewer
- Filter by error type
- Sort by file, line, severity
- Export options

## Testing

Test files are located in the project root:
- `test1.il` - Basic test cases for undeclared variables and parameter redeclaration
- `test_comprehensive.il` - Comprehensive test suite covering all language features
- `test_real.il` - Real-world code samples
- `demo.il` - Demonstration examples
- `test_undefined.il` - Specific edge cases

Run tests manually:
```bash
python3 skillup.py test1.il
python3 skillup.py test_comprehensive.il
```

## Debugging Parenthesis Issues

When adding new parsing logic:

1. Ensure `with_paren` parameter is handled correctly in recursive calls
2. Check if opening parenthesis is counted in `overall_paren_count`
3. If yes, ensure matching closing parenthesis decrements and advances
4. Use `_parse_expr()` for general expressions - it handles its own parentheses
5. Test with both forms: `(keyword ...)` and `keyword(...)`

To debug specific issues:
```python
# Add temporary debugging in parse functions
print(f"pos={self.pos}, tok={self._current()}, pc={self.overall_paren_count}, depth={depth}")
```

## Configuration

App-specific settings stored in `$SKILLUP_CONFIG_HOME/skillverifier/`:
- Last used define file
- Recent database paths
- UI preferences

## Development Notes

### Adding New Error Types

1. Add error code to `Code` enum in [core.py](core.py#L28-L74)
2. Create alias for readability (e.g., `Code.my_error = Code.E10`)
3. Add detection logic in appropriate parser function
4. Update error messages in `print_message()` function

### Extending SKILL Language Support

1. Add new keyword to builtin list if needed
2. Implement parsing function (e.g., `_parse_new_construct()`)
3. Call from `_parse_expr()` or appropriate parent function
4. Handle scope changes if construct introduces new scope
5. Add test cases in test files

### Performance Optimization

- Large files: Parser is single-pass after preprocessing
- Database queries: Indexed by name for O(1) lookup
- Incremental builds: SHA256 hash comparison skips unchanged files
- NFS safety: WAL mode reduces lock contention

## See Also

- [/CLAUDE.md](/CLAUDE.md) - Project-level documentation
- [Project root](../../) - Main skillup entry point
- [lib/desktop.py](../../lib/desktop.py) - Desktop framework
