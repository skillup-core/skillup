"""
SKILL Code Debug Transformer

Transforms SKILL code by inserting conditional breakpoints into procedure bodies.
This enables line-by-line debugging without requiring a debug license.

Strategy:
  Original code:
    procedure(aaa()
    let((a b c)
        a = 10
        printf("a => %L\n" a)
        b = 20
    ))

  Transformed code (each statement in procedure body gets a conditional break):
    procedure(aaa()
    let((a b c)
        when(member(3 __sbk_bp) _sbDbgBreak(3))
        a = 10
        when(member(4 __sbk_bp) _sbDbgBreak(4))
        printf("a => %L\n" a)
        when(member(5 __sbk_bp) _sbDbgBreak(5))
        b = 20
    ))

  _sbDbgBreak(N) notifies Python of the break line, then polls __sbk_cmd
  (via ipcSleep) until Python sends "continue" or "quit" via debug_continue/debug_quit.
  Variable evaluation uses the normal execute path (no special eval channel).

  The line numbers correspond to the ORIGINAL source line numbers (1-based).
  __sbk_bp  = global list of active breakpoint lines
  __sbk_ln  = global current stopped line number
"""

import re


def _strip_block_comments(lines: list) -> list:
    """Replace /* ... */ block comment content with spaces, preserving line count.

    Newlines inside a block comment are kept so that all 1-based line numbers
    remain identical to the original source.  Every other character inside the
    comment (including parentheses) is replaced with a space so that the paren-
    depth scanner is not confused by code inside comments.

    Handles nested /* */ comments (SKILL supports them).
    """
    result = []
    depth = 0      # block-comment nesting depth
    in_string = False

    for line in lines:
        out = []
        i = 0
        while i < len(line):
            ch = line[i]

            if in_string:
                if ch == '\\' and i + 1 < len(line):
                    out.append(ch)
                    out.append(line[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    in_string = False
                out.append(ch)
                i += 1
                continue

            if depth > 0:
                # Inside a block comment — suppress all content except newlines
                # and watch for nested /* or closing */
                if ch == '/' and i + 1 < len(line) and line[i + 1] == '*':
                    depth += 1
                    out.append(' ')
                    out.append(' ')
                    i += 2
                    continue
                if ch == '*' and i + 1 < len(line) and line[i + 1] == '/':
                    depth -= 1
                    out.append(' ')
                    out.append(' ')
                    i += 2
                    continue
                # Replace any character with a space (preserve length for column
                # accuracy is not required, but keep it consistent)
                out.append(' ')
                i += 1
                continue

            # Not inside a block comment
            if ch == ';':
                # Line comment: keep as-is (rest of line is already ignored by parser)
                out.append(line[i:])
                break

            if ch == '"':
                in_string = True
                out.append(ch)
                i += 1
                continue

            if ch == '/' and i + 1 < len(line) and line[i + 1] == '*':
                depth += 1
                out.append(' ')
                out.append(' ')
                i += 2
                continue

            out.append(ch)
            i += 1

        result.append(''.join(out))

    return result


def transform_for_debug(source: str, breakpoint_lines: list = None, file_id: int = 0) -> dict:
    """Transform SKILL source code for debugging.

    Args:
        source: Original SKILL source code
        breakpoint_lines: List of 1-based line numbers for initial breakpoints.
                         If None or empty, breaks on every line (step mode).
        file_id: Integer file identifier for multi-file debugging.

    Returns:
        dict with keys:
            'code': Transformed SKILL code ready to send to Virtuoso
            'setup': SKILL setup code to run BEFORE the main code
            'line_map': dict mapping transformed line -> original line
            'total_lines': total number of original source lines
            'procedure_ranges': list of {name, start_line, end_line} for each procedure
            'insertable_lines': sorted list of insertable line numbers
    """
    lines = source.split('\n')
    total_lines = len(lines)

    # Strip /* */ block comments before parsing so that parentheses and keywords
    # inside comments do not confuse the paren-depth scanner.  Line count is
    # preserved so that all 1-based line numbers remain correct.
    parse_lines = _strip_block_comments(lines)

    # Parse procedure boundaries
    procedures = _find_procedures(parse_lines)

    if not procedures:
        # No procedures found - return as-is (can't debug non-procedure code)
        return {
            'code': source,
            'setup': '',
            'line_map': {i+1: i+1 for i in range(total_lines)},
            'total_lines': total_lines,
            'procedure_ranges': [],
            'insertable_lines': [],
        }

    # Find all insertable line positions (lines inside procedure bodies that are statements)
    insertable = _find_insertable_lines(parse_lines, procedures)

    # Build transformed code
    transformed_lines = []
    line_map = {}  # transformed_line_num -> original_line_num
    t_line = 0

    for orig_idx, line in enumerate(lines):
        orig_line_num = orig_idx + 1  # 1-based

        if orig_line_num in insertable:
            # Insert breakpoint guard BEFORE this line
            t_line += 1
            bp_code = f'when(member({orig_line_num} __sbk_bp_{file_id}) _sbDbgBreak({orig_line_num} {file_id}))'
            indent = _get_indent(line)
            transformed_lines.append(indent + bp_code)
            line_map[t_line] = orig_line_num  # breakpoint line maps to original

        t_line += 1
        transformed_lines.append(line)
        line_map[t_line] = orig_line_num

    transformed_code = '\n'.join(transformed_lines)

    # Build setup code (per-file breakpoint variable)
    if breakpoint_lines:
        bp_list = ' '.join(str(n) for n in sorted(breakpoint_lines))
        setup = f'__sbk_bp_{file_id} = list({bp_list})\n__sbk_ln = 0\n__sbk_fid = 0'
    else:
        # No breakpoints: run to completion without stopping
        setup = f'__sbk_bp_{file_id} = nil\n__sbk_ln = 0\n__sbk_fid = 0'

    return {
        'code': transformed_code,
        'setup': setup,
        'line_map': line_map,
        'total_lines': total_lines,
        'procedure_ranges': [
            {'name': p['name'], 'start_line': p['start_line'], 'end_line': p['end_line']}
            for p in procedures
        ],
        'insertable_lines': sorted(insertable),
    }


def _find_procedures(lines: list) -> list:
    """Find procedure definitions and their body ranges.

    Returns list of dicts with:
        name: procedure name
        start_line: 1-based line of 'procedure('
        body_start_line: 1-based line where body statements begin
        end_line: 1-based line of closing ')'
        paren_depth_at_body: paren depth at body start
    """
    procedures = []

    # Pattern for procedure definition: procedure(name(args)
    # Also handles: procedure(name(args) or mprocedure, nprocedure, etc.
    proc_pattern = re.compile(
        r'^(\s*)(procedure|mprocedure|nprocedure)\s*\(\s*(\w+)\s*\(',
        re.IGNORECASE
    )

    i = 0
    while i < len(lines):
        line = lines[i]
        m = proc_pattern.match(line)
        if m:
            proc_name = m.group(3)
            proc_start = i + 1  # 1-based

            # Find the body start: after the argument list and optional let/prog
            body_start, paren_depth_at_body = _find_body_start(lines, i)

            # Find the end of the procedure by tracking paren depth
            proc_end = _find_procedure_end(lines, i)

            if body_start and proc_end:
                procedures.append({
                    'name': proc_name,
                    'start_line': proc_start,
                    'body_start_line': body_start,
                    'end_line': proc_end,
                    'paren_depth_at_body': paren_depth_at_body,
                })

        i += 1

    return procedures


def _find_body_start(lines: list, proc_line_idx: int) -> tuple:
    """Find where the procedure body statements begin.

    Handles two cases:
      1. procedure(name(args) let((vars) BODY ))  — body after variable list
      2. procedure(name(args) BODY )               — body right after args

    Returns (1-based line number, paren depth at that point) or (None, 0).
    """
    text = '\n'.join(lines[proc_line_idx:])
    depth = 0
    i = 0
    in_string = False
    args_closed = False  # True after args list ')' is found (depth 2->1)

    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if ch == ';':
            while i < len(text) and text[i] != '\n':
                i += 1
            continue

        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            # depth 2->1 means args list just closed: procedure(name(args) <here>
            if depth == 1 and not args_closed:
                args_closed = True
                i += 1
                # Check if let/letseq/letrec/prog follows
                remaining = text[i:].lstrip()
                if remaining.startswith(('let(', 'letseq(', 'letrec(', 'prog(')):
                    # Structure: let( (vars) body )
                    # Skip whitespace + keyword to reach let's '('
                    j = i
                    while j < len(text) and text[j] in ' \t\n':
                        j += 1
                    while j < len(text) and text[j] != '(':
                        j += 1
                    if j < len(text):
                        j += 1  # skip let's '('
                        # Now find the variable list '(' and its matching ')'
                        # Skip whitespace to reach '(' of variable list
                        while j < len(text) and text[j] in ' \t\n':
                            j += 1
                        if j < len(text) and text[j] == '(':
                            # Find matching ')' for variable list: ((a b c)) or (a b c)
                            vd = 1
                            j += 1  # skip '('
                            while j < len(text) and vd > 0:
                                if text[j] == '(':
                                    vd += 1
                                elif text[j] == ')':
                                    vd -= 1
                                j += 1
                        # j is past variable list ')' — body starts on the NEXT line
                        body_line = proc_line_idx + text[:j].count('\n') + 1
                        while body_line < len(lines) and not _is_statement_line(lines[body_line].strip()):
                            body_line += 1
                        if body_line < len(lines):
                            actual_depth = _count_paren_depth(lines, proc_line_idx, body_line + 1)
                            return body_line + 1, actual_depth
                    return None, 0
                else:
                    # No let/prog — body starts on the NEXT line after args close
                    body_line = proc_line_idx + text[:i].count('\n') + 1
                    while body_line < len(lines) and not _is_statement_line(lines[body_line].strip()):
                        body_line += 1
                    if body_line < len(lines):
                        actual_depth = _count_paren_depth(lines, proc_line_idx, body_line + 1)
                        return body_line + 1, actual_depth
                    return None, 0

        i += 1

    return None, 0


def _is_statement_line(stripped: str) -> bool:
    """Check if a stripped line looks like an executable statement."""
    if not stripped:
        return False
    # Skip closing parens only
    if all(c in ')( \t' for c in stripped):
        return False
    # Skip comment-only lines
    if stripped.startswith(';'):
        return False
    return True


def _find_procedure_end(lines: list, proc_line_idx: int) -> int:
    """Find the closing line of a procedure definition.

    Returns 1-based line number of the line containing the final ')'.
    """
    depth = 0
    in_string = False

    for i in range(proc_line_idx, len(lines)):
        line = lines[i]
        j = 0
        while j < len(line):
            ch = line[j]
            if in_string:
                if ch == '\\' and j + 1 < len(line):
                    j += 2
                    continue
                if ch == '"':
                    in_string = False
                j += 1
                continue

            if ch == '"':
                in_string = True
                j += 1
                continue

            if ch == ';':
                break  # rest is comment

            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return i + 1  # 1-based

            j += 1

    return None


def _count_paren_depth(lines: list, start_idx: int, end_line: int) -> int:
    """Count paren depth from start_idx to end_line (1-based, exclusive)."""
    depth = 0
    in_string = False
    for i in range(start_idx, min(end_line - 1, len(lines))):
        line = lines[i]
        j = 0
        while j < len(line):
            ch = line[j]
            if in_string:
                if ch == '\\' and j + 1 < len(line):
                    j += 2
                    continue
                if ch == '"':
                    in_string = False
                j += 1
                continue
            if ch == '"':
                in_string = True
                j += 1
                continue
            if ch == ';':
                break
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            j += 1
    return depth


def _find_insertable_lines(lines: list, procedures: list) -> set:
    """Find all line numbers (1-based) where breakpoint guards can be inserted.

    A line is insertable if it is a top-level statement in a procedure body
    (or in the body portion of a special form like for/foreach/while/etc.).
    Non-body arguments of special forms are excluded.
    """
    insertable = set()

    for proc in procedures:
        body_start = proc['body_start_line']
        end_line = proc['end_line']

        if not body_start or not end_line:
            continue

        proc_start_idx = proc['start_line'] - 1
        base_depth = _count_paren_depth(lines, proc_start_idx, body_start)

        ctx = _ScanCtx(lines, end_line - 1)
        ctx.scan_body(body_start - 1, 0, base_depth, insertable)

    return insertable


# Special forms: number of leading args that are NOT body statements.
_SPECIAL_FORM_SKIP = {
    'for':     3,  # for(var init limit body...)
    'foreach': 2,  # foreach(var collection body...)
    'setof':   2,  # setof(var collection body...)
    'while':   1,  # while(cond body...)
    'until':   1,  # until(cond body...)
    'when':    1,  # when(cond body...)
    'unless':  1,  # unless(cond body...)
    # 'if' is NOT in this table — handled as a plain expression (no body descent).
    # if(cond then-expr [else-expr]) has no safe breakpoint insertion points inside.
    # 'cond' is NOT in this table — handled by _scan_cond.
    'let':     1,  # let((vars) body...)
    'letseq':  1,  # letseq((vars) body...)
    'letrec':  1,  # letrec((vars) body...)
    'prog':    1,  # prog((vars) body...)
    'lambda':  1,  # lambda((vars) body...)
    'begin':   0,  # begin(body...)
}

# Forms where the body is exactly ONE expression (bare atoms not breakpointable).
# skip_count: number of leading non-body args to skip.
# If the single body expr is a paren-group (begin/let/prog/etc.), descend into it.
# If it is a bare atom/expression (e.g. x > 3), skip without inserting a breakpoint.
_SINGLE_BODY_FORM_SKIP = {
    'exists':  2,  # exists(var collection expr) — body must be single expr
    'forall':  2,  # forall(var collection expr) — body must be single expr
}


class _ScanCtx:
    """Character-level scanner for SKILL source lines."""

    def __init__(self, lines: list, hard_end: int):
        self.lines = lines
        self.hard_end = hard_end  # exclusive line index upper bound

    # ------------------------------------------------------------------
    # Public entry: collect insertable statement lines in a body range.
    # start_li / start_ci : position of first char to scan (0-based line/col)
    # base_depth           : paren depth at which top-level statements live
    # insertable           : set to collect 1-based line numbers into
    # Returns (li, ci) just after the last consumed character.
    # ------------------------------------------------------------------
    def scan_body(self, start_li, start_ci, base_depth, insertable):
        """Scan statements at base_depth and add their start lines to insertable.

        Handles two kinds of top-level statements:
        1. Paren-expressions: special forms (for/foreach/while/...) and regular calls.
        2. Bare statements: assignments (x = 10), atoms used as statements.

        For paren-expressions at depth==base_depth, the identifier BEFORE '(' is the
        form name (SKILL syntax: for(... not (for ...)).
        """
        li, ci = start_li, start_ci
        in_string = False
        depth = base_depth
        last_ident = None  # last identifier read (for recognising special forms)
        stmt_started = False  # True when we've started a top-level statement
        after_assign = False  # True after '=' operator — suppress stmt reset at EOL

        while li < self.hard_end:
            line = self.lines[li]
            while ci < len(line):
                ch = line[ci]

                if in_string:
                    if ch == '\\' and ci + 1 < len(line):
                        ci += 2; continue
                    if ch == '"':
                        in_string = False
                    ci += 1; continue

                if ch == '"':
                    in_string = True
                    if depth == base_depth and not stmt_started:
                        stripped = line.strip()
                        if stripped and not stripped.startswith(';'):
                            insertable.add(li + 1)
                        stmt_started = True
                    after_assign = False
                    last_ident = None; ci += 1; continue

                if ch == ';':
                    break  # rest of line is comment

                if ch in ' \t':
                    ci += 1; continue

                if ch == '(':
                    if depth == base_depth:
                        # A paren-expression starts (or continues after an identifier).
                        form = last_ident
                        skip = _SPECIAL_FORM_SKIP.get(form) if form else None
                        single_skip = _SINGLE_BODY_FORM_SKIP.get(form) if form else None
                        if not stmt_started:
                            # Mark statement start (the identifier before '(' or this line)
                            stmt_li = li  # '(' is on this line; identifier may be earlier
                            # Find the line the identifier was on (last_ident_li tracking
                            # would be complex; just use current line — good enough since
                            # SKILL keywords are always on the same line as their '(')
                            stripped = self.lines[stmt_li].strip()
                            if stripped and not stripped.startswith(';') and \
                                    not all(c in ') \t' for c in stripped):
                                insertable.add(stmt_li + 1)
                            stmt_started = True
                        if form == 'if':
                            # if(cond [then] expr1 [else] expr2): special handling
                            li, ci, in_string = self._scan_if(
                                li, ci + 1, depth + 1, insertable)
                            depth = base_depth
                            last_ident = None
                            stmt_started = False
                            line = self.lines[li] if li < self.hard_end else ''
                            continue
                        elif form in ('cond', 'case', 'caseq', 'casev'):
                            # cond/case(clause1 clause2 ...) where each clause is ((val) body...)
                            li, ci, in_string = self._scan_cond(
                                li, ci + 1, depth + 1, insertable)
                            depth = base_depth
                            last_ident = None
                            stmt_started = False
                            line = self.lines[li] if li < self.hard_end else ''
                            continue
                        elif skip is not None:
                            # Special form: skip leading non-body args, then recurse
                            li, ci, in_string = self._scan_special(
                                li, ci + 1, depth + 1, skip, insertable)
                            depth = base_depth
                            last_ident = None
                            stmt_started = False
                            line = self.lines[li] if li < self.hard_end else ''
                            continue
                        elif single_skip is not None:
                            # Single-body form: skip leading args, descend into paren body only
                            li, ci, in_string = self._scan_special(
                                li, ci + 1, depth + 1, single_skip, insertable,
                                max_body=1)
                            depth = base_depth
                            last_ident = None
                            stmt_started = False
                            line = self.lines[li] if li < self.hard_end else ''
                            continue
                        else:
                            depth += 1
                            last_ident = None
                    else:
                        # depth > base_depth: inside a regular paren-expression.
                        # Still descend into lambda/cond/case/special forms found here.
                        nested_skip = _SPECIAL_FORM_SKIP.get(last_ident) if last_ident else None
                        nested_single_skip = _SINGLE_BODY_FORM_SKIP.get(last_ident) if last_ident else None
                        if last_ident == 'if':
                            li, ci, in_string = self._scan_if(
                                li, ci + 1, depth + 1, insertable)
                            line = self.lines[li] if li < self.hard_end else ''
                            last_ident = None
                            continue
                        elif last_ident in ('cond', 'case', 'caseq', 'casev'):
                            li, ci, in_string = self._scan_cond(
                                li, ci + 1, depth + 1, insertable)
                            line = self.lines[li] if li < self.hard_end else ''
                            last_ident = None
                            continue
                        elif nested_skip is not None:
                            li, ci, in_string = self._scan_special(
                                li, ci + 1, depth + 1, nested_skip, insertable)
                            line = self.lines[li] if li < self.hard_end else ''
                            last_ident = None
                            continue
                        elif nested_single_skip is not None:
                            li, ci, in_string = self._scan_special(
                                li, ci + 1, depth + 1, nested_single_skip, insertable,
                                max_body=1)
                            line = self.lines[li] if li < self.hard_end else ''
                            last_ident = None
                            continue
                        else:
                            depth += 1
                            last_ident = None

                elif ch == ')':
                    depth -= 1
                    last_ident = None
                    if depth == base_depth:
                        # Closed a paren-expression — statement is done
                        stmt_started = False
                        after_assign = False
                    elif depth < base_depth:
                        return li, ci + 1  # exited our scope

                elif ch.isalpha() or ch == '_':
                    # Identifier token
                    end = ci
                    while end < len(line) and (line[end].isalnum() or line[end] == '_'):
                        end += 1
                    token = line[ci:end].lower()
                    if depth == base_depth and not stmt_started:
                        # First token of a new statement
                        stripped = line.strip()
                        if stripped and not stripped.startswith(';') and \
                                not all(c in ') \t' for c in stripped):
                            insertable.add(li + 1)
                        stmt_started = True
                    last_ident = token
                    ci = end
                    continue

                else:
                    # Non-alpha, non-paren character (digit, operator, etc.)
                    if ch == '=' and depth == base_depth:
                        # SKILL infix assignment operator: LHS = RHS
                        # '=' continues the current statement — do NOT start a new one,
                        # and suppress stmt_started reset at EOL so RHS on next line(s)
                        # is not treated as a new statement.
                        stmt_started = True  # ensure we stay in-statement
                        after_assign = True
                    else:
                        if depth == base_depth and not stmt_started:
                            stripped = line.strip()
                            if stripped and not stripped.startswith(';') and \
                                    not all(c in ') \t' for c in stripped):
                                insertable.add(li + 1)
                            stmt_started = True
                        after_assign = False
                    last_ident = None

                ci += 1

            li += 1; ci = 0; last_ident = None
            # When we start a new line at base_depth, the previous bare statement
            # (like `x = 10`) has ended — reset stmt_started so the next identifier
            # on the new line can be recognised as a new statement start.
            # Exception: after '=' operator, RHS may span multiple lines — keep stmt alive.
            if depth == base_depth and not after_assign:
                stmt_started = False

        return li, ci

    # ------------------------------------------------------------------
    # Scan inside an if() form.  Positioned just after the opening '('.
    # Structure: if(cond [then] then-expr [else] else-expr)
    # 'then' and 'else' are optional keywords that MUST NOT have a
    # breakpoint inserted before them.  Breakpoints go before the
    # then-expr and else-expr only when they are on their own line.
    # Returns (li, ci, in_string) just AFTER the closing ')'.
    # ------------------------------------------------------------------
    def _scan_if(self, start_li, start_ci, form_depth, insertable):
        """Scan inside an if() form, positioned just after the opening '('.

        Rules:
        - 'then' keyword seen  → then-expr gets a breakpoint
        - 'else' keyword seen  → else-expr gets a breakpoint
        - No keyword (bare expr) → NO breakpoint (e.g. if(cond expr) or
          if(cond then-expr else-expr) without keywords)
        Returns (li, ci, in_string) just after the closing ')'.
        """
        li, ci = start_li, start_ci
        in_string = False
        cond_li = li  # line where cond expression ends (to detect same-line exprs)

        # States: 'cond' -> 'then_expr' -> 'else_expr'
        state = 'cond'
        then_keyword_seen = False  # 'then' keyword was explicitly present
        else_keyword_seen = False  # 'else' keyword was explicitly present
        then_keyword_li = -1       # line index where 'then' keyword appeared
        else_keyword_li = -1       # line index where 'else' keyword appeared
        last_ident = None

        while li < self.hard_end:
            line = self.lines[li]
            while ci < len(line):
                ch = line[ci]

                if in_string:
                    if ch == '\\' and ci + 1 < len(line):
                        ci += 2; continue
                    if ch == '"':
                        in_string = False
                    ci += 1; continue

                if ch == '"':
                    in_string = True; last_ident = None; ci += 1; continue

                if ch == ';':
                    break

                if ch in ' \t':
                    ci += 1; continue

                if state == 'cond':
                    # Skip the condition expression (one atom or paren-group).
                    if ch == '(':
                        li, ci, in_string = self._skip_paren(li, ci + 1, in_string)
                        cond_li = li
                        state = 'then_expr'
                        last_ident = None
                        line = self.lines[li] if li < self.hard_end else ''
                        continue
                    elif ch == ')':
                        return li, ci + 1, in_string
                    else:
                        # Read an atom token (identifier or symbol)
                        end = ci
                        while end < len(line) and line[end] not in ' \t\n();"':
                            end += 1
                        ci = end
                        # If the atom is immediately followed by '(' it is a function call
                        # that is part of the condition (e.g. inner(a)).  Skip whitespace
                        # and then consume the paren-group so it is not mistaken for the
                        # then-expression.
                        skip_ci = ci
                        skip_li = li
                        while skip_li < self.hard_end:
                            ln = self.lines[skip_li]
                            while skip_ci < len(ln):
                                c = ln[skip_ci]
                                if c in ' \t':
                                    skip_ci += 1
                                    continue
                                if c == '(':
                                    li, ci, in_string = self._skip_paren(
                                        skip_li, skip_ci + 1, in_string)
                                    line = self.lines[li] if li < self.hard_end else ''
                                    # The atom+paren form may chain further calls; stay in
                                    # 'cond' state so subsequent '(' chains are consumed too.
                                    skip_ci = ci
                                    skip_li = li
                                    continue
                                break
                            else:
                                skip_ci = 0
                                skip_li += 1
                                continue
                            break
                        cond_li = li
                        state = 'then_expr'
                        last_ident = None
                        continue

                elif state == 'then_expr':
                    if ch.isalpha() or ch == '_':
                        end = ci
                        while end < len(line) and (line[end].isalnum() or line[end] == '_'):
                            end += 1
                        token = line[ci:end].lower()
                        if token == 'then':
                            then_keyword_seen = True
                            then_keyword_li = li
                            last_ident = None
                            ci = end
                            continue
                        elif token == 'else':
                            # 'else' keyword before then-expr was consumed
                            else_keyword_seen = True
                            else_keyword_li = li
                            last_ident = None
                            ci = end
                            state = 'else_expr'
                            continue
                        else:
                            last_ident = token
                            ci = end
                            continue
                    elif ch == '(':
                        # Paren-group: this is the then-expr (or part of cond)
                        expr_li = li
                        nested_skip = _SPECIAL_FORM_SKIP.get(last_ident) if last_ident else None
                        # Only insert breakpoint if expr is on its own line
                        # (not on the same line as cond or the 'then' keyword)
                        if then_keyword_seen and expr_li != cond_li and expr_li != then_keyword_li:
                            stripped = line.strip()
                            if stripped and not stripped.startswith(';') and \
                                    not all(c in ') \t' for c in stripped):
                                insertable.add(expr_li + 1)
                        if last_ident == 'if':
                            li, ci, in_string = self._scan_if(li, ci + 1, form_depth + 1, insertable)
                        elif nested_skip is not None:
                            li, ci, in_string = self._scan_special(
                                li, ci + 1, form_depth + 1, nested_skip, insertable)
                        else:
                            li, ci, in_string = self._skip_paren(li, ci + 1, in_string)
                        last_ident = None
                        state = 'else_expr'
                        line = self.lines[li] if li < self.hard_end else ''
                        continue
                    elif ch == ')':
                        return li, ci + 1, in_string
                    else:
                        # Non-alpha, non-paren: part of cond or bare then-expr atom
                        end = ci
                        while end < len(line) and line[end] not in ' \t\n();"':
                            end += 1
                        last_ident = None
                        ci = end
                        continue

                elif state == 'else_expr':
                    if ch.isalpha() or ch == '_':
                        end = ci
                        while end < len(line) and (line[end].isalnum() or line[end] == '_'):
                            end += 1
                        token = line[ci:end].lower()
                        if token == 'else':
                            else_keyword_seen = True
                            else_keyword_li = li
                            last_ident = None
                            ci = end
                            continue
                        else:
                            last_ident = token
                            ci = end
                            continue
                    elif ch == '(':
                        expr_li = li
                        nested_skip = _SPECIAL_FORM_SKIP.get(last_ident) if last_ident else None
                        # Only insert breakpoint if expr is on its own line
                        # (not on the same line as cond or the 'else' keyword)
                        if else_keyword_seen and expr_li != cond_li and expr_li != else_keyword_li:
                            stripped = line.strip()
                            if stripped and not stripped.startswith(';') and \
                                    not all(c in ') \t' for c in stripped):
                                insertable.add(expr_li + 1)
                        if last_ident == 'if':
                            li, ci, in_string = self._scan_if(li, ci + 1, form_depth + 1, insertable)
                        elif nested_skip is not None:
                            li, ci, in_string = self._scan_special(
                                li, ci + 1, form_depth + 1, nested_skip, insertable)
                        else:
                            li, ci, in_string = self._skip_paren(li, ci + 1, in_string)
                        last_ident = None
                        line = self.lines[li] if li < self.hard_end else ''
                        continue
                    elif ch == ')':
                        return li, ci + 1, in_string
                    else:
                        # Atom else-expr
                        end = ci
                        while end < len(line) and line[end] not in ' \t\n();"':
                            end += 1
                        if else_keyword_seen and li != cond_li and li != else_keyword_li:
                            stripped = line.strip()
                            if stripped and not stripped.startswith(';') and \
                                    not all(c in ') \t' for c in stripped):
                                insertable.add(li + 1)
                        last_ident = None
                        ci = end
                        continue

                ci += 1

            li += 1; ci = 0; last_ident = None

        return li, ci, in_string

    # ------------------------------------------------------------------
    # Scan inside a cond() form.  Positioned just after the opening '('
    # at depth `form_depth`.
    # Structure: cond(clause1 clause2 ...)
    #   each clause: ((cond-expr) body-stmt1 body-stmt2 ...)
    #   or:          (t body-stmt1 ...)  (t = atom condition)
    # Breakpoints go before each body statement inside each clause.
    # Returns (li, ci, in_string) just AFTER the closing ')'.
    # ------------------------------------------------------------------
    def _scan_cond(self, start_li, start_ci, form_depth, insertable):
        li, ci = start_li, start_ci
        in_string = False

        while li < self.hard_end:
            line = self.lines[li]
            while ci < len(line):
                ch = line[ci]

                if in_string:
                    if ch == '\\' and ci + 1 < len(line):
                        ci += 2; continue
                    if ch == '"':
                        in_string = False
                    ci += 1; continue

                if ch == '"':
                    in_string = True; ci += 1; continue

                if ch == ';':
                    break  # comment

                if ch in ' \t':
                    ci += 1; continue

                if ch == '(':
                    # Start of a clause: (cond-expr body...)
                    # Skip the first arg (the condition), then scan body
                    li, ci, in_string = self._scan_special(
                        li, ci + 1, form_depth + 1, 1, insertable)
                    line = self.lines[li] if li < self.hard_end else ''
                    continue

                elif ch == ')':
                    # Closing paren of cond()
                    return li, ci + 1, in_string

                else:
                    # Atom at cond level (e.g. 't' — but in practice cond uses parens)
                    end = ci
                    while end < len(line) and line[end] not in ' \t\n();"':
                        end += 1
                    ci = end
                    continue

                ci += 1

            li += 1; ci = 0

        return li, ci, in_string

    # ------------------------------------------------------------------
    # Scan inside a special form.  We are positioned just after the '('
    # at depth `form_depth`.  Skip `skip_count` top-level args, then
    # treat all remaining args as body statements (via scan_body).
    # max_body: if not None, only paren-group body exprs are descended into;
    #   bare atom body exprs are skipped without inserting a breakpoint.
    #   Used for forms like exists/forall where the body is a single expression.
    # Returns (li, ci, in_string) positioned just AFTER the closing ')'.
    # ------------------------------------------------------------------
    def _scan_special(self, start_li, start_ci, form_depth, skip_count, insertable,
                      max_body=None):
        li, ci = start_li, start_ci
        in_string = False
        args_skipped = 0
        last_ident = None
        last_nonskip_li = None  # line index where the last non-body arg ended

        while li < self.hard_end:
            line = self.lines[li]
            while ci < len(line):
                ch = line[ci]

                if in_string:
                    if ch == '\\' and ci + 1 < len(line):
                        ci += 2; continue
                    if ch == '"':
                        in_string = False
                    ci += 1; continue

                if ch == '"':
                    in_string = True; last_ident = None; ci += 1; continue

                if ch == ';':
                    break  # comment

                if ch in ' \t':
                    ci += 1; continue

                if ch == '(':
                    if args_skipped < skip_count:
                        # Non-body paren-group: skip entirely
                        li, ci, in_string = self._skip_paren(li, ci + 1, in_string)
                        args_skipped += 1
                        last_ident = None
                        last_nonskip_li = li
                        line = self.lines[li] if li < self.hard_end else ''
                        continue
                    else:
                        # Body paren-group: mark its start line, handle recursively
                        # Check if it's a nested special form (using last_ident before '(')
                        nested_skip = _SPECIAL_FORM_SKIP.get(last_ident) if last_ident else None
                        nested_single_skip = _SINGLE_BODY_FORM_SKIP.get(last_ident) if last_ident else None
                        stmt_line = li + 1  # 1-based
                        # Only mark as insertable if body starts on a different line than
                        # the last non-body arg (same line = non-body and body are mixed,
                        # can't safely insert a breakpoint before the body paren)
                        if max_body is None and li != last_nonskip_li:
                            stripped = line.strip()
                            if stripped and not stripped.startswith(';') and \
                                    not all(c in ') \t' for c in stripped):
                                insertable.add(stmt_line)
                        if last_ident == 'if':
                            li, ci, in_string = self._scan_if(
                                li, ci + 1, form_depth + 1, insertable)
                        elif last_ident in ('cond', 'case', 'caseq', 'casev'):
                            li, ci, in_string = self._scan_cond(
                                li, ci + 1, form_depth + 1, insertable)
                        elif nested_skip is not None:
                            # Nested special form: scan its body recursively
                            li, ci, in_string = self._scan_special(
                                li, ci + 1, form_depth + 1, nested_skip, insertable)
                        elif nested_single_skip is not None:
                            li, ci, in_string = self._scan_special(
                                li, ci + 1, form_depth + 1, nested_single_skip, insertable,
                                max_body=1)
                        else:
                            # Regular paren-group in body: scan interior for nested
                            # special forms (e.g. lambda inside mapcar inside lambda)
                            li, ci, in_string = self._scan_interior(
                                li, ci + 1, form_depth + 1, insertable)
                        last_ident = None
                        line = self.lines[li] if li < self.hard_end else ''
                        continue

                elif ch == ')':
                    # Closing paren of the special form
                    return li, ci + 1, in_string

                else:
                    # Atom (identifier, number, symbol, operator, etc.)
                    # Read the full token
                    end = ci
                    if ch.isalpha() or ch == '_':
                        while end < len(line) and (line[end].isalnum() or line[end] == '_'):
                            end += 1
                        token = line[ci:end].lower()
                    else:
                        while end < len(line) and line[end] not in ' \t\n();"':
                            end += 1
                        token = None

                    if args_skipped < skip_count:
                        # Non-body atom: count and skip
                        last_ident = token
                        args_skipped += 1
                        last_nonskip_li = li  # remember which line this non-body arg was on
                        ci = end
                        continue
                    else:
                        # Body atom as statement
                        if max_body is None:
                            # Normal multi-body form: mark this line as insertable
                            # (only if not on the same line as the last non-body arg)
                            if li != last_nonskip_li:
                                stripped = line.strip()
                                if stripped and not stripped.startswith(';') and \
                                        not all(c in ') \t' for c in stripped):
                                    insertable.add(li + 1)
                        # else: single-body form — bare atom body, skip without breakpoint
                        last_ident = token
                        ci = end
                        continue

                ci += 1

            li += 1; ci = 0; last_ident = None

        return li, ci, in_string

    # ------------------------------------------------------------------
    # Scan the interior of a regular (non-special) paren-group to find
    # nested special forms (lambda, for, etc.) and descend into them.
    # Does NOT mark any lines as insertable itself — only delegates to
    # the appropriate scan methods when a special form is recognised.
    # Positioned just after the opening '(' at depth `form_depth`.
    # Returns (li, ci, in_string) just AFTER the closing ')'.
    # ------------------------------------------------------------------
    def _scan_interior(self, start_li, start_ci, form_depth, insertable):
        li, ci = start_li, start_ci
        in_string = False
        depth = form_depth
        last_ident = None

        while li < self.hard_end:
            line = self.lines[li]
            while ci < len(line):
                ch = line[ci]

                if in_string:
                    if ch == '\\' and ci + 1 < len(line):
                        ci += 2; continue
                    if ch == '"':
                        in_string = False
                    ci += 1; continue

                if ch == '"':
                    in_string = True; last_ident = None; ci += 1; continue

                if ch == ';':
                    break

                if ch in ' \t':
                    ci += 1; continue

                if ch == '(':
                    nested_skip = _SPECIAL_FORM_SKIP.get(last_ident) if last_ident else None
                    nested_single_skip = _SINGLE_BODY_FORM_SKIP.get(last_ident) if last_ident else None
                    if last_ident == 'if':
                        li, ci, in_string = self._scan_if(
                            li, ci + 1, depth + 1, insertable)
                        line = self.lines[li] if li < self.hard_end else ''
                        last_ident = None; continue
                    elif last_ident in ('cond', 'case', 'caseq', 'casev'):
                        li, ci, in_string = self._scan_cond(
                            li, ci + 1, depth + 1, insertable)
                        line = self.lines[li] if li < self.hard_end else ''
                        last_ident = None; continue
                    elif nested_skip is not None:
                        li, ci, in_string = self._scan_special(
                            li, ci + 1, depth + 1, nested_skip, insertable)
                        line = self.lines[li] if li < self.hard_end else ''
                        last_ident = None; continue
                    elif nested_single_skip is not None:
                        li, ci, in_string = self._scan_special(
                            li, ci + 1, depth + 1, nested_single_skip, insertable,
                            max_body=1)
                        line = self.lines[li] if li < self.hard_end else ''
                        last_ident = None; continue
                    else:
                        depth += 1; last_ident = None

                elif ch == ')':
                    depth -= 1
                    if depth < form_depth:
                        return li, ci + 1, in_string
                    last_ident = None

                elif ch.isalpha() or ch == '_':
                    end = ci
                    while end < len(line) and (line[end].isalnum() or line[end] == '_'):
                        end += 1
                    last_ident = line[ci:end].lower()
                    ci = end; continue

                else:
                    last_ident = None

                ci += 1

            li += 1; ci = 0; last_ident = None

        return li, ci, in_string

    # ------------------------------------------------------------------
    # Skip a parenthesised expression.  Called with ci pointing just
    # AFTER the opening '(', in_string as current string state.
    # Returns (li, ci, in_string) just after matching ')'.
    # ------------------------------------------------------------------
    def _skip_paren(self, start_li, start_ci, in_string):
        li, ci = start_li, start_ci
        depth = 1

        while li < self.hard_end:
            line = self.lines[li]
            while ci < len(line):
                ch = line[ci]

                if in_string:
                    if ch == '\\' and ci + 1 < len(line):
                        ci += 2; continue
                    if ch == '"':
                        in_string = False
                    ci += 1; continue

                if ch == '"':
                    in_string = True; ci += 1; continue

                if ch == ';':
                    break

                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        return li, ci + 1, in_string

                ci += 1

            li += 1; ci = 0

        return li, ci, in_string

    def _peek_name(self, li, ci):
        """Peek at first identifier token starting at (li, ci), skipping whitespace."""
        while li < self.hard_end:
            line = self.lines[li]
            while ci < len(line):
                c = line[ci]
                if c in ' \t':
                    ci += 1; continue
                if c == ';':
                    break
                if c.isalpha() or c == '_':
                    end = ci
                    while end < len(line) and (line[end].isalnum() or line[end] == '_'):
                        end += 1
                    return line[ci:end].lower()
                return None
            li += 1; ci = 0
        return None


def _get_indent(line: str) -> str:
    """Extract leading whitespace from a line."""
    return line[:len(line) - len(line.lstrip())]


def build_breakpoint_update_code(breakpoint_lines: list, file_id: int = 0) -> str:
    """Build SKILL code to update per-file breakpoint variable during a debug session.

    This is sent while in break state to change which lines will trigger next break.
    """
    if breakpoint_lines:
        bp_list = ' '.join(str(n) for n in sorted(breakpoint_lines))
        return f'__sbk_bp_{file_id} = list({bp_list})'
    else:
        return f'__sbk_bp_{file_id} = nil'


def build_next_step_code_multi(files_insertable: dict, files_user_bp: dict) -> str:
    """Build SKILL code for 'next' (step-in) operation across multiple files.

    Sets ALL insertable lines as breakpoints for every file so execution
    stops at the very next executed line, including cross-file calls.

    Args:
        files_insertable: {file_id: [insertable_lines...]}
        files_user_bp: {file_id: [user_breakpoints...]}

    Returns:
        SKILL code to execute in debug toplevel for stepping
    """
    parts = []
    for fid in sorted(files_insertable.keys()):
        insertable = files_insertable[fid]
        user_bp = files_user_bp.get(fid, [])
        all_bp = sorted(set(user_bp) | set(insertable))
        if all_bp:
            bp_list = ' '.join(str(n) for n in all_bp)
            parts.append(f'__sbk_bp_{fid} = list({bp_list})')
        else:
            parts.append(f'__sbk_bp_{fid} = nil')
    return '\n'.join(parts) if parts else ''


def build_next_step_code(insertable_lines: list, breakpoint_lines: list) -> str:
    """Build SKILL code for 'next' (step-in) operation (legacy single-file).

    Sets ALL insertable lines as breakpoints so execution stops at the very
    next executed line, including lines inside called functions.

    Args:
        insertable_lines: Sorted list of all insertable lines
        breakpoint_lines: Current user-set breakpoints

    Returns:
        SKILL code to execute in debug toplevel for stepping
    """
    if not insertable_lines:
        return 'continue'

    # Step-in: break on every insertable line (enters called functions)
    all_bp = sorted(set(breakpoint_lines or []) | set(insertable_lines))
    bp_list = ' '.join(str(n) for n in all_bp)
    return f'__sbk_bp = list({bp_list})\ncontinue'


def has_entry_point(source: str) -> bool:
    """Return True if the source contains executable code outside procedure definitions.

    An "entry point" is any non-blank, non-comment line that is NOT inside a
    procedure(...) body.  If all executable lines are inside procedures the
    code has no entry point and must be called from CIW (idle mode).
    """
    lines = source.split('\n')
    procedures = _find_procedures(lines)

    if not procedures:
        # No procedures at all — treat bare expressions as the entry point
        return any(_is_statement_line(l.strip()) for l in lines)

    # Build set of line numbers (1-based) that are inside any procedure
    inside = set()
    for p in procedures:
        for ln in range(p['start_line'], p['end_line'] + 1):
            inside.add(ln)

    for i, line in enumerate(lines):
        ln = i + 1
        if ln in inside:
            continue
        if _is_statement_line(line.strip()):
            return True

    return False
