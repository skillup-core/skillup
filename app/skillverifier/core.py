import sys
import os
import sqlite3
import hashlib
import json
import shutil
import subprocess
import threading
import time
import configparser
import re
from datetime import datetime
from typing import List, Union, Any, Optional, Set, Tuple, Dict
from dataclasses import dataclass
from enum import Enum


# ============================================================================
# Error Code Definitions
# ============================================================================

class Code(Enum):
    """Error and warning codes for SKILL verification"""
    # Warnings (W01-W03)
    W1 = ("warn", "undefined function call")
    W2 = ("warn", "using undeclared variable")
    W3 = ("warn", "assignment in condition (use == for comparison)")

    # Errors (E01-E10)
    E1 = ("error", "declaring parameters as local variable")
    E2 = ("error", "function definition missing opening parenthesis after name")
    E3 = ("error", "syntax error in if statement: multiple expressions require 'then' or 'else' keyword")
    E4 = ("error", "mismatched parentheses")
    E5 = ("error", "parameter declaration with (name value) pair without @optional or @key")
    E6 = ("error", "non-identifier in variable binding position")
    E7 = ("error", "constant (number or string) in variable name position")
    E8 = ("error", "invalid cond clause syntax: each clause must be (condition expr...)")
    E9 = ("error", "function parameter must be a symbol (identifier)")

    def __init__(self, severity, message):
        self.severity = severity
        self.message = message

    @property
    def is_error(self):
        """Check if this code represents an error (not a warning)"""
        return self.severity == "error"

    @property
    def is_warning(self):
        """Check if this code represents a warning"""
        return self.severity == "warn"


# Readable aliases for error codes
Code.undefined_function = Code.W1
Code.undeclared_variable = Code.W2
Code.assignment_in_condition = Code.W3
Code.parameter_redeclaration = Code.E1
Code.function_missing_paren = Code.E2
Code.if_missing_then_else = Code.E3
Code.mismatched_parentheses = Code.E4
Code.parameter_pair_without_key = Code.E5
Code.non_identifier_in_binding = Code.E6
Code.constant_in_variable_position = Code.E7
Code.invalid_cond_clause = Code.E8
Code.parameter_not_symbol = Code.E9


# ============================================================================
# Definition Database for Cross-File References
# ============================================================================

class DefinitionDatabase:
    """
    SQLite database for storing function/variable definitions across multiple files.

    Supports:
    - Build mode (--build): Parse files and store definitions
    - Query mode (--data): Look up definitions to skip undefined errors
    - Incremental builds: Skip unchanged files (SHA256 hash comparison)
    - NFS-safe: WAL mode + proper locking for concurrent access
    - Auto-VACUUM: Threshold-based (20% fragmentation)
    """

    TYPE_FUNCTION = 1
    TYPE_VARIABLE = 2

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self._deleted_count = 0

    def connect(self):
        """Connect to database with NFS-safe settings"""
        self.conn = sqlite3.connect(self.db_path, timeout=30.0)

        # Enable WAL mode for better concurrency (NFS-safe in recent SQLite)
        self.conn.execute('PRAGMA journal_mode=WAL')

        # Enable foreign keys
        self.conn.execute('PRAGMA foreign_keys = ON')

        # Enable incremental auto-vacuum
        self.conn.execute('PRAGMA auto_vacuum = INCREMENTAL')

        # Set busy timeout for NFS environments
        self.conn.execute('PRAGMA busy_timeout = 30000')

        return self

    def create_schema(self):
        """Create database schema if not exists"""
        if not self.conn:
            self.connect()

        cursor = self.conn.cursor()

        # Files table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                file_hash TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Definition types table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS definition_types (
                type_id INTEGER PRIMARY KEY,
                type_name TEXT NOT NULL UNIQUE
            )
        ''')

        # Definitions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS definitions (
                def_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                type_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                line_number INTEGER,
                FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
                FOREIGN KEY (type_id) REFERENCES definition_types(type_id)
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_definitions_name ON definitions(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_definitions_file_type ON definitions(file_id, type_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_definitions_name_type ON definitions(name, type_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash)')

        # Insert definition types
        cursor.execute('INSERT OR IGNORE INTO definition_types (type_id, type_name) VALUES (?, ?)',
                      (self.TYPE_FUNCTION, 'function'))
        cursor.execute('INSERT OR IGNORE INTO definition_types (type_id, type_name) VALUES (?, ?)',
                      (self.TYPE_VARIABLE, 'variable'))

        self.conn.commit()

    @staticmethod
    def calculate_file_hash(file_path: str) -> Optional[str]:
        """Calculate SHA256 hash of file content"""
        try:
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except (IOError, OSError):
            return None

    @staticmethod
    def get_file_size(file_path: str) -> Optional[int]:
        """Get file size in bytes"""
        try:
            return os.path.getsize(file_path)
        except (IOError, OSError):
            return None

    def should_rebuild_file(self, file_path: str) -> Tuple[bool, Optional[int]]:
        """Check if file needs to be rebuilt

        Returns:
            (should_rebuild: bool, file_id: int or None)
        """
        if not self.conn:
            self.connect()

        cursor = self.conn.cursor()
        file_path = os.path.abspath(file_path)

        current_hash = self.calculate_file_hash(file_path)
        current_size = self.get_file_size(file_path)

        cursor.execute(
            'SELECT file_id, file_hash, file_size FROM files WHERE file_path = ?',
            (file_path,)
        )
        row = cursor.fetchone()

        if not row:
            return True, None

        file_id, stored_hash, stored_size = row

        if stored_hash != current_hash or stored_size != current_size:
            return True, file_id

        return False, file_id

    def update_or_create_file(self, file_path: str) -> int:
        """Update or create file record

        Returns:
            file_id
        """
        if not self.conn:
            self.connect()

        cursor = self.conn.cursor()
        file_path = os.path.abspath(file_path)

        current_hash = self.calculate_file_hash(file_path)
        current_size = self.get_file_size(file_path)

        cursor.execute('SELECT file_id FROM files WHERE file_path = ?', (file_path,))
        row = cursor.fetchone()

        if row:
            file_id = row[0]
            cursor.execute('''
                UPDATE files
                SET file_size = ?, file_hash = ?, last_updated = ?
                WHERE file_id = ?
            ''', (current_size, current_hash, datetime.now(), file_id))
        else:
            cursor.execute(
                'INSERT INTO files (file_path, file_size, file_hash, last_updated) VALUES (?, ?, ?, ?)',
                (file_path, current_size, current_hash, datetime.now())
            )
            file_id = cursor.lastrowid

        return file_id

    def get_database_stats(self) -> dict:
        """Get database statistics"""
        if not self.conn:
            self.connect()

        cursor = self.conn.cursor()

        cursor.execute('PRAGMA page_count')
        page_count = cursor.fetchone()[0]

        cursor.execute('PRAGMA freelist_count')
        freelist_count = cursor.fetchone()[0]

        cursor.execute('PRAGMA page_size')
        page_size = cursor.fetchone()[0]

        total_size = page_count * page_size
        wasted_size = freelist_count * page_size
        fragmentation = (freelist_count / page_count * 100) if page_count > 0 else 0

        return {
            'total_size_bytes': total_size,
            'wasted_size_bytes': wasted_size,
            'fragmentation_percent': fragmentation,
            'should_vacuum': fragmentation > 20
        }

    def incremental_vacuum(self):
        """Incrementally vacuum database"""
        if not self.conn:
            self.connect()

        self.conn.execute('PRAGMA incremental_vacuum')
        self.conn.commit()
        self._deleted_count = 0

    def auto_vacuum_if_needed(self):
        """Auto-vacuum based on threshold (20% fragmentation)"""
        stats = self.get_database_stats()
        if stats['should_vacuum']:
            self.incremental_vacuum()

    def add_definitions(self, file_path: str, functions: dict, variables: dict,
                       force_rebuild: bool = False) -> dict:
        """Add function/variable definitions from a file

        Args:
            file_path: Path to source .il file
            functions: Dict {func_name: line_number}
            variables: Dict {var_name: line_number}
            force_rebuild: If True, rebuild even if file hasn't changed

        Returns:
            dict: Build result with statistics
        """
        if not self.conn:
            self.connect()
            self.create_schema()

        should_rebuild, existing_file_id = self.should_rebuild_file(file_path)

        if not should_rebuild and not force_rebuild:
            return {
                'built': False,
                'reason': 'unchanged',
                'file': file_path
            }

        cursor = self.conn.cursor()

        # Delete old definitions if file exists
        deleted_count = 0
        if existing_file_id:
            cursor.execute('SELECT COUNT(*) FROM definitions WHERE file_id = ?',
                          (existing_file_id,))
            deleted_count = cursor.fetchone()[0]
            cursor.execute('DELETE FROM definitions WHERE file_id = ?',
                          (existing_file_id,))
            self._deleted_count += deleted_count

        # Update or create file record
        file_id = self.update_or_create_file(file_path)

        # Insert functions
        func_count = 0
        for func_name, line_num in functions.items():
            cursor.execute(
                'INSERT INTO definitions (file_id, type_id, name, line_number) VALUES (?, ?, ?, ?)',
                (file_id, self.TYPE_FUNCTION, func_name, line_num)
            )
            func_count += 1

        # Insert variables
        var_count = 0
        for var_name, line_num in variables.items():
            cursor.execute(
                'INSERT INTO definitions (file_id, type_id, name, line_number) VALUES (?, ?, ?, ?)',
                (file_id, self.TYPE_VARIABLE, var_name, line_num)
            )
            var_count += 1

        self.conn.commit()

        # Auto-vacuum if needed
        self.auto_vacuum_if_needed()

        return {
            'built': True,
            'reason': 'modified' if existing_file_id else 'new',
            'file': file_path,
            'deleted_definitions': deleted_count,
            'added_functions': func_count,
            'added_variables': var_count
        }

    def lookup_function(self, name: str) -> List[Tuple[str, str, str, int]]:
        """Look up function definition

        Returns:
            List of tuples: (file_path, type_name, name, line_number)
        """
        if not self.conn:
            self.connect()
            self.create_schema()

        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT f.file_path, dt.type_name, d.name, d.line_number
            FROM definitions d
            JOIN files f ON d.file_id = f.file_id
            JOIN definition_types dt ON d.type_id = dt.type_id
            WHERE d.name = ? AND dt.type_name = 'function'
        ''', (name,))

        return cursor.fetchall()

    def lookup_variable(self, name: str) -> List[Tuple[str, str, str, int]]:
        """Look up variable definition

        Returns:
            List of tuples: (file_path, type_name, name, line_number)
        """
        if not self.conn:
            self.connect()
            self.create_schema()

        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT f.file_path, dt.type_name, d.name, d.line_number
            FROM definitions d
            JOIN files f ON d.file_id = f.file_id
            JOIN definition_types dt ON d.type_id = dt.type_id
            WHERE d.name = ? AND dt.type_name = 'variable'
        ''', (name,))

        return cursor.fetchall()

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None


# ============================================================================
# Define File Parser
# ============================================================================

def parse_define_file(filepath: str) -> tuple:
    """
    Parse a define file to extract function/variable names to skip from error checking.

    The define file format:
    - /* ... */ : Block comments (ignored)
    - # : Line comments (ignored)
    - [VARIABLE] : Section for variable names
    - [FUNCTION] : Section for function names
    - Names must be under appropriate section headers

    Args:
        filepath: Path to the define file

    Returns:
        Tuple of (defined_variables: Set[str], defined_functions: Set[str])
        Returns (None, None) if file is invalid
    """
    if not filepath:
        return set(), set()

    if not os.path.exists(filepath):
        print_message("error", error_text=f"define file not found: {filepath}")
        return None, None

    defined_variables = set()
    defined_functions = set()
    current_section = None  # None, 'VARIABLE', or 'FUNCTION'
    in_block_comment = False
    line_number = 0
    section_started = False  # Track if we've seen any section header

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line_number += 1
                # Remove leading/trailing whitespace
                original_line = line
                line = line.strip()

                # Handle block comments
                if '/*' in line:
                    in_block_comment = True
                    # Handle /* ... */ on same line
                    if '*/' in line:
                        # Remove everything between /* and */
                        before = line[:line.index('/*')]
                        after_idx = line.index('*/') + 2
                        if after_idx < len(line):
                            line = before + line[after_idx:]
                        else:
                            line = before
                        in_block_comment = False
                    else:
                        # Remove everything after /*
                        line = line[:line.index('/*')]

                if '*/' in line and in_block_comment:
                    in_block_comment = False
                    # Take content after */
                    after_idx = line.index('*/') + 2
                    if after_idx < len(line):
                        line = line[after_idx:]
                    else:
                        continue

                # Skip if we're still in a block comment
                if in_block_comment:
                    continue

                # Remove line comments (everything after #)
                if '#' in line:
                    line = line[:line.index('#')]

                # Clean up
                line = line.strip()

                # Skip empty lines
                if not line:
                    continue

                # Check for section headers
                if line == '[VARIABLE]':
                    current_section = 'VARIABLE'
                    section_started = True
                    continue
                elif line == '[FUNCTION]':
                    current_section = 'FUNCTION'
                    section_started = True
                    continue

                # If we have a non-empty line, check if it's before any section
                if not section_started:
                    # ANSI color codes
                    YELLOW = '\033[93m'
                    RED = '\033[91m'
                    RESET = '\033[0m'
                    print(f"{RED}[error]{RESET} Invalid define file format", file=sys.stderr)
                    print(f"Error: Invalid define file format at line {YELLOW}{line_number}{RESET}", file=sys.stderr)
                    print(f"       Names must be defined under {YELLOW}[VARIABLE]{RESET} or {YELLOW}[FUNCTION]{RESET} section", file=sys.stderr)
                    print(f"       Found: {YELLOW}{line}{RESET}", file=sys.stderr)
                    return None, None

                # Add name to appropriate section
                if current_section == 'VARIABLE':
                    defined_variables.add(line)
                elif current_section == 'FUNCTION':
                    defined_functions.add(line)
                else:
                    # This shouldn't happen if validation above works
                    # ANSI color codes
                    YELLOW = '\033[93m'
                    RED = '\033[91m'
                    RESET = '\033[0m'
                    print(f"{RED}[error]{RESET} Invalid define file format", file=sys.stderr)
                    print(f"Error: Invalid define file format at line {YELLOW}{line_number}{RESET}", file=sys.stderr)
                    print(f"       Name {YELLOW}{line}{RESET} found without section header", file=sys.stderr)
                    return None, None

    except Exception as e:
        print_message("warn", error_text=f"Failed to parse define file {filepath}: {e}")
        return None, None

    return defined_variables, defined_functions


# ============================================================================
# AST(Abstract syntax tree) Node Classes
# ============================================================================

@dataclass
class ASTNode:
    """Base class for AST nodes"""
    line: int = 0
    col: int = 0


@dataclass
class Number(ASTNode):
    """Numeric literal"""
    value: Union[int, float] = 0


@dataclass
class String(ASTNode):
    """String literal"""
    value: str = ""


@dataclass
class Symbol(ASTNode):
    """Identifier/Symbol"""
    name: str = ""


@dataclass
class QuotedExpr(ASTNode):
    """Quoted expression: 'expr"""
    expr: Any = None


@dataclass
class FunctionDef(ASTNode):
    """Function definition: (procedure name(params) body)"""
    keyword: str = ""  # procedure, defun, nprocedure
    name: str = ""
    params: List[str] = None
    body: List[Any] = None
    syntax_errors: List[dict] = None  # Syntax errors found during parsing

    def __post_init__(self):
        if self.params is None:
            self.params = []
        if self.body is None:
            self.body = []
        if self.syntax_errors is None:
            self.syntax_errors = []


@dataclass
class Let(ASTNode):
    """Let/Prog binding: let((vars) body)"""
    keyword: str = ""  # let, prog
    bindings: List[tuple] = None  # [(var, init_value), ...]
    body: List[Any] = None
    syntax_errors: List[dict] = None  # Syntax errors found during parsing

    def __post_init__(self):
        if self.bindings is None:
            self.bindings = []
        if self.body is None:
            self.body = []
        if self.syntax_errors is None:
            self.syntax_errors = []


@dataclass
class If(ASTNode):
    """Conditional: if(cond then expr1 else expr2)"""
    condition: Any = None
    then_expr: Any = None
    else_expr: Optional[Any] = None
    syntax_errors: List[dict] = None

    def __post_init__(self):
        if self.syntax_errors is None:
            self.syntax_errors = []


@dataclass
class When(ASTNode):
    """When clause: when(cond expr)"""
    condition: Any = None
    body: List[Any] = None

    def __post_init__(self):
        if self.body is None:
            self.body = []


@dataclass
class Unless(ASTNode):
    """Unless clause: unless(cond expr)"""
    condition: Any = None
    body: List[Any] = None

    def __post_init__(self):
        if self.body is None:
            self.body = []


@dataclass
class For(ASTNode):
    """For loop: for(var start end body)"""
    var: str = ""
    start: Any = None
    end: Any = None
    body: List[Any] = None

    def __post_init__(self):
        if self.body is None:
            self.body = []


@dataclass
class While(ASTNode):
    """While loop: while(cond body)"""
    condition: Any = None
    body: List[Any] = None

    def __post_init__(self):
        if self.body is None:
            self.body = []


@dataclass
class Foreach(ASTNode):
    """Foreach loop: foreach(var list body)"""
    var: str = ""
    list_expr: Any = None
    body: List[Any] = None

    def __post_init__(self):
        if self.body is None:
            self.body = []


@dataclass
class Setof(ASTNode):
    """Setof loop: setof(var collection condition...)"""
    var: str = ""
    collection: Any = None
    conditions: List[Any] = None

    def __post_init__(self):
        if self.conditions is None:
            self.conditions = []


@dataclass
class Lambda(ASTNode):
    """Lambda function: lambda((params) body)"""
    params: List[str] = None
    body: List[Any] = None
    syntax_errors: List[dict] = None

    def __post_init__(self):
        if self.params is None:
            self.params = []
        if self.body is None:
            self.body = []
        if self.syntax_errors is None:
            self.syntax_errors = []


@dataclass
class FunctionCall(ASTNode):
    """Function call: (func args...)"""
    func: str = ""
    args: List[Any] = None
    syntax_errors: List[dict] = None  # Syntax errors found during parsing

    def __post_init__(self):
        if self.args is None:
            self.args = []
        if self.syntax_errors is None:
            self.syntax_errors = []


@dataclass
class BinaryOp(ASTNode):
    """Binary operation: a + b"""
    op: str = ""
    left: Any = None
    right: Any = None


@dataclass
class UnaryOp(ASTNode):
    """Unary operation: !x, -x, +x"""
    op: str = ""
    operand: Any = None


@dataclass
class Assignment(ASTNode):
    """Assignment: var = value"""
    var: str = ""
    value: Any = None


@dataclass
class PropertyAccess(ASTNode):
    """Property access: obj~>prop or obj->prop"""
    obj: Any = None
    op: str = ""  # ~>, ->, .
    prop: str = ""


@dataclass
class ListExpr(ASTNode):
    """Generic list expression"""
    elements: List[Any] = None

    def __post_init__(self):
        if self.elements is None:
            self.elements = []


# ============================================================================
# Token Class
# ============================================================================

class Token:
    """Represents a token in SKILL code"""
    def __init__(self, type_: str, value: Any, line: int = 0, col: int = 0, space_before: bool = False):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col
        self.space_before = space_before  # True if whitespace before this token

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


# ============================================================================
# Tokenizer
# ============================================================================

class Tokenizer:
    """Tokenize SKILL source code"""

    def __init__(self, code: str):
        self.code = code
        self.pos = 0
        self.line = 1
        self.col = 1

    def tokenize(self) -> List[Token]:
        tokens = []
        had_whitespace = False  # Track if we just skipped whitespace

        while self.pos < len(self.code):
            ch = self.code[self.pos]

            # Skip whitespace
            if ch in ' \t\r\n':
                had_whitespace = True
                if ch == '\n':
                    self.line += 1
                    self.col = 1
                else:
                    self.col += 1
                self.pos += 1
                continue

            # Line comment
            if ch == ';':
                had_whitespace = True  # Comments are treated as whitespace
                while self.pos < len(self.code) and self.code[self.pos] != '\n':
                    self.pos += 1
                continue

            # Block comment
            if ch == '/' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '*':
                had_whitespace = True  # Comments are treated as whitespace
                self.pos += 2
                self.col += 2
                while self.pos + 1 < len(self.code):
                    if self.code[self.pos] == '*' and self.code[self.pos + 1] == '/':
                        self.pos += 2
                        self.col += 2
                        break
                    if self.code[self.pos] == '\n':
                        self.line += 1
                        self.col = 1
                    else:
                        self.col += 1
                    self.pos += 1
                continue

            # String
            if ch == '"':
                tokens.append(self._read_string(had_whitespace))
                had_whitespace = False
                continue

            # Quote
            if ch == "'":
                tokens.append(Token('QUOTE', "'", self.line, self.col, had_whitespace))
                self.pos += 1
                self.col += 1
                had_whitespace = False
                continue

            # Backtick (quasiquote)
            if ch == "`":
                tokens.append(Token('BACKTICK', "`", self.line, self.col, had_whitespace))
                self.pos += 1
                self.col += 1
                had_whitespace = False
                continue

            # Comma (unquote) - may be followed by @ for unquote-splicing
            if ch == ",":
                if self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '@':
                    tokens.append(Token('UNQUOTE_SPLICING', ",@", self.line, self.col, had_whitespace))
                    self.pos += 2
                    self.col += 2
                else:
                    tokens.append(Token('UNQUOTE', ",", self.line, self.col, had_whitespace))
                    self.pos += 1
                    self.col += 1
                had_whitespace = False
                continue

            # Property operators
            if ch == '~' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '>':
                tokens.append(Token('PROP', '~>', self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            if ch == '-' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '>':
                tokens.append(Token('PROP', '->', self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            # Number (including negative and decimal starting with .)
            # For negative numbers: '-' should only start a number if it's not after an identifier/number/closing paren
            # (i.e., it should be a unary minus, not binary minus)
            is_negative_number = False
            if ch == '-' and self.pos + 1 < len(self.code) and self.code[self.pos + 1].isdigit():
                # Check if previous token suggests this is a binary operator
                if tokens:
                    last_tok = tokens[-1]
                    # If previous token is IDENT, NUMBER, RPAREN, or RBRACKET, this is binary minus
                    if last_tok.type in ('IDENT', 'NUMBER', 'RPAREN', 'RBRACKET'):
                        is_negative_number = False  # It's a binary operator
                    else:
                        is_negative_number = True  # It's a unary minus (negative number)
                else:
                    is_negative_number = True  # Start of file - must be unary

            if ch.isdigit() or is_negative_number or (ch == '.' and self.pos + 1 < len(self.code) and self.code[self.pos + 1].isdigit()):
                tokens.append(self._read_number(had_whitespace))
                had_whitespace = False
                continue

            # Parentheses
            if ch == '(':
                tokens.append(Token('LPAREN', '(', self.line, self.col, had_whitespace))
                self.pos += 1
                self.col += 1
                had_whitespace = False
                continue

            if ch == ')':
                tokens.append(Token('RPAREN', ')', self.line, self.col, had_whitespace))
                self.pos += 1
                self.col += 1
                had_whitespace = False
                continue

            # Brackets (array access)
            if ch == '[':
                tokens.append(Token('LBRACKET', '[', self.line, self.col, had_whitespace))
                self.pos += 1
                self.col += 1
                had_whitespace = False
                continue

            if ch == ']':
                tokens.append(Token('RBRACKET', ']', self.line, self.col, had_whitespace))
                self.pos += 1
                self.col += 1
                had_whitespace = False
                continue

            # Two-char operators
            if ch == '=' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '=':
                tokens.append(Token('OP', '==', self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            if ch == '!' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '=':
                tokens.append(Token('OP', '!=', self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            if ch == '<' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '=':
                tokens.append(Token('OP', '<=', self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            if ch == '>' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '=':
                tokens.append(Token('OP', '>=', self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            if ch == '&' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '&':
                tokens.append(Token('OP', '&&', self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            if ch == '|' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '|':
                tokens.append(Token('OP', '||', self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            # Single-char operators
            if ch in '+-*/<>=!.&|:':
                tokens.append(Token('OP', ch, self.line, self.col, had_whitespace))
                self.pos += 1
                self.col += 1
                had_whitespace = False
                continue

            # Escaped character literals: \( \) \< \> \, etc.
            # In SKILL, these are character literals, not actual parentheses/operators
            if ch == '\\' and self.pos + 1 < len(self.code):
                next_ch = self.code[self.pos + 1]
                # Create a symbol token for the escaped character
                tokens.append(Token('IDENT', '\\' + next_ch, self.line, self.col, had_whitespace))
                self.pos += 2
                self.col += 2
                had_whitespace = False
                continue

            # Keyword argument: ?name (used in function calls like hiCreateField(?name "foo"))
            # These are parameter names, not variables, so tokenize them specially
            if ch == '?' and self.pos + 1 < len(self.code) and (self.code[self.pos + 1].isalpha() or self.code[self.pos + 1] == '_'):
                # Read ?identifier as a keyword argument token
                tokens.append(self._read_keyword_arg(had_whitespace))
                had_whitespace = False
                continue

            # Identifier (including @optional, @key)
            if ch.isalpha() or ch == '_' or ch == '@':
                tokens.append(self._read_identifier(had_whitespace))
                had_whitespace = False
                continue

            # Unknown - skip
            self.pos += 1
            self.col += 1

        tokens.append(Token('EOF', None, self.line, self.col, False))
        return tokens

    def _read_string(self, space_before: bool = False) -> Token:
        start_line, start_col = self.line, self.col
        result = []
        self.pos += 1  # skip opening "
        self.col += 1

        while self.pos < len(self.code) and self.code[self.pos] != '"':
            if self.code[self.pos] == '\\' and self.pos + 1 < len(self.code):
                result.append(self.code[self.pos:self.pos+2])
                self.pos += 2
                self.col += 2
            else:
                result.append(self.code[self.pos])
                if self.code[self.pos] == '\n':
                    self.line += 1
                    self.col = 1
                else:
                    self.col += 1
                self.pos += 1

        if self.pos < len(self.code):
            self.pos += 1  # skip closing "
            self.col += 1

        return Token('STRING', ''.join(result), start_line, start_col, space_before)

    def _read_number(self, space_before: bool = False) -> Token:
        start_line, start_col = self.line, self.col
        result = []

        # Handle negative sign
        if self.code[self.pos] == '-':
            result.append('-')
            self.pos += 1
            self.col += 1

        # Read digits, decimal point, and exponent
        while self.pos < len(self.code):
            ch = self.code[self.pos]
            if ch.isdigit() or ch == '.':
                result.append(ch)
                self.pos += 1
                self.col += 1
            elif ch in 'eE':
                # Scientific notation: check for e+, e-, or just e
                result.append(ch)
                self.pos += 1
                self.col += 1
                # Check for optional sign after e
                if self.pos < len(self.code) and self.code[self.pos] in '+-':
                    result.append(self.code[self.pos])
                    self.pos += 1
                    self.col += 1
            else:
                break

        num_str = ''.join(result)
        # Try to parse as int first, then float
        try:
            value = int(num_str)
        except ValueError:
            try:
                value = float(num_str)
            except ValueError:
                # If parsing fails, return 0 as fallback
                value = 0

        return Token('NUMBER', value, start_line, start_col, space_before)

    def _read_identifier(self, space_before: bool = False) -> Token:
        start_line, start_col = self.line, self.col
        result = []

        while self.pos < len(self.code) and (self.code[self.pos].isalnum() or self.code[self.pos] in '_?!@'):
            # Don't consume ! if it's part of != operator
            if self.code[self.pos] == '!' and self.pos + 1 < len(self.code) and self.code[self.pos + 1] == '=':
                break
            result.append(self.code[self.pos])
            self.pos += 1
            self.col += 1

        return Token('IDENT', ''.join(result), start_line, start_col, space_before)

    def _read_keyword_arg(self, space_before: bool = False) -> Token:
        """Read keyword argument like ?name or ?prompt"""
        start_line, start_col = self.line, self.col
        result = []

        # Read the ? prefix
        if self.pos < len(self.code) and self.code[self.pos] == '?':
            result.append(self.code[self.pos])
            self.pos += 1
            self.col += 1

        # Read the identifier part
        while self.pos < len(self.code) and (self.code[self.pos].isalnum() or self.code[self.pos] in '_'):
            result.append(self.code[self.pos])
            self.pos += 1
            self.col += 1

        return Token('KEYWORD_ARG', ''.join(result), start_line, start_col, space_before)


# ============================================================================
# Parser
# ============================================================================

class Parser:
    """Parse tokens into AST"""

    # SKILL keywords
    FUNC_KEYWORDS = {'procedure', 'defun', 'nprocedure'}
    VAR_KEYWORDS = {'let', 'prog'}
    LOOP_KEYWORDS = {'for', 'foreach', 'while', 'forall', 'setof'}
    COND_KEYWORDS = {'if', 'when', 'unless', 'cond', 'case'}
    BINARY_OPS = {'+', '-', '*', '/', '==', '!=', '<', '>', '<=', '>=', '&&', '||'}

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.overall_paren_count = 0
        self.paren_stack = []  # Stack to track unclosed LPAREN positions
        self.extra_rparen_positions = []  # Track extra closing parenthesis positions
        self.in_quasiquote = 0  # Track nesting depth of backtick expressions
        self.recursion_depth = 0  # Track recursion depth to prevent infinite recursion
        self.max_recursion_depth = 300  # Maximum allowed recursion depth
        self.parsing_errors = []  # List to collect structured parsing errors

    def parse(self) -> List[ASTNode]:
        """Parse all top-level forms"""
        forms = []

        while not self._is_eof():
            # Check for unexpected closing parenthesis at top level
            if self._current().type == 'RPAREN':
                # Extra closing paren - record and skip it
                self._consume_rparen()
                continue

            form = self._parse_form()
            if form is not None:
                forms.append(form)

        # Check for parenthesis mismatch
        if self.overall_paren_count != 0:
            if self.overall_paren_count > 0:
                # Missing closing parenthesis - show unclosed opening positions
                print_message("error", error_text=f"Parsing failed: Missing {self.overall_paren_count} closing parenthesis", code_id="E04")
                if self.paren_stack:
                    for line, col in self.paren_stack:
                        print_message("error", line=line, error_text=f"Unclosed opening parenthesis at column {col}", code_id="E04")
                        # Add to structured errors
                        self.parsing_errors.append({
                            'line': line,
                            'message': 'mismatched parentheses',
                            'code': Code.mismatched_parentheses.name,
                            'error_code': 'E4'
                        })
            else:
                # Extra closing parenthesis - show positions
                print_message("error", error_text=f"Parsing failed: {-self.overall_paren_count} extra closing parenthesis", code_id="E04")
                if self.extra_rparen_positions:
                    for line, col in self.extra_rparen_positions:
                        print_message("error", line=line, error_text=f"Extra closing parenthesis at column {col}", code_id="E04")
                        # Add to structured errors
                        self.parsing_errors.append({
                            'line': line,
                            'message': 'mismatched parentheses',
                            'code': Code.mismatched_parentheses.name,
                            'error_code': 'E4'
                        })
            return None

        return forms

    def _current(self) -> Token:
        if self.pos >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self.pos]

    def _peek(self, offset: int = 1) -> Token:
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[pos]

    def _advance(self):
        if self.pos < len(self.tokens) - 1:
            self.pos += 1

    def _consume_lparen(self):
        """Advance past LPAREN and update paren count"""
        if self._current().type == 'LPAREN':
            token = self._current()
            self.overall_paren_count += 1
            self.paren_stack.append((token.line, token.col))
            self._advance()

    def _consume_rparen(self):
        """Advance past RPAREN and update paren count"""
        if self._current().type == 'RPAREN':
            token = self._current()
            self.overall_paren_count -= 1
            if self.paren_stack:
                self.paren_stack.pop()
            else:
                # Extra closing parenthesis with no matching opening
                self.extra_rparen_positions.append((token.line, token.col))
            self._advance()

    def _is_eof(self) -> bool:
        return self._current().type == 'EOF'

    def _get_operator_precedence(self, op: str) -> int:
        """Get operator precedence (higher number = higher precedence)"""
        precedence = {
            ':': 0,  # Cons cell operator (lowest precedence)
            '||': 1,
            '&&': 2,
            '==': 3, '!=': 3,
            '<': 4, '>': 4, '<=': 4, '>=': 4,
            '+': 5, '-': 5,
            '*': 6, '/': 6, '%': 6,
        }
        return precedence.get(op, 0)

    def _is_binary_operator(self, token) -> bool:
        """Check if token is a binary operator"""
        return (token.type == 'OP' and
                token.value in ['==', '!=', '<', '>', '<=', '>=', '+', '-', '*', '/', '%', '&&', '||', ':'])

    def _parse_expression_with_precedence(self, min_precedence: int = 0) -> Optional[ASTNode]:
        """Parse expression with operator precedence using precedence climbing.
        This properly handles chains like: a && b || c && d
        """
        # Check recursion depth to prevent stack overflow
        self.recursion_depth += 1
        if self.recursion_depth > self.max_recursion_depth:
            self.recursion_depth -= 1
            # Return a dummy node and skip to next safe point
            return Symbol(name='<recursion-limit>', line=self._current().line, col=self._current().col)

        try:
            # Parse the left-hand side (primary expression)
            left = self._parse_primary_expr()
            if left is None:
                return None

            # Process operators with appropriate precedence
            while not self._is_eof():
                token = self._current()

                # Check if it's a binary operator
                if not self._is_binary_operator(token):
                    break

                op = token.value
                precedence = self._get_operator_precedence(op)

                # If precedence is too low, stop
                if precedence < min_precedence:
                    break

                # Consume the operator
                op_line, op_col = token.line, token.col
                self._advance()

                # Parse right-hand side with higher precedence
                # Use precedence + 1 for left-associative operators
                right = self._parse_expression_with_precedence(precedence + 1)
                if right is None:
                    # If we can't parse right side, create a dummy node
                    right = Symbol(name='<error>', line=op_line, col=op_col)

                # Create binary operation node
                left = BinaryOp(left=left, op=op, right=right, line=op_line, col=op_col)

            return left
        finally:
            self.recursion_depth -= 1

    def _parse_primary_expr(self) -> Optional[ASTNode]:
        """Parse a primary expression (atom with property access, etc.)
        Does NOT handle infix binary operators - use _parse_expression_with_precedence for that.
        """
        token = self._current()

        if token.type == 'EOF':
            return None

        # Quoted expression: 'expr
        # Quote should only parse ONE atom (symbol, number, string, or list)
        if token.type == 'QUOTE':
            line, col = token.line, token.col
            self._advance()
            # Parse only one atom - not a full expression
            quoted_token = self._current()
            if quoted_token.type == 'LPAREN':
                # Quoted list: '(a b c)
                expr = self._parse_list()
            elif quoted_token.type == 'IDENT':
                # Quoted symbol: 'symbol
                expr = Symbol(name=quoted_token.value, line=quoted_token.line, col=quoted_token.col)
                self._advance()
            elif quoted_token.type == 'NUMBER':
                # Quoted number: '123
                expr = Number(value=quoted_token.value, line=quoted_token.line, col=quoted_token.col)
                self._advance()
            elif quoted_token.type == 'STRING':
                # Quoted string: '"hello"
                expr = String(value=quoted_token.value, line=quoted_token.line, col=quoted_token.col)
                self._advance()
            else:
                # Unexpected token after quote
                expr = Symbol(name='<error>', line=line, col=col)
            return QuotedExpr(expr=expr, line=line, col=col)

        # Backtick (quasiquote): `expr
        # Same as quote - only parse ONE atom
        if token.type == 'BACKTICK':
            line, col = token.line, token.col
            self._advance()
            # Parse only one atom - not a full expression
            quoted_token = self._current()
            if quoted_token.type == 'LPAREN':
                # Quasiquoted list: `(a b c)
                expr = self._parse_list()
            elif quoted_token.type == 'IDENT':
                # Quasiquoted symbol: `symbol
                expr = Symbol(name=quoted_token.value, line=quoted_token.line, col=quoted_token.col)
                self._advance()
            elif quoted_token.type == 'NUMBER':
                # Quasiquoted number: `123
                expr = Number(value=quoted_token.value, line=quoted_token.line, col=quoted_token.col)
                self._advance()
            elif quoted_token.type == 'STRING':
                # Quasiquoted string: `"hello"
                expr = String(value=quoted_token.value, line=quoted_token.line, col=quoted_token.col)
                self._advance()
            else:
                # Unexpected token after backtick
                expr = Symbol(name='<error>', line=line, col=col)
            return QuotedExpr(expr=expr, line=line, col=col)

        # Parenthesized expression - recursively parse with full precedence
        if token.type == 'LPAREN':
            result = self._parse_list()
            # Check for property access after the parenthesized expression
            while self._current().type == 'PROP' or (self._current().type == 'OP' and self._current().value == '.'):
                op = self._current().value
                line, col = self._current().line, self._current().col
                self._advance()
                if self._current().type == 'IDENT' and not self._current().space_before:
                    prop = self._current().value
                    self._advance()
                    result = PropertyAccess(obj=result, op=op, prop=prop, line=line, col=col)
                else:
                    break
            return result

        # Number
        if token.type == 'NUMBER':
            self._advance()
            return Number(value=token.value, line=token.line, col=token.col)

        # String
        if token.type == 'STRING':
            self._advance()
            return String(value=token.value, line=token.line, col=token.col)

        # Unary operators: !, -, +
        if token.type == 'OP' and token.value in ['!', '-', '+']:
            op = token.value
            line, col = token.line, token.col
            self._advance()
            # Use full expression parsing for operand with high precedence
            operand = self._parse_expression_with_precedence(100)
            return UnaryOp(op=op, operand=operand, line=line, col=col)

        # Identifier - could be keyword, function call, property access, or symbol
        if token.type == 'IDENT':
            name = token.value
            line, col = token.line, token.col

            # Check for special keywords before advancing
            # These are keywords that look like function calls but need special parsing
            if name in ('lambda', 'setof', 'foreach', 'for', 'while', 'if', 'when', 'unless') and self.tokens[self.pos + 1].type == 'LPAREN' if self.pos + 1 < len(self.tokens) else False:
                self._advance()  # consume keyword
                if name == 'lambda':
                    return self._parse_lambda(line, col)
                elif name == 'setof':
                    return self._parse_setof(line, col)
                elif name == 'foreach':
                    return self._parse_foreach(line, col)
                elif name == 'for':
                    return self._parse_for(line, col)
                elif name == 'while':
                    return self._parse_while(line, col)
                elif name == 'if':
                    return self._parse_if(line, col)
                elif name == 'when':
                    return self._parse_when(line, col)
                elif name == 'unless':
                    return self._parse_unless(line, col)

            self._advance()

            # Start with the base symbol
            result = Symbol(name=name, line=line, col=col)

            # Process postfix operators (array access, function call, property access)
            while True:
                # Check for array access: var[index] or var[index1][index2]
                if self._current().type == 'LBRACKET':
                    self._advance()  # skip [
                    index = self._parse_expression_with_precedence(0)
                    if self._current().type == 'RBRACKET':
                        self._advance()  # skip ]
                    # Create function call node representing array access: (nth index array)
                    result = FunctionCall(func='nth', args=[index, result], line=line, col=col)

                # Check for function call
                # Don't parse as function call if there's whitespace before the LPAREN
                # (this prevents "func() (if ...)" from being parsed as chained call)
                elif self._current().type == 'LPAREN' and not self._current().space_before:
                    args = self._parse_args()
                    func_name = name if isinstance(result, Symbol) and result.name == name else '<complex>'
                    result = FunctionCall(func=func_name, args=args, line=line, col=col)

                # Check for property access chain (PROP tokens: ~>, -> and OP token: .)
                elif self._current().type == 'PROP' or (self._current().type == 'OP' and self._current().value == '.'):
                    op = self._current().value
                    self._advance()
                    if self._current().type == 'IDENT' and not self._current().space_before:
                        prop = self._current().value
                        self._advance()
                        result = PropertyAccess(obj=result, op=op, prop=prop, line=line, col=col)
                    else:
                        break

                else:
                    break

            # Check for assignment after all postfix operators: var[i] = value or var.prop = value
            if self._current().type == 'OP' and self._current().value == '=':
                self._advance()  # skip =
                value = self._parse_expression_with_precedence(0)
                # For array access or property access, we need to represent the assignment differently
                # For now, we'll use Assignment with a complex "var" representation
                if isinstance(result, Symbol):
                    return Assignment(var=result.name, value=value, line=line, col=col)
                else:
                    # Complex lvalue (array[index] or obj.prop) - represent as assignment to entire expression
                    return Assignment(var=str(result), value=value, line=line, col=col)

            return result

        # Keyword argument: ?name (parameter name in keyword argument syntax)
        # Treat as a special symbol that won't be verified as a variable
        if token.type == 'KEYWORD_ARG':
            self._advance()
            return Symbol(name=token.value, line=token.line, col=token.col)

        # Other operators (shouldn't appear at start of expression)
        if token.type == 'OP':
            self._advance()
            return Symbol(name=token.value, line=token.line, col=token.col)

        # Property operators (shouldn't appear at start of expression)
        if token.type == 'PROP':
            self._advance()
            return Symbol(name=token.value, line=token.line, col=token.col)

        # Unexpected token - advance to avoid infinite loop
        if token.type not in ['EOF', 'RPAREN']:
            self._advance()
        return None


    def _parse_form(self) -> Optional[ASTNode]:
        """Parse a single form (expression) with full operator support."""
        # Track recursion depth
        self.recursion_depth += 1
        if self.recursion_depth > self.max_recursion_depth:
            self.recursion_depth -= 1
            token = self._current()
            return Symbol(name='<recursion-limit>', line=token.line, col=token.col)

        try:
            token = self._current()

            if token.type == 'EOF':
                return None

            # Quoted expression: 'expr
            if token.type == 'QUOTE':
                self._advance()
                expr = self._parse_form()
                return QuotedExpr(expr=expr, line=token.line, col=token.col)

            # Backtick (quasiquote): `expr
            if token.type == 'BACKTICK':
                self._advance()
                self.in_quasiquote += 1
                expr = self._parse_form()
                self.in_quasiquote -= 1
                return QuotedExpr(expr=expr, line=token.line, col=token.col)

            # Unquote: ,expr
            if token.type == 'UNQUOTE':
                self._advance()
                expr = self._parse_form()
                return expr  # Just return the expression for now

            # Unquote-splicing: ,@expr
            if token.type == 'UNQUOTE_SPLICING':
                self._advance()
                expr = self._parse_form()
                return expr  # Just return the expression for now

            # Parenthesized expression - handle specially for special forms
            if token.type == 'LPAREN':
                # Parse the parenthesized expression/list
                left = self._parse_list()

                # Check for property access after the parenthesized expression
                while self._current().type == 'PROP' or (self._current().type == 'OP' and self._current().value == '.'):
                    op = self._current().value
                    prop_line, prop_col = self._current().line, self._current().col
                    self._advance()
                    if self._current().type == 'IDENT' and not self._current().space_before:
                        prop = self._current().value
                        self._advance()
                        left = PropertyAccess(obj=left, op=op, prop=prop, line=prop_line, col=prop_col)
                    else:
                        break

                # Check if there are binary operators following - if so, continue parsing as expression
                while self._is_binary_operator(self._current()):
                    op = self._current().value
                    op_line, op_col = self._current().line, self._current().col
                    self._advance()

                    # Parse right-hand side
                    right = self._parse_expression_with_precedence(self._get_operator_precedence(op) + 1)
                    if right is None:
                        right = Symbol(name='<error>', line=op_line, col=op_col)

                    # Create binary operation
                    left = BinaryOp(left=left, op=op, right=right, line=op_line, col=op_col)

                return left

            # Check for special keywords followed by LPAREN: if(...), let(...), procedure(...), etc.
            if token.type == 'IDENT':
                name = token.value
                # Look ahead to see if next is LPAREN
                if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == 'LPAREN':
                    # Check if it's a special keyword
                    if name in self.FUNC_KEYWORDS:
                        self._advance()  # consume keyword
                        # Check for space before LPAREN (E02 error)
                        if self._current().space_before:
                            func_def = self._parse_function_def(name, token.line, token.col)
                            # Add E02 syntax error
                            if not hasattr(func_def, 'syntax_errors') or func_def.syntax_errors is None:
                                func_def.syntax_errors = []
                            func_def.syntax_errors.append({
                                'line': token.line,
                                'message': 'function definition missing opening parenthesis after name',
                                'code': f'{name} ('
                            })
                            return func_def
                        return self._parse_function_def(name, token.line, token.col)
                    elif name in self.VAR_KEYWORDS:
                        self._advance()  # consume keyword
                        return self._parse_let(name, token.line, token.col)
                    elif name == 'if':
                        self._advance()  # consume 'if'
                        return self._parse_if(token.line, token.col)
                    elif name == 'when':
                        self._advance()  # consume 'when'
                        return self._parse_when(token.line, token.col)
                    elif name == 'unless':
                        self._advance()  # consume 'unless'
                        return self._parse_unless(token.line, token.col)
                    elif name == 'for':
                        self._advance()  # consume 'for'
                        return self._parse_for(token.line, token.col)
                    elif name == 'while':
                        self._advance()  # consume 'while'
                        return self._parse_while(token.line, token.col)
                    elif name == 'foreach':
                        self._advance()  # consume 'foreach'
                        left = self._parse_foreach(token.line, token.col)
                        # Check for binary operators after foreach
                        while self._is_binary_operator(self._current()):
                            op = self._current().value
                            op_line, op_col = self._current().line, self._current().col
                            self._advance()
                            right = self._parse_expression_with_precedence(self._get_operator_precedence(op) + 1)
                            if right is None:
                                right = Symbol(name='<error>', line=op_line, col=op_col)
                            left = BinaryOp(left=left, op=op, right=right, line=op_line, col=op_col)
                        return left
                    elif name == 'setof':
                        self._advance()  # consume 'setof'
                        left = self._parse_setof(token.line, token.col)
                        # Check for binary operators after setof
                        while self._is_binary_operator(self._current()):
                            op = self._current().value
                            op_line, op_col = self._current().line, self._current().col
                            self._advance()
                            right = self._parse_expression_with_precedence(self._get_operator_precedence(op) + 1)
                            if right is None:
                                right = Symbol(name='<error>', line=op_line, col=op_col)
                            left = BinaryOp(left=left, op=op, right=right, line=op_line, col=op_col)
                        return left
                    elif name == 'lambda':
                        self._advance()  # consume 'lambda'
                        return self._parse_lambda(token.line, token.col)
                    elif name == 'case':
                        self._advance()  # consume 'case'
                        return self._parse_case(token.line, token.col)
                    elif name == 'caseq':
                        self._advance()  # consume 'caseq'
                        return self._parse_caseq(token.line, token.col)
                    elif name == 'cond':
                        self._advance()  # consume 'cond'
                        return self._parse_cond(token.line, token.col)

            # For all other cases (IDENT, NUMBER, STRING, OP), use the new precedence parser
            # which properly handles all expressions including operators
            return self._parse_expression_with_precedence(0)
        finally:
            self.recursion_depth -= 1


    def _parse_list(self) -> ASTNode:
        """Parse a parenthesized list: (...)"""
        # Track recursion depth
        self.recursion_depth += 1
        if self.recursion_depth > self.max_recursion_depth:
            self.recursion_depth -= 1
            line, col = self._current().line, self._current().col
            return Symbol(name='<recursion-limit>', line=line, col=col)

        try:
            line, col = self._current().line, self._current().col

            if self._current().type != 'LPAREN':
                return ListExpr(elements=[], line=line, col=col)

            self._consume_lparen()

            # Empty list
            if self._current().type == 'RPAREN':
                self._consume_rparen()
                return ListExpr(elements=[], line=line, col=col)

            # Check first element for keywords
            first_token = self._current()

            if first_token.type == 'IDENT':
                keyword = first_token.value

                # (procedure name(...) body)
                if keyword in self.FUNC_KEYWORDS:
                    self._advance()
                    return self._parse_function_def_paren(keyword, line, col)

                # (let (...) body)
                elif keyword in self.VAR_KEYWORDS:
                    self._advance()
                    return self._parse_let_paren(keyword, line, col)

                # (if cond then expr else expr)
                elif keyword == 'if':
                    self._advance()
                    return self._parse_if_paren(line, col)

                # (when cond body)
                elif keyword == 'when':
                    self._advance()
                    return self._parse_when_paren(line, col)

                # (unless cond body)
                elif keyword == 'unless':
                    self._advance()
                    return self._parse_unless_paren(line, col)

                # (for var start end body)
                elif keyword == 'for':
                    self._advance()
                    return self._parse_for_paren(line, col)

                # (while cond body)
                elif keyword == 'while':
                    self._advance()
                    return self._parse_while_paren(line, col)

                # (foreach var list body)
                elif keyword == 'foreach':
                    self._advance()
                    return self._parse_foreach_paren(line, col)

                # (setof var collection condition...)
                elif keyword == 'setof':
                    self._advance()
                    return self._parse_setof_paren(line, col)

                # (lambda (params) body)
                elif keyword == 'lambda':
                    self._advance()
                    return self._parse_lambda_paren(line, col)

                # (case value (pattern1 result1) (pattern2 result2) ...)
                elif keyword == 'case':
                    self._advance()
                    return self._parse_case_paren(line, col)

                # (caseq value (pattern1 result1) (pattern2 result2) ...)
                elif keyword == 'caseq':
                    self._advance()
                    return self._parse_caseq_paren(line, col)

                # (cond (condition1 expr...) (condition2 expr...) ...)
                elif keyword == 'cond':
                    self._advance()
                    return self._parse_cond_paren(line, col)

                # (func args...) - function call, or (expr) - parenthesized expression
                else:
                    # Check if this is a parenthesized expression or a function call
                    # Look ahead to see if the next token is a binary operator
                    saved_pos = self.pos
                    func_name = keyword
                    self._advance()

                    # If next token is a binary operator, property access, or array access, this is an expression or mixed list
                    if self._is_binary_operator(self._current()) or self._current().type in ('PROP', 'LBRACKET'):
                        # Reset and parse as expression
                        self.pos = saved_pos
                        first_expr = self._parse_expression_with_precedence(0)

                        # Check if there are more elements after the expression
                        # If so, this is a list with mixed content (e.g., (p == 1 t))
                        if self._current().type != 'RPAREN':
                            # Parse remaining elements as a list
                            elements = [first_expr]
                            while self._current().type != 'RPAREN' and not self._is_eof():
                                elements.append(self._parse_form())
                            self._consume_rparen()
                            return ListExpr(elements=elements, line=line, col=col)
                        else:
                            # Just a single parenthesized expression
                            self._consume_rparen()
                            return first_expr

                    # Otherwise it's a function call
                    args = []
                    while self._current().type != 'RPAREN' and not self._is_eof():
                        args.append(self._parse_form())

                    self._consume_rparen()

                    return FunctionCall(func=func_name, args=args, line=line, col=col)

            # Generic list
            elements = []
            while self._current().type != 'RPAREN' and not self._is_eof():
                elements.append(self._parse_form())

            self._consume_rparen()

            return ListExpr(elements=elements, line=line, col=col)
        finally:
            self.recursion_depth -= 1

    def _parse_args(self) -> List[ASTNode]:
        """Parse function arguments: (arg1 arg2 ...)"""
        if self._current().type != 'LPAREN':
            return []

        self._consume_lparen()

        args = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            args.append(self._parse_form())

        self._consume_rparen()

        return args

    def _parse_function_def(self, keyword: str, line: int, col: int) -> FunctionDef:
        """Parse: defun(name(params) body)"""
        self._consume_lparen()

        # Get function name
        if self._current().type != 'IDENT':
            return FunctionDef(keyword=keyword, name='', params=[], body=[], line=line, col=col)

        name = self._current().value
        self._advance()

        # Parse parameters
        params = []
        param_default_exprs = []  # Store default value expressions for validation
        syntax_errors = []

        if self._current().type == 'LPAREN':
            self._consume_lparen()
            # Track if we've seen @optional or @key
            seen_optional_or_key = False
            while self._current().type != 'RPAREN' and not self._is_eof():
                if self._current().type == 'IDENT':
                    ident_value = self._current().value
                    # Check for @optional or @key keywords
                    if ident_value in ('@optional', '@key'):
                        seen_optional_or_key = True
                        self._advance()
                    else:
                        params.append(ident_value)
                        self._advance()
                elif self._current().type == 'LPAREN':
                    # Parameter with default value: (param default_val)
                    # This is only valid after @optional or @key
                    lparen_line = self._current().line
                    # Skip syntax check if inside quasiquote (backtick) expression
                    if not seen_optional_or_key and self.in_quasiquote == 0:
                        # Syntax error: (name value) without @optional or @key
                        syntax_errors.append({
                            'line': lparen_line,
                            'message': 'parameter declaration with (name value) pair without @optional or @key',
                            'code': f'(name value) pair without @optional or @key'
                        })
                    self._consume_lparen()
                    # First element should be the parameter name
                    if self._current().type == 'IDENT':
                        param_name = self._current().value
                        params.append(param_name)
                        self._advance()
                        # Parse default value expression(s)
                        while self._current().type != 'RPAREN' and not self._is_eof():
                            default_expr = self._parse_form()
                            if default_expr is not None:
                                param_default_exprs.append(default_expr)
                    else:
                        # Error: parameter name must be an identifier (E09)
                        error_line = self._current().line
                        error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                        syntax_errors.append({
                            'line': error_line,
                            'message': 'function parameter must be a symbol (identifier)',
                            'code': f'{error_token}'
                        })
                        # Skip contents until matching RPAREN if no valid param name
                        depth = 1
                        while depth > 0 and not self._is_eof():
                            if self._current().type == 'LPAREN':
                                self._consume_lparen()
                                depth += 1
                            elif self._current().type == 'RPAREN':
                                self._consume_rparen()
                                depth -= 1
                            else:
                                self._advance()
                        continue
                    self._consume_rparen()
                else:
                    # Error: parameter must be an identifier or (name value) pair (E09)
                    error_line = self._current().line
                    error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                    syntax_errors.append({
                        'line': error_line,
                        'message': 'function parameter must be a symbol (identifier)',
                        'code': f'{error_token}'
                    })
                    self._advance()
            self._consume_rparen()

        # Parse body
        body = []
        # Add parameter default expressions to body for validation
        body.extend(param_default_exprs)
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        result = FunctionDef(keyword=keyword, name=name, params=params, body=body, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_function_def_paren(self, keyword: str, line: int, col: int) -> FunctionDef:
        """Parse: (procedure name(params) body) or (procedure (name params...) body)"""
        # Check for two forms:
        # Form 1: (procedure name(params) body) - name is IDENT followed by LPAREN
        # Form 2: (procedure (name params...) body) - LPAREN with name and params inside

        if self._current().type == 'LPAREN':
            # Form 2: (procedure (name params...) body)
            self._consume_lparen()
            # First element should be function name
            if self._current().type != 'IDENT':
                return FunctionDef(keyword=keyword, name='', params=[], body=[], line=line, col=col)
            name = self._current().value
            self._advance()
            # Rest are parameters
            params = []
            syntax_errors = []
            while self._current().type != 'RPAREN' and not self._is_eof():
                if self._current().type == 'IDENT':
                    params.append(self._current().value)
                    self._advance()
                else:
                    # Error: parameter must be an identifier (E09)
                    error_line = self._current().line
                    error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                    syntax_errors.append({
                        'line': error_line,
                        'message': 'function parameter must be a symbol (identifier)',
                        'code': f'{error_token}'
                    })
                    self._advance()
            self._consume_rparen()
            # Parse body
            body = []
            while self._current().type != 'RPAREN' and not self._is_eof():
                form = self._parse_form()
                if form is not None:
                    body.append(form)
            self._consume_rparen()
            result = FunctionDef(keyword=keyword, name=name, params=params, body=body, line=line, col=col)
            result.syntax_errors = syntax_errors
            return result

        # Form 1: (procedure name(params) body)
        # Get function name
        if self._current().type != 'IDENT':
            return FunctionDef(keyword=keyword, name='', params=[], body=[], line=line, col=col)

        name = self._current().value
        self._advance()

        # Parse parameters
        params = []
        param_default_exprs = []  # Store default value expressions for validation
        syntax_errors = []

        if self._current().type == 'LPAREN':
            self._consume_lparen()
            # Track if we've seen @optional or @key
            seen_optional_or_key = False
            while self._current().type != 'RPAREN' and not self._is_eof():
                if self._current().type == 'IDENT':
                    ident_value = self._current().value
                    # Check for @optional or @key keywords
                    if ident_value in ('@optional', '@key'):
                        seen_optional_or_key = True
                        self._advance()
                    else:
                        params.append(ident_value)
                        self._advance()
                elif self._current().type == 'LPAREN':
                    # Parameter with default value: (param default_val)
                    # This is only valid after @optional or @key
                    lparen_line = self._current().line
                    # Skip syntax check if inside quasiquote (backtick) expression
                    if not seen_optional_or_key and self.in_quasiquote == 0:
                        # Syntax error: (name value) without @optional or @key
                        syntax_errors.append({
                            'line': lparen_line,
                            'message': 'parameter declaration with (name value) pair without @optional or @key',
                            'code': f'(name value) pair without @optional or @key'
                        })
                    self._consume_lparen()
                    # First element should be the parameter name
                    if self._current().type == 'IDENT':
                        param_name = self._current().value
                        params.append(param_name)
                        self._advance()
                        # Parse default value expression(s)
                        while self._current().type != 'RPAREN' and not self._is_eof():
                            default_expr = self._parse_form()
                            if default_expr is not None:
                                param_default_exprs.append(default_expr)
                    else:
                        # Error: parameter name must be an identifier (E09)
                        error_line = self._current().line
                        error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                        syntax_errors.append({
                            'line': error_line,
                            'message': 'function parameter must be a symbol (identifier)',
                            'code': f'{error_token}'
                        })
                        # Skip contents until matching RPAREN if no valid param name
                        depth = 1
                        while depth > 0 and not self._is_eof():
                            if self._current().type == 'LPAREN':
                                self._consume_lparen()
                                depth += 1
                            elif self._current().type == 'RPAREN':
                                self._consume_rparen()
                                depth -= 1
                            else:
                                self._advance()
                        continue
                    self._consume_rparen()
                else:
                    # Error: parameter must be an identifier or (name value) pair (E09)
                    error_line = self._current().line
                    error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                    syntax_errors.append({
                        'line': error_line,
                        'message': 'function parameter must be a symbol (identifier)',
                        'code': f'{error_token}'
                    })
                    self._advance()
            self._consume_rparen()

        # Parse body
        body = []
        # Add parameter default expressions to body for validation
        body.extend(param_default_exprs)
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        result = FunctionDef(keyword=keyword, name=name, params=params, body=body, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_let(self, keyword: str, line: int, col: int) -> Let:
        """Parse: let((bindings) body)"""
        self._consume_lparen()

        # Parse bindings
        bindings = []
        syntax_errors = []
        if self._current().type == 'LPAREN':
            self._consume_lparen()
            while self._current().type != 'RPAREN' and not self._is_eof():
                if self._current().type == 'IDENT':
                    var = self._current().value
                    bindings.append((var, None))
                    self._advance()
                elif self._current().type == 'LPAREN':
                    # (var value) binding
                    self._consume_lparen()
                    if self._current().type == 'IDENT':
                        var = self._current().value
                        self._advance()
                        # Parse value(s) until RPAREN - may be multiple forms
                        values = []
                        while self._current().type != 'RPAREN' and not self._is_eof():
                            value = self._parse_form()
                            if value is not None:
                                values.append(value)
                        # Store the last value (or None if no values)
                        init_value = values[-1] if values else None
                        bindings.append((var, init_value))
                        self._consume_rparen()
                    else:
                        # Syntax error: (non-identifier) in binding position
                        err_line = self._current().line
                        err_token = self._current().value
                        syntax_errors.append({
                            'line': err_line,
                            'message': 'non-identifier in variable binding position',
                            'code': f'({err_token}...)'
                        })
                        # Skip to matching closing paren
                        depth = 1
                        while depth > 0 and not self._is_eof():
                            self._advance()
                            if self._current().type == 'LPAREN':
                                depth += 1
                            elif self._current().type == 'RPAREN':
                                depth -= 1
                        if not self._is_eof():
                            self._consume_rparen()
                elif self._current().type in ('NUMBER', 'STRING'):
                    # Syntax error: constant in variable name position
                    err_line = self._current().line
                    err_value = self._current().value
                    syntax_errors.append({
                        'line': err_line,
                        'message': 'constant (number or string) in variable name position',
                        'code': f'{err_value}'
                    })
                    self._advance()
                else:
                    self._advance()

            self._consume_rparen()

        # Parse body
        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        result = Let(keyword=keyword, bindings=bindings, body=body, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_let_paren(self, keyword: str, line: int, col: int) -> Let:
        """Parse: (let (bindings) body)"""
        # Same as _parse_let but already inside the outer paren
        bindings = []
        syntax_errors = []
        if self._current().type == 'LPAREN':
            self._consume_lparen()
            while self._current().type != 'RPAREN' and not self._is_eof():
                if self._current().type == 'IDENT':
                    var = self._current().value
                    bindings.append((var, None))
                    self._advance()
                elif self._current().type == 'LPAREN':
                    # (var value) binding
                    self._consume_lparen()
                    if self._current().type == 'IDENT':
                        var = self._current().value
                        self._advance()
                        # Parse value(s) until RPAREN - may be multiple forms
                        values = []
                        while self._current().type != 'RPAREN' and not self._is_eof():
                            value = self._parse_form()
                            if value is not None:
                                values.append(value)
                        # Store the last value (or None if no values)
                        init_value = values[-1] if values else None
                        bindings.append((var, init_value))
                        self._consume_rparen()
                    else:
                        # Syntax error: (non-identifier) in binding position
                        err_line = self._current().line
                        err_token = self._current().value
                        syntax_errors.append({
                            'line': err_line,
                            'message': 'non-identifier in variable binding position',
                            'code': f'({err_token}...)'
                        })
                        # Skip to matching closing paren
                        depth = 1
                        while depth > 0 and not self._is_eof():
                            self._advance()
                            if self._current().type == 'LPAREN':
                                depth += 1
                            elif self._current().type == 'RPAREN':
                                depth -= 1
                        if not self._is_eof():
                            self._consume_rparen()
                elif self._current().type in ('NUMBER', 'STRING'):
                    # Syntax error: constant in variable name position
                    err_line = self._current().line
                    err_value = self._current().value
                    syntax_errors.append({
                        'line': err_line,
                        'message': 'constant (number or string) in variable name position',
                        'code': f'{err_value}'
                    })
                    self._advance()
                else:
                    self._advance()

            self._consume_rparen()

        # Parse body
        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        result = Let(keyword=keyword, bindings=bindings, body=body, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_if(self, line: int, col: int) -> If:
        """Parse: if(cond then expr else expr) or if(cond expr1 expr2)"""
        self._consume_lparen()

        condition = self._parse_form()

        # Check for 'then' keyword
        has_then = False
        if self._current().type == 'IDENT' and self._current().value == 'then':
            has_then = True
            self._advance()

        then_expr = self._parse_form()

        else_expr = None
        # Check for 'else' keyword
        has_else = False
        if self._current().type == 'IDENT' and self._current().value == 'else':
            has_else = True
            self._advance()
            else_expr = self._parse_form()
        # If no 'else' keyword but there's another expression, it could be the 3rd param (else branch)
        elif self._current().type != 'RPAREN' and not self._is_eof() and not has_then:
            # This is the 3rd parameter - parse it as else_expr
            # Valid SKILL: if(cond then-expr else-expr) - 3 params without keywords is OK
            else_expr = self._parse_form()

        syntax_errors = []
        # Check for additional parameters (4+ total parameters without then/else keywords)
        # Valid SKILL: if(cond then-expr else-expr) - 3 params without keywords
        # Invalid: if(cond expr1 expr2 expr3+) - 4+ params without keywords needs 'then'/'else'
        if self._current().type != 'RPAREN' and not self._is_eof():
            if not has_then and not has_else:
                syntax_errors.append({
                    'line': line,
                    'message': "syntax error in if statement: multiple expressions require 'then' or 'else' keyword",
                    'code': None
                })
            # Consume remaining expressions to continue parsing
            while self._current().type != 'RPAREN' and not self._is_eof():
                self._parse_form()

        self._consume_rparen()

        result = If(condition=condition, then_expr=then_expr, else_expr=else_expr, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_if_paren(self, line: int, col: int) -> If:
        """Parse: (if cond then expr else expr)"""
        condition = self._parse_form()

        # Check for 'then' keyword
        has_then = False
        if self._current().type == 'IDENT' and self._current().value == 'then':
            has_then = True
            self._advance()

        then_expr = self._parse_form()

        else_expr = None
        # Check for 'else' keyword
        has_else = False
        if self._current().type == 'IDENT' and self._current().value == 'else':
            has_else = True
            self._advance()
            else_expr = self._parse_form()
        # If no 'else' keyword but there's another expression, it could be the 3rd param (else branch)
        elif self._current().type != 'RPAREN' and not self._is_eof() and not has_then:
            # This is the 3rd parameter - parse it as else_expr
            else_expr = self._parse_form()

        syntax_errors = []
        # Check for additional parameters (4+ total parameters without then/else keywords)
        # If there are MORE expressions after we've consumed condition, then, and else,
        # and we didn't have 'then' or 'else' keywords, it's a syntax error
        if self._current().type != 'RPAREN' and not self._is_eof():
            if not has_then and not has_else:
                syntax_errors.append({
                    'line': line,
                    'message': "syntax error in if statement: multiple expressions require 'then' or 'else' keyword",
                    'code': None
                })
            # Consume remaining expressions to continue parsing
            while self._current().type != 'RPAREN' and not self._is_eof():
                self._parse_form()

        self._consume_rparen()

        result = If(condition=condition, then_expr=then_expr, else_expr=else_expr, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_when(self, line: int, col: int) -> When:
        """Parse: when(cond body)"""
        self._consume_lparen()

        condition = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return When(condition=condition, body=body, line=line, col=col)

    def _parse_when_paren(self, line: int, col: int) -> When:
        """Parse: (when cond body)"""
        condition = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return When(condition=condition, body=body, line=line, col=col)

    def _parse_unless(self, line: int, col: int) -> Unless:
        """Parse: unless(cond body)"""
        self._consume_lparen()

        condition = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return Unless(condition=condition, body=body, line=line, col=col)

    def _parse_unless_paren(self, line: int, col: int) -> Unless:
        """Parse: (unless cond body)"""
        condition = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return Unless(condition=condition, body=body, line=line, col=col)

    def _parse_for(self, line: int, col: int) -> For:
        """Parse: for(var start end body)"""
        self._consume_lparen()

        var = ''
        if self._current().type == 'IDENT':
            var = self._current().value
            self._advance()

        start = self._parse_form()
        end = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return For(var=var, start=start, end=end, body=body, line=line, col=col)

    def _parse_for_paren(self, line: int, col: int) -> For:
        """Parse: (for var start end body)"""
        var = ''
        if self._current().type == 'IDENT':
            var = self._current().value
            self._advance()

        start = self._parse_form()
        end = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return For(var=var, start=start, end=end, body=body, line=line, col=col)

    def _parse_while(self, line: int, col: int) -> While:
        """Parse: while(cond body)"""
        self._consume_lparen()

        condition = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return While(condition=condition, body=body, line=line, col=col)

    def _parse_while_paren(self, line: int, col: int) -> While:
        """Parse: (while cond body)"""
        condition = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return While(condition=condition, body=body, line=line, col=col)

    def _parse_foreach(self, line: int, col: int) -> Foreach:
        """Parse: foreach(var list body)"""
        self._consume_lparen()

        var = ''
        if self._current().type == 'IDENT':
            var = self._current().value
            self._advance()

        list_expr = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return Foreach(var=var, list_expr=list_expr, body=body, line=line, col=col)

    def _parse_foreach_paren(self, line: int, col: int) -> Foreach:
        """Parse: (foreach var list body)"""
        var = ''
        if self._current().type == 'IDENT':
            var = self._current().value
            self._advance()

        list_expr = self._parse_form()

        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        return Foreach(var=var, list_expr=list_expr, body=body, line=line, col=col)

    def _parse_setof(self, line: int, col: int) -> Setof:
        """Parse: setof(var collection condition...)"""
        self._consume_lparen()

        var = ''
        if self._current().type == 'IDENT':
            var = self._current().value
            self._advance()

        collection = self._parse_form()

        conditions = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                conditions.append(form)

        self._consume_rparen()

        return Setof(var=var, collection=collection, conditions=conditions, line=line, col=col)

    def _parse_setof_paren(self, line: int, col: int) -> Setof:
        """Parse: (setof var collection condition...)"""
        var = ''
        if self._current().type == 'IDENT':
            var = self._current().value
            self._advance()

        collection = self._parse_form()

        conditions = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                conditions.append(form)

        self._consume_rparen()

        return Setof(var=var, collection=collection, conditions=conditions, line=line, col=col)

    def _parse_lambda(self, line: int, col: int) -> Lambda:
        """Parse: lambda((params) body)"""
        self._consume_lparen()

        # Parse parameter list - should be a list in parentheses
        params = []
        syntax_errors = []
        if self._current().type == 'LPAREN':
            self._advance()  # consume (
            self.overall_paren_count += 1

            while self._current().type != 'RPAREN' and not self._is_eof():
                if self._current().type == 'IDENT':
                    params.append(self._current().value)
                    self._advance()
                elif self._current().type == 'LPAREN':
                    # Could be (param default_val) form
                    self._consume_lparen()
                    if self._current().type == 'IDENT':
                        params.append(self._current().value)
                        self._advance()
                        # Skip default value expressions
                        while self._current().type != 'RPAREN' and not self._is_eof():
                            self._advance()
                    else:
                        # Error: parameter name must be an identifier (E09)
                        error_line = self._current().line
                        error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                        syntax_errors.append({
                            'line': error_line,
                            'message': 'function parameter must be a symbol (identifier)',
                            'code': f'{error_token}'
                        })
                        # Skip until matching RPAREN
                        depth = 1
                        while depth > 0 and not self._is_eof():
                            if self._current().type == 'LPAREN':
                                self._consume_lparen()
                                depth += 1
                            elif self._current().type == 'RPAREN':
                                self._consume_rparen()
                                depth -= 1
                            else:
                                self._advance()
                        continue
                    self._consume_rparen()
                else:
                    # Error: parameter must be an identifier or (name value) pair (E09)
                    error_line = self._current().line
                    error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                    syntax_errors.append({
                        'line': error_line,
                        'message': 'function parameter must be a symbol (identifier)',
                        'code': f'{error_token}'
                    })
                    self._advance()

            if self._current().type == 'RPAREN':
                self._advance()  # consume )
                self.overall_paren_count -= 1

        # Parse body expressions
        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        result = Lambda(params=params, body=body, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_case(self, line: int, col: int) -> FunctionCall:
        """Parse: case(value (pattern1 result1) (pattern2 result2) ...)
        In case, both the value and patterns are evaluated."""
        self._consume_lparen()

        # Parse the value to test
        value = self._parse_form()

        # Parse case clauses
        clauses = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            clause = self._parse_form()
            clauses.append(clause)

        self._consume_rparen()

        # Return as a function call with all arguments
        return FunctionCall(func='case', args=[value] + clauses, line=line, col=col)

    def _parse_caseq(self, line: int, col: int) -> FunctionCall:
        """Parse: caseq(value (pattern1 result1) (pattern2 result2) ...)
        In caseq, patterns are NOT evaluated (treated as symbols).
        We need to parse them specially to avoid undefined function errors."""
        self._consume_lparen()

        # Parse the value to test (this IS evaluated)
        value = self._parse_form()

        # Parse case clauses - patterns are quoted symbols
        clauses = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            # Each clause should be a list like (pattern body...)
            if self._current().type == 'LPAREN':
                clause_line, clause_col = self._current().line, self._current().col
                self._consume_lparen()

                # First element is the pattern (should NOT be evaluated)
                # We parse it but mark it as quoted
                if self._current().type == 'IDENT':
                    pattern = Symbol(name=self._current().value, line=self._current().line, col=self._current().col)
                    self._advance()
                else:
                    pattern = self._parse_form()

                # Rest are body expressions (these ARE evaluated)
                body = []
                while self._current().type != 'RPAREN' and not self._is_eof():
                    body.append(self._parse_form())

                self._consume_rparen()

                # Create a list with quoted pattern followed by body
                clause = ListExpr(elements=[QuotedExpr(expr=pattern, line=clause_line, col=clause_col)] + body,
                                line=clause_line, col=clause_col)
                clauses.append(clause)
            else:
                # Unexpected - parse it normally
                clauses.append(self._parse_form())

        self._consume_rparen()

        # Return as a function call
        return FunctionCall(func='caseq', args=[value] + clauses, line=line, col=col)

    def _parse_lambda_paren(self, line: int, col: int) -> Lambda:
        """Parse: (lambda (params) body)"""
        # Parse parameter list - should be a list in parentheses
        params = []
        syntax_errors = []
        if self._current().type == 'LPAREN':
            self._advance()  # consume (
            self.overall_paren_count += 1

            while self._current().type != 'RPAREN' and not self._is_eof():
                if self._current().type == 'IDENT':
                    params.append(self._current().value)
                    self._advance()
                elif self._current().type == 'LPAREN':
                    # Could be (param default_val) form
                    self._consume_lparen()
                    if self._current().type == 'IDENT':
                        params.append(self._current().value)
                        self._advance()
                        # Skip default value expressions
                        while self._current().type != 'RPAREN' and not self._is_eof():
                            self._advance()
                    else:
                        # Error: parameter name must be an identifier (E09)
                        error_line = self._current().line
                        error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                        syntax_errors.append({
                            'line': error_line,
                            'message': 'function parameter must be a symbol (identifier)',
                            'code': f'{error_token}'
                        })
                        # Skip until matching RPAREN
                        depth = 1
                        while depth > 0 and not self._is_eof():
                            if self._current().type == 'LPAREN':
                                self._consume_lparen()
                                depth += 1
                            elif self._current().type == 'RPAREN':
                                self._consume_rparen()
                                depth -= 1
                            else:
                                self._advance()
                        continue
                    self._consume_rparen()
                else:
                    # Error: parameter must be an identifier or (name value) pair (E09)
                    error_line = self._current().line
                    error_token = self._current().value if hasattr(self._current(), 'value') else self._current().type
                    syntax_errors.append({
                        'line': error_line,
                        'message': 'function parameter must be a symbol (identifier)',
                        'code': f'{error_token}'
                    })
                    self._advance()

            if self._current().type == 'RPAREN':
                self._advance()  # consume )
                self.overall_paren_count -= 1

        # Parse body expressions
        body = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            form = self._parse_form()
            if form is not None:
                body.append(form)

        self._consume_rparen()

        result = Lambda(params=params, body=body, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_case_paren(self, line: int, col: int) -> FunctionCall:
        """Parse: (case value (pattern1 result1) (pattern2 result2) ...)
        In case, both the value and patterns are evaluated."""
        # Parse the value to test
        value = self._parse_form()

        # Parse case clauses
        clauses = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            clause = self._parse_form()
            clauses.append(clause)

        self._consume_rparen()

        # Return as a function call with all arguments
        return FunctionCall(func='case', args=[value] + clauses, line=line, col=col)

    def _parse_caseq_paren(self, line: int, col: int) -> FunctionCall:
        """Parse: (caseq value (pattern1 result1) (pattern2 result2) ...)
        In caseq, patterns are NOT evaluated (treated as symbols).
        We need to parse them specially to avoid undefined function errors."""
        # Parse the value to test (this IS evaluated)
        value = self._parse_form()

        # Parse case clauses - patterns are quoted symbols
        clauses = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            # Each clause should be a list like (pattern body...)
            if self._current().type == 'LPAREN':
                clause_line, clause_col = self._current().line, self._current().col
                self._consume_lparen()

                # First element is the pattern (should NOT be evaluated)
                # We parse it but mark it as quoted
                if self._current().type == 'IDENT':
                    pattern = Symbol(name=self._current().value, line=self._current().line, col=self._current().col)
                    self._advance()
                else:
                    pattern = self._parse_form()

                # Rest are body expressions (these ARE evaluated)
                body = []
                while self._current().type != 'RPAREN' and not self._is_eof():
                    body.append(self._parse_form())

                self._consume_rparen()

                # Create a list with quoted pattern followed by body
                clause = ListExpr(elements=[QuotedExpr(expr=pattern, line=clause_line, col=clause_col)] + body,
                                line=clause_line, col=clause_col)
                clauses.append(clause)
            else:
                # Unexpected - parse it normally
                clauses.append(self._parse_form())

        self._consume_rparen()

        # Return as a function call
        return FunctionCall(func='caseq', args=[value] + clauses, line=line, col=col)

    def _parse_cond(self, line: int, col: int) -> FunctionCall:
        """Parse: cond((condition1 expr...) (condition2 expr...) ...)
        Each clause must be a list starting with a condition.
        Validates that each clause follows correct syntax and reports E08 errors."""
        self._consume_lparen()

        # Parse cond clauses
        clauses = []
        syntax_errors = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            # Each clause must be a list: (condition expr1 expr2 ...)
            if self._current().type == 'LPAREN':
                clause_line, clause_col = self._current().line, self._current().col
                self._consume_lparen()

                # Parse the condition (first element in the clause)
                condition = self._parse_form()

                # Parse body expressions (remaining elements)
                body = []
                while self._current().type != 'RPAREN' and not self._is_eof():
                    body.append(self._parse_form())

                self._consume_rparen()

                # Create a list representing the clause
                clause = ListExpr(elements=[condition] + body, line=clause_line, col=clause_col)
                clauses.append(clause)
            else:
                # ERROR E08: clause is not wrapped in parentheses
                error_line = self._current().line

                # Record the syntax error (only once per line)
                if not syntax_errors or syntax_errors[-1]['line'] != error_line:
                    syntax_errors.append({
                        'line': error_line,
                        'message': 'invalid cond clause syntax: each clause must be (condition expr...)',
                        'code': None
                    })

                # Skip tokens until we find the next clause or the closing paren
                # Parse as a form to consume the invalid expression
                error_clause = self._parse_form()
                clauses.append(error_clause)

        self._consume_rparen()

        # Return as a function call
        result = FunctionCall(func='cond', args=clauses, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result

    def _parse_cond_paren(self, line: int, col: int) -> FunctionCall:
        """Parse: (cond (condition1 expr...) (condition2 expr...) ...)
        Each clause must be a list starting with a condition.
        Validates that each clause follows correct syntax and reports E08 errors."""
        # Parse cond clauses
        clauses = []
        syntax_errors = []
        while self._current().type != 'RPAREN' and not self._is_eof():
            # Each clause must be a list: (condition expr1 expr2 ...)
            if self._current().type == 'LPAREN':
                clause_line, clause_col = self._current().line, self._current().col
                self._consume_lparen()

                # Parse the condition (first element in the clause)
                condition = self._parse_form()

                # Parse body expressions (remaining elements)
                body = []
                while self._current().type != 'RPAREN' and not self._is_eof():
                    body.append(self._parse_form())

                self._consume_rparen()

                # Create a list representing the clause
                clause = ListExpr(elements=[condition] + body, line=clause_line, col=clause_col)
                clauses.append(clause)
            else:
                # ERROR E08: clause is not wrapped in parentheses
                error_line = self._current().line

                # Record the syntax error (only once per line)
                if not syntax_errors or syntax_errors[-1]['line'] != error_line:
                    syntax_errors.append({
                        'line': error_line,
                        'message': 'invalid cond clause syntax: each clause must be (condition expr...)',
                        'code': None
                    })

                # Skip tokens until we find the next clause or the closing paren
                # Parse as a form to consume the invalid expression
                error_clause = self._parse_form()
                clauses.append(error_clause)

        self._consume_rparen()

        # Return as a function call
        result = FunctionCall(func='cond', args=clauses, line=line, col=col)
        result.syntax_errors = syntax_errors
        return result


# ============================================================================
# Pretty Printer for AST - LISP/SKILL Style
# ============================================================================

def ast_to_lisp(node: ASTNode, indent: int = 0) -> str:
    """Convert AST node to LISP-style string (like original SKILL code)"""
    prefix = "  " * indent

    if node is None:
        return "nil"

    if isinstance(node, Number):
        return str(node.value)

    elif isinstance(node, String):
        return f'"{node.value}"'

    elif isinstance(node, Symbol):
        return node.name

    elif isinstance(node, QuotedExpr):
        return f"'{ast_to_lisp(node.expr, 0)}"

    elif isinstance(node, FunctionDef):
        params_str = " ".join(node.params)
        body_lines = []
        for b in node.body:
            body_lines.append(ast_to_lisp(b, indent + 1))
        body_str = "\n".join(body_lines)

        return f"{prefix}({node.keyword} {node.name}({params_str})\n{body_str}\n{prefix})"

    elif isinstance(node, Let):
        # Format bindings
        bindings = []
        for var, val in node.bindings:
            if val is None:
                bindings.append(var)
            else:
                bindings.append(f"({var} {ast_to_lisp(val, 0)})")
        bindings_str = " ".join(bindings)

        # Format body
        body_lines = []
        for b in node.body:
            body_lines.append(ast_to_lisp(b, indent + 1))
        body_str = "\n".join(body_lines)

        return f"{prefix}({node.keyword} ({bindings_str})\n{body_str}\n{prefix})"

    elif isinstance(node, If):
        cond_str = ast_to_lisp(node.condition, 0)
        then_str = ast_to_lisp(node.then_expr, 0)

        if node.else_expr:
            else_str = ast_to_lisp(node.else_expr, 0)
            return f"{prefix}(if {cond_str}\n{prefix}  then {then_str}\n{prefix}  else {else_str}\n{prefix})"
        else:
            return f"{prefix}(if {cond_str}\n{prefix}  then {then_str}\n{prefix})"

    elif isinstance(node, When):
        cond_str = ast_to_lisp(node.condition, 0)
        body_lines = [ast_to_lisp(b, indent + 1) for b in node.body]
        body_str = "\n".join(body_lines)
        return f"{prefix}(when {cond_str}\n{body_str}\n{prefix})"

    elif isinstance(node, Unless):
        cond_str = ast_to_lisp(node.condition, 0)
        body_lines = [ast_to_lisp(b, indent + 1) for b in node.body]
        body_str = "\n".join(body_lines)
        return f"{prefix}(unless {cond_str}\n{body_str}\n{prefix})"

    elif isinstance(node, For):
        start_str = ast_to_lisp(node.start, 0)
        end_str = ast_to_lisp(node.end, 0)
        body_lines = [ast_to_lisp(b, indent + 1) for b in node.body]
        body_str = "\n".join(body_lines)
        return f"{prefix}(for {node.var} {start_str} {end_str}\n{body_str}\n{prefix})"

    elif isinstance(node, While):
        cond_str = ast_to_lisp(node.condition, 0)
        body_lines = [ast_to_lisp(b, indent + 1) for b in node.body]
        body_str = "\n".join(body_lines)
        return f"{prefix}(while {cond_str}\n{body_str}\n{prefix})"

    elif isinstance(node, Foreach):
        list_str = ast_to_lisp(node.list_expr, 0)
        body_lines = [ast_to_lisp(b, indent + 1) for b in node.body]
        body_str = "\n".join(body_lines)
        return f"{prefix}(foreach {node.var} {list_str}\n{body_str}\n{prefix})"

    elif isinstance(node, Setof):
        collection_str = ast_to_lisp(node.collection, 0)
        conditions_lines = [ast_to_lisp(c, 0) for c in node.conditions]
        conditions_str = " ".join(conditions_lines)
        return f"{prefix}(setof {node.var} {collection_str} {conditions_str})"

    elif isinstance(node, Lambda):
        params_str = " ".join(node.params)
        body_lines = [ast_to_lisp(b, indent + 1) for b in node.body]
        body_str = "\n".join(body_lines) if body_lines else ""
        return f"{prefix}(lambda ({params_str})\n{body_str}\n{prefix})"

    elif isinstance(node, FunctionCall):
        if not node.args:
            return f"{prefix}({node.func})"

        args_str = " ".join([ast_to_lisp(a, 0) for a in node.args])
        return f"{prefix}({node.func} {args_str})"

    elif isinstance(node, BinaryOp):
        left_str = ast_to_lisp(node.left, 0)
        right_str = ast_to_lisp(node.right, 0)
        return f"({node.op} {left_str} {right_str})"

    elif isinstance(node, Assignment):
        value_str = ast_to_lisp(node.value, 0)
        return f"{prefix}{node.var} = {value_str}"

    elif isinstance(node, PropertyAccess):
        obj_str = ast_to_lisp(node.obj, 0)
        return f"{obj_str}{node.op}{node.prop}"

    elif isinstance(node, ListExpr):
        if not node.elements:
            return "()"

        elements_str = " ".join([ast_to_lisp(e, 0) for e in node.elements])
        return f"({elements_str})"

    else:
        return str(node)


def print_ast_lisp(ast_list: List[ASTNode]):
    """Print AST in LISP/SKILL style"""
    for node in ast_list:
        print(ast_to_lisp(node, 0))
        print()  # Empty line between top-level forms


# ============================================================================
# File Collection and Verification
# ============================================================================

def collect_files(paths):
    """Collect all .il files from given paths (files and directories)"""
    files = []

    for path in paths:
        if os.path.isfile(path):
            files.append(path)
        elif os.path.isdir(path):
            # Recursively find all .il files
            for root, dirs, filenames in os.walk(path):
                for filename in filenames:
                    if filename.endswith('.il'):
                        files.append(os.path.join(root, filename))
        else:
            print_message("error", error_text=f"Path not found: {path}")

    return files


def verify_file(filepath, defined_variables=None, defined_functions=None, silent=False):
    """Verify a single file and return (error_count, error_list, source_code)

    Args:
        filepath: Path to the file to verify
        defined_variables: Set of predefined variables
        defined_functions: Set of predefined functions
        silent: If True, don't print messages (for desktop mode)
    """
    # Print info message (skip if silent mode)
    if not silent:
        print_message("info", error_text=f"verify {filepath}")

    # Parse
    ast, source_code, parsing_errors = parse_skill(filepath)

    if not ast:
        # Parsing failed, but we still have parsing errors to report
        parsing_error_count = len(parsing_errors)
        # Convert parsing errors to the format expected by all_errors
        formatted_parsing_errors = []
        for err in parsing_errors:
            formatted_parsing_errors.append({
                'type': 'error',
                'line': err.get('line'),
                'function': None,
                'message': err.get('message'),
                'code': err.get('code'),
                'error_code': err.get('error_code')
            })

        return parsing_error_count, formatted_parsing_errors, source_code

    # Verify
    verifier = Skillup(ast, filepath, source_code, defined_variables, defined_functions)
    errors, warnings = verifier.verify()

    # Print warnings (skip lines with [skillverify]ignore_line)
    for warning in warnings:
        warning_line = warning.get('line')
        # Skip warnings for lines marked with [skillverify]ignore_line
        if warning_line not in verifier.ignored_lines:
            if not silent:
                print_message(
                    "warn",
                    line=warning_line,
                    func_name=warning.get('function'),
                    error_text=warning.get('message'),
                    error_code=warning.get('code'),
                    code_id=warning.get('error_code')
                )

    # Print errors (skip lines with [skillverify]ignore_line)
    printed_errors = []
    for error in errors:
        error_line = error.get('line')
        # Skip errors for lines marked with [skillverify]ignore_line
        if error_line not in verifier.ignored_lines:
            if not silent:
                print_message(
                    "error",
                    line=error_line,
                    func_name=error.get('function'),
                    error_text=error.get('message'),
                    error_code=error.get('code'),
                    code_id=error.get('error_code')
                )
            printed_errors.append(error)

    # Combine warnings and errors
    all_issues = []
    for warning in warnings:
        warning_dict = {
            'type': 'warning',
            'line': warning.get('line'),
            'function': warning.get('function'),
            'message': warning.get('message'),
            'code': warning.get('code'),
            'error_code': warning.get('error_code')
        }
        all_issues.append(warning_dict)

    for error in printed_errors:
        error_dict = {
            'type': 'error',
            'line': error.get('line'),
            'function': error.get('function'),
            'message': error.get('message'),
            'code': error.get('code'),
            'error_code': error.get('error_code')
        }
        all_issues.append(error_dict)

    return len(printed_errors), all_issues, source_code


# ============================================================================
# Verifier - Check for errors
# ============================================================================

class Skillup:
    """Verify SKILL code for common errors"""

    # Built-in functions and operators that don't need to be declared
    BUILTINS = {
        # Functions
        'car', 'cdr', 'cons', 'list', 'append', 'length', 'null',
        'equal', 'eq', 'neq', 'plus', 'minus', 'times', 'quotient',
        'setq', 'and', 'or', 'not', 'print', 'println', 'printf',
        't', 'nil', 'then', 'else', 'return',
        'nthelem', 'strcat', 'sprintf', 'fprintf', 'evalstring', 'stringp',
        'floatp', 'simSetDef', 'simPrintMessage',
        'ncons', 'sqrt', 'spcRound', 'eqv', 'exit', 'load', 'prependInstallPath',
        'evalstring', 'strcat', 'argv', 'argc',
        # Conditional statements (treated as functions for now)
        'case', 'caseq', 'cond',
        # Other common functions
        'when', 'unless', 'nth',
        # Object-oriented programming
        'defclass', 'makeInstance',
        # Class definition keywords
        '@initarg', '@initform', '@reader', '@writer', '@accessor',
        # Operators
        '+', '-', '*', '/', '%',
        '==', '!=', '<', '>', '<=', '>=',
        '&&', '||', '!',
        '=',  # assignment
    }

    # Functions that take function parameters at specific positions
    # Maps function name to set of parameter indices that should be functions
    FUNCTION_PARAM_POSITIONS = {
        'funcall': {0},      # funcall(function, args...)
        'mapcar': {0},       # mapcar(function, list...)
        'mapc': {0},         # mapc(function, list...)
        'maplist': {0},      # maplist(function, list...)
        'apply': {0},        # apply(function, args)
        'filter': {0},       # filter(function, list)
        'sort': {1},         # sort(list, comparator)
    }

    def __init__(self, ast: List[ASTNode], filepath: str, source_code: str = None, defined_variables: Set[str] = None, defined_functions: Set[str] = None):
        self.ast = ast
        self.filepath = filepath
        self.errors = []
        self.warnings = []

        # Parse ignore_line comments from source
        self.ignored_lines = set()
        if source_code:
            self._parse_ignore_lines(source_code)

        # Defined names from define file (to skip undeclared errors)
        self.defined_variables = defined_variables if defined_variables else set()
        self.defined_functions = defined_functions if defined_functions else set()

        # Scope management
        self.scopes = []  # Stack of scopes
        self.current_function = None

        # Collect all function names first (for forward references)
        self.all_functions = set()
        self._collect_functions(ast)

        # Collect global variables (top-level assignments)
        self.global_variables = {}  # {var_name: line_number}
        self._collect_global_variables(ast)

    def _collect_functions(self, nodes: List[ASTNode]):
        """Collect all top-level function names"""
        for node in nodes:
            if isinstance(node, FunctionDef):
                self.all_functions.add(node.name)

    def _collect_global_variables(self, nodes: List[ASTNode]):
        """Collect all top-level assignments as global variable declarations"""
        for node in nodes:
            if isinstance(node, Assignment):
                # Top-level assignment is a global variable declaration
                if node.var and not node.var.startswith('<'):
                    self.global_variables[node.var] = node.line

    def _parse_ignore_lines(self, source_code: str):
        """Parse source code to find lines with [skillverify]ignore_line comment"""
        import re
        lines = source_code.split('\n')
        for line_num, line in enumerate(lines, start=1):
            # EXACT match: ; followed by optional whitespace, then [skillverify]ignore_line, then end of line or only whitespace
            # Matches: ; [skillverify]ignore_line or ;[skillverify]ignore_line
            # Does NOT match: ; a [skillverify]ignore_line or ; [skillverify]ignore_line a
            if re.search(r';\s*\[skillverify\]ignore_line\s*$', line):
                self.ignored_lines.add(line_num)

    def _push_scope(self):
        """Push a new scope onto the stack"""
        self.scopes.append({
            'variables': set(),
            'parameters': set(),
            'functions': set(),
        })

    def _pop_scope(self):
        """Pop the current scope"""
        if self.scopes:
            self.scopes.pop()

    def _add_variable(self, name: str):
        """Add a variable to the current scope"""
        if self.scopes:
            self.scopes[-1]['variables'].add(name)

    def _add_parameter(self, name: str):
        """Add a parameter to the current scope"""
        if self.scopes:
            self.scopes[-1]['parameters'].add(name)

    def _add_function(self, name: str):
        """Add a function to the current scope"""
        if self.scopes:
            self.scopes[-1]['functions'].add(name)

    def _is_declared(self, name: str, is_function: bool = False) -> bool:
        """Check if a name is declared (variable, parameter, function, or builtin)

        Args:
            name: The name to check
            is_function: If True, check function definitions; if False, check variable definitions
        """
        # Check builtins
        if name in self.BUILTINS:
            return True

        # Check defined names from define file based on context
        if is_function:
            if name in self.defined_functions:
                return True
        else:
            if name in self.defined_variables:
                return True

        # Check functions
        if name in self.all_functions:
            return True

        # Check all scopes (from innermost to outermost)
        for scope in reversed(self.scopes):
            if name in scope['variables'] or name in scope['parameters'] or name in scope['functions']:
                return True

        return False

    def _is_parameter(self, name: str) -> bool:
        """Check if a name is a parameter in parent scope"""
        # Check parent scopes for parameters
        if len(self.scopes) >= 2:
            # Check the parent scope (not current scope)
            for scope in reversed(self.scopes[:-1]):
                if name in scope['parameters']:
                    return True
        return False

    def _error(self, line: int, error_code: Code, code: str = None):
        """Add an error

        Args:
            line: Line number where error occurred
            error_code: Code enum value (e.g., Code.parameter_redeclaration or Code.E1)
            code: Optional code snippet showing the error context
        """
        self.errors.append({
            'line': line,
            'function': self.current_function,
            'message': error_code.message,
            'error_code': error_code.name,  # Store "E1", "W1", etc.
            'code': code
        })

    def _warn(self, line: int, error_code: Code, code: str = None):
        """Add a warning

        Args:
            line: Line number where warning occurred
            error_code: Code enum value (e.g., Code.undefined_function or Code.W1)
            code: Optional code snippet showing the warning context
        """
        self.warnings.append({
            'line': line,
            'function': self.current_function,
            'message': error_code.message,
            'error_code': error_code.name,  # Store "E1", "W1", etc.
            'code': code
        })

    def _contains_assignment(self, node: ASTNode) -> bool:
        """Check if a node or its children contain an assignment (=)"""
        if node is None:
            return False

        if isinstance(node, Assignment):
            return True

        # Check children for various node types
        if isinstance(node, BinaryOp):
            return self._contains_assignment(node.left) or self._contains_assignment(node.right)

        if isinstance(node, UnaryOp):
            return self._contains_assignment(node.operand)

        if isinstance(node, FunctionCall):
            return any(self._contains_assignment(arg) for arg in node.args)

        if isinstance(node, PropertyAccess):
            return self._contains_assignment(node.obj)

        if isinstance(node, List):
            return any(self._contains_assignment(item) for item in node.items)

        return False

    def verify(self):
        """Verify the AST"""
        for node in self.ast:
            self._verify_node(node)

        return self.errors, self.warnings

    def _verify_node(self, node: ASTNode, expect_function=False):
        """Verify a single node

        Args:
            node: The AST node to verify
            expect_function: If True, this node is expected to be a function reference
        """
        if node is None:
            return

        if isinstance(node, FunctionDef):
            self._verify_function(node)

        elif isinstance(node, Let):
            self._verify_let(node)

        elif isinstance(node, For):
            self._verify_for(node)

        elif isinstance(node, Foreach):
            self._verify_foreach(node)

        elif isinstance(node, Setof):
            self._verify_setof(node)

        elif isinstance(node, Lambda):
            self._verify_lambda(node)

        elif isinstance(node, While):
            self._verify_while(node)

        elif isinstance(node, If):
            self._verify_if(node)

        elif isinstance(node, When):
            self._verify_when(node)

        elif isinstance(node, Unless):
            self._verify_unless(node)

        elif isinstance(node, FunctionCall):
            self._verify_function_call(node)

        elif isinstance(node, Assignment):
            self._verify_assignment(node)

        elif isinstance(node, Symbol):
            self._verify_symbol(node, expect_function=expect_function)

        elif isinstance(node, PropertyAccess):
            # Only check the base object - it could be Symbol, PropertyAccess (chained), or FunctionCall
            self._verify_node(node.obj, expect_function=expect_function)

        elif isinstance(node, BinaryOp):
            # Verify both sides of the binary operation
            self._verify_node(node.left)
            self._verify_node(node.right)

        elif isinstance(node, ListExpr):
            for elem in node.elements:
                self._verify_node(elem)

    def _verify_function(self, node: FunctionDef):
        """Verify function definition"""
        # Report any syntax errors found during parsing
        if node.syntax_errors:
            for err in node.syntax_errors:
                # Map message to appropriate error code
                msg = err['message']
                if 'missing opening parenthesis' in msg:
                    error_code = Code.function_missing_paren
                elif '(name value) pair without @optional or @key' in msg:
                    error_code = Code.parameter_pair_without_key
                elif 'function parameter must be a symbol' in msg:
                    error_code = Code.parameter_not_symbol
                else:
                    error_code = Code.function_missing_paren  # default for function errors
                self._error(err['line'], error_code, err['code'])

        old_function = self.current_function
        self.current_function = node.name

        # Push new scope
        self._push_scope()

        # Add parameters to scope
        for param in node.params:
            self._add_parameter(param)

        # Verify body sequentially - nested functions must be defined before use
        for stmt in node.body:
            # If this is a nested function definition, add it to scope before continuing
            if isinstance(stmt, FunctionDef):
                self._add_function(stmt.name)
            # Then verify the statement
            self._verify_node(stmt)

        # Pop scope
        self._pop_scope()

        self.current_function = old_function

    def _verify_let(self, node: Let):
        """Verify let/prog binding"""
        # Report any syntax errors found during parsing
        if node.syntax_errors:
            for err in node.syntax_errors:
                # Map message to appropriate error code
                msg = err['message']
                if 'non-identifier in variable binding position' in msg:
                    error_code = Code.non_identifier_in_binding
                elif 'constant (number or string) in variable name position' in msg:
                    error_code = Code.constant_in_variable_position
                else:
                    error_code = Code.non_identifier_in_binding  # default for let/prog errors
                self._error(err['line'], error_code, err['code'])

        # Push new scope
        self._push_scope()

        # Add variables to scope and check for parameter redeclaration
        for var, init_val in node.bindings:
            # Check if this variable is a parameter in parent scope
            if self._is_parameter(var):
                self._error(node.line, Code.parameter_redeclaration, var)

            self._add_variable(var)

            # Verify initialization value
            if init_val:
                self._verify_node(init_val)

        # Verify body
        for stmt in node.body:
            self._verify_node(stmt)

        # Pop scope
        self._pop_scope()

    def _verify_for(self, node: For):
        """Verify for loop"""
        # Verify start and end BEFORE adding loop variable to scope
        # (loop variable is not in scope for start/end expressions)
        self._verify_node(node.start)
        self._verify_node(node.end)

        # Push new scope
        self._push_scope()

        # Add loop variable
        if node.var:
            self._add_variable(node.var)

        # Verify body
        for stmt in node.body:
            self._verify_node(stmt)

        # Pop scope
        self._pop_scope()

    def _verify_foreach(self, node: Foreach):
        """Verify foreach loop"""
        # Verify list expression BEFORE adding loop variable to scope
        # (loop variable is not in scope for list expression)
        self._verify_node(node.list_expr)

        # Push new scope
        self._push_scope()

        # Add loop variable
        if node.var:
            self._add_variable(node.var)

        # Verify body
        for stmt in node.body:
            self._verify_node(stmt)

        # Pop scope
        self._pop_scope()

    def _verify_setof(self, node: Setof):
        """Verify setof loop"""
        # Verify collection expression BEFORE adding loop variable to scope
        # (loop variable is not in scope for collection expression)
        self._verify_node(node.collection)

        # Push new scope
        self._push_scope()

        # Add loop variable
        if node.var:
            self._add_variable(node.var)

        # Verify condition expressions and check for assignment
        for cond in node.conditions:
            if self._contains_assignment(cond):
                self._warn(node.line, Code.assignment_in_condition, "=")
            self._verify_node(cond)

        # Pop scope
        self._pop_scope()

    def _verify_lambda(self, node: Lambda):
        """Verify lambda function"""
        # Report any syntax errors found during parsing
        if node.syntax_errors:
            for err in node.syntax_errors:
                # Map message to appropriate error code
                msg = err['message']
                if 'function parameter must be a symbol' in msg:
                    error_code = Code.parameter_not_symbol
                else:
                    error_code = Code.parameter_not_symbol  # default
                self._error(err['line'], error_code, err['code'])

        # Push new scope
        self._push_scope()

        # Add parameters as local variables
        for param in node.params:
            self._add_variable(param)

        # Verify body
        for stmt in node.body:
            self._verify_node(stmt)

        # Pop scope
        self._pop_scope()

    def _verify_while(self, node: While):
        """Verify while loop"""
        # Check for assignment in condition
        if self._contains_assignment(node.condition):
            self._warn(node.line, Code.assignment_in_condition, "=")

        # Verify condition
        self._verify_node(node.condition)

        # Verify body (while doesn't create new scope for variables)
        for stmt in node.body:
            self._verify_node(stmt)

    def _verify_if(self, node: If):
        """Verify if statement"""
        # Report any syntax errors found during parsing
        if node.syntax_errors:
            for err in node.syntax_errors:
                # Determine the correct error code based on the message
                if "multiple expressions require 'then' or 'else'" in err['message']:
                    error_code = Code.if_missing_then_else
                else:
                    error_code = Code.syntax_error
                self._error(err['line'], error_code, err.get('code'))

        # Check for assignment in condition
        if self._contains_assignment(node.condition):
            self._warn(node.line, Code.assignment_in_condition, "=")

        self._verify_node(node.condition)
        self._verify_node(node.then_expr)
        if node.else_expr:
            self._verify_node(node.else_expr)

    def _verify_when(self, node: When):
        """Verify when statement"""
        # Check for assignment in condition
        if self._contains_assignment(node.condition):
            self._warn(node.line, Code.assignment_in_condition, "=")

        self._verify_node(node.condition)
        for stmt in node.body:
            self._verify_node(stmt)

    def _verify_unless(self, node: Unless):
        """Verify unless statement"""
        # Check for assignment in condition
        if self._contains_assignment(node.condition):
            self._warn(node.line, Code.assignment_in_condition, "=")

        self._verify_node(node.condition)
        for stmt in node.body:
            self._verify_node(stmt)

    def _verify_function_call(self, node: FunctionCall):
        """Verify function call"""
        # Report any syntax errors found during parsing
        if node.syntax_errors:
            for err in node.syntax_errors:
                # Map message to appropriate error code
                msg = err['message']
                if 'non-identifier in variable binding position' in msg:
                    error_code = Code.non_identifier_in_binding
                elif 'constant (number or string) in variable name position' in msg:
                    error_code = Code.constant_in_variable_position
                elif 'invalid cond clause syntax' in msg:
                    error_code = Code.invalid_cond_clause
                else:
                    error_code = Code.non_identifier_in_binding  # default
                self._error(err['line'], error_code, err['code'])

        # Skip verification of defclass - it has special syntax
        if node.func == 'defclass':
            return

        # Special handling for case and caseq
        # In both case and caseq, the first argument (the value being tested) is verified normally
        # The remaining arguments are clauses (pattern body...) which are already parsed specially
        if node.func in ('case', 'caseq'):
            # Verify the value being tested
            if node.args:
                self._verify_node(node.args[0])
            # Verify the clause bodies (patterns are already handled during parsing)
            for clause in node.args[1:]:
                # Each clause is a ListExpr with QuotedExpr pattern (for caseq) or normal expr (for case)
                # We just verify the entire clause
                self._verify_node(clause)
            return

        # Special handling for cond
        # Each argument is a clause (condition body...)
        if node.func == 'cond':
            # Verify each clause
            for clause in node.args:
                self._verify_node(clause)
            return

        # Check if function is declared
        # Skip <complex> placeholder - these are complex expressions that can't be analyzed
        if node.func != '<complex>' and not self._is_declared(node.func, is_function=True):
            self._warn(node.line, Code.undefined_function, node.func)

        # Verify arguments
        # Check if this function has positions that expect function parameters
        func_param_positions = self.FUNCTION_PARAM_POSITIONS.get(node.func, set())
        for i, arg in enumerate(node.args):
            expect_function = i in func_param_positions
            self._verify_node(arg, expect_function=expect_function)

    def _verify_assignment(self, node: Assignment):
        """Verify assignment"""
        # Check if the variable being assigned to is declared
        # In SKILL, variables should be declared with let/prog before use
        # Simple variable names should be checked (not complex expressions like "array[0]" or property access)
        if node.var and not node.var.startswith('<') and '[' not in node.var and '.' not in node.var and 'PropertyAccess(' not in node.var:
            # Check if this is a variable (not just any declared name like a function)
            is_variable = False

            # Check builtins
            if node.var in self.BUILTINS:
                is_variable = True

            # Check defined variables from define file (NOT functions)
            if node.var in self.defined_variables:
                is_variable = True

            # Check if it's a global variable declared before this line
            if node.var in self.global_variables:
                global_decl_line = self.global_variables[node.var]
                # Global variable is available at or after its declaration line
                if node.line >= global_decl_line:
                    is_variable = True

            # Check all scopes for variables/parameters (NOT functions)
            for scope in reversed(self.scopes):
                if node.var in scope['variables'] or node.var in scope['parameters']:
                    is_variable = True
                    break

            if not is_variable:
                self._warn(node.line, Code.undeclared_variable, node.var)

        # Verify the value being assigned
        self._verify_node(node.value)

    def _verify_symbol(self, node, expect_function=False):
        """Verify symbol (variable reference)

        Args:
            node: The Symbol node to verify
            expect_function: If True, this symbol is expected to be a function reference
        """
        if isinstance(node, Symbol):
            # Skip placeholder symbols created during error recovery
            if node.name in ['<error>', '<recursion-limit>', '<complex>']:
                return
            # Skip keyword arguments (parameter names starting with ?)
            # These are not variables but parameter names in function calls
            if node.name.startswith('?'):
                return

            # Check if it's a global variable declared before this line
            if node.name in self.global_variables:
                global_decl_line = self.global_variables[node.name]
                # Global variable is available after its declaration line
                if node.line >= global_decl_line:
                    return  # Valid reference to global variable

            # Check if variable is declared (in scopes, builtins, or functions)
            if not self._is_declared(node.name, is_function=expect_function):
                # Report the appropriate error type based on context
                if expect_function:
                    self._warn(node.line, Code.undefined_function, node.name)
                else:
                    self._warn(node.line, Code.undeclared_variable, node.name)


# ============================================================================
# Output Formatting
# ============================================================================

# ============================================================================
# Configuration Management
# ============================================================================

def get_config_home():
    """
    Get the configuration directory path.

    Priority:
    1. SKILLUP_CONFIG_HOME environment variable
    2. XDG_CONFIG_HOME/skillup
    3. ~/.config/skillup (default)

    Returns:
        str: Absolute path to config directory
    """
    # Check SKILLUP_CONFIG_HOME first
    config_home = os.environ.get('SKILLUP_CONFIG_HOME')
    if config_home:
        return os.path.expanduser(config_home)

    # Check XDG_CONFIG_HOME
    xdg_config = os.environ.get('XDG_CONFIG_HOME')
    if xdg_config:
        return os.path.join(os.path.expanduser(xdg_config), 'skillup')

    # Default to ~/.config/skillup
    return os.path.expanduser('~/.config/skillup')


# ============================================================================
# Color Output Utilities
# ============================================================================

class Color:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'


def print_message(msg_type: str, line: int = None, func_name: str = None,
                  error_text: str = None, error_code: str = None, code_id: str = None,
                  return_string: bool = False):
    """Print formatted colored message

    Args:
        msg_type: Type of message (info, warn, error)
        line: Line number
        func_name: Function name where error occurred
        error_text: Error message text
        error_code: Code snippet showing error context
        code_id: Error code identifier (E1, W1, etc.)
        return_string: If True, return the formatted string instead of printing
    """
    if msg_type == "info":
        prefix_color = Color.GREEN
    elif msg_type == "warn":
        prefix_color = Color.YELLOW
    else:  # error
        prefix_color = Color.RED

    output = f"{prefix_color}[{msg_type:5s}]{Color.RESET}"

    # Format and colorize code_id (e.g., "W1" -> "[W01]" in yellow, "E1" -> "[E01]" in red)
    if code_id is not None:
        # Extract letter and number (e.g., "W1" -> "W", "1")
        code_letter = code_id[0] if code_id else ""
        code_number = code_id[1:] if len(code_id) > 1 else ""

        # Format number with leading zero (e.g., "1" -> "01")
        formatted_code = f"{code_letter}{code_number.zfill(2)}"

        # Color based on error type (W = yellow, E = red)
        if code_letter == 'W':
            code_color = Color.YELLOW
        else:  # E
            code_color = Color.RED

        output += f"{code_color}[{formatted_code}]{Color.RESET} "

    if line is not None:
        output += f"line {Color.YELLOW}{line}{Color.RESET}, "

    if func_name is not None:
        output += f"in function {Color.YELLOW}{func_name}{Color.RESET}, "

    if error_text is not None:
        output += f"{error_text}"
        if error_code is not None:
            output += f", {Color.RED}{error_code}{Color.RESET}"

    if return_string:
        return output
    else:
        print(output)


# ============================================================================
# Main Function
# ============================================================================

def parse_skill(filepath: str):
    """Parse SKILL file and return (AST, source_code, parsing_errors)"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
    except FileNotFoundError:
        print_message("error", error_text=f"File not found: {filepath}")
        return None, None, []
    except Exception as e:
        print_message("error", error_text=f"Error reading file: {e}")
        return None, None, []

    # Tokenize
    tokenizer = Tokenizer(code)
    tokens = tokenizer.tokenize()

    # Parse
    parser = Parser(tokens)
    ast = parser.parse()

    return ast, code, parser.parsing_errors
