// ── State ────────────────────────────────────────────────────────────────────
let editor;
let ilPath = "";
let currentLanguage = 'en'; // 'en' or 'ko'
let currentLayout = 'bottom'; // 'bottom' or 'right'

// Debug state
let _debugActive = false;
let _debugIdle = false;             // True when waiting for CIW call (idle mode)
let _selectedCiw = null;           // Last selected CIW info { window_id, title, pid }
// Per-tab debug state accessed via _getActiveTab().debugBreakpoints / debugCurrentLine / debugInsertableLines
let _debugPendingEval = null;      // Expression waiting for eval result
let _debugLineMarker = null;       // CodeMirror line widget for current debug line

// ── CodeMirror init ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    tooltipTriggerList.forEach(function (tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl)
    })

    const textarea = document.getElementById('codeEditor');
    if (!textarea) return;

    if (typeof CodeMirror === 'undefined') {
        document.getElementById('output').innerHTML =
            '<div class="out-entry out-err"><div class="out-text">ERROR: CodeMirror failed to load.</div></div>';
        return;
    }

    let initialCmTheme = 'dracula';
    try {
        const parentThemeSelect = window.parent.document.getElementById('theme-select');
        if (parentThemeSelect && parentThemeSelect.value === 'white') {
            initialCmTheme = 'eclipse';
        }
    } catch (e) {
        if (window.matchMedia('(prefers-color-scheme: light)').matches) {
            initialCmTheme = 'eclipse';
        }
    }

    document.body.classList.toggle('theme-white', initialCmTheme === 'eclipse');

    editor = CodeMirror.fromTextArea(textarea, {
        mode: 'skill',
        theme: initialCmTheme,
        lineNumbers: true,
        matchBrackets: true,
        autoCloseBrackets: false,
        styleActiveLine: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        lineWrapping: false,
        gutters: ["CodeMirror-linenumbers", "sb-breakpoint-gutter"],
        extraKeys: {
            "Ctrl-Up": function(cm) {
                const lh = cm.defaultTextHeight();
                if (_virtualExtra > 0) {
                    _virtualExtra = Math.max(0, _virtualExtra - lh);
                    _applyVirtualScroll();
                } else {
                    cm.scrollTo(null, Math.max(0, cm.getScrollInfo().top - lh));
                }
            },
            "Ctrl-Down": function(cm) {
                const sc = cm.getScrollerElement();
                const lh = cm.defaultTextHeight();
                const lastLineTop = _getLastLineTop();
                const cmMaxScroll = sc.scrollHeight - sc.clientHeight;
                const maxExtra = Math.max(0, lastLineTop - cmMaxScroll);
                const atMax = sc.scrollTop >= cmMaxScroll - 1;
                if (_virtualExtra > 0 || atMax) {
                    _virtualExtra = Math.min(_virtualExtra + lh, maxExtra);
                    _applyVirtualScroll();
                    if (!atMax) cm.scrollTo(null, cmMaxScroll);
                } else {
                    cm.scrollTo(null, Math.min(cm.getScrollInfo().top + lh, cmMaxScroll));
                }
            },
            "Ctrl-Home": function(cm) {
                _virtualExtra = 0;
                _applyVirtualScroll();
                cm.execCommand('goDocStart');
                // Defer scroll to let async highlight settle (Python mode)
                setTimeout(function() { cm.scrollIntoView(null); }, 0);
            },
            "Ctrl-End": function(cm) {
                // Reset virtual scroll first, then move cursor to end
                _virtualExtra = 0;
                _applyVirtualScroll();
                cm.execCommand('goDocEnd');
                // Defer scroll to let async highlight settle (Python mode)
                setTimeout(function() { cm.scrollIntoView(null); }, 0);
            },
            "PageDown": function(cm) {
                _virtualExtra = 0;
                _applyVirtualScroll();
                cm.execCommand('goPageDown');
                setTimeout(function() { cm.scrollIntoView(null); }, 0);
            },
            "PageUp": function(cm) {
                _virtualExtra = 0;
                _applyVirtualScroll();
                cm.execCommand('goPageUp');
                setTimeout(function() { cm.scrollIntoView(null); }, 0);
            },
            "Ctrl-Enter": function(cm) { /* Run removed */ },
            "Ctrl-S": function(cm) { EXP.saveCurrentFile(); },
            "Ctrl-/": function(cm) { cm.execCommand("toggleComment"); },
            "Ctrl-Space": function(cm) { if (EXP.isILFile()) ISK.onChange(cm); },
            "Ctrl-F": function(cm) { SBFind.open(false); return false; },
            "Ctrl-H": function(cm) { SBFind.open(true); return false; },
            "F3": function(cm) { SBFind.findNext(false); return false; },
            "Shift-F3": function(cm) { SBFind.findNext(true); return false; },
            "Tab": function(cm) {
                const sel = cm.listSelections()[0];
                if (sel.anchor.line !== sel.head.line) {
                    // Multi-line selection: indent all selected lines by +4
                    const from = Math.min(sel.anchor.line, sel.head.line);
                    const to = Math.max(sel.anchor.line, sel.head.line);
                    for (let i = from; i <= to; i++) {
                        cm.replaceRange("    ", {line: i, ch: 0});
                    }
                } else {
                    const col = cm.getCursor().ch;
                    const spaces = 4 - (col % 4);
                    cm.replaceSelection(" ".repeat(spaces));
                }
            },
            "Enter": function(cm) {
                const cur = cm.getCursor();
                const line = cm.getLine(cur.line);
                const lineIndent = line.match(/^(\s*)/)[1].length;
                // Use cursor position as indent if cursor is within the leading spaces
                const indent = (cur.ch <= lineIndent) ? cur.ch : lineIndent;

                // Count unmatched open parens on the CURRENT LINE only (up to cursor)
                const lineUpToCursor = line.slice(0, cur.ch);

                let openParens = 0;
                let inStr = false;
                let inBlockComment = false;

                // Check if we're already inside a block comment from previous lines
                const textBefore = cm.getRange({line: 0, ch: 0}, {line: cur.line, ch: 0});
                for (let i = 0; i < textBefore.length; i++) {
                    const ch = textBefore[i];
                    const nextCh = textBefore[i + 1];
                    if (inBlockComment) {
                        if (ch === '*' && nextCh === '/') { inBlockComment = false; i++; }
                        continue;
                    }
                    if (inStr) {
                        if (ch === '"' && textBefore[i - 1] !== '\\') inStr = false;
                        continue;
                    }
                    if (ch === '"') inStr = true;
                    else if (ch === '/' && nextCh === '*') { inBlockComment = true; i++; }
                }

                // Now count parens on the current line
                for (let i = 0; i < lineUpToCursor.length; i++) {
                    const ch = lineUpToCursor[i];
                    const nextCh = lineUpToCursor[i + 1];

                    if (inBlockComment) {
                        if (ch === '*' && nextCh === '/') {
                            inBlockComment = false;
                            i++;
                        }
                        continue;
                    }

                    if (inStr) {
                        if (ch === '"' && lineUpToCursor[i - 1] !== '\\') {
                            inStr = false;
                        }
                        continue;
                    }

                    if (ch === ';') break; // line comment - rest is comment
                    if (ch === '"') {
                        inStr = true;
                    } else if (ch === '/' && nextCh === '*') {
                        inBlockComment = true;
                        i++;
                    } else if (ch === '(') {
                        openParens++;
                    } else if (ch === ')') {
                        openParens--;
                    }
                }

                const newIndent = indent + (openParens > 0 ? 4 : 0);
                cm.replaceSelection("\n" + " ".repeat(newIndent));
                // Ensure the new line is visible after virtual scroll transform
                setTimeout(() => {
                    if (_virtualExtra > 0) {
                        _virtualExtra = 0;
                        _applyVirtualScroll();
                    }
                    cm.scrollIntoView(null, cm.defaultTextHeight());
                }, 0);
            },
            "Ctrl-Backspace": function(cm) {
                const cur = cm.getCursor();
                const line = cm.getLine(cur.line);
                const indent = line.match(/^(\s*)/)[1].length;
                // Act if cursor is within the leading spaces: delete back to the previous tab stop
                if (cur.ch <= indent && cur.ch > 0) {
                    const newCh = Math.floor((cur.ch - 1) / 4) * 4;
                    cm.replaceRange(
                        " ".repeat(newCh),
                        {line: cur.line, ch: 0},
                        {line: cur.line, ch: cur.ch}
                    );
                    cm.setCursor({line: cur.line, ch: newCh});
                } else {
                    cm.execCommand("delWordBefore");
                }
            },
            "Shift-Tab": function(cm) {
                const sel = cm.listSelections()[0];
                const from = Math.min(sel.anchor.line, sel.head.line);
                const to = Math.max(sel.anchor.line, sel.head.line);
                for (let i = from; i <= to; i++) {
                    const line = cm.getLine(i);
                    const indent = line.match(/^(\s*)/)[1].length;
                    if (indent >= 4) {
                        cm.replaceRange(
                            " ".repeat(indent - 4),
                            {line: i, ch: 0},
                            {line: i, ch: indent}
                        );
                    } else if (indent > 0) {
                        cm.replaceRange("", {line: i, ch: 0}, {line: i, ch: indent});
                    }
                }
            },
            ")": function(cm) {
                const cur = cm.getCursor();
                const line = cm.getLine(cur.line);

            },
        },
        dragDrop: false,
    });

    // Overlay: highlight @skillbot keyword inside comments
    editor.addOverlay({
        token: function(stream) {
            if (stream.match('@skillbot')) return 'skillbot-tag';
            stream.next();
            return null;
        }
    }, true);

    ISK.initWithEditor(editor);
    editor.on('change', (cm) => { if (EXP.isILFile()) ISK.onChange(cm); EXP.onEditorChange(); });
    editor.on('cursorActivity', (cm) => { if (EXP.isILFile()) ISK.onCursorActivity(cm); });
    editor.on('keydown', (cm, e) => { if (EXP.isILFile()) ISK.onKeyDown(cm, e); });
    editor.on('mousemove', (cm, e) => { if (EXP.isILFile()) ISK.onHover(cm, e); });

    // Auto-indent ')' on whitespace-only lines to match the opening '('
    editor.on('beforeChange', function(cm, change) {
        if (change.text.length !== 1 || change.text[0] !== ')') return;
        if (change.origin !== '+input') return;
        const cur = change.from;
        const line = cm.getLine(cur.line);
        if (line.trim() !== '') return;

        const textAbove = cm.getRange({line: 0, ch: 0}, {line: cur.line, ch: 0});
        let depth = 0, matchIndent = -1, inStr = false, inBlockComment = false;

        for (let i = textAbove.length - 1; i >= 0; i--) {
            const ch = textAbove[i];
            const prevCh = textAbove[i - 1];
            if (inBlockComment) {
                if (prevCh === '/' && ch === '*') { inBlockComment = false; i--; }
                continue;
            }
            if (prevCh === '*' && ch === '/') { inBlockComment = true; i--; continue; }
            if (inStr) {
                if (ch === '"' && prevCh !== '\\') inStr = false;
                continue;
            }
            if (ch === '"') { inStr = true; continue; }
            if (ch === ')') { depth++; }
            else if (ch === '(') {
                if (depth === 0) {
                    const before = textAbove.slice(0, i);
                    const nl = before.lastIndexOf('\n');
                    matchIndent = textAbove.slice(nl + 1).match(/^(\s*)/)[1].length;
                    break;
                }
                depth--;
            }
        }

        if (matchIndent >= 0) {
            change.cancel();
            cm.replaceRange(
                ' '.repeat(matchIndent) + ')',
                {line: cur.line, ch: 0},
                {line: cur.line, ch: line.length}
            );
        }
    });
    editor.getWrapperElement().addEventListener('mouseleave', () => ISK.hideSig());
    editor.getWrapperElement().addEventListener('mousemove', (e) => { ISK.trackMouseMove(e); });

    // Breakpoint gutter click
    editor.on('gutterClick', function(cm, line, gutter) {
        if (gutter !== 'sb-breakpoint-gutter') return;
        const lineNum = line + 1; // 1-based
        toggleBreakpoint(lineNum);
    });

    // ── Indent guides ──────────────────────────────────────────────────────────
    // Draw vertical guide lines using background-image on each line element.
    // Does not touch the DOM text nodes, so CodeMirror cursor is unaffected.
    (function() {
        const INDENT = 4;
        const MAX_DEPTH = 64;
        const GUIDE_COLOR = 'rgba(128,128,128,0.25)';
        const GUIDE_COLOR_ACTIVE = 'rgba(140,140,140,0.9)';
        let _activeDepth = -1; // currently highlighted guide depth (0-based)
        let _activeRange = null; // { from, to } line range of the active block

        function leadingSpaces(text) {
            let i = 0;
            while (i < text.length && text[i] === ' ') i++;
            return i;
        }

        function applyIndentGuides(cm, line, elt) {
            const text = line.text;
            let spaces = leadingSpaces(text);
            const isBlank = (spaces === text.length); // empty or spaces-only

            if (isBlank) {
                const lineNo = (typeof line.lineNo === 'function') ? line.lineNo() : cm.getLineNumber(line);
                let maxSpaces = spaces;
                if (lineNo !== null && lineNo !== undefined) {
                    const lineCount = cm.lineCount();
                    // Walk up
                    for (let i = lineNo - 1; i >= 0; i--) {
                        const t = cm.getLine(i);
                        if (t === null) break;
                        if (t.length === 0) continue;
                        const s = leadingSpaces(t);
                        if (s === t.length) {
                            if (s > maxSpaces) maxSpaces = s;
                        } else {
                            if (s > maxSpaces) maxSpaces = s;
                            break;
                        }
                    }
                    // Walk down
                    for (let i = lineNo + 1; i < lineCount; i++) {
                        const t = cm.getLine(i);
                        if (t === null) break;
                        if (t.length === 0) continue;
                        const s = leadingSpaces(t);
                        if (s === t.length) {
                            if (s > maxSpaces) maxSpaces = s;
                        } else {
                            if (s > maxSpaces) maxSpaces = s;
                            break;
                        }
                    }
                }
                spaces = maxSpaces;
            }

            const depth = Math.min(Math.ceil(spaces / INDENT), MAX_DEPTH);
            const lineEl = elt.querySelector('.CodeMirror-line') || elt;
            if (depth === 0) {
                lineEl.style.background = '';
                return;
            }

            const charWidth = cm.defaultCharWidth();
            const gradients = [];
            const thisLine = (typeof line.lineNo === 'function') ? line.lineNo() : cm.getLineNumber(line);
            const inActiveRange = _activeRange !== null && thisLine >= _activeRange.from && thisLine <= _activeRange.to;
            for (let d = 1; d < depth; d++) {
                const x = Math.round(d * INDENT * charWidth) + 'px';
                const isActive = (d === _activeDepth && d > 0 && inActiveRange);
                const color = isActive ? GUIDE_COLOR_ACTIVE : GUIDE_COLOR;
                const width = isActive ? '1.5px' : '1px';
                gradients.push(
                    `linear-gradient(${color}, ${color}) ${x} 0 / ${width} 100% no-repeat`
                );
            }
            lineEl.style.background = gradients.join(', ');
        }

        function getEffectiveSpaces(cm, lineNo) {
            const t = cm.getLine(lineNo) || '';
            const s = leadingSpaces(t);
            if (s < t.length) {
                // content line: closing paren gets +INDENT
                return (t.trimStart()[0] === ')') ? s + INDENT : s;
            }
            return s; // spaces-only: use own spaces
        }

        function updateActiveGuide(cm) {
            const cur = cm.getCursor();
            const text = cm.getLine(cur.line) || '';
            const spaces = leadingSpaces(text);
            const isBlank = (spaces === text.length);
            let newActive = -1;
            let newRange = null;

            if (!isBlank) {
                const effectiveSpaces = (text.trimStart()[0] === ')') ? spaces + INDENT : spaces;
                const cursorDepth = Math.ceil(effectiveSpaces / INDENT);
                newActive = cursorDepth > 0 ? cursorDepth - 1 : -1;
            } else {
                // blank/spaces-only: look up and down for nearest content line
                const lineCount = cm.lineCount();
                let maxSpaces = spaces;
                for (let i = cur.line - 1; i >= 0; i--) {
                    const t = cm.getLine(i) || '';
                    if (t.length === 0) continue;
                    const s = leadingSpaces(t);
                    if (s === t.length) { if (s > maxSpaces) maxSpaces = s; }
                    else { maxSpaces = Math.max(maxSpaces, getEffectiveSpaces(cm, i)); break; }
                }
                for (let i = cur.line + 1; i < lineCount; i++) {
                    const t = cm.getLine(i) || '';
                    if (t.length === 0) continue;
                    const s = leadingSpaces(t);
                    if (s === t.length) { if (s > maxSpaces) maxSpaces = s; }
                    else { maxSpaces = Math.max(maxSpaces, getEffectiveSpaces(cm, i)); break; }
                }
                const cursorDepth = Math.ceil(maxSpaces / INDENT);
                newActive = cursorDepth > 0 ? cursorDepth - 1 : -1;
            }

            // Compute the line range of the block the cursor belongs to.
            // A block boundary is any line whose indent depth <= newActive (i.e. < newActive+1 spaces).
            if (newActive >= 0) {
                const threshold = newActive * INDENT; // lines with fewer spaces are outside this block
                const lineCount = cm.lineCount();
                let from = cur.line;
                let to = cur.line;
                for (let i = cur.line - 1; i >= 0; i--) {
                    const t = cm.getLine(i) || '';
                    const s = leadingSpaces(t);
                    const isBlankLine = (s === t.length && t.length === 0);
                    if (!isBlankLine && s <= threshold) break;
                    from = i;
                }
                for (let i = cur.line + 1; i < lineCount; i++) {
                    const t = cm.getLine(i) || '';
                    const s = leadingSpaces(t);
                    const isBlankLine = (s === t.length && t.length === 0);
                    if (!isBlankLine && s <= threshold) break;
                    to = i;
                }
                newRange = { from, to };
            }

            const rangeChanged = (
                (_activeRange === null) !== (newRange === null) ||
                (newRange !== null && (_activeRange.from !== newRange.from || _activeRange.to !== newRange.to))
            );
            if (newActive !== _activeDepth || rangeChanged) {
                _activeDepth = newActive;
                _activeRange = newRange;
                cm.refresh();
            }
        }

        editor.on('renderLine', applyIndentGuides);
        editor.on('cursorActivity', updateActiveGuide);
        editor.refresh();
    })();

    // ── Unmatched bracket highlighting ────────────────────────────────────────
    let _unmatchedMarks = [];
    let _unmatchedTimer = null;

    function updateUnmatchedBrackets(cm) {
        // Clear previous marks
        for (const m of _unmatchedMarks) m.clear();
        _unmatchedMarks = [];

        const text = cm.getValue();
        const parenStack = [];   // positions of unmatched open '('
        const bracketStack = []; // positions of unmatched open '['
        const unmatched = [];    // positions of unmatched brackets

        let inStr = false;          // inside "..."
        let inBlockComment = false; // inside /* ... */
        let i = 0;
        while (i < text.length) {
            const c = text[i];
            // ── block comment /* ... */ ──
            if (inBlockComment) {
                if (c === '*' && text[i+1] === '/') { i += 2; inBlockComment = false; }
                else i++;
                continue;
            }
            if (c === '/' && text[i+1] === '*') { inBlockComment = true; i += 2; continue; }
            // ── string "..." ──
            if (inStr) {
                if (c === '\\') { i += 2; continue; }
                if (c === '"') inStr = false;
                i++;
                continue;
            }
            if (c === '"') { inStr = true; i++; continue; }
            // ── line comment ; ──
            if (c === ';') {
                while (i < text.length && text[i] !== '\n') i++;
                continue;
            }
            // ── brackets ──
            if (c === '(') {
                parenStack.push(i);
            } else if (c === ')') {
                if (parenStack.length > 0) parenStack.pop();
                else unmatched.push(i);
            } else if (c === '[') {
                bracketStack.push(i);
            } else if (c === ']') {
                if (bracketStack.length > 0) bracketStack.pop();
                else unmatched.push(i);
            }
            i++;
        }
        for (const pos of parenStack) unmatched.push(pos);
        for (const pos of bracketStack) unmatched.push(pos);

        // Convert flat index to {line, ch} and mark
        if (unmatched.length === 0) return;
        const lines = text.split('\n');
        function indexToPos(idx) {
            let offset = 0;
            for (let ln = 0; ln < lines.length; ln++) {
                const end = offset + lines[ln].length;
                if (idx <= end) return { line: ln, ch: idx - offset };
                offset = end + 1;
            }
            return { line: lines.length - 1, ch: lines[lines.length - 1].length };
        }

        for (const pos of unmatched) {
            const from = indexToPos(pos);
            const to = { line: from.line, ch: from.ch + 1 };
            const mark = cm.markText(from, to, { className: 'cm-unmatched-bracket' });
            _unmatchedMarks.push(mark);
        }
    }

    editor.on('change', (cm) => {
        clearTimeout(_unmatchedTimer);
        _unmatchedTimer = setTimeout(() => updateUnmatchedBrackets(cm), 300);
    });
    // Initial run
    setTimeout(() => updateUnmatchedBrackets(editor), 400);

    // Shift breakpoint line numbers when lines are inserted or deleted
    editor.on('change', function(cm, change) {
        if (change.origin === 'setValue') return; // tab switch — not a real edit
        const tab = EXP.getActiveTab();
        if (!tab || tab.debugBreakpoints.size === 0) return;
        const linesAdded   = change.text.length - 1;     // newlines in inserted text
        const linesRemoved = change.removed.length - 1;  // newlines in removed text
        const delta = linesAdded - linesRemoved;
        if (delta === 0) return;
        const fromLine = change.from.line + 1; // 1-based line where change starts
        const newBps = new Set();
        tab.debugBreakpoints.forEach(function(bp) {
            if (bp > fromLine) {
                // Breakpoint is below the changed line — shift it
                const newBp = bp + delta;
                if (newBp >= 1) newBps.add(newBp);
            } else {
                newBps.add(bp);
            }
        });
        if (newBps.size === tab.debugBreakpoints.size &&
            [...newBps].every(v => tab.debugBreakpoints.has(v))) return; // no change
        // Rebuild gutter markers
        tab.debugBreakpoints.forEach(bp => {
            editor.setGutterMarker(bp - 1, 'sb-breakpoint-gutter', null);
        });
        tab.debugBreakpoints = newBps;
        tab.debugBreakpoints.forEach(bp => {
            const marker = document.createElement('div');
            marker.className = 'sb-bp-marker';
            editor.setGutterMarker(bp - 1, 'sb-breakpoint-gutter', marker);
        });
    });

    // Auto-dedent ) when typed as first non-whitespace character on a line
    editor.on('change', function(cm, change) {
        if (change.origin !== '+input' && change.origin !== '+delete') return;
        if (change.text.length !== 1 || change.text[0] !== ')') return;
        const cur = cm.getCursor();
        const line = cm.getLine(cur.line);
        const beforeParen = line.slice(0, cur.ch - 1);
        if (!/^\s*$/.test(beforeParen)) return;
        const indent = beforeParen.length;
        if (indent < 4) return;
        const newIndent = indent - 4;
        cm.replaceRange(
            " ".repeat(newIndent) + ")",
            {line: cur.line, ch: 0},
            {line: cur.line, ch: cur.ch}
        );
        cm.setCursor({line: cur.line, ch: newIndent + 1});
    });

    // Scroll CM scroller directly, bypassing CM's internal scrollTop clamp.
    // CM clamps scrollTop to scrollHeight-clientHeight; to scroll further we
    // Virtual scroll: track extra scroll beyond CM's natural max.
    // When scrolled past CM's max, apply translateY to the wrapper to simulate scrolling.
    let _virtualExtra = 0; // how many px we've scrolled beyond CM's natural max
    function _getLastLineTop() {
        const lastLine = editor.lastLine();
        return editor.charCoords({line: lastLine, ch: 0}, 'local').top;
    }
    function _applyVirtualScroll() {
        const wrap = editor.getWrapperElement();
        wrap.style.transform = _virtualExtra > 0 ? `translateY(-${_virtualExtra}px)` : '';
    }
    // Reset virtual scroll on mouse click or cursor-key navigation
    const _virtualResetKeys = new Set([
        'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
        'Home', 'End', 'PageUp', 'PageDown',
    ]);
    editor.on('mousedown', function() {
        if (_virtualExtra > 0) {
            _virtualExtra = 0;
            _applyVirtualScroll();
        }
    });
    editor.on('keydown', function(cm, e) {
        if (_virtualExtra > 0 && _virtualResetKeys.has(e.key) && !e.ctrlKey) {
            _virtualExtra = 0;
            _applyVirtualScroll();
        }
    });

    setTimeout(() => { editor.refresh(); editor.focus(); }, 100);

    const exampleCode = [
      'procedure(inner(a)',
      '    printf("[IN], a=%d\\n" a)',
      '    printf("[IN], return\\n")',
      '    a+100',
      ')',
      'procedure(test()',
      'let((a b c)',
      '    printf("[OUT 0]\\n")',
      '    a = 0',
      '    printf("[OUT 1]\\n")',
      '    a = inner(a)',
      '    printf("[OUT] 2]\\n")',
      '    printf(">>> %d\\n" a)',
      '))',
      '; @skillbot(run-debug:test())',
    ].join('\n');
    ISK.setEditorValue(editor, exampleCode);
    setLayout('bottom');

    initResizer();
    initExplorerResizer();

    function loadLayoutFromConfig() {
        if (typeof callPython !== 'function') {
            setTimeout(loadLayoutFromConfig, 200);
            return;
        }
        callPython('get_layout', {}).then(res => {
            const layout = (res && res.success && res.layout) || 'bottom';
            if (layout !== currentLayout) setLayout(layout);
        }).catch(() => {});
    }

    function loadEditorPrefs() {
        if (typeof callPython !== 'function') {
            setTimeout(loadEditorPrefs, 200);
            return;
        }
        callPython('get_editor_prefs', {}).then(res => {
            const prefs = (res && res.success && res.prefs) ? res.prefs : {};
            const fontSize = prefs['editor.font_size'] || PREFS_DEFAULT['editor.font_size'];
            _applyEditorFontSize(fontSize);
        }).catch(() => {});
    }

    function loadSkillSyntax() {
        if (typeof callPython !== 'function') {
            setTimeout(loadSkillSyntax, 200);
            return;
        }
        callPython('get_skill_syntax', {}).then(res => {
            if (res && res.success && res.builtins) {
                CodeMirror.initSKILLBuiltins(res.builtins);
                // Refresh editor highlighting
                if (editor) {
                    editor.setOption('mode', 'skill');
                }
            }
            if (res && res.all_functions) {
                ISK.setIntellisenseFuncs(res.all_functions);
            }
        }).catch(() => {});
    }

    function startPolling() {
        callPython('get_skillbot_config', {}).then(res => {
            const interval = (res && res.success && res.connection_check_interval_ms) || 5000;
            // Get current language from parent window
            try {
                const languageSelect = window.parent.document.getElementById('language-select');
                if (languageSelect && languageSelect.value === 'ko') {
                    currentLanguage = 'ko';
                } else {
                    currentLanguage = 'en';
                }
            } catch (e) {
                currentLanguage = 'en';
            }
            refreshStatus();
            setInterval(refreshStatus, interval);
        }).catch(() => {
            refreshStatus();
            setInterval(refreshStatus, 5000);
        });
    }

    function waitForCallPythonThenPoll() {
        if (typeof callPython === 'function') {
            startPolling();
        } else {
            setTimeout(waitForCallPythonThenPoll, 200);
        }
    }

    if (window.skillupInitialized) {
        waitForCallPythonThenPoll();
        loadLayoutFromConfig();
        loadSkillSyntax();
        loadEditorPrefs();
        EXP.init();
        EXP.loadIconTheme(initialCmTheme === 'eclipse' ? 'light' : 'dark');
    } else {
        window.addEventListener('skillupInitialized', function() {
            waitForCallPythonThenPoll();
            loadLayoutFromConfig();
            loadSkillSyntax();
            loadEditorPrefs();
            EXP.init();
            EXP.loadIconTheme(initialCmTheme === 'eclipse' ? 'light' : 'dark');
        }, { once: true });
    }

    // ESC key to close modals
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            hideConnectionHelp();
            hideCiwSelect();
            hidePreferences();
            EXP.hideCtxMenu();
        }
    });

    // Ctrl+1~9: switch to nth tab
    document.addEventListener('keydown', function(e) {
        if (!e.ctrlKey || e.altKey || e.shiftKey) return;
        const n = parseInt(e.key);
        if (n >= 1 && n <= 9) {
            const tabs = EXP.getTabs();
            if (tabs[n - 1]) {
                e.preventDefault();
                EXP.switchTab(tabs[n - 1].id);
            }
        }
    });


    // VS Code-style debug hotkeys
    // F5/F10: keydown (need preventDefault to block browser refresh/default)
    document.addEventListener('keydown', function(e) {
        const key = e.code && e.code.startsWith('F') ? e.code : e.key;
        // Ctrl+F5: Run
        if (key === 'F5' && e.ctrlKey && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            runCode();
            return;
        }
        // F5: Debug Start (if not active) or Continue (if active)
        if (key === 'F5' && !e.ctrlKey && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            if (_debugActive) {
                debugContinue();
            } else {
                debugStart();
            }
            return;
        }
        // Shift+F5: Stop debug
        if (key === 'F5' && e.shiftKey && !e.ctrlKey) {
            e.preventDefault();
            if (_debugActive) debugStop();
            return;
        }
        // F10: Next (Step Over)
        if (key === 'F10' && !e.ctrlKey && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            if (_debugActive) {
                const cmEl = editor && editor.getWrapperElement();
                if (cmEl) cmEl.classList.add('sb-cursor-hidden');
                debugNext();
            }
            return;
        }
    }, true);

    // F9: keyup — Korean IME swallows keydown for F9, but keyup always fires
    document.addEventListener('keyup', function(e) {
        const key = e.code || e.key;
        // F9: Toggle Breakpoint
        if (key === 'F9' && !e.ctrlKey && !e.shiftKey && !e.altKey) {
            if (editor && EXP.isILFile()) toggleBreakpoint(editor.getCursor().line + 1);
            return;
        }
        // Ctrl+Shift+F9: Remove All Breakpoints
        if (key === 'F9' && e.ctrlKey && e.shiftKey) {
            if (editor && EXP.isILFile()) clearAllBreakpoints();
            return;
        }
    }, true);
});

// ── Status ───────────────────────────────────────────────────────────────────
function refreshStatus() {
    if (typeof callPython !== 'function') return;
    callPython('get_status', {}).then(res => {
        if (!res || !res.success) return;
        ilPath = res.il_path || ilPath;
        updateStatusUI(res.ipc_alive);
    }).catch(e => { console.error('[SkillBot] get_status error:', e); });
}

function updateStatusUI(ipcAlive) {
    updateUITexts();
    document.getElementById('helpIlPath').textContent = ilPath;
}

function updateUITexts() {
    // Update all elements with data-en and data-ko attributes
    document.querySelectorAll('[data-en][data-ko]').forEach(el => {
        const textAttr = el.getAttribute(`data-${currentLanguage}`);
        if (textAttr) {
            // For elements with tooltip (Bootstrap)
            if (el.hasAttribute('data-bs-toggle') && el.getAttribute('data-bs-toggle') === 'tooltip') {
                let tooltipText = textAttr;
                // Add status indicator dot for status badge
                if (el.id === 'statusBadge') {
                    const status = el.getAttribute('data-status');
                    const dot = (status === 'connected') ? '🟢' : '🔴';
                    tooltipText = `${dot} ${textAttr}`;
                }
                el.setAttribute('data-bs-title', tooltipText);
                // Update Bootstrap tooltip title without dispose/recreate cycle
                try {
                    const tooltipInstance = bootstrap.Tooltip.getInstance(el);
                    if (tooltipInstance) {
                        tooltipInstance.setContent({ '.tooltip-inner': tooltipText });
                    }
                } catch (e) { /* ignore tooltip update errors */ }
            }
            // For button with span child (Run button)
            if (el.tagName === 'BUTTON') {
                const span = el.querySelector('span');
                if (span && !span.hasAttribute('data-en')) {
                    span.textContent = textAttr;
                } else if (!el.hasAttribute('data-bs-toggle')) {
                    el.textContent = textAttr;
                }
            } else if (!el.hasAttribute('data-bs-toggle')) {
                // For other elements (including DIV), just set textContent
                el.textContent = textAttr;
            }
        }
    });
}

// ── Output helpers ────────────────────────────────────────────────────────────
function appendOutput(type, text) {
    const out = document.getElementById('output');
    const entry = document.createElement('div');
    entry.className = 'out-entry out-' + type;

    const time = document.createElement('div');
    time.className = 'out-time';
    time.textContent = new Date().toLocaleTimeString();

    const body = document.createElement('div');
    body.className = 'out-text';
    body.textContent = text;

    entry.appendChild(time);
    entry.appendChild(body);
    out.appendChild(entry);
    out.scrollTop = out.scrollHeight;
}

function clearOutput() { document.getElementById('output').innerHTML = ''; }

function escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Connection help modal ─────────────────────────────────────────────────────
function showConnectionHelp() {
    if (window.parent && window.parent.desktopModal) {
        const isKo = currentLanguage === 'ko';
        const ilPath = document.getElementById('helpIlPath').textContent;
        const loadCmd = 'load("' + ilPath + '")';

        const html =
            '<div style="margin-bottom:14px;">' +
              '<div style="display:flex;align-items:center;margin-bottom:6px;">' +
                '<span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;' +
                  'border-radius:50%;background:var(--accent-primary,#4a9eff);color:#fff;font-size:11px;font-weight:700;margin-right:8px;flex-shrink:0;">1</span>' +
                '<span style="font-size:13px;font-weight:600;color:var(--text-primary,#e0e0e0);">' +
                  (isKo ? 'Cadence CIW에서 SKILL 모듈 로드 (세션당 1회)' : 'Load the SKILL module in Cadence CIW (once per session)') +
                '</span>' +
              '</div>' +
              '<div style="font-size:12px;color:var(--text-secondary,#aaa);margin-bottom:8px;">' +
                (isKo ? 'Cadence CIW (Command Input Window)에서 이 명령어를 복사하여 실행하세요:'
                      : 'Copy and run this command in the Cadence CIW (Command Input Window):') +
              '</div>' +
              '<div style="position:relative;background:var(--bg-tertiary,#2a2f38);border-radius:5px;padding:8px 70px 8px 10px;' +
                'font-family:monospace;font-size:12px;color:var(--text-primary,#e0e0e0);">' +
                _escHtml(loadCmd) +
                '<button data-copy-cmd style="position:absolute;right:8px;top:50%;transform:translateY(-50%);' +
                  'font-size:11px;padding:2px 8px;border:1px solid var(--border-color,#373c47);border-radius:3px;' +
                  'background:var(--bg-secondary,#1a1d23);color:var(--text-secondary,#aaa);cursor:pointer;">' +
                  (isKo ? '복사' : 'Copy') +
                '</button>' +
              '</div>' +
            '</div>' +
            '<div>' +
              '<div style="display:flex;align-items:center;margin-bottom:6px;">' +
                '<span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;' +
                  'border-radius:50%;background:var(--accent-primary,#4a9eff);color:#fff;font-size:11px;font-weight:700;margin-right:8px;flex-shrink:0;">2</span>' +
                '<span style="font-size:13px;font-weight:600;color:var(--text-primary,#e0e0e0);">' +
                  (isKo ? 'F5를 눌러 디버그 시작 (Ctrl+F5로 실행)' : 'Press F5 to start debugging (Ctrl+F5 to run)') +
                '</span>' +
              '</div>' +
              '<div style="font-size:12px;color:var(--text-secondary,#aaa);">' +
                (isKo ? 'SkillBot이 자동으로 Virtuoso CIW 창을 찾아 디버그 세션을 시작합니다. 수동 연결이 필요 없습니다.'
                      : 'SkillBot will automatically find the Virtuoso CIW window and start the debug session. No manual connection needed.') +
              '</div>' +
            '</div>';

        window.parent.postMessage({ action: 'skillbotModalOpen' }, '*');
        window.parent.desktopModal.open({
            title: isKo ? 'SkillBot 디버거 사용 방법' : 'How to Use SkillBot Debugger',
            html: html,
            buttons: [{ label: isKo ? '닫기' : 'Close', primary: true }],
            onBodyClick: function(e) {
                if (e.target.closest('[data-copy-cmd]')) {
                    navigator.clipboard.writeText(loadCmd).catch(function() {});
                }
            },
            onClose: function() {
                window.parent.postMessage({ action: 'skillbotModalClose' }, '*');
            }
        });
    } else {
        document.getElementById('helpOverlay').style.display = 'block';
        document.getElementById('connectionHelp').style.display = 'block';
    }
}

function hideConnectionHelp() {
    if (window.parent && window.parent.desktopModal) {
        window.parent.desktopModal.close();
    } else {
        document.getElementById('helpOverlay').style.display = 'none';
        document.getElementById('connectionHelp').style.display = 'none';
    }
}

function copyCiwCmd(type) {
    const path = document.getElementById('helpIlPath').textContent;
    const text = `load("${path}")`;
    navigator.clipboard.writeText(text).catch(() => {
        const el = document.createElement('textarea');
        el.value = text;
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
    });
}

// ── Theme ─────────────────────────────────────────────────────────────────────
function applyEditorTheme(skillupTheme) {
    if (!editor) return;
    editor.setOption('theme', skillupTheme === 'white' ? 'eclipse' : 'dracula');
    document.body.classList.toggle('theme-white', skillupTheme === 'white');
    const iconTheme = skillupTheme === 'white' ? 'light' : 'dark';
    EXP.loadIconTheme(iconTheme);
    EXP.renderIcons();
}

window.addEventListener('message', function(event) {
    if (event.data && event.data.action === 'setTheme' && event.data.theme) {
        applyEditorTheme(event.data.theme);
    }
    if (event.data && event.data.action === 'setLanguage' && event.data.language) {
        currentLanguage = event.data.language === 'ko' ? 'ko' : 'en';
        refreshStatus();
    }
    if (event.data && event.data.action === 'requestFocus') {
        if (editor) editor.focus();
    }
});

// ── Python -> JS events ───────────────────────────────────────────────────────
function onConnectionChange(data) {
    appendOutput('info', data.message || 'Connection changed');
    refreshStatus();
}

// ── Debug ─────────────────────────────────────────────────────────────────────

async function clearAllBreakpoints() {
    const tabs = EXP.getTabs();
    const hasAny = tabs.some(t => t.debugBreakpoints.size > 0);
    if (!hasAny) return;
    const msg = currentLanguage === 'ko' ? '모든 중단점을 삭제하시겠습니까?' : 'Clear all breakpoints?';
    const title = currentLanguage === 'ko' ? '중단점 삭제' : 'Clear Breakpoints';
    if (!await parent.showConfirmDialog(title, msg)) return;
    const activeTab = EXP.getActiveTab();
    tabs.forEach(t => {
        if (t === activeTab) {
            t.debugBreakpoints.forEach(lineNum => {
                editor.setGutterMarker(lineNum - 1, 'sb-breakpoint-gutter', null);
            });
        }
        if (_debugActive && typeof callPython === 'function') {
            callPython('debug_update_bp', { file_id: t.debugFileId, breakpoints: [] });
        }
        t.debugBreakpoints.clear();
    });
}

function openNewTab() { EXP.openNewTab(); }

// ── Preferences ───────────────────────────────────────────────────────────────
const PREFS_DEFAULT = { 'editor.font_size': 16 };
const PREFS_FONT_SIZES = [10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 24];

function openPreferences() {
    const modal = window.parent && window.parent.desktopModal;
    if (!modal) return;

    const ko = currentLanguage === 'ko';

    // Build select element HTML
    const options = PREFS_FONT_SIZES.map(sz => `<option value="${sz}">${sz}px</option>`).join('');
    const labelText = ko ? '편집기 글꼴 크기' : 'Editor Font Size';
    const selectStyle = 'background:var(--bg-primary,#1a1d23);border:1px solid var(--border-color,#373c47);' +
        'color:var(--text-primary,#e0e0e0);border-radius:4px;padding:4px 8px;font-size:13px;outline:none;' +
        'cursor:pointer;min-width:80px;';
    const html = `<div style="display:flex;align-items:center;">` +
        `<span style="font-size:13px;color:var(--text-secondary,#a0a0a0);flex:1;margin-right:12px;white-space:nowrap;">${labelText}</span>` +
        `<select id="prefsFontSize" style="${selectStyle}">${options}</select>` +
        `</div>`;

    // Load current prefs then open modal
    callPython('get_editor_prefs', {}).then(res => {
        const prefs = (res && res.success && res.prefs) ? res.prefs : Object.assign({}, PREFS_DEFAULT);
        const parentDoc = window.parent.document;
        modal.open({
            title: ko ? '환경설정' : 'Preferences',
            html: html,
            buttons: [
                {
                    label: ko ? '확인' : 'OK',
                    primary: true,
                    onClick: function() {
                        const sel = parentDoc.getElementById('prefsFontSize');
                        if (!sel) return;
                        const fontSize = parseInt(sel.value, 10);
                        callPython('save_editor_prefs', { prefs: { 'editor.font_size': fontSize } }).then(() => {
                            _applyEditorFontSize(fontSize);
                        });
                        modal.close();
                    }
                },
                {
                    label: ko ? '디폴트' : 'Default',
                    onClick: function() {
                        const sel = parentDoc.getElementById('prefsFontSize');
                        if (sel) sel.value = PREFS_DEFAULT['editor.font_size'];
                    }
                },
                { label: ko ? '취소' : 'Cancel' }
            ],
            onClose: function() {}
        });
        // Set current value after modal.open() synchronously inserts HTML into parent DOM
        const sel = parentDoc.getElementById('prefsFontSize');
        if (sel) sel.value = prefs['editor.font_size'] || PREFS_DEFAULT['editor.font_size'];
    });
}

function hidePreferences() {
    const modal = window.parent && window.parent.desktopModal;
    if (modal && modal.isOpen()) modal.close();
}

function _applyEditorFontSize(size) {
    if (typeof editor !== 'undefined' && editor) {
        editor.getWrapperElement().style.fontSize = size + 'px';
        editor.refresh();
    }
}

const _tbSubMenus = {
    file:  'tbSubMenuFile',
    debug: 'tbSubMenuDebug',
};
let _tbOpenSub = null;

function toggleToolbarMenu() {
    const popup = document.getElementById('toolbarPopup');
    if (popup.style.display === 'block') {
        hideToolbarMenu();
        return;
    }
    _tbHideSubMenu();
    const btn  = document.getElementById('btnMenu');
    const rect = btn.getBoundingClientRect();
    popup.style.left = (rect.right + 2) + 'px';
    popup.style.top  = rect.top + 'px';
    popup.style.display = 'flex';
    btn.classList.add('active');
    // Apply i18n text to popup items
    popup.querySelectorAll('[data-en]').forEach(el => {
        el.textContent = currentLanguage === 'ko' ? el.dataset.ko : el.dataset.en;
    });
    setTimeout(() => document.addEventListener('mousedown', _tbOutsideClick), 0);
}

function hideToolbarMenu() {
    _tbHideSubMenu();
    const popup = document.getElementById('toolbarPopup');
    if (popup) popup.style.display = 'none';
    const btn = document.getElementById('btnMenu');
    if (btn) btn.classList.remove('active');
    document.removeEventListener('mousedown', _tbOutsideClick);
}

function tbPopupHover(key) {
    _tbHideSubMenu();
    const itemId = key === 'file' ? 'tbMenuFile' : 'tbMenuDebug';
    const item   = document.getElementById(itemId);
    const subId  = _tbSubMenus[key];
    const sub    = document.getElementById(subId);
    if (!item || !sub) return;
    item.classList.add('active');
    _tbOpenSub = key;
    // Apply i18n to sub-menu items
    sub.querySelectorAll('[data-en]').forEach(el => {
        el.textContent = currentLanguage === 'ko' ? el.dataset.ko : el.dataset.en;
    });
    // Position sub-menu below the popup item
    const itemRect = item.getBoundingClientRect();
    sub.style.left = itemRect.left + 'px';
    sub.style.top  = (itemRect.bottom + 1) + 'px';
    sub.style.display = 'block';
}

function _tbHideSubMenu() {
    if (_tbOpenSub) {
        const itemId = _tbOpenSub === 'file' ? 'tbMenuFile' : 'tbMenuDebug';
        const item = document.getElementById(itemId);
        if (item) item.classList.remove('active');
        const sub = document.getElementById(_tbSubMenus[_tbOpenSub]);
        if (sub) sub.style.display = 'none';
        _tbOpenSub = null;
    }
}

function _tbOutsideClick(e) {
    const popup    = document.getElementById('toolbarPopup');
    const subFile  = document.getElementById('tbSubMenuFile');
    const subDebug = document.getElementById('tbSubMenuDebug');
    const btn      = document.getElementById('btnMenu');
    if (popup  && popup.contains(e.target))    return;
    if (subFile  && subFile.contains(e.target))  return;
    if (subDebug && subDebug.contains(e.target)) return;
    if (e.target === btn) return;
    hideToolbarMenu();
}

function toggleBreakpoint(lineNum) {
    const tab = EXP.getActiveTab();
    if (!tab) return;
    if (tab.debugBreakpoints.has(lineNum)) {
        tab.debugBreakpoints.delete(lineNum);
        editor.setGutterMarker(lineNum - 1, 'sb-breakpoint-gutter', null);
    } else {
        tab.debugBreakpoints.add(lineNum);
        const marker = document.createElement('div');
        marker.className = 'sb-bp-marker';
        editor.setGutterMarker(lineNum - 1, 'sb-breakpoint-gutter', marker);
    }
    // Update breakpoints in active debug session
    if (_debugActive && typeof callPython === 'function') {
        callPython('debug_update_bp', { file_id: tab.debugFileId, breakpoints: Array.from(tab.debugBreakpoints).sort((a,b) => a-b) });
    }
}

function _collectRunFiles() {
    const cur = EXP.getActiveTab();
    if (cur && editor) cur.content = editor.getValue();
    const ilTabs = EXP.getTabs().filter(t => _isILTab(t));
    return ilTabs.map(tab => ({
        name:    tab.name,
        path:    tab.path || null,
        dirty:   tab.dirty,
        content: tab.content,
    }));
}

function _handleRunCodeResponse(res) {
    if (!res || !res.success) {
        if (res && res.error === 'ciw_selection_needed') {
            showCiwSelect(res.ciw_windows, res.files, 'run');
        } else if (res && res.error === 'ciw_wrong_desktop') {
            const cur = res.current_desktop, ciw = res.ciw_desktop;
            const title = currentLanguage === 'ko' ? 'CIW 데스크탑 오류' : 'CIW Desktop Error';
            const text = currentLanguage === 'ko'
                ? `CIW가 다른 가상 데스크탑에 있습니다 (현재=${cur}, CIW=${ciw}).\n데스크탑 ${ciw}으로 이동 후 다시 시도하세요.`
                : `CIW is on a different virtual desktop (current=${cur}, CIW=${ciw}).\nPlease switch to desktop ${ciw} and retry.`;
            _selectedCiw = null;
            _updateCiwCombo(null);
            window.parent.postMessage({ action: 'showMessageBox', title, text }, '*');
        } else if (res && res.error && res.error.indexOf('CIW window not found') !== -1) {
            const noVirtuosoLog = currentLanguage === 'ko'
                ? 'CIW 창을 찾을 수 없습니다. Virtuoso가 실행 중인지 확인하세요.'
                : 'CIW window not found. Is Virtuoso running?';
            appendOutput('err', noVirtuosoLog);
            _showNoVirtuosoMsg();
        } else {
            appendOutput('err', res ? res.error : 'No response');
        }
        return;
    }
    if (res.ciw_info && res.ciw_info.window_id) {
        _selectedCiw = res.ciw_info;
        _updateCiwCombo(_selectedCiw);
    }
}

function runCode() {
    if (!editor || _debugActive) return;

    const files = _collectRunFiles();
    if (files.length === 0) return;

    appendOutput('cmd', currentLanguage === 'ko' ? '[실행]' : '[Run]');

    if (_selectedCiw) {
        const payload = {
            window_id: _selectedCiw.window_id,
            title:     _selectedCiw.title,
            pid:       _selectedCiw.pid,
            files:     files,
        };
        callPython('run_code_selected', payload).then(res => {
            if (!res || !res.success) {
                if (res && res.error === 'ciw_selection_needed') {
                    _selectedCiw = null;
                    _updateCiwCombo(null);
                    showCiwSelect(res.ciw_windows, res.files, 'run');
                } else {
                    _handleRunCodeResponse(res);
                }
            } else if (res.ciw_info && res.ciw_info.window_id) {
                _selectedCiw = res.ciw_info;
                _updateCiwCombo(_selectedCiw);
            }
        }).catch(e => appendOutput('err', String(e)));
        return;
    }

    callPython('run_code', { files: files }).then(_handleRunCodeResponse).catch(e => appendOutput('err', String(e)));
}

function _isILTab(tab) {
    const ext = (tab.name || '').split('.').pop().toLowerCase();
    return ext === 'il' || ext === 'ils';
}

// Replace lines marked with @skillbot(run-debug:expr) for debug execution.
// Pattern: ;+ whitespace* @skillbot(run-debug:expr)
// e.g. "; @skillbot(run-debug:test())" => "test()"
// The entire line (including leading indent) is replaced with the expr inside run-debug:...
function _applyRunDebug(code) {
    return code.split('\n').map(line => {
        const m = line.match(/^(\s*);+\s*@skillbot\(run-debug:(.*)\)\s*$/);
        if (!m) return line;
        return m[1] + m[2].trim();
    }).join('\n');
}

function _collectDebugFiles() {
    // Save current editor content to active tab first
    const mainTab = EXP.getActiveTab();
    if (mainTab && editor) mainTab.content = editor.getValue();

    // Main tab: current active tab (always included if IL, even if debugEnabled=false)
    // Other tabs: included only if debugEnabled=true
    const allILTabs = EXP.getTabs().filter(t => _isILTab(t));
    const includedTabs = allILTabs.filter(t => t === mainTab || t.debugEnabled);

    let idx = 0;
    const files = includedTabs.map(tab => {
        tab.debugFileId = idx;
        const isMain = (tab === mainTab);
        const entry = {
            file_id: idx,
            tab_id: tab.id,
            name: tab.name,
            path: tab.path,
            // @skillbot(run-debug:...) only applied to main tab
            code: isMain ? _applyRunDebug(tab.content) : tab.content,
            breakpoints: Array.from(tab.debugBreakpoints).sort((a, b) => a - b),
        };
        idx++;
        return entry;
    });

    // Collect paths of saved IL tabs that are excluded (debugEnabled=false, not main tab).
    // These will be pre-loaded into CIW before debug starts so their functions are defined.
    files._preloadPaths = allILTabs
        .filter(t => t !== mainTab && !t.debugEnabled && t.path)
        .map(t => t.path);

    return files;
}

function debugStart() {
    if (!editor) return;
    if (_debugActive) { debugStop(); return; }

    const files = _collectDebugFiles();
    if (files.length === 0 || files.every(f => !f.code.trim())) return;

    appendOutput('cmd', currentLanguage === 'ko' ? '[디버그 시작]' : '[Debug Start]');

    // If a CIW was already selected, skip the selection dialog and use it directly
    if (_selectedCiw) {
        const payload = {
            window_id:     _selectedCiw.window_id,
            title:         _selectedCiw.title,
            pid:           _selectedCiw.pid,
            files:         files,
            inject_load:   true,
            preload_paths: files._preloadPaths || [],
        };
        callPython('debug_start_selected', payload).then(res => {
            if (!res || !res.success) {
                if (res && res.error === 'ciw_selection_needed') {
                    // CIW no longer valid; clear selection and show dialog
                    _selectedCiw = null;
                    _updateCiwCombo(null);
                    showCiwSelect(res.ciw_windows, res.files, null, files._preloadPaths);
                } else if (res && res.error === 'ciw_wrong_desktop') {
                    const cur = res.current_desktop, ciw = res.ciw_desktop;
                    const title = currentLanguage === 'ko' ? 'CIW 데스크탑 오류' : 'CIW Desktop Error';
                    const text = currentLanguage === 'ko'
                        ? `CIW가 다른 가상 데스크탑에 있습니다 (현재=${cur}, CIW=${ciw}).\n데스크탑 ${ciw}으로 이동 후 다시 시도하세요.`
                        : `CIW is on a different virtual desktop (current=${cur}, CIW=${ciw}).\nPlease switch to desktop ${ciw} and retry.`;
                    _selectedCiw = null;
                    _updateCiwCombo(null);
                    window.parent.postMessage({ action: 'showMessageBox', title, text }, '*');
                } else if (res && res.error && res.error.indexOf('CIW window not found') !== -1) {
                    const noVirtuosoLog = currentLanguage === 'ko'
                        ? 'CIW 창을 찾을 수 없습니다. Virtuoso가 실행 중인지 확인하세요.'
                        : 'CIW window not found. Is Virtuoso running?';
                    appendOutput('err', noVirtuosoLog);
                    _showNoVirtuosoMsg();
                } else {
                    appendOutput('err', res ? res.error : 'No response');
                }
                return;
            }
            _debugActive = true;
            if (res.ciw_info && res.ciw_info.window_id) {
                _selectedCiw = res.ciw_info;
                _updateCiwCombo(_selectedCiw);
            }
            if (res.files_info) {
                res.files_info.forEach(fi => {
                    const tab = EXP.getTabs().find(t => t.debugFileId === fi.file_id);
                    if (tab) tab.debugInsertableLines = fi.insertable_lines || [];
                });
            }
            updateDebugUI();
        }).catch(e => appendOutput('err', String(e)));
        return;
    }

    const payload = { files: files, preload_paths: files._preloadPaths || [] };

    callPython('debug_start', payload).then(res => {
        if (!res || !res.success) {
            if (res && res.error === 'ciw_selection_needed') {
                showCiwSelect(res.ciw_windows, res.files, null, files._preloadPaths);
            } else if (res && res.error === 'ciw_wrong_desktop') {
                const cur = res.current_desktop, ciw = res.ciw_desktop;
                const title = currentLanguage === 'ko' ? 'CIW 데스크탑 오류' : 'CIW Desktop Error';
                const text = currentLanguage === 'ko'
                    ? `CIW가 다른 가상 데스크탑에 있습니다 (현재=${cur}, CIW=${ciw}).\n데스크탑 ${ciw}으로 이동 후 다시 시도하세요.`
                    : `CIW is on a different virtual desktop (current=${cur}, CIW=${ciw}).\nPlease switch to desktop ${ciw} and retry.`;
                _selectedCiw = null;
                _updateCiwCombo(null);
                window.parent.postMessage({ action: 'showMessageBox', title, text }, '*');
            } else if (res && res.error && res.error.indexOf('CIW window not found') !== -1) {
                const noVirtuosoLog = currentLanguage === 'ko'
                    ? 'CIW 창을 찾을 수 없습니다. Virtuoso가 실행 중인지 확인하세요.'
                    : 'CIW window not found. Is Virtuoso running?';
                appendOutput('err', noVirtuosoLog);
                _showNoVirtuosoMsg();
            } else {
                appendOutput('err', res ? res.error : 'No response');
            }
            return;
        }
        // Async: Python returns immediately with ack.
        // Actual break/ended events arrive via onDebugEvent() callback.
        _debugActive = true;
        if (res.ciw_info && res.ciw_info.window_id) {
            _selectedCiw = res.ciw_info;
            _updateCiwCombo(_selectedCiw);
        }
        // Store per-file insertable lines from response
        if (res.files_info) {
            res.files_info.forEach(fi => {
                const tab = EXP.getTabs().find(t => t.debugFileId === fi.file_id);
                if (tab) tab.debugInsertableLines = fi.insertable_lines || [];
            });
        }
        updateDebugUI();
    }).catch(e => {
        appendOutput('err', String(e));
    });
}

// ── CIW Selection Modal ───────────────────────────────────────────────────────
let _ciwSelectFiles = [];
let _ciwSelectPreloadPaths = [];
let _ciwSelectMode = 'debug';   // 'debug' | 'run'

function showCiwSelect(ciwWindows, files, mode, preloadPaths) {
    _ciwSelectFiles = files || [];
    _ciwSelectPreloadPaths = preloadPaths || (files && files._preloadPaths) || [];
    _ciwSelectMode  = mode || 'debug';

    if (window.parent && window.parent.desktopModal) {
        const lang = currentLanguage;
        const isKo = lang === 'ko';

        const multiText = ciwWindows.length > 1
            ? (isKo ? '<p style="font-size:12px;color:var(--text-secondary,#aaa);margin-bottom:12px;">Virtuoso CIW 창이 여러 개 발견되었습니다. 디버깅에 사용할 창을 선택하세요.</p>'
                    : '<p style="font-size:12px;color:var(--text-secondary,#aaa);margin-bottom:12px;">Multiple Virtuoso CIW windows were found. Select the one to use for debugging.</p>')
            : (isKo ? '<p style="font-size:12px;color:var(--text-secondary,#aaa);margin-bottom:12px;">디버깅에 사용할 창을 선택하세요.</p>'
                    : '<p style="font-size:12px;color:var(--text-secondary,#aaa);margin-bottom:12px;">Select the window to use for debugging.</p>');

        let listHtml = '<ul style="list-style:none;margin:0;padding:0;">';
        ciwWindows.forEach(function(w, idx) {
            listHtml +=
                '<li data-ciw-idx="' + idx + '" style="display:flex;align-items:center;padding:9px 12px;' +
                'border-radius:7px;border:1px solid var(--border-color,#373c47);margin-bottom:7px;cursor:pointer;' +
                'background:var(--bg-primary,#1a1d23);" ' +
                'onmouseover="this.style.background=\'var(--bg-tertiary,#2a2f38)\'" ' +
                'onmouseout="this.style.background=\'var(--bg-primary,#1a1d23)\'">' +
                '<span style="font-size:18px;margin-right:10px;">🖥</span>' +
                '<span>' +
                  '<div style="font-size:13px;font-weight:600;color:var(--text-primary,#e0e0e0);">' + _escHtml(w.title) + '</div>' +
                  '<div style="font-size:11px;color:var(--text-muted,#888);">PID: ' + (w.pid || '?') + '</div>' +
                '</span></li>';
        });
        listHtml += '</ul>';

        window.parent.postMessage({ action: 'skillbotModalOpen' }, '*');
        window.parent.desktopModal.open({
            title: isKo ? 'CIW 창 선택' : 'Select CIW Window',
            html: multiText + listHtml,
            buttons: [{ label: isKo ? '취소' : 'Cancel' }],
            onBodyClick: function(e) {
                const li = e.target.closest('[data-ciw-idx]');
                if (li) {
                    const idx = parseInt(li.dataset.ciwIdx);
                    window.parent.desktopModal.close();
                    selectCiw(ciwWindows[idx]);
                }
            },
            onClose: function() {
                window.parent.postMessage({ action: 'skillbotModalClose' }, '*');
            }
        });
    } else {
        // fallback: local modal
        const list = document.getElementById('ciwList');
        list.innerHTML = '';
        ciwWindows.forEach(function(w) {
            const li = document.createElement('li');
            li.className = 'ciw-list-item';
            li.innerHTML =
                '<span class="ciw-list-item-icon">🖥</span>' +
                '<span class="ciw-list-item-info">' +
                    '<div class="ciw-list-item-title">' + _escHtml(w.title) + '</div>' +
                    '<div class="ciw-list-item-pid">PID: ' + (w.pid || '?') + '</div>' +
                '</span>';
            li.addEventListener('click', function() { selectCiw(w); });
            list.appendChild(li);
        });

        const descMulti = document.getElementById('ciwSelectDescMulti');
        if (descMulti) descMulti.style.display = ciwWindows.length > 1 ? '' : 'none';

        const modal = document.getElementById('ciwSelectModal');
        modal.querySelectorAll('[data-en]').forEach(function(el) {
            el.textContent = currentLanguage === 'ko' ? el.dataset.ko : el.dataset.en;
        });
        modal.querySelectorAll('[data-en] + button, button[data-en]').forEach(function(el) {
            if (el.dataset.en) el.textContent = currentLanguage === 'ko' ? el.dataset.ko : el.dataset.en;
        });

        document.getElementById('ciwSelectOverlay').style.display = 'block';
        document.getElementById('ciwSelectModal').style.display = 'block';
    }
}

function hideCiwSelect() {
    if (window.parent && window.parent.desktopModal) {
        window.parent.desktopModal.close();
    } else {
        document.getElementById('ciwSelectOverlay').style.display = 'none';
        document.getElementById('ciwSelectModal').style.display = 'none';
    }
}

function _ciwShortTitle(title) {
    // Extract shortest meaningful name: prefer "CDS.log", "CDS.log.1", etc.
    if (!title) return '?';
    const m = title.match(/CDS\.log(?:\.\d+)?/i);
    if (m) return m[0];
    // Fallback: last path component up to 20 chars
    const parts = title.replace(/\\/g, '/').split('/');
    const last = parts[parts.length - 1] || title;
    return last.length > 20 ? last.slice(0, 18) + '…' : last;
}

function _updateCiwCombo(ciwInfo, dead) {
    const btn = document.getElementById('ciwCombo');
    if (!btn) return;
    btn.classList.remove('sb-ciw-selected', 'sb-ciw-dead');
    if (ciwInfo) {
        if (!dead) btn.classList.add('sb-ciw-selected');
        const titleText = 'CIW: ' + _ciwShortTitle(ciwInfo.title);
        btn.setAttribute('data-bs-toggle', 'tooltip');
        btn.setAttribute('data-bs-placement', 'bottom');
        btn.setAttribute('data-bs-title', titleText);
        if (window.bootstrap && bootstrap.Tooltip) {
            try {
                const existing = bootstrap.Tooltip.getInstance(btn);
                if (existing) {
                    existing.setContent({ '.tooltip-inner': titleText });
                } else {
                    new bootstrap.Tooltip(btn);
                }
            } catch (e) { /* ignore tooltip errors */ }
        }
    } else {
        if (window.bootstrap && bootstrap.Tooltip) {
            try {
                const existing = bootstrap.Tooltip.getInstance(btn);
                if (existing) existing.dispose();
            } catch (e) { /* ignore */ }
        }
        btn.removeAttribute('data-bs-toggle');
        btn.removeAttribute('data-bs-title');
    }
}

function _showNoVirtuosoMsg() {
    const title = currentLanguage === 'ko' ? 'CIW를 찾을 수 없음' : 'CIW Not Found';
    const text  = currentLanguage === 'ko'
        ? 'CIW 창을 찾을 수 없습니다. Virtuoso가 실행 중인지 확인하세요.'
        : 'CIW window not found. Is Virtuoso running?';
    window.parent.postMessage({ action: 'showMessageBox', title, text }, '*');
}

function _openCiwSelectDialog() {
    callPython('get_ciw_list', {}).then(res => {
        if (res && res.success && res.ciw_windows && res.ciw_windows.length > 0) {
            showCiwSelect(res.ciw_windows, null, null);
        } else {
            _showNoVirtuosoMsg();
        }
    }).catch(() => { _showNoVirtuosoMsg(); });
}

function onCiwBtnClick() {
    _openCiwSelectDialog();
}

function selectCiw(ciwInfo) {
    hideCiwSelect();
    _selectedCiw = { window_id: ciwInfo.window_id, title: ciwInfo.title, pid: ciwInfo.pid };
    _updateCiwCombo(_selectedCiw);

    // Combo-only selection (no files): just store CIW, don't start debug/run
    if (!_ciwSelectFiles || _ciwSelectFiles.length === 0) return;

    appendOutput('cmd', currentLanguage === 'ko'
        ? '[CIW 선택: ' + ciwInfo.title + ']'
        : '[CIW Selected: ' + ciwInfo.title + ']');

    // Run mode: use run_code_selected
    if (_ciwSelectMode === 'run') {
        const payload = {
            window_id: ciwInfo.window_id,
            title:     ciwInfo.title,
            pid:       ciwInfo.pid,
            files:     _ciwSelectFiles,
        };
        callPython('run_code_selected', payload).then(_handleRunCodeResponse).catch(e => appendOutput('err', String(e)));
        return;
    }

    const payload = {
        window_id:     ciwInfo.window_id,
        title:         ciwInfo.title,
        pid:           ciwInfo.pid,
        files:         _ciwSelectFiles,
        inject_load:   true,
        preload_paths: _ciwSelectPreloadPaths,
    };

    callPython('debug_start_selected', payload).then(res => {
        if (!res || !res.success) {
            if (res && res.error === 'ciw_wrong_desktop') {
                const cur = res.current_desktop, ciw = res.ciw_desktop;
                const title = currentLanguage === 'ko' ? 'CIW 데스크탑 오류' : 'CIW Desktop Error';
                const text = currentLanguage === 'ko'
                    ? `CIW가 다른 가상 데스크탑에 있습니다 (현재=${cur}, CIW=${ciw}).\n데스크탑 ${ciw}으로 이동 후 다시 시도하세요.`
                    : `CIW is on a different virtual desktop (current=${cur}, CIW=${ciw}).\nPlease switch to desktop ${ciw} and retry.`;
                _selectedCiw = null;
                _updateCiwCombo(null);
                window.parent.postMessage({ action: 'showMessageBox', title, text }, '*');
            } else if (res && res.error && res.error.indexOf('CIW window not found') !== -1) {
                const noVirtuosoLog = currentLanguage === 'ko'
                    ? 'CIW 창을 찾을 수 없습니다. Virtuoso가 실행 중인지 확인하세요.'
                    : 'CIW window not found. Is Virtuoso running?';
                appendOutput('err', noVirtuosoLog);
                _showNoVirtuosoMsg();
            } else {
                appendOutput('err', res ? res.error : 'No response');
            }
            return;
        }
        _debugActive = true;
        if (res.files_info) {
            res.files_info.forEach(fi => {
                const tab = EXP.getTabs().find(t => t.debugFileId === fi.file_id);
                if (tab) tab.debugInsertableLines = fi.insertable_lines || [];
            });
        }
        updateDebugUI();
    }).catch(e => appendOutput('err', String(e)));
}

function _escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _clearActiveTabDebugLine() {
    const tab = EXP.getActiveTab();
    if (tab) tab.debugCurrentLine = 0;
}

function debugContinue() {
    if (!_debugActive) return;
    clearDebugHighlight();
    _clearActiveTabDebugLine();
    updateDebugInfo();
    callPython('debug_continue', {}).then(res => {
        if (!res || !res.success) {
            appendOutput('err', res ? res.error : 'No response');
            return;
        }
        // Async: ack received. Break/ended events via onDebugEvent().
    }).catch(e => appendOutput('err', String(e)));
}

function debugNext() {
    if (!_debugActive) return;
    clearDebugHighlight();
    _clearActiveTabDebugLine();
    updateDebugInfo();
    callPython('debug_next', {}).then(res => {
        if (!res || !res.success) {
            appendOutput('err', res ? res.error : 'No response');
            return;
        }
        // Async: ack received. Break/ended events via onDebugEvent().
    }).catch(e => appendOutput('err', String(e)));
}

function debugStop() {
    if (!_debugActive) return;
    callPython('debug_stop', {}).then(() => {
        appendOutput('info', currentLanguage === 'ko' ? '[디버그 중지]' : '[Debug Stopped]');
        debugCleanup();
    }).catch(e => appendOutput('err', String(e)));
}


function debugEvalExpr() {
    const input = document.getElementById('debugEvalInput');
    const expr = input.value.trim();
    if (!expr || !_debugActive) return;

    input.value = '';
    _debugPendingEval = expr;
    // Async: result arrives via onDebugEvalResult()
    callPython('debug_eval', { expr: expr }).catch(e => appendOutput('err', String(e)));
}

function onDebugEvalResult(res) {
    const expr = _debugPendingEval || '?';
    _debugPendingEval = null;
    const content = document.getElementById('debugVarsContent');
    const row = document.createElement('div');
    row.className = 'sb-debug-var-row';
    const nameEl = document.createElement('span');
    nameEl.className = 'sb-debug-var-name';
    nameEl.textContent = expr;
    const valEl = document.createElement('span');
    valEl.className = 'sb-debug-var-value';
    valEl.textContent = res && res.success ? (res.result || 'nil') : ((res && res.error) || 'error');
    if (!res || !res.success) valEl.style.color = '#e74c3c';
    row.appendChild(nameEl);
    row.appendChild(valEl);
    content.appendChild(row);
    content.scrollTop = content.scrollHeight;
}

function highlightDebugLine(lineNum) {
    if (!editor || lineNum <= 0) return;
    const line = lineNum - 1; // 0-based
    _debugLineMarker = editor.addLineClass(line, 'wrap', 'sb-debug-line');
    editor.addLineClass(line, 'gutter', 'sb-debug-line-gutter');
    // Move cursor to debug line, preserving current column
    const curCh = editor.getCursor().ch;
    const lineLen = editor.getLine(line).length;
    editor.setCursor({ line: line, ch: Math.min(curCh, lineLen) });
    editor.scrollIntoView({ line: line, ch: 0 }, 100);
}

function clearDebugHighlight() {
    if (!editor) return;
    // Remove all debug line classes
    const lineCount = editor.lineCount();
    for (let i = 0; i < lineCount; i++) {
        editor.removeLineClass(i, 'wrap', 'sb-debug-line');
        editor.removeLineClass(i, 'gutter', 'sb-debug-line-gutter');
    }
    _debugLineMarker = null;
}

function updateDebugUI() {
    const toolbar = document.getElementById('debugToolbar');
    const varsPanel = document.getElementById('debugVarsPanel');
    const btnDebug = document.getElementById('btnDebug');
    const btnRun = document.getElementById('btnRun');
    const explorerPanel = document.getElementById('explorerPanel');

    if (_debugActive) {
        toolbar.classList.add('active');
        varsPanel.classList.add('active');
        btnDebug.classList.add('debugging');
        btnDebug.disabled = false;
        btnRun.disabled = true;
        editor.setOption('readOnly', true);
        if (explorerPanel) explorerPanel.classList.add('sb-debug-locked');
        updateDebugInfo();
    } else {
        toolbar.classList.remove('active');
        varsPanel.classList.remove('active');
        btnDebug.classList.remove('debugging');
        btnDebug.disabled = false;
        btnRun.disabled = false;
        editor.setOption('readOnly', false);
        if (explorerPanel) explorerPanel.classList.remove('sb-debug-locked');
    }
}

function updateDebugInfo() {
    const info = document.getElementById('debugInfo');
    const tab = EXP.getActiveTab();
    const curLine = tab ? tab.debugCurrentLine : 0;
    if (_debugIdle) {
        info.textContent = currentLanguage === 'ko' ? 'CIW 호출 대기 중...' : 'Waiting for CIW call...';
    } else if (curLine > 0) {
        info.innerHTML = (currentLanguage === 'ko'
            ? `<strong>라인 ${curLine}</strong>에서 중단됨`
            : `Paused at <strong>line ${curLine}</strong>`);
    } else {
        info.textContent = currentLanguage === 'ko' ? '실행 중...' : 'Running...';
    }
}

function debugCleanup() {
    _debugActive = false;
    _debugIdle = false;
    // Reset all tabs' debug fields (preserve breakpoints across sessions)
    EXP.getTabs().forEach(t => {
        t.debugCurrentLine = 0;
        t.debugInsertableLines = [];
        t.debugFileId = null;
    });
    clearDebugHighlight();
    updateDebugUI();
    EXP.renderTabs(); // Re-render to show close buttons again
    // Clear variables panel
    document.getElementById('debugVarsContent').innerHTML = '';
}

function _showCursor() {
    const cmEl = editor && editor.getWrapperElement();
    if (cmEl) cmEl.classList.remove('sb-cursor-hidden');
}

// Python -> JS debug events
function onDebugEvent(data) {
    if (!data) return;
    _showCursor();
    if (data.type === 'idle') {
        // Store insertable_lines per file if provided
        const tabs = EXP.getTabs();
        if (data.files_info) {
            data.files_info.forEach(fi => {
                const tab = tabs.find(t => t.debugFileId === fi.file_id);
                if (tab) tab.debugInsertableLines = fi.insertable_lines || [];
            });
        } else if (data.insertable_lines) {
            // Backward compat: single-file
            const tab = tabs.find(t => t.debugFileId === 0);
            if (tab) tab.debugInsertableLines = data.insertable_lines;
        }
        appendOutput('info', currentLanguage === 'ko'
            ? '[대기 중] CIW에서 함수를 호출하면 디버깅이 시작됩니다.'
            : '[Idle] Procedures loaded. Call a function from CIW to start debugging.');
        _debugIdle = true;
        updateDebugInfo();
    } else if (data.type === 'break') {
        _debugIdle = false;
        const fileId = data.file_id != null ? data.file_id : 0;
        const targetTab = EXP.getTabs().find(t => t.debugFileId === fileId);
        const activeTab = EXP.getActiveTab();

        // Cross-file navigation: switch to the target tab
        if (targetTab && activeTab && targetTab.id !== activeTab.id) {
            // Clear highlight on old tab before switching
            clearDebugHighlight();
            EXP.switchTab(targetTab.id);
        }

        if (targetTab) {
            targetTab.debugCurrentLine = data.line || 0;
            if (data.insertable_lines) targetTab.debugInsertableLines = data.insertable_lines;
        }
        if (data.output) data.output.forEach(o => appendOutput('ok', o));
        const fileName = targetTab ? targetTab.name : '';
        const lineInfo = fileName ? `${fileName}:${data.line}` : `${data.line}`;
        appendOutput('info', (currentLanguage === 'ko' ? '중단점 도달: 라인 ' : 'Break at line ') + lineInfo);
        clearDebugHighlight();
        highlightDebugLine(data.line);
        updateDebugInfo();
    } else if (data.type === 'ended') {
        _debugIdle = false;
        if (data.output) data.output.forEach(o => appendOutput('ok', o));
        appendOutput('info', currentLanguage === 'ko' ? '[디버그 완료]' : '[Debug Finished]');
        debugCleanup();
    } else if (data.type === 'error') {
        _debugIdle = false;
        if (data.error && data.error.indexOf('CIW not responding') !== -1) {
            _updateCiwCombo(_selectedCiw, true);
        }
        appendOutput('err', data.error || 'Debug error');
        debugCleanup();
    } else if (data.type === 'stopped') {
        _debugIdle = false;
        debugCleanup();
    }
}

// ── Output Collapse ───────────────────────────────────────────────────────────
let _outputCollapsed = false;
let _outputSavedSize = null;  // height (bottom) or width (right)

function _collapseIcon(collapsed) {
    // bottom layout: ⌄ / ⌃,  right layout: › / ‹
    if (currentLayout === 'bottom') return collapsed ? '⌃' : '⌄';
    return collapsed ? '‹' : '›';
}

function toggleOutputCollapse() {
    const outputPanel = document.getElementById('outputPanel');
    const btn = document.getElementById('outputCollapseBtn');
    const resizer = document.getElementById('resizer');
    const isBottom = currentLayout === 'bottom';
    const header = outputPanel.querySelector('.sb-panel-header');

    if (!_outputCollapsed) {
        if (isBottom) {
            _outputSavedSize = outputPanel.offsetHeight;
            const headerH = header.offsetHeight;
            outputPanel.style.setProperty('height', headerH + 'px', 'important');
            outputPanel.style.setProperty('min-height', headerH + 'px', 'important');
        } else {
            _outputSavedSize = outputPanel.offsetWidth;
            outputPanel.classList.add('collapsed-right');
        }
        if (resizer) resizer.style.pointerEvents = 'none';
        btn.textContent = _collapseIcon(true);
        _outputCollapsed = true;
    } else {
        if (isBottom) {
            const restoreH = _outputSavedSize || 120;
            outputPanel.style.setProperty('height', restoreH + 'px', 'important');
            outputPanel.style.removeProperty('min-height');
        } else {
            const restoreW = _outputSavedSize || 380;
            outputPanel.classList.remove('collapsed-right');
            outputPanel.style.width = restoreW + 'px';
        }
        if (resizer) resizer.style.pointerEvents = '';
        btn.textContent = _collapseIcon(false);
        _outputCollapsed = false;
    }
    if (editor) editor.refresh();
}

// ── Resizer ───────────────────────────────────────────────────────────────────
function initResizer() {
    const resizer     = document.getElementById('resizer');
    const outputPanel = document.getElementById('outputPanel');
    const main        = document.getElementById('main') || document.querySelector('.sb-main');
    let startX, startY, startWidth, startHeight;

    resizer.addEventListener('mousedown', e => {
        e.preventDefault();
        const isBottom = currentLayout === 'bottom';

        if (isBottom) {
            startY = e.clientY;
            startHeight = outputPanel.offsetHeight;
        } else {
            startX = e.clientX;
            startWidth = outputPanel.offsetWidth;
        }

        document.body.style.cursor = isBottom ? 'row-resize' : 'col-resize';
        document.body.style.userSelect = 'none';

        function onMove(e) {
            if (isBottom) {
                const delta = startY - e.clientY;
                const newH = Math.max(80, Math.min(window.innerHeight * 0.7, startHeight + delta));
                outputPanel.style.setProperty('height', newH + 'px', 'important');
            } else {
                const delta = startX - e.clientX;
                const newW = Math.max(200, Math.min(window.innerWidth * 0.7, startWidth + delta));
                outputPanel.style.width = newW + 'px';
            }
        }

        function onUp() {
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            if (editor) editor.refresh();
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });

}

// ── Intellisense ──────────────────────────────────────────────────────────────
const ISK = (() => {
    // State
    let _dropdown = null;
    let _sigBox = null;
    let _items = [];          // [{name, signatures}]
    let _activeIdx = 0;
    let _sigData = null;      // {name, signatures, arguments, returns, arg_index}
    // Functions excluded from intellisense (SKILL-like names that conflict with other tools)
    const _intellisenseExclude = new Set([
        'ac', 'average', 'bandwidth', 'clip', 'cross', 'dc', 'delete', 'design',
        'i', 'ic', 'ip', 'noise', 'off', 'option', 'peak', 'phase', 'plot',
        'report', 'restore', 'resume', 'root', 'sample', 'save', 'setup',
        'temp', 'v', 'view', 'watch',
    ]);
    let _completeTimer = null;
    let _sigTimer = null;
    let _parseTimer = null;
    let _lastWord = '';
    let _lastChangeTime = 0;  // timestamp of last onChange event
    let _suppressChange = false;   // true during programmatic setValue
    let _sigShownByCursor = false; // true if signature was shown via cursor-idle (not typing)
    let _lastMouseX = 0, _lastMouseY = 0;  // last mousemove coords on editor
    let _sigRequestMouseX = 0, _sigRequestMouseY = 0; // mouse coords when sig timer started
    let _cursorMovedByKeyboard = false; // true if cursor last moved via keyboard (not mouse)

    // ── Local symbol cache ──
    // _localFuncs: { name -> { params: [string], startOffset, endOffset } }  — active tab only
    // _localScopes: [ { type:'let'|'letseq'|'letrec'|'prog', vars:[string], startOffset, endOffset } ] — active tab only
    // _tabFuncsCache: { tabId -> { funcs, scopes } } — one entry per open tab
    let _localFuncs = {};
    let _localScopes = [];
    let _lastParsedContent = '';
    let _tabFuncsCache = {};   // persists across tab switches

    // ── Undefined variable warning state ──
    let _undefMarks = [];           // active TextMarkers for undef warnings
    let _nowarnNames = new Set();   // names suppressed via ;; @skillbot(no-warn:name)
    const _skillBuiltins = new Set();  // populated by CodeMirror.initSKILLBuiltins
    const _intellisenseFuncs = new Set(); // all DB function names (intellisense candidates)

    // ── Occurrence highlight state ──
    let _occurrenceMarks = [];      // active TextMarkers for same-word highlights
    let _occurrenceWord = '';       // currently highlighted word

    // ── Goto Definition state ──
    let _gotoMark = null;           // current TextMarker for underline
    let _gotoCm = null;             // cm instance for cleanup

    // ── SKILL local symbol parser ──

    // Skip whitespace and comments, return new index
    function _skipWS(src, i) {
        while (i < src.length) {
            // whitespace
            if (/\s/.test(src[i])) { i++; continue; }
            // line comment
            if (src[i] === ';') {
                while (i < src.length && src[i] !== '\n') i++;
                continue;
            }
            // block comment
            if (src[i] === '/' && src[i+1] === '*') {
                i += 2;
                while (i < src.length - 1 && !(src[i] === '*' && src[i+1] === '/')) i++;
                if (i < src.length - 1) i += 2;
                continue;
            }
            break;
        }
        return i;
    }

    // Read an identifier at position i, return {name, start, end} or null
    function _readIdent(src, i) {
        i = _skipWS(src, i);
        if (i >= src.length || !/[a-zA-Z_]/.test(src[i])) return null;
        let start = i;
        while (i < src.length && /[\w!?]/.test(src[i])) i++;
        return { name: src.slice(start, i), start, end: i };
    }

    // Find matching close paren for open paren at pos (src[pos] should be '(' or '[')
    function _matchParen(src, pos) {
        const open = src[pos];
        const close = open === '(' ? ')' : ']';
        let depth = 1;
        let i = pos + 1;
        let inStr = false;
        let inBlockComment = false;
        while (i < src.length && depth > 0) {
            if (inBlockComment) {
                if (src[i] === '*' && src[i+1] === '/') { inBlockComment = false; i += 2; continue; }
                i++; continue;
            }
            if (src[i] === '/' && src[i+1] === '*') { inBlockComment = true; i += 2; continue; }
            if (src[i] === ';' && !inStr) {
                while (i < src.length && src[i] !== '\n') i++;
                continue;
            }
            if (src[i] === '"') {
                if (!inStr) { inStr = true; i++; continue; }
                // check escape
                let bs = 0; let k = i - 1;
                while (k >= pos && src[k] === '\\') { bs++; k--; }
                if (bs % 2 === 0) inStr = false;
                i++; continue;
            }
            if (inStr) { i++; continue; }
            if (src[i] === open) depth++;
            else if (src[i] === close) depth--;
            i++;
        }
        return depth === 0 ? i - 1 : -1;
    }

    // Parse procedure parameter list string into a flat array of parameter names.
    // Handles: plain params, @optional/@rest/@key tags, (name default) pairs.
    function _parseProcParams(paramStr) {
        const params = [];
        let i = 0;
        while (i < paramStr.length) {
            // Skip whitespace
            while (i < paramStr.length && /\s/.test(paramStr[i])) i++;
            if (i >= paramStr.length) break;
            // @optional, @rest, @key — skip the tag itself, not a param name
            if (paramStr[i] === '@') {
                while (i < paramStr.length && !/\s/.test(paramStr[i])) i++;
                continue;
            }
            // (name default) pair — extract first identifier as the param name
            if (paramStr[i] === '(') {
                i++;
                while (i < paramStr.length && /\s/.test(paramStr[i])) i++;
                const start = i;
                while (i < paramStr.length && /[\w!?]/.test(paramStr[i])) i++;
                if (i > start) params.push(paramStr.slice(start, i));
                // Skip to matching ')'
                let depth = 1;
                while (i < paramStr.length && depth > 0) {
                    if (paramStr[i] === '(') depth++;
                    else if (paramStr[i] === ')') depth--;
                    i++;
                }
                continue;
            }
            // Plain identifier
            if (/[a-zA-Z_]/.test(paramStr[i])) {
                const start = i;
                while (i < paramStr.length && /[\w!?]/.test(paramStr[i])) i++;
                params.push(paramStr.slice(start, i));
                continue;
            }
            i++;
        }
        return params;
    }

    // Parse all local symbols from SKILL source code.
    // SKILL uses prefix-call syntax: keyword(args...) — NOT (keyword args...)
    function _parseLocalSymbols(src) {
        const funcs = {};   // name -> { params, startOffset, endOffset }
        const scopes = [];  // { type, vars, startOffset, endOffset }

        const procKeywords = new Set([
            'procedure', 'nprocedure', 'mprocedure', 'defun'
        ]);
        const letKeywords = new Set([
            'let', 'letseq', 'letrec', 'prog'
        ]);
        const scopeKeywords = new Set([
            'let', 'letseq', 'letrec', 'prog', 'foreach', 'for', 'lambda', 'nlambda'
        ]);

        // Scan character by character looking for identifiers followed by '('
        let i = 0;
        let inStr = false;
        let inBlockComment = false;

        while (i < src.length) {
            // Block comment
            if (inBlockComment) {
                if (src[i] === '*' && src[i+1] === '/') { inBlockComment = false; i += 2; }
                else i++;
                continue;
            }
            if (src[i] === '/' && src[i+1] === '*') { inBlockComment = true; i += 2; continue; }

            // Line comment
            if (src[i] === ';') {
                while (i < src.length && src[i] !== '\n') i++;
                continue;
            }

            // String literal
            if (src[i] === '"') {
                i++;
                while (i < src.length) {
                    if (src[i] === '\\') { i += 2; continue; }
                    if (src[i] === '"') { i++; break; }
                    i++;
                }
                continue;
            }

            // Identifier start
            if (/[a-zA-Z_]/.test(src[i])) {
                const identStart = i;
                while (i < src.length && /[\w!?]/.test(src[i])) i++;
                const kw = src.slice(identStart, i);

                // Skip whitespace between keyword and '('
                let j = i;
                while (j < src.length && (src[j] === ' ' || src[j] === '\t')) j++;

                if (j < src.length && src[j] === '(') {
                    const formStart = identStart;  // keyword is the start of the form
                    const outerClose = _matchParen(src, j);
                    const formEnd = outerClose >= 0 ? outerClose + 1 : src.length;

                    if (procKeywords.has(kw)) {
                        // procedure(name(p1 p2) body...)
                        let k = j + 1;
                        k = _skipWS(src, k);

                        // Read function name
                        const nameId = _readIdent(src, k);
                        if (nameId) {
                            let m = nameId.end;
                            m = _skipWS(src, m);
                            if (m < src.length && src[m] === '(') {
                                // name(p1 p2 @optional (name1 v1) ...)
                                const paramClose = _matchParen(src, m);
                                if (paramClose > 0) {
                                    const paramStr = src.slice(m + 1, paramClose).trim();
                                    const params = _parseProcParams(paramStr);
                                    funcs[nameId.name] = { params, startOffset: formStart, endOffset: formEnd, nameOffset: nameId.start };
                                }
                            } else {
                                // procedure(name) — no params
                                funcs[nameId.name] = { params: [], startOffset: formStart, endOffset: formEnd, nameOffset: nameId.start };
                            }
                        }
                        i = j + 1;
                        continue;
                    }

                    if (kw === 'lambda' || kw === 'nlambda') {
                        // lambda((p1 p2) body...)
                        let k = j + 1;
                        k = _skipWS(src, k);
                        if (k < src.length && src[k] === '(') {
                            const paramClose = _matchParen(src, k);
                            if (paramClose > 0) {
                                const paramStr = src.slice(k + 1, paramClose).trim();
                                const params = paramStr ? paramStr.split(/\s+/).filter(p => p.length > 0) : [];
                                if (params.length > 0) {
                                    scopes.push({ type: 'lambda', vars: params, startOffset: formStart, endOffset: formEnd });
                                }
                            }
                        }
                        i = j + 1;
                        continue;
                    }

                    if (letKeywords.has(kw)) {
                        // let((v1 v2 ...) body...) or let(((v1 e1)(v2 e2)) body...)
                        let k = j + 1;
                        k = _skipWS(src, k);
                        if (k < src.length && src[k] === '(') {
                            const bindClose = _matchParen(src, k);
                            if (bindClose > 0) {
                                const bindStr = src.slice(k + 1, bindClose).trim();
                                const vars = [];
                                if (kw === 'prog') {
                                    // prog((v1 v2) body) — bare var list
                                    bindStr.split(/\s+/).forEach(v => {
                                        if (v && /^[a-zA-Z_]/.test(v)) vars.push(v);
                                    });
                                } else {
                                    // let((v1 v2) body) — bare list
                                    // let(((v1 e1)(v2 e2)) body) — pair list
                                    let bi = 0;
                                    while (bi < bindStr.length) {
                                        while (bi < bindStr.length && /\s/.test(bindStr[bi])) bi++;
                                        if (bi >= bindStr.length) break;
                                        if (bindStr[bi] === '(') {
                                            // (varname expr) pair
                                            bi++;
                                            while (bi < bindStr.length && /\s/.test(bindStr[bi])) bi++;
                                            const vs = bi;
                                            while (bi < bindStr.length && /[\w!?]/.test(bindStr[bi])) bi++;
                                            if (bi > vs) vars.push(bindStr.slice(vs, bi));
                                            // skip to matching )
                                            let depth = 1;
                                            while (bi < bindStr.length && depth > 0) {
                                                if (bindStr[bi] === '(') depth++;
                                                else if (bindStr[bi] === ')') depth--;
                                                bi++;
                                            }
                                        } else if (/[a-zA-Z_]/.test(bindStr[bi])) {
                                            const vs = bi;
                                            while (bi < bindStr.length && /[\w!?]/.test(bindStr[bi])) bi++;
                                            vars.push(bindStr.slice(vs, bi));
                                        } else {
                                            bi++;
                                        }
                                    }
                                }
                                if (vars.length > 0) {
                                    scopes.push({ type: kw, vars, startOffset: formStart, endOffset: formEnd });
                                }
                            }
                        }
                        i = j + 1;
                        continue;
                    }

                    if (kw === 'foreach' || kw === 'setof' || kw === 'exists' || kw === 'forall') {
                        // foreach(varname list body...) / setof(varname list filter)
                        let k = j + 1;
                        k = _skipWS(src, k);
                        const varId = _readIdent(src, k);
                        if (varId) {
                            scopes.push({ type: kw, vars: [varId.name], startOffset: formStart, endOffset: formEnd });
                        }
                        i = j + 1;
                        continue;
                    }

                    if (kw === 'for') {
                        // for(var 0 n body...) or for((var 0 n) body...)
                        let k = j + 1;
                        k = _skipWS(src, k);
                        if (k < src.length && src[k] === '(') {
                            const varId = _readIdent(src, k + 1);
                            if (varId) {
                                scopes.push({ type: 'for', vars: [varId.name], startOffset: formStart, endOffset: formEnd });
                            }
                        } else {
                            const varId = _readIdent(src, k);
                            if (varId) {
                                scopes.push({ type: 'for', vars: [varId.name], startOffset: formStart, endOffset: formEnd });
                            }
                        }
                        i = j + 1;
                        continue;
                    }
                }
                // Not a special keyword with '(' — just advance past identifier
                continue;
            }

            i++;
        }

        return { funcs, scopes };
    }

    // Get local symbols in scope at a given offset in the source
    function _getLocalSymbolsAtOffset(offset) {
        const symbols = [];
        const seen = new Set();

        // Add all locally-defined function names from the active tab (global scope)
        for (const name in _localFuncs) {
            if (!seen.has(name)) {
                seen.add(name);
                const f = _localFuncs[name];
                const sig = name + '(' + f.params.join(' ') + ')';
                symbols.push({ name, signatures: [sig], kind: 'function' });
            }
        }

        // Add function names from all other open tabs
        for (const tabId in _tabFuncsCache) {
            const cached = _tabFuncsCache[tabId];
            for (const name in cached.funcs) {
                if (!seen.has(name)) {
                    seen.add(name);
                    const f = cached.funcs[name];
                    const sig = name + '(' + f.params.join(' ') + ')';
                    symbols.push({ name, signatures: [sig], kind: 'function' });
                }
            }
        }

        // Add parameters of the enclosing function(s)
        for (const name in _localFuncs) {
            const f = _localFuncs[name];
            if (offset >= f.startOffset && offset <= f.endOffset) {
                for (const p of f.params) {
                    if (!seen.has(p)) {
                        seen.add(p);
                        symbols.push({ name: p, signatures: [], kind: 'param' });
                    }
                }
            }
        }

        // Add variables from enclosing let/prog/foreach scopes
        for (const scope of _localScopes) {
            if (offset >= scope.startOffset && offset <= scope.endOffset) {
                for (const v of scope.vars) {
                    if (!seen.has(v)) {
                        seen.add(v);
                        symbols.push({ name: v, signatures: [], kind: scope.type });
                    }
                }
            }
        }

        return symbols;
    }

    // Get cursor offset in the source
    function _cursorOffset(cm) {
        const cur = cm.getCursor();
        const lines = cm.getValue().split('\n');
        let offset = 0;
        for (let i = 0; i < cur.line; i++) offset += lines[i].length + 1;
        offset += cur.ch;
        return offset;
    }

    // Debounced re-parse of editor content
    function _scheduleReparse(cm) {
        clearTimeout(_parseTimer);
        _parseTimer = setTimeout(() => {
            const content = cm.getValue();
            if (content !== _lastParsedContent) {
                _lastParsedContent = content;
                const result = _parseLocalSymbols(content);
                _localFuncs = result.funcs;
                _localScopes = result.scopes;
                // Update cache for the active tab
                const activeTab = typeof EXP !== 'undefined' && EXP.getActiveTab ? EXP.getActiveTab() : null;
                if (activeTab) _tabFuncsCache[activeTab.id] = { funcs: result.funcs, scopes: result.scopes };
            }
            _updateUndefWarnings(cm);
        }, 300);
    }

    // Parse ;; @skillbot(no-warn:name) directives from source
    function _parseNowarn(src) {
        const names = new Set();
        const re = /;+[^\n]*@skillbot\(no-warn:([^)\s]+)\)/g;
        let m;
        while ((m = re.exec(src)) !== null) {
            names.add(m[1].trim());
        }
        return names;
    }

    // Highlight all occurrences of the selected word in the editor.
    function _updateOccurrenceHighlight(cm) {
        const sel = cm.getSelection();
        const word = sel.trim();

        // Only highlight if selection is a single word (letters, digits, underscore, no whitespace)
        const isWord = word.length > 1 && /^[\w?!$%^&*\-+<>=~]+$/.test(word) && !/\s/.test(word);

        if (!isWord) {
            if (_occurrenceMarks.length > 0) {
                _occurrenceMarks.forEach(mk => mk.clear());
                _occurrenceMarks = [];
                _occurrenceWord = '';
            }
            return;
        }

        if (word === _occurrenceWord) return; // no change

        _occurrenceMarks.forEach(mk => mk.clear());
        _occurrenceMarks = [];
        _occurrenceWord = word;

        // Get selected range to skip self
        const selFrom = cm.getCursor('from');
        const selTo = cm.getCursor('to');
        const selFromIdx = cm.indexFromPos(selFrom);
        const selToIdx = cm.indexFromPos(selTo);

        const content = cm.getValue();
        const re = new RegExp(word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
        let match;
        while ((match = re.exec(content)) !== null) {
            // Skip the currently selected occurrence
            if (match.index === selFromIdx && match.index + word.length === selToIdx) continue;
            const from = cm.posFromIndex(match.index);
            const to = cm.posFromIndex(match.index + word.length);
            const mk = cm.markText(from, to, { className: 'isk-occurrence' });
            _occurrenceMarks.push(mk);
        }
    }

    // Scan source for identifier usages that are not defined locally and mark them.
    // Only warns inside function/let/scope bodies — identifiers at file top-level are ignored.
    function _updateUndefWarnings(cm) {
        // Clear existing marks
        _undefMarks.forEach(mk => mk.clear());
        _undefMarks = [];

        const src = cm.getValue();
        _nowarnNames = _parseNowarn(src);

        // File-level function names are always valid anywhere in the file
        const funcNames = new Set(Object.keys(_localFuncs));

        // Collect all other tabs' function names too
        for (const tabId in _tabFuncsCache) {
            for (const name in _tabFuncsCache[tabId].funcs) funcNames.add(name);
        }

        if (funcNames.size === 0 && _localScopes.length === 0) return;

        const lines = src.split('\n');
        let lineOffset = 0;
        let inBlockComment = false;

        for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
            const line = lines[lineIdx];
            let i = 0;

            if (inBlockComment) {
                const end = line.indexOf('*/');
                if (end >= 0) { inBlockComment = false; i = end + 2; }
                else { lineOffset += line.length + 1; continue; }
            }

            while (i < line.length) {
                if (line[i] === '/' && line[i + 1] === '*') { inBlockComment = true; i += 2; continue; }
                if (line[i] === ';') break;
                if (line[i] === '"') {
                    i++;
                    while (i < line.length) {
                        if (line[i] === '\\') { i += 2; continue; }
                        if (line[i] === '"') { i++; break; }
                        i++;
                    }
                    continue;
                }
                // Skip quoted symbol: 'xxx
                if (line[i] === "'") { i++; while (i < line.length && /[\w!?]/.test(line[i])) i++; continue; }
                // Skip keyword arg: ?name
                if (line[i] === '?') { i++; while (i < line.length && /[\w!?]/.test(line[i])) i++; continue; }
                // Skip @rest/@optional/@key tags in procedure parameter lists
                if (line[i] === '@') {
                    const atStart = i; i++;
                    const tagEnd = i;
                    while (i < line.length && /[\w!?]/.test(line[i])) i++;
                    const tag = line.slice(tagEnd, i);
                    if (tag === 'rest' || tag === 'optional' || tag === 'key') continue;
                    i = atStart + 1; // not a known tag — rewind and let normal scanning handle the word
                }
                // Skip -> and ~> slot access: the identifier after -> or ~> is a slot name, not a variable
                if ((line[i] === '-' && line[i + 1] === '>') || (line[i] === '~' && line[i + 1] === '>')) {
                    i += 2;
                    while (i < line.length && /[\w!?]/.test(line[i])) i++;
                    continue;
                }
                // Skip member access after dot: xxx.name
                if (line[i] === '.' && i > 0 && /[\w!?]/.test(line[i - 1])) {
                    i++;
                    while (i < line.length && /[\w!?]/.test(line[i])) i++;
                    continue;
                }
                // Skip numeric literals including scientific notation (e.g. 1e-10, 1.5e+3)
                if (/[0-9]/.test(line[i])) {
                    while (i < line.length && /[0-9]/.test(line[i])) i++;
                    if (i < line.length && line[i] === '.') { i++; while (i < line.length && /[0-9]/.test(line[i])) i++; }
                    if (i < line.length && (line[i] === 'e' || line[i] === 'E')) {
                        i++;
                        if (i < line.length && (line[i] === '+' || line[i] === '-')) i++;
                        while (i < line.length && /[0-9]/.test(line[i])) i++;
                    }
                    continue;
                }
                if (/[a-zA-Z_]/.test(line[i])) {
                    const start = i;
                    while (i < line.length && /[\w!?]/.test(line[i])) i++;
                    const name = line.slice(start, i);

                    // Skip qualified name xxx.yyy — dot access, not a plain variable
                    if (i < line.length && line[i] === '.') {
                        i++;
                        while (i < line.length && /[\w!?]/.test(line[i])) i++;
                        continue;
                    }

                    const offset = lineOffset + start;

                    // Skip if followed by '(' — it's a function call name, not a variable
                    let j = i;
                    while (j < line.length && (line[j] === ' ' || line[j] === '\t')) j++;
                    if (line[j] === '(') continue;

                    // Skip SKILL keywords and builtins
                    if (CodeMirror.skillKeywords && CodeMirror.skillKeywords[name]) continue;
                    if (_skillBuiltins.has(name)) continue;
                    if (_intellisenseFuncs.has(name)) continue;

                    // Skip nowarn names
                    if (_nowarnNames.has(name)) continue;

                    // Skip function names (always valid)
                    if (funcNames.has(name)) continue;

                    // Only warn if this offset is inside some local scope (procedure body / let)
                    const enclosingScope = _getEnclosingLocalScope(offset);
                    if (!enclosingScope) continue; // top-level — no warning

                    // Check if name is visible in scope at this offset
                    if (_isVisibleInScope(name, offset)) continue;

                    // Skip definition sites (e.g. the function name in procedure(foo(...)))
                    if (_isDefinitionSite(name, offset)) continue;

                    const from = { line: lineIdx, ch: start };
                    const to   = { line: lineIdx, ch: i };
                    const mk = cm.markText(from, to, { className: 'isk-undef-var' });
                    _undefMarks.push(mk);
                    continue;
                }
                i++;
            }
            lineOffset += line.length + 1;
        }
    }

    // Returns the innermost function or let scope containing offset, or null if top-level
    function _getEnclosingLocalScope(offset) {
        let best = null;
        // Check procedure bodies
        for (const fname in _localFuncs) {
            const f = _localFuncs[fname];
            if (offset >= f.startOffset && offset < f.endOffset) {
                if (!best || (f.endOffset - f.startOffset) < (best.endOffset - best.startOffset)) {
                    best = f;
                }
            }
        }
        // Check let/prog/foreach/for scopes
        for (const scope of _localScopes) {
            if (offset >= scope.startOffset && offset < scope.endOffset) {
                if (!best || (scope.endOffset - scope.startOffset) < (best.endOffset - best.startOffset)) {
                    best = scope;
                }
            }
        }
        return best;
    }

    // Returns true if `name` is visible (in scope) at `offset`
    function _isVisibleInScope(name, offset) {
        // Function params: visible inside the procedure body
        for (const fname in _localFuncs) {
            const f = _localFuncs[fname];
            if (offset >= f.startOffset && offset < f.endOffset) {
                if (f.params.includes(name)) return true;
            }
        }
        // Let/prog/foreach/for vars: visible inside that scope
        for (const scope of _localScopes) {
            if (offset >= scope.startOffset && offset < scope.endOffset) {
                if (scope.vars.includes(name)) return true;
            }
        }
        return false;
    }

    // Returns true if `offset` is the definition site of `name`
    function _isDefinitionSite(name, offset) {
        if (_localFuncs[name]) {
            const f = _localFuncs[name];
            const nameOff = f.nameOffset !== undefined ? f.nameOffset : f.startOffset;
            if (offset === nameOff) return true;
        }
        return false;
    }

    // ── Goto Definition ──

    // Convert linear offset to {line, ch} for CodeMirror
    function _offsetToPos(cm, offset) {
        const lines = cm.getValue().split('\n');
        let remaining = offset;
        for (let i = 0; i < lines.length; i++) {
            if (remaining <= lines[i].length) return { line: i, ch: remaining };
            remaining -= lines[i].length + 1;
        }
        return { line: lines.length - 1, ch: lines[lines.length - 1].length };
    }

    // Find the definition offset of a name in the source.
    // Returns { defOffset, kind } or null.
    function _findDefinition(name, tokenOffset) {
        // 1. local function definition — but NOT when hovering on the definition itself
        if (_localFuncs[name]) {
            const f = _localFuncs[name];
            const nameOff = f.nameOffset !== undefined ? f.nameOffset : f.startOffset;
            // If the token IS the definition site, don't offer a link
            if (tokenOffset === nameOff) return null;
            return { defOffset: nameOff, kind: 'function' };
        }

        // 2. parameter of enclosing function
        for (const fname in _localFuncs) {
            const f = _localFuncs[fname];
            if (tokenOffset >= f.startOffset && tokenOffset <= f.endOffset) {
                if (f.params.includes(name)) {
                    // Find the exact offset of this param inside the param list
                    const src = _lastParsedContent;
                    // Search for the param name starting from nameOffset
                    let searchFrom = f.nameOffset !== undefined ? f.nameOffset : f.startOffset;
                    // Skip past function name and opening paren of param list
                    while (searchFrom < src.length && /[\w!?]/.test(src[searchFrom])) searchFrom++;
                    while (searchFrom < src.length && src[searchFrom] !== '(') searchFrom++;
                    searchFrom++; // skip '('
                    // Find param in the param list
                    const paramRe = new RegExp('\\b' + name.replace(/[!?]/g, '\\$&') + '\\b');
                    const paramStr = src.slice(searchFrom);
                    const m = paramRe.exec(paramStr);
                    if (m) return { defOffset: searchFrom + m.index, kind: 'param' };
                    // fallback: jump to function name
                    return { defOffset: f.nameOffset !== undefined ? f.nameOffset : f.startOffset, kind: 'param' };
                }
            }
        }

        // 3. local variable from enclosing scope
        for (const scope of _localScopes) {
            if (tokenOffset >= scope.startOffset && tokenOffset <= scope.endOffset) {
                if (scope.vars.includes(name)) {
                    // Find exact offset of this var name within the binding list
                    const src = _lastParsedContent;
                    // scope.startOffset points to the keyword (let/prog/...)
                    // Find the opening '(' of the binding list
                    let searchFrom = scope.startOffset;
                    while (searchFrom < src.length && src[searchFrom] !== '(') searchFrom++;
                    searchFrom++; // skip keyword's '('
                    // Skip whitespace and find inner '(' of binding list
                    while (searchFrom < src.length && /\s/.test(src[searchFrom])) searchFrom++;
                    if (searchFrom < src.length && src[searchFrom] === '(') searchFrom++; // skip inner '('
                    // Now search for the var name
                    const varRe = new RegExp('\\b' + name.replace(/[!?]/g, '\\$&') + '\\b');
                    const varStr = src.slice(searchFrom);
                    const mv = varRe.exec(varStr);
                    if (mv) return { defOffset: searchFrom + mv.index, kind: scope.type };
                    return { defOffset: scope.startOffset, kind: scope.type };
                }
            }
        }

        return null;
    }

    // Get identifier token under a mouse event in CodeMirror
    function _getTokenAtMouseEvent(cm, e) {
        const pos = cm.coordsChar({ left: e.clientX, top: e.clientY }, 'window');
        const token = cm.getTokenAt(pos);
        if (!token || !token.string || !/^[a-zA-Z_][\w!?]*$/.test(token.string)) return null;
        // Verify the mouse is actually over the token's rendered character range,
        // not just past the end of a short line where coordsChar snaps to EOL.
        const startCoords = cm.charCoords({ line: pos.line, ch: token.start }, 'window');
        const endCoords   = cm.charCoords({ line: pos.line, ch: token.end },   'window');
        if (e.clientX < startCoords.left || e.clientX > endCoords.right ||
            e.clientY < startCoords.top  || e.clientY > endCoords.bottom) return null;
        // Suppress underline for tokens immediately after -> or ~> (slot/method access)
        const lineText = cm.getLine(pos.line);
        const before = lineText.slice(0, token.start).trimEnd();
        if (before.endsWith('->') || before.endsWith('~>')) return null;
        // Compute offset of token start
        const src = cm.getValue();
        const lines = src.split('\n');
        let offset = 0;
        for (let i = 0; i < pos.line; i++) offset += lines[i].length + 1;
        offset += token.start;
        return { name: token.string, offset, tokenStart: { line: pos.line, ch: token.start }, tokenEnd: { line: pos.line, ch: token.end } };
    }

    // Clear the goto underline mark
    function _clearGotoMark(cm) {
        if (_gotoMark) { _gotoMark.clear(); _gotoMark = null; }
        if (cm) cm.getWrapperElement().classList.remove('isk-gotodef-active');
        _gotoCm = null;
    }

    // Apply underline to token under mouse; show pointer cursor only when Ctrl is held
    function _updateGotoMark(cm, e) {
        const tok = _getTokenAtMouseEvent(cm, e);
        if (!tok) { _clearGotoMark(cm); return; }

        const def = _findDefinition(tok.name, tok.offset);
        if (!def) { _clearGotoMark(cm); return; }

        // Check if the mark already covers this exact range to avoid flicker
        if (_gotoMark && _gotoCm === cm) {
            const range = _gotoMark.find();
            if (range && range.from.line === tok.tokenStart.line &&
                range.from.ch === tok.tokenStart.ch &&
                range.to.ch === tok.tokenEnd.ch) {
                // Mark exists — just update pointer cursor based on Ctrl state
                const wrapper = cm.getWrapperElement();
                if (e && e.ctrlKey) wrapper.classList.add('isk-gotodef-active');
                else wrapper.classList.remove('isk-gotodef-active');
                return;
            }
        }

        _clearGotoMark(cm);
        _gotoMark = cm.markText(tok.tokenStart, tok.tokenEnd, { className: 'isk-gotodef-mark' });
        _gotoCm = cm;
        if (e && e.ctrlKey) cm.getWrapperElement().classList.add('isk-gotodef-active');
    }

    // Handle click: jump to definition (no Ctrl required)
    function _handleGotoClick(cm, e) {
        if (!_gotoMark) return; // only jump if a mark is currently shown
        const tok = _getTokenAtMouseEvent(cm, e);
        if (!tok) return;
        const def = _findDefinition(tok.name, tok.offset);
        if (!def) return;

        e.preventDefault();
        e.stopPropagation();
        _clearGotoMark(cm);

        const pos = _offsetToPos(cm, def.defOffset);
        cm.setCursor(pos);
        cm.scrollIntoView(pos, 100);
        cm.focus();
    }

    // Wire up hover/click events on the CodeMirror instance
    function _initGotoDef(cm) {
        const wrapper = cm.getWrapperElement();

        wrapper.addEventListener('mousemove', (e) => {
            _updateGotoMark(cm, e);
        });

        wrapper.addEventListener('mouseleave', () => {
            _clearGotoMark(cm);
        });

        wrapper.addEventListener('mousedown', (e) => {
            if (e.button === 0 && e.ctrlKey) {
                _handleGotoClick(cm, e);
            }
        }, true); // capture phase so we get it before CodeMirror

        // Update pointer cursor when Ctrl is pressed/released while hovering
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Control' && _gotoMark) wrapper.classList.add('isk-gotodef-active');
        });
        document.addEventListener('keyup', (e) => {
            if (e.key === 'Control') wrapper.classList.remove('isk-gotodef-active');
        });
    }

    function init() {
        _dropdown = document.getElementById('isk-dropdown');
        _dropdown.style.display = 'none';
        _sigBox   = document.getElementById('isk-signature');

        // Close dropdown when clicking outside the dropdown or editor
        document.addEventListener('mousedown', (e) => {
            if (_dropdown && _dropdown.style.display !== 'none') {
                if (!_dropdown.contains(e.target)) {
                    hideDropdown();
                }
            }
        }, true);
    }

    function initWithEditor(cm) {
        init();
        _initGotoDef(cm);
    }

    // ── Helpers ──

    function _currentWordAndPos(cm) {
        const cur = cm.getCursor();
        const line = cm.getLine(cur.line);
        let start = cur.ch;
        while (start > 0 && /[\w!?]/.test(line[start - 1])) start--;
        const word = line.slice(start, cur.ch);
        return { word, cur, line, start };
    }

    // Parse the function name and argument index at cursor position
    // Walks backward from cursor to find enclosing (funcName arg0 arg1 ...)
    function _parseFuncContext(cm) {
        const cur = cm.getCursor();
        const content = cm.getValue();
        // Convert cursor to linear offset
        const lines = content.split('\n');
        let offset = 0;
        for (let i = 0; i < cur.line; i++) offset += lines[i].length + 1;
        offset += cur.ch;

        let depth = 0;
        let argIdx = 0;
        let i = offset - 1;
        let inStr = false;   // inside a double-quoted string
        let inStrSingle = false; // inside a single-quoted string (SKILL uses ?)

        // If cursor is inside a string, skip backward to just before the
        // opening " so the backward parser doesn't see an unmatched quote.
        if (_isInString(cm)) {
            while (i >= 0 && content[i] !== '"') i--;
            // i now points at the opening "; move before it
            if (i >= 0) i--;
        }

        // Walk backward, counting parens and commas/spaces at depth 0
        while (i >= 0) {
            const ch = content[i];

            // Handle string boundaries (walking backward)
            if (ch === '"' && !inStrSingle) {
                // Count preceding backslashes to see if this quote is escaped
                let bs = 0;
                let k = i - 1;
                while (k >= 0 && content[k] === '\\') { bs++; k--; }
                if (bs % 2 === 0) inStr = !inStr;
                i--;
                continue;
            }
            // While inside a string, skip everything
            if (inStr) { i--; continue; }

            if (ch === ')') { depth++; }
            else if (ch === '(') {
                if (depth === 0) {
                    // Found the opening paren - now get the function name before it
                    let j = i - 1;
                    while (j >= 0 && content[j] === ' ') j--;
                    let end = j + 1;
                    while (j >= 0 && /[\w!?]/.test(content[j])) j--;
                    const funcName = content.slice(j + 1, end);
                    if (!funcName) return null;
                    // Forward-parse the argument tokens from '(' to cursor
                    const argTokens = _parseArgTokens(content, i + 1, offset);
                    return { funcName, argIdx, argTokens };
                }
                depth--;
            } else if (depth === 0 && ch === '\n') {
                // Newline at depth 0 means the opening '(' is on a different line - close intellisense
                return null;
            } else if (depth === 0 && (ch === ' ' || ch === '\t')) {
                // Spaces between args - count transitions
                // (SKILL uses prefix notation: funcName is first, args follow separated by spaces)
                // Count if: next char is a non-space/non-paren token, OR cursor is right after this space
                if (i === offset - 1 || (i < offset - 1 && /[^\s(]/.test(content[i + 1]))) argIdx++;
            }
            i--;
        }
        return null;
    }

    // Forward-parse argument tokens from position start up to (not including) end.
    // Returns array of token strings (e.g. ["lib", "cell", "?view", "myview"])
    function _parseArgTokens(content, start, end) {
        const tokens = [];
        let i = start;
        let inStr = false;
        while (i < end) {
            const ch = content[i];
            if (ch === '"') {
                inStr = !inStr;
                i++;
                continue;
            }
            if (inStr) { i++; continue; }
            if (ch === ' ' || ch === '\n' || ch === '\t') { i++; continue; }
            // collect token
            let j = i;
            if (ch === '"') {
                // string token
                j++;
                while (j < end && content[j] !== '"') j++;
                if (j < end) j++;
            } else {
                while (j < end && content[j] !== ' ' && content[j] !== '\n' && content[j] !== '\t') j++;
            }
            const tok = content.slice(i, j).trim();
            if (tok) tokens.push(tok);
            i = j;
        }
        return tokens;
    }

    // ── Dropdown ──

    function _showDropdown(cm, items) {
        _items = items;
        _activeIdx = 0;
        if (!items.length) { hideDropdown(); return; }

        const cur = cm.getCursor();
        const coords = cm.charCoords(cur, 'window');

        _dropdown.innerHTML = items.map((it, idx) => {
            const sig = it.signatures && it.signatures[0] ? it.signatures[0] : '';
            const shortSig = sig.length > 50 ? sig.slice(0, 47) + '…' : sig;
            // Kind badge for local symbols
            let badge = '';
            if (it.kind === 'function') badge = '<span class="isk-item-badge isk-badge-fn">fn</span>';
            else if (it.kind === 'param') badge = '<span class="isk-item-badge isk-badge-var">arg</span>';
            else if (it.kind) badge = '<span class="isk-item-badge isk-badge-var">var</span>';
            return `<div class="isk-item${idx === 0 ? ' isk-active' : ''}" data-idx="${idx}"
                onclick="ISK.pick(${idx})"
                onmouseover="ISK.setActive(${idx})">
                ${badge}<span class="isk-item-name">${it.name}</span>
                ${shortSig ? `<span class="isk-item-sig">${_esc(shortSig)}</span>` : ''}
            </div>`;
        }).join('');

        _dropdown.style.left = coords.left + 'px';
        _dropdown.style.top  = (coords.bottom + 2) + 'px';
        _dropdown.style.display = 'block';
    }

    let _suppressSigRestore = false;

    function hideDropdown() {
        if (_dropdown) _dropdown.style.display = 'none';
        _items = [];
        // Restore signature hint if cursor is still inside a function call
        if (editor && !_suppressSigRestore) onCursorActivity(editor);
    }

    function setActive(idx) {
        _activeIdx = idx;
        var activeEl = null;
        _dropdown.querySelectorAll('.isk-item').forEach((el, i) => {
            el.classList.toggle('isk-active', i === idx);
            if (i === idx) activeEl = el;
        });
        if (activeEl) {
            const top = activeEl.offsetTop;
            const bottom = top + activeEl.offsetHeight;
            const scrollTop = _dropdown.scrollTop;
            const viewBottom = scrollTop + _dropdown.clientHeight;
            if (top < scrollTop) {
                _dropdown.scrollTop = top;
            } else if (bottom > viewBottom) {
                _dropdown.scrollTop = bottom - _dropdown.clientHeight;
            }
        }
    }

    function pick(idx) {
        if (!editor) return;
        const item = _items[idx];
        if (!item) return;
        hideDropdown();

        // @skillbot directive pick: replace only the prefix after '@skillbot('
        if (item.kind === 'skillbot') {
            const cur = editor.getCursor();
            const line = editor.getLine(cur.line);
            const tagIdx = line.lastIndexOf('@skillbot(', cur.ch);
            if (tagIdx >= 0) {
                const replaceFrom = { line: cur.line, ch: tagIdx + '@skillbot('.length };
                editor.replaceRange(item.name, replaceFrom, cur);
                editor.focus();
            }
            return;
        }

        const { word, cur, start } = _currentWordAndPos(editor);
        // Pre-set _lastWord to the completed name so onChange does not re-trigger completion
        _lastWord = item.name;
        _suppressSigRestore = true;
        editor.replaceRange(item.name, { line: cur.line, ch: start }, cur);
        _suppressSigRestore = false;

        // Trigger signature hint for the picked function
        setTimeout(() => _fetchSignature(editor, item.name, 0, []), 50);
    }

    // ── Signature hint ──

    // Parse the signature parameter string into token groups.
    // Returns an array of token groups, each group:
    //   { text: string, parts: [{text, highlight}], isVararg: bool, isKeyPair: bool, keyName: string }
    // Examples:
    //   "formatString [arg1 ...]"  => [{text:"formatString"}, {text:"[arg1 ...]", isVararg:true}]
    //   "[?key1 name1] [?key2 name2]" => [{isKeyPair:true, keyName:"?key1", ...}, ...]
    function _parseSigParams(paramsStr) {
        const tokens = [];
        let i = 0;
        const s = paramsStr.trim();
        while (i < s.length) {
            // skip whitespace
            while (i < s.length && s[i] === ' ') i++;
            if (i >= s.length) break;

            if (s[i] === '[') {
                // Find matching ] (also tracks {} depth inside)
                let j = i + 1;
                let depth = 1;
                let braceDepth = 0;
                while (j < s.length && depth > 0) {
                    if (s[j] === '{') braceDepth++;
                    else if (s[j] === '}') braceDepth--;
                    else if (braceDepth === 0) {
                        if (s[j] === '[') depth++;
                        else if (s[j] === ']') depth--;
                    }
                    j++;
                }
                const inner = s.slice(i + 1, j - 1).trim();
                const text = s.slice(i, j);
                // Check vararg: ends with " ..." e.g. "[arg1 ...]"
                const isVararg = inner.endsWith('...');
                // Check key pair: starts with ?  e.g. "[?key name]"
                const innerParts = inner.split(/\s+/);
                const isKeyPair = innerParts.length === 2 && innerParts[0].startsWith('?');
                // Optional single-word param: [xxx] - not vararg, not keypair => skip in positional mapping
                const isOptional = !isVararg && !isKeyPair;
                tokens.push({
                    text,
                    inner,
                    innerParts,
                    isVararg,
                    isKeyPair,
                    isOptional,
                    keyName: isKeyPair ? innerParts[0] : null,
                    valueName: isKeyPair ? innerParts[1] : null,
                });
                i = j;
            } else if (s[i] === '{') {
                // {opt1 | opt2 | ...} - treat as single token
                let j = i + 1;
                let depth = 1;
                while (j < s.length && depth > 0) {
                    if (s[j] === '{') depth++;
                    else if (s[j] === '}') depth--;
                    j++;
                }
                tokens.push({ text: s.slice(i, j), inner: s.slice(i + 1, j - 1).trim(), isVararg: false, isKeyPair: false });
                i = j;
            } else {
                // plain token (stop at space, [, {)
                let j = i;
                while (j < s.length && s[j] !== ' ' && s[j] !== '[' && s[j] !== '{') j++;
                tokens.push({ text: s.slice(i, j), inner: s.slice(i, j), isVararg: false, isKeyPair: false });
                i = j;
            }
        }
        return tokens;
    }

    // Given parsed sig tokens, argTokens (already-typed arguments), and argIdx (cursor position),
    // determine which sig token (and sub-part for key pairs) to highlight.
    // Returns array of {html} for rendering.
    //
    // Key-pair matching rules:
    //   - Non-keypair sig tokens consume argTokens in order.
    //   - KeyPair sig tokens ([?key val]) are optional and matched by ?key name.
    //   - When a ?xxx argToken is encountered, find the first matching [?xxx val] in sig
    //     at or after the current sig position (forward only).
    //   - Unknown ?xxx (no match) advances to the next keypair slot anyway (error tolerance).
    //   - The value token following a matched ?key maps to that keypair's val.
    //   - argIdx points to the current cursor token (0-based among argTokens).
    function _mapSigHighlight(tokens, argIdx, argTokens) {
        let highlightToken = -1;
        let highlightSubPart = -1; // 0=key, 1=value (for keypairs)

        // Split sig tokens into two categories with their sig indices:
        // - positional: non-keypair tokens (consumed in order)
        // - keypair pool: {ti, keyName} available from sig position onward
        // We walk argTokens one by one and simulate which sig token each maps to.

        // Build sig token index lists
        const positional = []; // sig indices of non-keypair, non-optional tokens
        const keypairMap = {}; // keyName -> ti
        for (let ti = 0; ti < tokens.length; ti++) {
            const tok = tokens[ti];
            if (tok.isKeyPair) {
                keypairMap[tok.keyName] = ti;
            } else if (!tok.isOptional) {
                // isOptional ([xxx] single-word) tokens are skipped in positional mapping
                positional.push(ti);
            }
        }

        let posIdx = 0;       // index into positional array
        let lastVarargTi = -1;
        // Track which keypair we last matched (for the following value token)
        let pendingKeyPairTi = -1; // sig ti of a matched ?key, waiting for its value token

        const totalArgs = argIdx + 1; // process up to cursor position (inclusive)
        // We'll track the highlight after processing all tokens up to argIdx

        // Track which keypair sig indices have been used (to enforce forward-only)
        // "forward-only" means once we pass a keypair's position in the sig, we can't go back.
        // We track: lastUsedKeyPairTi - the sig ti of the last matched keypair.
        let lastUsedKeyPairTi = -1;

        for (let ai = 0; ai < totalArgs; ai++) {
            const isLast = (ai === argIdx);
            const argTok = argTokens[ai] || '';

            if (pendingKeyPairTi >= 0) {
                // Previous token was a matched ?key; this token is its value
                if (isLast) {
                    highlightToken = pendingKeyPairTi;
                    highlightSubPart = 1;
                }
                pendingKeyPairTi = -1;
                continue;
            }

            if (argTok.startsWith('?')) {
                // Try to match a keypair by name, forward only
                const matchTi = keypairMap[argTok];
                if (matchTi !== undefined && matchTi > lastUsedKeyPairTi) {
                    // Valid forward match
                    lastUsedKeyPairTi = matchTi;
                    if (isLast) {
                        highlightToken = matchTi;
                        highlightSubPart = 0;
                    } else {
                        pendingKeyPairTi = matchTi;
                    }
                } else {
                    // Unknown ?key or backward reference - advance to next keypair slot
                    // Find the next keypair in sig after lastUsedKeyPairTi
                    let nextKpTi = -1;
                    for (let ti = lastUsedKeyPairTi + 1; ti < tokens.length; ti++) {
                        if (tokens[ti].isKeyPair) { nextKpTi = ti; break; }
                    }
                    if (nextKpTi >= 0) {
                        lastUsedKeyPairTi = nextKpTi;
                        if (isLast) {
                            highlightToken = nextKpTi;
                            highlightSubPart = 0;
                        } else {
                            pendingKeyPairTi = nextKpTi;
                        }
                    } else {
                        // No more keypairs - just highlight nothing extra
                        if (isLast) { highlightToken = -1; highlightSubPart = -1; }
                    }
                }
            } else {
                // Regular token - consume from positional list
                if (posIdx < positional.length) {
                    const sigTi = positional[posIdx];
                    const sigTok = tokens[sigTi];
                    if (sigTok.isVararg) {
                        // Vararg: stay on this slot
                        lastVarargTi = sigTi;
                        if (isLast) { highlightToken = sigTi; highlightSubPart = -1; }
                        // Don't advance posIdx for vararg
                    } else {
                        if (isLast) { highlightToken = sigTi; highlightSubPart = -1; }
                        posIdx++;
                    }
                } else if (lastVarargTi >= 0) {
                    if (isLast) { highlightToken = lastVarargTi; highlightSubPart = -1; }
                }
            }
        }

        const rendered = tokens.map((tok, ti) => {
            const active = ti === highlightToken;
            if (tok.isKeyPair) {
                const keyActive = active && highlightSubPart === 0;
                const valActive = active && highlightSubPart === 1;
                return {
                    html: `[<span class="isk-sig-arg${keyActive ? ' isk-sig-active' : ''}">${_esc(tok.keyName)}</span>` +
                          ` <span class="isk-sig-arg${valActive ? ' isk-sig-active' : ''}">${_esc(tok.valueName)}</span>]`
                };
            } else {
                const cls = 'isk-sig-arg' + (active ? ' isk-sig-active' : '');
                return { html: `<span class="${cls}">${_esc(tok.text)}</span>` };
            }
        });
        return { rendered, highlightToken, highlightSubPart };
    }

    function _showSignature(cm, sigData) {
        _sigData = sigData;
        if (!sigData || !sigData.signatures || !sigData.signatures.length) {
            hideSig(); return;
        }

        const sig = sigData.signatures[0];
        const args = sigData.arguments || [];
        const argIdx = sigData.arg_index || 0;
        const argTokens = sigData.arg_tokens || [];

        // Build colored signature HTML
        // sig looks like: funcName(formatString [arg1 ...]) => t
        const parenOpen = sig.indexOf('(');
        if (parenOpen < 0) {
            _sigBox.innerHTML = `<span class="isk-sig-func">${_esc(sig)}</span>`;
        } else {
            const funcPart = sig.slice(0, parenOpen);
            // Extract params string from inside parentheses
            const parenClose = sig.lastIndexOf(')');
            const paramsStr = parenClose > parenOpen ? sig.slice(parenOpen + 1, parenClose) : sig.slice(parenOpen + 1);

            let argsHtml = '';
            let activeParamName = null;
            const sigTokens = _parseSigParams(paramsStr);
            if (sigTokens.length) {
                const { rendered, highlightToken, highlightSubPart } =
                    _mapSigHighlight(sigTokens, argIdx, argTokens);
                argsHtml = rendered.map(r => r.html).join('<span class="isk-sig-sep"> </span>');
                // Determine active param name for description
                if (highlightToken >= 0) {
                    const htok = sigTokens[highlightToken];
                    if (htok.isKeyPair) {
                        activeParamName = highlightSubPart === 1 ? htok.valueName : htok.keyName;
                    } else if (htok.isVararg) {
                        activeParamName = htok.innerParts ? htok.innerParts[0] : htok.inner;
                    } else {
                        activeParamName = htok.text.replace(/^\[|\]$/g, '');
                    }
                }
            } else {
                argsHtml = `<span class="isk-sig-arg">${_esc(paramsStr)}</span>`;
            }

            let retHtml = '';
            if (sigData.returns && sigData.returns.length) {
                const ret = sigData.returns[0];
                retHtml = `<div class="isk-sig-ret">→ ${_esc(ret.type_name || ret.prefix || '')}</div>`;
            }

            let argDescHtml = '';
            if (activeParamName && args.length) {
                const matchArg = args.find(a => a.name === activeParamName);
                if (matchArg && matchArg.description) {
                    const desc = matchArg.description.replace(/<[^>]*>/g, '').slice(0, 80);
                    argDescHtml = `<div class="isk-sig-ret">${_esc(desc)}</div>`;
                }
            }

            _sigBox.innerHTML =
                `<span class="isk-sig-func">${_esc(funcPart)}</span>` +
                `<span class="isk-sig-paren">(</span>` +
                argsHtml +
                `<span class="isk-sig-paren">)</span>` +
                retHtml + argDescHtml;
        }

        const cur = cm.getCursor();
        const coords = cm.charCoords(cur, 'window');
        _sigBox.style.left = coords.left + 'px';
        _sigBox.style.top  = (coords.top - _sigBox.offsetHeight - 6) + 'px';
        _sigBox.style.display = 'block';

        // Reposition after render (offsetHeight now correct)
        requestAnimationFrame(() => {
            _sigBox.style.top = (coords.top - _sigBox.offsetHeight - 6) + 'px';
        });
    }

    function hideSig() {
        if (_sigBox) _sigBox.style.display = 'none';
        _sigData = null;
        _sigShownByCursor = false;
    }

    // ── Backend calls ──

    function _fetchComplete(cm, word, sigVisible) {
        if (!word || word.length < 2) { hideDropdown(); return; }
        clearTimeout(_completeTimer);
        _completeTimer = setTimeout(() => {
            // Gather local symbols that match the prefix
            const offset = _cursorOffset(cm);
            const localAll = _getLocalSymbolsAtOffset(offset);
            const wLower = word.toLowerCase();
            const localPrefix = [];
            for (const sym of localAll) {
                const nl = sym.name.toLowerCase();
                if (nl.startsWith(wLower)) localPrefix.push(sym);
            }
            const localHits = localPrefix;

            // While a signature hint is visible, hide it temporarily so the completion
            // dropdown can show DB results. The signature is restored when the dropdown
            // closes (via onCursorActivity) or when the user picks an item (via pick()).
            if (sigVisible) hideSig();

            if (typeof callPython !== 'function') {
                // No backend — show local-only results
                if (localHits.length) _showDropdown(cm, localHits);
                else hideDropdown();
                return;
            }
            callPython('intellisense_complete', { q: word, limit: 15 }).then(res => {
                const dbResults = (res && res.success && res.results) ? res.results : [];
                // Merge: local first, then DB (skip duplicates, excluded names, and non-prefix matches)
                const seen = new Set(localHits.map(s => s.name));
                const merged = localHits.slice();
                for (const r of dbResults) {
                    if (_intellisenseExclude.has(r.name)) continue;
                    if (!r.name.toLowerCase().startsWith(wLower)) continue;
                    if (!seen.has(r.name)) {
                        seen.add(r.name);
                        merged.push(r);
                    }
                }
                if (merged.length) _showDropdown(cm, merged);
                else hideDropdown();
            }).catch(() => {
                if (localHits.length) _showDropdown(cm, localHits);
                else hideDropdown();
            });
        }, 150);
    }

    function _fetchSignature(cm, funcName, argIdx, argTokens, delay, byCursor) {
        if (!funcName) return;
        if (_debugActive) return;
        if (delay === undefined) delay = 80;
        clearTimeout(_sigTimer);
        _sigRequestMouseX = _lastMouseX;
        _sigRequestMouseY = _lastMouseY;
        _sigTimer = setTimeout(() => {
            // If triggered by cursor idle, cancel if mouse moved or cursor moved by keyboard
            if (byCursor && _cursorMovedByKeyboard) return;
            if (byCursor && (Math.abs(_lastMouseX - _sigRequestMouseX) > 10 || Math.abs(_lastMouseY - _sigRequestMouseY) > 10)) return;
            // Check local functions first (active tab, then other tabs)
            let localFunc = _localFuncs[funcName];
            if (!localFunc) {
                for (const tabId in _tabFuncsCache) {
                    if (_tabFuncsCache[tabId].funcs[funcName]) {
                        localFunc = _tabFuncsCache[tabId].funcs[funcName];
                        break;
                    }
                }
            }
            if (localFunc) {
                const sig = funcName + '(' + localFunc.params.join(' ') + ')';
                const args = localFunc.params.map(p => ({ name: p, description: '' }));
                const localSig = {
                    success: true,
                    name: funcName,
                    signatures: [sig],
                    arguments: args,
                    returns: [],
                    arg_index: argIdx,
                    arg_tokens: argTokens || [],
                };
                _sigShownByCursor = !!byCursor;
                _showSignature(cm, localSig);
                return;
            }
            // Fall back to DB
            if (typeof callPython !== 'function') { hideSig(); return; }
            if (_intellisenseExclude.has(funcName)) { hideSig(); return; }
            callPython('intellisense_signature', { name: funcName, arg_index: argIdx }).then(res => {
                if (res && res.success) {
                    res.arg_tokens = argTokens || [];
                    _sigShownByCursor = !!byCursor;
                    _showSignature(cm, res);
                } else {
                    hideSig();
                }
            }).catch(() => hideSig());
        }, delay);
    }

    // ── CodeMirror event handlers ──

    // If cursor is on the function name itself (e.g. on "printf" in "printf(...)"),
    // return the function name so signature can be shown.
    function _parseFuncNameAtCursor(cm) {
        const cur = cm.getCursor();
        const line = cm.getLine(cur.line);
        // Find word boundaries around cursor
        let start = cur.ch;
        while (start > 0 && /[\w!?]/.test(line[start - 1])) start--;
        let end = cur.ch;
        while (end < line.length && /[\w!?]/.test(line[end])) end++;
        if (end === start) return null;
        const word = line.slice(start, end);
        // The character right after the word must be '('
        const afterWord = line[end];
        if (afterWord !== '(') return null;
        return word;
    }

    function onCursorActivity(cm) {
        _updateOccurrenceHighlight(cm);
        // Update signature arg highlight when cursor moves inside a call
        const ctx = _parseFuncContext(cm);
        const typedRecently = (Date.now() - _lastChangeTime) < 500;
        if (ctx) {
            if (_sigData && _sigData.name === ctx.funcName) {
                // Already have signature data — if shown by cursor-idle, close on next move
                if (_sigShownByCursor && !typedRecently) {
                    hideSig();
                    clearTimeout(_sigTimer);
                    return;
                }
                _sigData.arg_index = ctx.argIdx;
                _sigData.arg_tokens = ctx.argTokens;
                _showSignature(cm, _sigData);
            } else {
                if (_sigShownByCursor && !typedRecently) {
                    hideSig();
                }
                _fetchSignature(cm, ctx.funcName, ctx.argIdx, ctx.argTokens,
                                typedRecently ? 80 : 2000, !typedRecently);
            }
        } else {
            // Check if cursor is on the function name itself (before the open paren)
            const funcName = _parseFuncNameAtCursor(cm);
            if (funcName) {
                if (_sigShownByCursor && !typedRecently) {
                    hideSig();
                }
                _fetchSignature(cm, funcName, 0, [], typedRecently ? 80 : 2000, !typedRecently);
            } else {
                hideSig();
            }
        }
    }

    // Alt+G: goto definition at cursor
    function gotoDefinitionAtCursor(cm) {
        const cur = cm.getCursor();
        const line = cm.getLine(cur.line);
        // Find full word around cursor
        let start = cur.ch;
        let end = cur.ch;
        while (start > 0 && /[\w!?]/.test(line[start - 1])) start--;
        while (end < line.length && /[\w!?]/.test(line[end])) end++;
        const name = line.slice(start, end);
        if (!name || !/^[a-zA-Z_]/.test(name)) return;

        // Compute offset of the token start
        const src = cm.getValue();
        const lines = src.split('\n');
        let offset = 0;
        for (let i = 0; i < cur.line; i++) offset += lines[i].length + 1;
        offset += start;

        const def = _findDefinition(name, offset);
        if (!def) return;

        _clearGotoMark(cm);
        const pos = _offsetToPos(cm, def.defOffset);
        cm.setCursor(pos);
        cm.scrollIntoView(pos, 100);
        cm.focus();
    }

    function onKeyDown(cm, e) {
        if (e.key === 'Enter') {
            clearTimeout(_completeTimer);
        }
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown' || e.key === 'ArrowLeft' || e.key === 'ArrowRight' ||
            e.key === 'Home' || e.key === 'End' || e.key === 'PageUp' || e.key === 'PageDown') {
            _cursorMovedByKeyboard = true;
        }
        if (e.altKey && e.key === 'g') {
            e.preventDefault();
            gotoDefinitionAtCursor(cm);
            return;
        }
        if (_dropdown.style.display !== 'none') {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActive(Math.min(_activeIdx + 1, _items.length - 1));
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActive(Math.max(_activeIdx - 1, 0));
                return;
            }
            if (e.key === 'PageDown') {
                e.preventDefault();
                setActive(Math.min(_activeIdx + 5, _items.length - 1));
                return;
            }
            if (e.key === 'PageUp') {
                e.preventDefault();
                setActive(Math.max(_activeIdx - 5, 0));
                return;
            }
            if (e.key === 'Enter' || e.key === 'Tab') {
                if (_items.length > 0) {
                    e.preventDefault();
                    pick(_activeIdx);
                } else {
                    hideDropdown();
                }
                return;
            }
            if (e.key === 'Escape' || e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                hideDropdown();
                return;
            }
        }
        if (e.key === 'Escape' && _sigBox && _sigBox.style.display !== 'none') {
            e.preventDefault();
            hideSig();
            return;
        }
    }

    function _isInString(cm) {
        const cur = cm.getCursor();
        const token = cm.getTokenAt(cur);
        return token && token.type && token.type.indexOf('string') !== -1;
    }

    function _isInComment(cm) {
        const cur = cm.getCursor();
        const token = cm.getTokenAt(cur);
        return token && token.type && token.type.indexOf('comment') !== -1;
    }

    // Detect if cursor is inside a ;...@skillbot( ) context.
    // Returns the typed prefix after '@skillbot(' (may be empty), or null if not in context.
    function _getSkillbotDirectivePrefix(cm) {
        const cur = cm.getCursor();
        const line = cm.getLine(cur.line);
        const upToCursor = line.slice(0, cur.ch);
        const tagIdx = upToCursor.indexOf('@skillbot(');
        if (tagIdx < 0) return null;
        // Everything after '@skillbot(' up to cursor is the typed prefix
        return upToCursor.slice(tagIdx + '@skillbot('.length);
    }

    // @skillbot directives: { name, insert, description }
    const SKILLBOT_DIRECTIVES = [
        { name: 'no-warn',   insert: 'no-warn:',      desc: 'Suppress undefined-variable warning for a name' },
        { name: 'run-debug', insert: 'run-debug:',    desc: 'Expression to run when starting debug' },
    ];

    function _showSkillbotDropdown(cm, prefix) {
        const matched = SKILLBOT_DIRECTIVES.filter(d => d.name.startsWith(prefix));
        if (!matched.length) { hideDropdown(); return; }

        const cur = cm.getCursor();
        const coords = cm.charCoords(cur, 'window');

        _items = matched.map(d => ({ name: d.insert, signatures: [d.desc], kind: 'skillbot' }));
        _activeIdx = 0;

        _dropdown.innerHTML = matched.map((d, idx) => `
            <div class="isk-item${idx === 0 ? ' isk-active' : ''}" data-idx="${idx}"
                onclick="ISK.pick(${idx})"
                onmouseover="ISK.setActive(${idx})">
                <span class="isk-item-badge isk-badge-fn">tag</span>
                <span class="isk-item-name">${d.insert}</span>
                <span class="isk-item-sig">${_esc(d.desc)}</span>
            </div>`).join('');

        _dropdown.style.left = coords.left + 'px';
        _dropdown.style.top  = (coords.bottom + 2) + 'px';
        _dropdown.style.display = 'block';
    }

    function onChange(cm) {
        if (!_suppressChange) _lastChangeTime = Date.now();
        if (!_suppressChange) _scheduleReparse(cm);

        // @skillbot directive completion takes priority (works inside comments)
        const sbPrefix = _getSkillbotDirectivePrefix(cm);
        if (sbPrefix !== null) {
            _showSkillbotDropdown(cm, sbPrefix);
            return;
        }

        const { word } = _currentWordAndPos(cm);
        if (word !== _lastWord) {
            _lastWord = word;
            const startsWithDigit = word.length > 0 && /^[0-9]/.test(word);
            // Suppress completion dropdown while a signature hint is visible
            // (i.e. cursor is on the first line of a function call, inside the open paren).
            // Once the call spans to a new line, _parseFuncContext returns null and
            // the signature is hidden, so completion becomes available again.
            const sigVisible = _sigBox && _sigBox.style.display !== 'none';
            if (word.length >= 2 && !_isInString(cm) && !_isInComment(cm) && !startsWithDigit) {
                _fetchComplete(cm, word, sigVisible);
            } else if (!_isInString(cm)) {
                hideDropdown();
            }
            // When inside a string, keep the current dropdown as-is (don't close, don't fetch)
        }
    }

    function _esc(s) {
        if (!s) return '';
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function setEditorValue(cm, value, tabId) {
        _suppressChange = true;
        cm.setValue(value);
        cm.clearHistory();
        _suppressChange = false;
        _lastChangeTime = 0;
        // Parse local symbols immediately on content load
        _lastParsedContent = value;
        const result = _parseLocalSymbols(value);
        _localFuncs = result.funcs;
        _localScopes = result.scopes;
        // Update per-tab cache
        if (tabId != null) _tabFuncsCache[tabId] = { funcs: result.funcs, scopes: result.scopes };
        _updateUndefWarnings(cm);
    }

    let _hoverTimer = null;

    function onHover(cm, e) {
        if (_debugActive) return;
        clearTimeout(_hoverTimer);
        _hoverTimer = setTimeout(() => {
            const coords = { left: e.clientX, top: e.clientY };
            const pos = cm.coordsChar(coords, 'window');
            const token = cm.getTokenAt(pos);
            if (!token || !token.string || token.type === 'comment' || token.type === 'string') return;
            // Check we're hovering over an actual word token
            const word = token.string.trim();
            if (!word || word.length < 2 || /^[0-9]/.test(word)) return;
            // Only show signature if the token is immediately followed by '('
            // (i.e. the hovered word is a function call site, not a variable or keyword)
            const line = cm.getLine(pos.line) || '';
            const charAfterToken = line[token.end];
            if (charAfterToken !== '(') return;
            _fetchSignature(cm, word, 0, [], 0, true);
        }, 2000);
    }

    function trackMouseMove(e) { _lastMouseX = e.clientX; _lastMouseY = e.clientY; _cursorMovedByKeyboard = false; }

    function setIntellisenseFuncs(names) {
        _intellisenseFuncs.clear();
        for (const name of names) _intellisenseFuncs.add(name);
    }

    return { init, initWithEditor, pick, setActive, hideDropdown, hideSig, onKeyDown, onChange, onCursorActivity, setEditorValue, onHover, trackMouseMove, tabFuncsCache: _tabFuncsCache, parseSymbols: _parseLocalSymbols, setIntellisenseFuncs };
})();

// ── File Explorer ─────────────────────────────────────────────────────────────
const EXP = (() => {
    let _root = null;
    let _tree = {};             // { dirPath: [entries] }
    let _expanded = new Set();
    let _activeFile = null;     // path of active tab (null = untitled)
    let _suppressDirty = false;
    let _ctxEntry = null;

    // ── Tab management ──────────────────────────────────────────────────────
    // Each tab: { id, path (null=untitled), name, dirty, content, debugBreakpoints, debugCurrentLine, debugInsertableLines, debugFileId, debugEnabled }
    let _tabs = [];
    let _activeTabId = null;
    let _nextTabId = 1;

    function _makeTab(path, name, content, mtime) {
        const c = content || '';
        return {
            id: _nextTabId++, path, name: name || 'untitled.il', dirty: false, content: c, savedContent: c,
            mtime: mtime || null,
            cursor: null, scrollInfo: null, history: null,
            debugBreakpoints: new Set(),
            debugCurrentLine: 0,
            debugInsertableLines: [],
            debugFileId: null,
            changedOnDisk: false,
            debugEnabled: false,
        };
    }

    function _getActiveTab() {
        return _tabs.find(t => t.id === _activeTabId) || null;
    }

    function _disposeTabTooltips() {
        if (!window.bootstrap || !bootstrap.Tooltip) return;
        const bar = document.getElementById('editorTabBar');
        if (!bar) return;
        bar.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
            const tip = bootstrap.Tooltip.getInstance(el);
            if (tip) tip.dispose();
        });
    }

    let _dragTabId = null;

    function _renderTabs() {
        _disposeTabTooltips();
        const bar = document.getElementById('editorTabBar');
        if (!bar) return;
        bar.innerHTML = _tabs.map(tab => {
            const active = tab.id === _activeTabId ? ' active' : '';
            const dirty = tab.dirty ? ' dirty' : '';
            const closeHidden = _debugActive ? ' style="display:none"' : '';
            return `<div class="sb-tab${active}${dirty}" data-tabid="${tab.id}" data-tabname="${_esc(tab.name)}" draggable="true">` +
                `<span class="sb-tab-name">${_esc(tab.name)}</span>` +
                `<span class="sb-tab-dirty"></span>` +
                `<span class="sb-tab-close" data-tabid="${tab.id}"${closeHidden}>✕</span>` +
                `</div>`;
        }).join('');
        // Init Bootstrap tooltips only when name is truncated (scrollWidth > clientWidth)
        bar.querySelectorAll('.sb-tab').forEach(el => {
            const nameEl = el.querySelector('.sb-tab-name');
            if (nameEl && nameEl.scrollWidth > nameEl.clientWidth) {
                el.setAttribute('data-bs-toggle', 'tooltip');
                el.setAttribute('data-bs-placement', 'bottom');
                el.setAttribute('data-bs-title', el.dataset.tabname);
                if (window.bootstrap && bootstrap.Tooltip) new bootstrap.Tooltip(el, { trigger: 'hover' });
            }
        });
        bar.querySelectorAll('.sb-tab').forEach(el => {
            el.addEventListener('click', e => {
                if (e.target.classList.contains('sb-tab-close')) return;
                _switchTab(parseInt(el.dataset.tabid));
            });
            el.addEventListener('mousedown', e => {
                if (e.button === 1) {
                    e.preventDefault();
                    _closeTab(parseInt(el.dataset.tabid));
                    // Block mouseup and auxclick that follow middle-click to prevent selection paste
                    const block = ev => { ev.preventDefault(); ev.stopPropagation(); };
                    document.addEventListener('mouseup',  block, { capture: true, once: true });
                    document.addEventListener('auxclick', block, { capture: true, once: true });
                }
            });
            el.addEventListener('contextmenu', e => {
                e.preventDefault();
                _hideTabCtxMenu();
                _tabCtxId = parseInt(el.dataset.tabid);
                const menu = document.getElementById('tabCtxMenu');
                if (!menu) return;
                // Disable "Copy File Path" for untitled tabs
                const tab = _tabs.find(t => t.id === _tabCtxId);
                const copyItem = document.getElementById('tabCtxCopyPath');
                if (copyItem) copyItem.style.opacity = (tab && tab.path) ? '' : '0.4';
                // "Allow Debugging" item: only for IL tabs, show check mark when enabled
                const debugItem = document.getElementById('tabCtxDebugEnable');
                const debugSep  = document.getElementById('tabCtxDebugSep');
                if (debugItem) {
                    const isIL = tab && _isILTab(tab);
                    debugItem.style.display = isIL ? '' : 'none';
                    if (debugSep) debugSep.style.display = isIL ? '' : 'none';
                    const checked = tab && tab.debugEnabled;
                    const label = currentLanguage === 'ko' ? '디버깅 허용' : 'Allow Debugging';
                    debugItem.innerHTML = '<span class="sb-ctx-check' + (checked ? ' checked' : '') + '"></span>' + label;
                }
                menu.style.left = e.clientX + 'px';
                menu.style.top = e.clientY + 'px';
                menu.style.display = 'block';
                setTimeout(() => {
                    document.addEventListener('mousedown', function handler(e) {
                        const menu = document.getElementById('tabCtxMenu');
                        if (menu && menu.contains(e.target)) return;
                        _hideTabCtxMenu();
                        document.removeEventListener('mousedown', handler, true);
                    }, true);
                }, 0);
            });
            // Drag-to-reorder
            el.addEventListener('dragstart', e => {
                _dragTabId = parseInt(el.dataset.tabid);
                el.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            });
            el.addEventListener('dragend', () => {
                _dragTabId = null;
                bar.querySelectorAll('.sb-tab').forEach(t => {
                    t.classList.remove('dragging', 'drag-over', 'drag-over-end');
                });
            });
            el.addEventListener('dragover', e => {
                if (_dragTabId === null || _dragTabId === parseInt(el.dataset.tabid)) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                bar.querySelectorAll('.sb-tab').forEach(t => t.classList.remove('drag-over'));
                el.classList.add('drag-over');
            });
            el.addEventListener('dragleave', () => {
                el.classList.remove('drag-over');
            });
            el.addEventListener('drop', e => {
                e.preventDefault();
                const targetId = parseInt(el.dataset.tabid);
                if (_dragTabId === null || _dragTabId === targetId) return;
                const fromIdx = _tabs.findIndex(t => t.id === _dragTabId);
                let toIdx     = _tabs.findIndex(t => t.id === targetId);
                if (fromIdx === -1 || toIdx === -1) return;
                // Determine insert before or after target based on cursor X position
                const rect = el.getBoundingClientRect();
                const insertAfter = (e.clientX - rect.left) > rect.width / 2;
                const [moved] = _tabs.splice(fromIdx, 1);
                // After removal, recalculate target index
                toIdx = _tabs.findIndex(t => t.id === targetId);
                _tabs.splice(insertAfter ? toIdx + 1 : toIdx, 0, moved);
                _renderTabs();
            });
        });
        bar.querySelectorAll('.sb-tab-close').forEach(el => {
            el.addEventListener('click', e => {
                e.stopPropagation();
                _closeTab(parseInt(el.dataset.tabid));
            });
        });
        // Drop zone at the end of the tab bar for moving a tab to the last position
        const dropEnd = document.createElement('div');
        dropEnd.style.cssText = 'flex: 1; min-width: 40px; height: 100%;';
        bar.appendChild(dropEnd);
        dropEnd.addEventListener('dragover', e => {
            if (_dragTabId === null) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            bar.querySelectorAll('.sb-tab').forEach(t => t.classList.remove('drag-over'));
            const allTabs = bar.querySelectorAll('.sb-tab');
            const lastTab = allTabs[allTabs.length - 1];
            if (lastTab) lastTab.classList.add('drag-over-end');
        });
        dropEnd.addEventListener('dragleave', () => {
            bar.querySelectorAll('.sb-tab').forEach(t => t.classList.remove('drag-over-end'));
        });
        dropEnd.addEventListener('drop', e => {
            if (_dragTabId === null) return;
            e.preventDefault();
            const fromIdx = _tabs.findIndex(t => t.id === _dragTabId);
            if (fromIdx === -1) return;
            const [moved] = _tabs.splice(fromIdx, 1);
            _tabs.push(moved);
            _renderTabs();
        });
    }

    let _tabCtxId = null;

    function _copyFallback(text) {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        try {
            document.execCommand('copy');
            appendOutput('info', 'Copied: ' + text);
        } catch (e) {
            appendOutput('err', 'Clipboard copy failed');
        }
        document.body.removeChild(ta);
    }

    function _hideTabCtxMenu() {
        const menu = document.getElementById('tabCtxMenu');
        if (menu) menu.style.display = 'none';
    }

    function tabCtxClose() {
        _hideTabCtxMenu();
        if (_tabCtxId !== null) _closeTab(_tabCtxId);
    }

    function tabCtxCopyPath() {
        _hideTabCtxMenu();
        const tab = _tabs.find(t => t.id === _tabCtxId);
        if (!tab || !tab.path) return;
        const text = tab.path;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => {
                appendOutput('info', 'Copied: ' + text);
            }).catch(() => _copyFallback(text));
        } else {
            _copyFallback(text);
        }
    }

    function tabCtxToggleDebug() {
        _hideTabCtxMenu();
        const tab = _tabs.find(t => t.id === _tabCtxId);
        if (!tab || !_isILTab(tab)) return;
        tab.debugEnabled = !tab.debugEnabled;
    }

    function _updateILButtons() {
        const il = isILFile();
        const btnRun   = document.getElementById('btnRun');
        const btnDebug = document.getElementById('btnDebug');
        if (btnRun)   btnRun.disabled   = !il;
        if (btnDebug) btnDebug.disabled = !il;
        // F9 breakpoint gutter: show only for IL files
        editor.setOption('gutters', il
            ? ['CodeMirror-linenumbers', 'sb-breakpoint-gutter']
            : ['CodeMirror-linenumbers']);
    }

    function _restoreDebugVisuals(tab) {
        if (!editor || !tab) return;
        // Restore breakpoint gutter markers
        tab.debugBreakpoints.forEach(lineNum => {
            const marker = document.createElement('div');
            marker.className = 'sb-bp-marker';
            editor.setGutterMarker(lineNum - 1, 'sb-breakpoint-gutter', marker);
        });
        // Restore debug current line highlight
        if (_debugActive && tab.debugCurrentLine > 0) {
            highlightDebugLine(tab.debugCurrentLine);
        }
    }

    function _switchTab(tabId) {
        const tab = _tabs.find(t => t.id === tabId);
        if (!tab || tab.id === _activeTabId) return;
        // Save current editor content and cursor/scroll/history state to current tab
        const cur = _getActiveTab();
        if (cur && editor) {
            cur.content = editor.getValue();
            cur.cursor = editor.getCursor();
            cur.scrollInfo = editor.getScrollInfo();
            cur.history = editor.getHistory();
        }
        _activeTabId = tabId;
        _activeFile = tab.path;
        _suppressDirty = true;
        ISK.setEditorValue(editor, tab.content, tabId);
        // Restore undo history for the new tab (setEditorValue clears it)
        if (tab.history) editor.setHistory(tab.history);
        setTimeout(() => { _suppressDirty = false; }, 0);
        // Restore cursor and scroll position for the new tab
        if (tab.cursor) editor.setCursor(tab.cursor);
        if (tab.scrollInfo) editor.scrollTo(tab.scrollInfo.left, tab.scrollInfo.top);
        editor.setOption('mode', _modeForFile(tab.name));
        _renderTabs();
        _render();
        _updateILButtons();
        // Restore breakpoints and debug line highlight for the new tab
        _restoreDebugVisuals(tab);
        // Show or hide disk-change banner for the newly-active tab
        _checkDiskChangeBannerOnSwitch(tab);
        editor.focus();
    }

    async function _closeTab(tabId) {
        if (_debugActive) return; // Block tab closing during debug
        const tab = _tabs.find(t => t.id === tabId);
        if (!tab) return;
        if (tab.dirty) {
            const msg = currentLanguage === 'ko'
                ? `'${tab.name}' 저장하지 않은 변경사항이 있습니다. 닫으시겠습니까?`
                : `'${tab.name}' has unsaved changes. Close anyway?`;
            const title = currentLanguage === 'ko' ? '저장하지 않은 변경사항' : 'Unsaved Changes';
            if (!await parent.showConfirmDialog(title, msg)) return;
        }
        const idx = _tabs.indexOf(tab);
        _tabs.splice(idx, 1);
        delete ISK.tabFuncsCache[tabId];  // remove from cross-tab cache
        delete _diskChangeDismissed[tabId];
        if (tabId === _activeTabId) _hideDiskChangeBar(tabId);
        if (_tabs.length === 0) {
            // Open a fresh untitled tab
            const fresh = _makeTab(null, 'untitled.il', '');
            _tabs.push(fresh);
            _activeTabId = fresh.id;
            _activeFile = null;
        } else if (tab.id === _activeTabId) {
            const next = _tabs[Math.min(idx, _tabs.length - 1)];
            _activeTabId = next.id;
            _activeFile = next.path;
        }
        const active = _getActiveTab();
        _suppressDirty = true;
        ISK.setEditorValue(editor, active ? active.content : '', active ? active.id : null);
        setTimeout(() => { _suppressDirty = false; }, 0);
        if (active) editor.setOption('mode', _modeForFile(active.name));
        _renderTabs();
        _render();
        _updateILButtons();
        if (active) _restoreDebugVisuals(active);
    }

    function _setDirty(val) {
        const tab = _getActiveTab();
        if (tab) tab.dirty = val;
        _renderTabs();
    }

    function init() {
        // Create initial untitled tab (only once)
        if (_tabs.length === 0) {
            const untitled = _makeTab(null, 'untitled.il', editor ? editor.getValue() : '');
            _tabs.push(untitled);
            _activeTabId = untitled.id;
            _renderTabs();
        }

        if (typeof callPython !== 'function') { setTimeout(init, 200); return; }

        // Right-click on empty area of explorer → show context menu (New File only)
        const body = document.getElementById('explorerBody');
        if (body && !body._ctxBound) {
            body._ctxBound = true;
            body.addEventListener('contextmenu', e => {
                if (!e.target.closest('.sb-tree-item')) {
                    e.preventDefault();
                    _ctxEntry = null;
                    _showCtxMenu(e.clientX, e.clientY, null);
                }
            });
        }

        callPython('file_get_root', {}).then(res => {
            if (res && res.success && res.path) {
                _root = res.path;
                _expanded.add(_root);
                _refreshDir(_root, () => _render());
            }
        }).catch(e => console.error('[EXP] init error:', e));

        _updateILButtons();
        _startDiskChangePolling();

        // Drag-and-drop from Nautilus: receive file paths via Python dropEvent override.
        // Python intercepts the native drop, extracts full paths from QMimeData,
        // then forwards them via CustomEvent('nativeFileDrop') and postMessage.
        if (!window._nativeFileDropBound) {
            window._nativeFileDropBound = true;
            function _handleNativeFileDrop(paths) {
                paths.forEach(p => { if (p) _openFile(p); });
            }
            document.addEventListener('nativeFileDrop', e => {
                _handleNativeFileDrop(e.detail.paths || []);
            });
            window.addEventListener('message', e => {
                if (e.data && e.data.type === 'nativeFileDrop') {
                    _handleNativeFileDrop(e.data.paths || []);
                }
            });
        }
    }

    function _refreshDir(dirPath, callback) {
        callPython('file_list_dir', { path: dirPath }).then(res => {
            _tree[dirPath] = (res && !res.error) ? (res.files || []) : [];
            if (callback) callback();
        }).catch(() => { _tree[dirPath] = []; if (callback) callback(); });
    }

    function _render() {
        const body = document.getElementById('explorerBody');
        if (!body || !_root) return;
        const html = [];
        const rootName = _root.split('/').filter(Boolean).pop() || _root;
        const isRootExpanded = _expanded.has(_root);
        html.push(
            `<div class="sb-tree-item" data-path="${_esc(_root)}" data-isdir="1">` +
            `<span class="sb-tree-indent" style="width:0px"></span>` +
            `<span class="sb-tree-icon"><span class="sb-tree-arrow ${isRootExpanded ? 'expanded' : 'collapsed'}"></span></span>` +
            `<span class="sb-tree-name">${_esc(rootName)}</span>` +
            `</div>`
        );
        if (isRootExpanded && _tree[_root]) {
            _renderDir(_root, 1, html);
        }
        body.innerHTML = html.join('');
        _attachEvents(body);
    }

    function _sortEntries(entries) {
        return [...entries].sort((a, b) => {
            // Directories first
            if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
            // For files: sort by extension, then by name
            if (!a.is_dir) {
                const extA = a.name.includes('.') ? a.name.split('.').pop().toLowerCase() : '';
                const extB = b.name.includes('.') ? b.name.split('.').pop().toLowerCase() : '';
                if (extA !== extB) return extA.localeCompare(extB);
            }
            return a.name.localeCompare(b.name);
        });
    }

    function _renderDir(dirPath, depth, html, parentIsDot) {
        const entries = _sortEntries(_tree[dirPath] || []);
        for (const entry of entries) {
            const indent = depth * 14;
            const isExpanded = _expanded.has(entry.path);
            const isActive = entry.path === _activeFile;
            const icon = entry.is_dir
                ? `<span class="sb-tree-arrow ${isExpanded ? 'expanded' : 'collapsed'}"></span>`
                : _fileIcon(entry.name);
            const isDotfile = parentIsDot || entry.name.startsWith('.');
            const cls = 'sb-tree-item' + (isActive ? ' active' : '') + (isDotfile ? ' dotfile' : '');
            html.push(
                `<div class="${cls}" data-path="${_esc(entry.path)}" data-isdir="${entry.is_dir ? '1' : ''}">` +
                `<span class="sb-tree-indent" style="width:${indent}px"></span>` +
                `<span class="sb-tree-icon">${icon}</span>` +
                `<span class="sb-tree-name">${_esc(entry.name)}</span>` +
                `</div>`
            );
            if (entry.is_dir && isExpanded && _tree[entry.path]) {
                _renderDir(entry.path, depth + 1, html, isDotfile);
            }
        }
    }

    const _iconThemeBase = 'resource/icon';
    // Preloaded set of theme-specific icon filenames (populated at init)
    let _iconThemeOverrides = null;

    function _loadIconThemeOverrides(theme) {
        // theme: 'dark' or 'light'
        // Files that exist in dark/ or light/ directories (source of truth).
        const knownOverrides = {
            dark:  ['md'],
            light: ['md'],
        };
        _iconThemeOverrides = { theme, files: new Set(knownOverrides[theme] || []) };
    }

    function _iconSrc(iconName) {
        if (_iconThemeOverrides && _iconThemeOverrides.files.has(iconName)) {
            return `${_iconThemeBase}/${_iconThemeOverrides.theme}/${iconName}.svg`;
        }
        return `${_iconThemeBase}/default/${iconName}.svg`;
    }

    function _fileIcon(name) {
        const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : '';
        let iconName;
        switch (ext) {
            case 'il':
            case 'ils':  iconName = 'il';   break;
            case 'py':   iconName = 'py';   break;
            case 'txt':  iconName = 'txt';  break;
            case 'md':   iconName = 'md';   break;
            case 'ini':  iconName = 'ini';  break;
            case 'html':
            case 'htm':  iconName = 'html'; break;
            case 'css':  iconName = 'css';  break;
            case 'js':   iconName = 'js';   break;
            case 'json': iconName = 'json'; break;
            case 'sh':
            case 'bash': iconName = 'sh';   break;
            case 'jpg':
            case 'jpeg':
            case 'png':
            case 'gif':
            case 'svg':
            case 'webp':
            case 'bmp':
            case 'ico':  iconName = 'img';  break;
            default:     iconName = 'file'; break;
        }
        return `<img src="${_iconSrc(iconName)}" alt="">`;
    }

    function _attachEvents(body) {
        body.querySelectorAll('.sb-tree-item').forEach(el => {
            const path = el.getAttribute('data-path');
            const isDir = !!el.getAttribute('data-isdir');
            el.addEventListener('click', e => {
                e.stopPropagation();
                if (isDir) _toggleDir(path);
                else _openFile(path);
            });
            el.addEventListener('contextmenu', e => {
                e.preventDefault();
                e.stopPropagation();
                const name = el.querySelector('.sb-tree-name').textContent;
                _showCtxMenu(e.clientX, e.clientY, { path, name, is_dir: isDir });
            });
        });
    }

    function _toggleDir(dirPath) {
        if (_expanded.has(dirPath)) {
            _expanded.delete(dirPath);
            _render();
        } else {
            _expanded.add(dirPath);
            if (!_tree[dirPath]) {
                _refreshDir(dirPath, () => _render());
            } else {
                _render();
            }
        }
    }

    function _openFile(filePath) {
        if (_debugActive) return Promise.resolve(); // Block new file opens during debug
        // If already open in a tab, just switch to it
        const existing = _tabs.find(t => t.path === filePath);
        if (existing) { _switchTab(existing.id); return Promise.resolve(); }
        // Save current tab content before loading
        const cur = _getActiveTab();
        if (cur && editor) cur.content = editor.getValue();
        return _loadFile(filePath);
    }

    function _modeForFile(name) {
        const ext = (name || '').split('.').pop().toLowerCase();
        const map = {
            'py': 'python',
            'html': 'htmlmixed', 'htm': 'htmlmixed',
            'css': 'css',
            'js': 'javascript',
            'md': 'markdown', 'markdown': 'markdown',
            'xml': 'xml', 'svg': 'xml',
            'json': 'javascript',
        };
        return map[ext] || 'skill';
    }

    function _loadFile(filePath) {
        return callPython('file_read', { path: filePath }).then(res => {
            if (res && res.error) { appendOutput('err', 'Cannot open: ' + res.error); return; }
            const name = filePath.split('/').pop();
            const content = res.content || '';
            const mtime   = res.mtime || null;
            // If active tab is an untitled empty tab, reuse it
            const cur = _getActiveTab();
            let tab;
            if (cur && cur.path === null && !cur.dirty && cur.content === '') {
                cur.path = filePath;
                cur.name = name;
                cur.content = content;
                cur.dirty = false;
                cur.mtime = mtime;
                cur.changedOnDisk = false;
                tab = cur;
            } else {
                tab = _makeTab(filePath, name, content, mtime);
                _tabs.push(tab);
                _activeTabId = tab.id;
            }
            _activeFile = filePath;
            // Pre-parse and cache symbols for this tab regardless of whether it becomes active
            const parsed = ISK.parseSymbols(content);
            ISK.tabFuncsCache[tab.id] = parsed;
            _suppressDirty = true;
            ISK.setEditorValue(editor, content, tab.id);
            setTimeout(() => { _suppressDirty = false; }, 0);
            editor.setOption('mode', _modeForFile(name));
            _renderTabs();
            _render();
        }).catch(e => appendOutput('err', 'File read error: ' + e));
    }

    function onEditorChange() {
        if (_suppressDirty) return;
        const tab = _getActiveTab();
        if (!tab) return;
        const isDirty = editor.getValue() !== tab.savedContent;
        if (tab.dirty !== isDirty) _setDirty(isDirty);
    }

    function saveCurrentFile() {
        const tab = _getActiveTab();
        if (!tab || !editor) return;
        if (!tab.path) {
            // untitled — ask for path via prompt (simple fallback)
            appendOutput('warn', 'File has no path. Use "Save As" or save via explorer.');
            return;
        }
        const savedValue = editor.getValue();
        callPython('file_save', { path: tab.path, content: savedValue }).then(res => {
            if (res && res.success) {
                tab.savedContent = savedValue;
                tab.changedOnDisk = false;
                if (res.mtime) tab.mtime = res.mtime;
                _setDirty(false);
                _hideDiskChangeBar(tab.id);
                appendOutput('info', 'Saved: ' + tab.name);
            } else {
                appendOutput('err', 'Save failed: ' + (res && res.error));
            }
        }).catch(e => appendOutput('err', 'Save error: ' + e));
    }

    async function promptNewFile() {
        if (_debugActive) return; // Block new file creation during debug
        const dirPath = _activeFile
            ? _activeFile.split('/').slice(0, -1).join('/') || _root
            : _root;
        const name = await parent.showInputDialog(currentLanguage === 'ko' ? '새 파일 이름:' : 'New file name:', 'untitled.il');
        if (!name || !name.trim()) return;
        const newPath = dirPath + '/' + name.trim();
        callPython('file_new_file', { path: newPath }).then(res => {
            if (!res || !res.success) { appendOutput('err', 'Cannot create: ' + (res && res.error)); return; }
            _expanded.add(dirPath);
            _refreshDir(dirPath, () => { _render(); _loadFile(newPath); });
        }).catch(e => appendOutput('err', 'New file error: ' + e));
    }

    function _showCtxMenu(x, y, entry) {
        _ctxEntry = entry;
        const menu = document.getElementById('explorerCtxMenu');
        if (!menu) return;
        // Show/hide items based on context (entry=null means empty area click)
        const hasEntry = !!entry && !entry.is_dir;
        menu.querySelectorAll('[data-ctx]').forEach(el => {
            const ctx = el.dataset.ctx;
            el.style.display = (ctx === 'file' && !hasEntry) ? 'none' : '';
        });
        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
        menu.style.display = 'block';
        // Stop click inside menu from bubbling to document (which would close it)
        menu._stopHandler = menu._stopHandler || (e => e.stopPropagation());
        menu.removeEventListener('click', menu._stopHandler);
        menu.addEventListener('click', menu._stopHandler);
        // Close on next outside click (use capture to catch all clicks)
        setTimeout(() => {
            document.addEventListener('click', _onOutsideClick, { once: true, capture: true });
        }, 0);
    }

    function _onOutsideClick() {
        hideCtxMenu();
    }

    function hideCtxMenu() {
        const menu = document.getElementById('explorerCtxMenu');
        if (menu) menu.style.display = 'none';
    }

    function ctxRename() {
        hideCtxMenu();
        if (!_ctxEntry) return;
        const entry = _ctxEntry;
        let targetEl = null;
        document.querySelectorAll('.sb-tree-item').forEach(el => {
            if (el.getAttribute('data-path') === entry.path) targetEl = el;
        });
        if (!targetEl) return;
        const nameSpan = targetEl.querySelector('.sb-tree-name');
        const oldName = nameSpan.textContent;
        const input = document.createElement('input');
        input.className = 'sb-tree-rename-input';
        input.value = oldName;
        nameSpan.replaceWith(input);
        input.focus();
        input.select();

        let _committed = false;
        function _doRename() {
            if (_committed) return;
            _committed = true;
            const newName = input.value.trim();
            if (!newName || newName === oldName) { input.replaceWith(nameSpan); return; }
            const parts = entry.path.split('/');
            parts.pop();
            const newPath = parts.join('/') + '/' + newName;
            callPython('file_rename', { old_path: entry.path, new_path: newPath }).then(res => {
                if (!res || !res.success) {
                    appendOutput('err', 'Rename failed: ' + (res && res.error));
                    input.replaceWith(nameSpan);
                    return;
                }
                // Update any open tab with old path
                _tabs.forEach(t => {
                    if (t.path === entry.path) { t.path = newPath; t.name = newName; }
                });
                if (_activeFile === entry.path) _activeFile = newPath;
                _renderTabs();
                const parentDir = parts.join('/') || _root;
                _refreshDir(parentDir, () => _render());
            }).catch(e => { appendOutput('err', 'Rename error: ' + e); input.replaceWith(nameSpan); });
        }
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); _doRename(); }
            if (e.key === 'Escape') { _committed = true; input.replaceWith(nameSpan); }
        });
        input.addEventListener('blur', _doRename);
    }

    async function ctxDelete() {
        hideCtxMenu();
        if (!_ctxEntry) return;
        const entry = _ctxEntry;
        if (entry.is_dir) { appendOutput('err', 'Cannot delete directories.'); return; }
        const msg = currentLanguage === 'ko'
            ? `"${entry.name}" 파일을 삭제하시겠습니까?`
            : `Delete "${entry.name}"?`;
        const title = currentLanguage === 'ko' ? '파일 삭제' : 'Delete File';
        if (!await parent.showConfirmDialog(title, msg, { yesStyle: 'danger' })) return;
        callPython('file_delete', { path: entry.path }).then(res => {
            if (!res || !res.success) { appendOutput('err', 'Delete failed: ' + (res && res.error)); return; }
            // Close tab for deleted file
            const delTab = _tabs.find(t => t.path === entry.path);
            if (delTab) { delTab.dirty = false; _closeTab(delTab.id); }
            const parts = entry.path.split('/');
            parts.pop();
            _refreshDir(parts.join('/') || _root, () => _render());
        }).catch(e => appendOutput('err', 'Delete error: ' + e));
    }

    function _esc(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function isILFile() {
        const tab = _getActiveTab();
        const name = tab ? tab.name : '';
        const ext = name.split('.').pop().toLowerCase();
        return ext === 'il' || ext === 'ils';
    }

    function reloadRoot(newPath) {
        _root = newPath;
        _tree = {};
        _expanded = new Set([newPath]);
        _refreshDir(_root, () => _render());
    }

    // ── Disk-change detection ─────────────────────────────────────────────────

    const POLL_INTERVAL_MS = 3000;
    let _pollTimer = null;
    // tabId -> true when the user chose "keep editing" to suppress repeated banners
    let _diskChangeDismissed = {};

    function _startDiskChangePolling() {
        if (_pollTimer) return;
        _pollTimer = setInterval(_pollDiskChanges, POLL_INTERVAL_MS);
    }

    function _stopDiskChangePolling() {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    }

    function _pollDiskChanges() {
        const watchable = _tabs.filter(t => t.path && t.mtime !== null && !_diskChangeDismissed[t.id]);
        if (!watchable.length) return;
        const paths = watchable.map(t => t.path);
        callPython('file_check_mtime', { paths }).then(res => {
            if (!res || !res.mtimes) return;
            watchable.forEach(tab => {
                const newMtime = res.mtimes[tab.path];
                if (newMtime === null || newMtime === undefined) return; // file gone — ignore
                if (newMtime > tab.mtime + 0.001) {
                    // File changed on disk since we last loaded/saved it
                    if (!tab.changedOnDisk) {
                        tab.changedOnDisk = true;
                        // Show banner only if this is the active tab; otherwise mark for later
                        if (tab.id === _activeTabId) _showDiskChangeBar(tab);
                        else _renderTabs(); // re-render to show indicator on inactive tabs
                    }
                }
            });
        }).catch(() => {}); // network/Python errors silently ignored
    }

    function _showDiskChangeBar(tab) {
        const bar       = document.getElementById('diskChangeBar');
        const msgEl     = document.getElementById('diskChangeMsg');
        const btnReload = document.getElementById('diskChangeBtnReload');
        const btnKeep   = document.getElementById('diskChangeBtnKeep');
        if (!bar) return;

        const isKo = typeof currentLanguage !== 'undefined' && currentLanguage === 'ko';
        msgEl.textContent = isKo
            ? tab.name + ' 이(가) 외부에서 변경되었습니다.'
            : tab.name + ' has been modified on disk.';
        btnReload.textContent = isKo ? '다시 로딩' : 'Reload';
        btnKeep.textContent   = isKo ? '계속 편집' : 'Keep Editing';

        btnReload.onclick = () => _onDiskChangeReload(tab.id);
        btnKeep.onclick   = () => _onDiskChangeKeep(tab.id);

        bar.style.display = 'flex';
    }

    function _hideDiskChangeBar(tabId) {
        const bar = document.getElementById('diskChangeBar');
        if (bar) bar.style.display = 'none';
    }

    function _onDiskChangeReload(tabId) {
        const tab = _tabs.find(t => t.id === tabId);
        if (!tab || !tab.path) return;
        _hideDiskChangeBar(tabId);
        delete _diskChangeDismissed[tabId];
        callPython('file_read', { path: tab.path }).then(res => {
            if (res && res.error) { appendOutput('err', 'Reload failed: ' + res.error); return; }
            const content = res.content || '';
            tab.mtime = res.mtime || tab.mtime;
            tab.changedOnDisk = false;
            tab.savedContent = content;
            tab.content = content;
            tab.dirty = false;
            if (tab.id === _activeTabId && editor) {
                _suppressDirty = true;
                ISK.setEditorValue(editor, content, tab.id);
                setTimeout(() => { _suppressDirty = false; }, 0);
            }
            _setDirty(false);
            _renderTabs();
        }).catch(e => appendOutput('err', 'Reload error: ' + e));
    }

    function _onDiskChangeKeep(tabId) {
        const tab = _tabs.find(t => t.id === tabId);
        if (tab) {
            tab.changedOnDisk = false;
            _diskChangeDismissed[tabId] = true;
        }
        _hideDiskChangeBar(tabId);
    }

    // Called by _switchTab to show banner if the newly-active tab has a pending disk change
    function _checkDiskChangeBannerOnSwitch(tab) {
        _hideDiskChangeBar(tab.id);
        if (tab.changedOnDisk && !_diskChangeDismissed[tab.id]) _showDiskChangeBar(tab);
    }

    function openNewTab() {
        const tab = _makeTab(null, 'untitled.il', '');
        _tabs.push(tab);
        // Save current editor state before switching
        const cur = _getActiveTab();
        if (cur && editor) {
            cur.content = editor.getValue();
            cur.cursor = editor.getCursor();
            cur.scrollInfo = editor.getScrollInfo();
        }
        _activeTabId = tab.id;
        _activeFile = null;
        _suppressDirty = true;
        ISK.setEditorValue(editor, '', tab.id);
        setTimeout(() => { _suppressDirty = false; }, 0);
        editor.setOption('mode', _modeForFile(tab.name));
        _renderTabs();
        _render();
        _updateILButtons();
        editor.focus();
    }

    return { init, reloadRoot, onEditorChange, saveCurrentFile, promptNewFile, openNewTab, openFile: _openFile, closeTab: _closeTab, ctxRename, ctxDelete, hideCtxMenu, tabCtxClose, tabCtxCopyPath, tabCtxToggleDebug, isILFile, renderIcons: _render, loadIconTheme: _loadIconThemeOverrides, getActiveTab: _getActiveTab, getTabs: () => _tabs, switchTab: _switchTab, renderTabs: _renderTabs, startDiskChangePolling: _startDiskChangePolling, stopDiskChangePolling: _stopDiskChangePolling };
})();

// ── Explorer open folder ───────────────────────────────────────────────────────
function explorerOpenFolder() {
    if (typeof callPython !== 'function') return;
    callPython('select_directory', { language: typeof currentLanguage !== 'undefined' ? currentLanguage : 'ko' }).then(res => {
        if (res && res.success && res.path) {
            callPython('file_set_root', { path: res.path }).then(r => {
                if (r && r.success) {
                    EXP.reloadRoot(r.path);
                }
            });
        }
    }).catch(e => console.error('[EXP] open folder error:', e));
}

// ── Explorer resizer ───────────────────────────────────────────────────────────
function initExplorerResizer() {
    const resizer = document.getElementById('expResizer');
    const panel   = document.getElementById('explorerPanel');
    if (!resizer || !panel) return;
    let startX, startW;
    resizer.addEventListener('mousedown', e => {
        e.preventDefault();
        startX = e.clientX;
        startW = panel.offsetWidth;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        function onMove(e) {
            const newW = Math.max(120, Math.min(500, startW + (e.clientX - startX)));
            panel.style.width = newW + 'px';
            if (editor) editor.refresh();
        }
        function onUp() {
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });
}

// ── Layout toggle ─────────────────────────────────────────────────────────────
function toggleLayout() {
    const newLayout = currentLayout === 'bottom' ? 'right' : 'bottom';
    setLayout(newLayout);
}

function setLayout(layout) {
    if (layout !== 'bottom' && layout !== 'right') return;

    currentLayout = layout;
    const main = document.querySelector('.sb-main');
    const outputPanel = document.getElementById('outputPanel');
    const editorPanel = document.getElementById('editorPanel');

    // Remove both classes and add the appropriate one
    main.classList.remove('layout-bottom', 'layout-right');
    main.classList.add(`layout-${layout}`);

    // Reset collapse state on layout change
    _outputCollapsed = false;
    _outputSavedSize = null;
    outputPanel.classList.remove('collapsed-right');
    outputPanel.style.removeProperty('min-height');
    outputPanel.style.removeProperty('min-width');
    const collapseBtn = document.getElementById('outputCollapseBtn');
    if (collapseBtn) collapseBtn.textContent = _collapseIcon(false);
    const resizer = document.getElementById('resizer');
    if (resizer) resizer.style.pointerEvents = '';

    // Reset panel dimensions based on layout
    if (layout === 'bottom') {
        outputPanel.style.width = '100%';
        outputPanel.style.height = '100px';
    } else {
        outputPanel.style.width = '380px';
        outputPanel.style.height = 'auto';
    }

    // Save preference to Python config (only when callPython is available)
    if (typeof callPython === 'function') callPython('save_layout', {layout: layout}).catch(() => {});

    // Refresh editor
    if (editor) editor.refresh();
}

// ============================================================================
// SBFind: Find & Replace using desktopModal (draggable)
// ============================================================================
const SBFind = (function() {
    let _matches = [];
    let _matchIdx = -1;
    let _lastQuery = '';
    let _lastCase = false;
    let _lastRegex = false;
    let _highlightMark = null;
    let _allMarks = [];
    let _noResultsText = 'No results';
    let _dialogOpen = false;

    function _clearMarks() {
        _allMarks.forEach(m => m.clear());
        _allMarks = [];
        if (_highlightMark) { _highlightMark.clear(); _highlightMark = null; }
    }

    function _buildMatches(query, useCase, useRegex) {
        _clearMarks();
        _matches = [];
        _matchIdx = -1;
        if (!query || !editor) return;

        const doc = editor.getValue();
        let re;
        try {
            const flags = useCase ? 'g' : 'gi';
            re = useRegex ? new RegExp(query, flags) : new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags);
        } catch(e) { return; }

        let m;
        while ((m = re.exec(doc)) !== null) {
            const from = editor.posFromIndex(m.index);
            const to = editor.posFromIndex(m.index + m[0].length);
            _matches.push({ from, to });
            _allMarks.push(editor.markText(from, to, { className: 'sb-find-match' }));
            if (m[0].length === 0) re.lastIndex++; // avoid infinite loop on zero-width match
        }
    }

    function _highlightCurrent() {
        if (_highlightMark) { _highlightMark.clear(); _highlightMark = null; }
        if (_matchIdx < 0 || _matchIdx >= _matches.length) return;
        const { from, to } = _matches[_matchIdx];
        _highlightMark = editor.markText(from, to, { className: 'sb-find-match-current' });
        editor.scrollIntoView({ from, to }, 80);
        editor.setSelection(from, to);
    }

    function _pd() { return window.parent ? window.parent.document : document; }

    function _updateStatus() {
        const el = _pd().getElementById('sb-find-status');
        if (!el) return;
        if (_matches.length === 0) {
            el.textContent = _lastQuery ? _noResultsText : '';
            el.style.color = _lastQuery ? 'var(--text-danger, #e74c3c)' : 'var(--text-secondary)';
        } else {
            el.textContent = (_matchIdx + 1) + ' / ' + _matches.length;
            el.style.color = 'var(--text-secondary)';
        }
    }

    function _onQueryInput() {
        const pd = _pd();
        const q = pd.getElementById('sb-find-input').value;
        const useCase = pd.getElementById('sb-find-case').checked;
        const useRegex = pd.getElementById('sb-find-regex').checked;
        _lastQuery = q; _lastCase = useCase; _lastRegex = useRegex;
        _buildMatches(q, useCase, useRegex);
        if (_matches.length > 0) { _matchIdx = 0; _highlightCurrent(); }
        _updateStatus();
    }

    function findNext(reverse) {
        if (!_lastQuery) return;
        if (!_dialogOpen) {
            // Dialog is closed: always re-scan so edits are reflected
            const cur = editor ? editor.indexFromPos(editor.getCursor()) : 0;
            _buildMatches(_lastQuery, _lastCase, _lastRegex);
            if (_matches.length === 0) { _updateStatus(); return; }
            let best = reverse ? _matches.length - 1 : 0;
            for (let i = 0; i < _matches.length; i++) {
                const mIdx = editor ? editor.indexFromPos(_matches[i].from) : 0;
                if (reverse ? mIdx < cur : mIdx >= cur) { best = i; break; }
                if (!reverse) best = i;
            }
            _matchIdx = best;
        } else {
            if (_matches.length === 0) return;
            if (reverse) {
                _matchIdx = (_matchIdx <= 0) ? _matches.length - 1 : _matchIdx - 1;
            } else {
                _matchIdx = (_matchIdx >= _matches.length - 1) ? 0 : _matchIdx + 1;
            }
        }
        _highlightCurrent();
        _updateStatus();
    }

    function _doReplace() {
        if (!editor || _matches.length === 0 || _matchIdx < 0) return;
        const _ri = _pd().getElementById('sb-replace-input');
        const replaceVal = _ri ? _ri.value : '';
        const { from, to } = _matches[_matchIdx];
        editor.replaceRange(replaceVal, from, to);
        // re-scan and move to next
        const q = _lastQuery;
        _buildMatches(q, _lastCase, _lastRegex);
        if (_matches.length > 0) {
            _matchIdx = Math.min(_matchIdx, _matches.length - 1);
            _highlightCurrent();
        }
        _updateStatus();
    }

    function _doReplaceAll() {
        if (!editor || _matches.length === 0) return;
        const _ri2 = _pd().getElementById('sb-replace-input');
        const replaceVal = _ri2 ? _ri2.value : '';
        // Replace from last to first to preserve positions
        const ms = _matches.slice();
        editor.operation(() => {
            for (let i = ms.length - 1; i >= 0; i--) {
                editor.replaceRange(replaceVal, ms[i].from, ms[i].to);
            }
        });
        _buildMatches(_lastQuery, _lastCase, _lastRegex);
        _matchIdx = -1;
        _updateStatus();
    }

    function open(withReplace) {
        const modal = window.parent && window.parent.desktopModal;
        if (!modal) return;

        const isKo = currentLanguage === 'ko';
        const t = {
            find:         isKo ? '찾기' : 'Find',
            findReplace:  isKo ? '찾기 및 바꾸기' : 'Find & Replace',
            replaceWith:  isKo ? '바꿀 내용' : 'Replace with',
            replace:      isKo ? '바꾸기' : 'Replace',
            replaceAll:   isKo ? '모두 바꾸기' : 'Replace All',
            caseSensitive:isKo ? '대소문자 구분' : 'Case sensitive',
            noResults:    isKo ? '결과 없음' : 'No results',
        };

        const replaceRow = withReplace ? `
            <div style="display:flex;align-items:center;margin-top:8px;">
                <input id="sb-replace-input" type="text" placeholder="${t.replaceWith}"
                    style="flex:1;background:var(--bg-primary);border:1px solid var(--border-color);color:var(--text-primary);border-radius:4px;padding:5px 8px;font-size:13px;outline:none;">
            </div>
            <div style="display:flex;margin-top:8px;">
                <button id="sb-btn-replace" class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:6px;">${t.replace}</button>
                <button id="sb-btn-replace-all" class="btn btn-secondary" style="font-size:12px;padding:4px 10px;">${t.replaceAll}</button>
            </div>` : '';

        const html = `<div style="min-width:320px;">
            <div style="display:flex;align-items:center;">
                <input id="sb-find-input" type="text" placeholder="${t.find}"
                    style="flex:1;background:var(--bg-primary);border:1px solid var(--border-color);color:var(--text-primary);border-radius:4px;padding:5px 8px;font-size:13px;outline:none;">
                <button id="sb-btn-prev" class="btn btn-secondary" style="font-size:12px;padding:4px 8px;margin-left:6px;" title="Shift+F3">&#8593;</button>
                <button id="sb-btn-next" class="btn btn-secondary" style="font-size:12px;padding:4px 8px;margin-left:4px;" title="F3">&#8595;</button>
            </div>
            <div style="display:flex;align-items:center;margin-top:6px;">
                <label style="display:flex;align-items:center;font-size:12px;color:var(--text-secondary);margin-right:12px;cursor:pointer;">
                    <input id="sb-find-case" type="checkbox" style="margin-right:4px;cursor:pointer;"> ${t.caseSensitive}
                </label>
                <label style="display:flex;align-items:center;font-size:12px;color:var(--text-secondary);cursor:pointer;">
                    <input id="sb-find-regex" type="checkbox" style="margin-right:4px;cursor:pointer;"> Regex
                </label>
                <span id="sb-find-status" style="margin-left:auto;font-size:12px;color:var(--text-secondary);"></span>
            </div>
            ${replaceRow}
        </div>`;

        _noResultsText = t.noResults;
        _dialogOpen = true;

        modal.open({
            title: withReplace ? t.findReplace : t.find,
            html: html,
            draggable: true,
            position: 'bottom-right',
            buttons: [],
            onClose: function() {
                _dialogOpen = false;
                _clearMarks();
                _matches = [];
                _matchIdx = -1;
                if (editor) editor.focus();
            }
        });

        // wire up events after DOM is inserted
        // Elements are in parent document (desktopModal lives in parent frame)
        const pd = window.parent.document;
        const inp = pd.getElementById('sb-find-input');
        if (inp) {
            inp.addEventListener('input', _onQueryInput);
            inp.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') { e.preventDefault(); findNext(e.shiftKey); }
                else if (e.key === 'Escape') { e.preventDefault(); modal.close(); }
            });
            // pre-fill: current selection > last query
            if (editor) {
                const sel = editor.getSelection();
                if (sel && sel.indexOf('\n') === -1) {
                    inp.value = sel;
                    _lastQuery = sel;
                } else if (_lastQuery) {
                    inp.value = _lastQuery;
                }
            }
            // Qt WebEngine cross-frame focus needs a small delay; 0ms is unreliable.
            setTimeout(() => { inp.focus(); inp.select(); _onQueryInput(); }, 50);
        }

        const btnNext = pd.getElementById('sb-btn-next');
        const btnPrev = pd.getElementById('sb-btn-prev');
        if (btnNext) btnNext.addEventListener('click', () => findNext(false));
        if (btnPrev) btnPrev.addEventListener('click', () => findNext(true));

        if (withReplace) {
            const replInp = pd.getElementById('sb-replace-input');
            if (replInp) replInp.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') { e.preventDefault(); _doReplace(); }
                else if (e.key === 'Escape') { e.preventDefault(); modal.close(); }
            });
            const btnReplace = pd.getElementById('sb-btn-replace');
            const btnReplaceAll = pd.getElementById('sb-btn-replace-all');
            if (btnReplace) btnReplace.addEventListener('click', _doReplace);
            if (btnReplaceAll) btnReplaceAll.addEventListener('click', _doReplaceAll);
        }
    }

    return { open, findNext };
})();

// ── PRJ: Project Manager ──────────────────────────────────────────────────────
const PRJ = (function() {
    let _projects = [];       // [{id, name, description, files:[]}]
    let _editingId = null;    // project id currently shown in edit panel (null = new)
    let _editFiles = [];      // mutable file list for the edit panel
    let _activeProjectId = null; // project id that was last switched to

    // ── helpers ──

    function _t(en, ko) {
        return currentLanguage === 'ko' ? ko : en;
    }

    function _esc(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    // ── public: open / close ──

    function openDialog() {
        _load(function() {
            document.getElementById('prjOverlay').classList.add('visible');
            document.getElementById('prjDialog').classList.add('visible');
            document.getElementById('prjBtn').classList.add('active');
            _renderList();
            // Default: select first project or blank new-form
            if (_projects.length > 0) {
                _selectProject(_projects[0].id);
            } else {
                startNew();
            }
        });
    }

    function closeDialog() {
        document.getElementById('prjOverlay').classList.remove('visible');
        document.getElementById('prjDialog').classList.remove('visible');
        document.getElementById('prjBtn').classList.remove('active');
    }

    // ── list rendering ──

    function _renderList() {
        const list = document.getElementById('prjList');
        if (!list) return;
        if (_projects.length === 0) {
            list.innerHTML = '<div class="prj-list-empty">' +
                _esc(_t('No projects yet', '프로젝트가 없습니다')) + '</div>';
            return;
        }
        list.innerHTML = _projects.map(p => {
            let cls = 'prj-list-item';
            if (_editingId === p.id) cls += ' active';
            if (_activeProjectId === p.id) cls += ' current';
            return `<div class="${cls}" data-id="${_esc(p.id)}">${_esc(p.name)}</div>`;
        }).join('');
        list.querySelectorAll('.prj-list-item').forEach(el => {
            el.addEventListener('click', () => _selectProject(el.dataset.id));
        });
        // i18n labels
        _applyI18n(document.getElementById('prjDialog'));
    }

    function _selectProject(id) {
        const p = _projects.find(x => x.id === id);
        if (!p) return;
        _editingId = id;
        _editFiles = p.files.slice();
        document.getElementById('prjNameInput').value = p.name;
        document.getElementById('prjDescInput').value = p.description || '';
        document.getElementById('prjDeleteBtn').style.display = '';
        document.getElementById('prjSwitchBtn').style.display = '';
        _renderFileList();
        _renderList();
    }

    // ── new project ──

    function startNew() {
        _editingId = null;
        _editFiles = [];
        document.getElementById('prjNameInput').value = '';
        document.getElementById('prjDescInput').value = '';
        document.getElementById('prjDeleteBtn').style.display = 'none';
        document.getElementById('prjSwitchBtn').style.display = 'none';
        _renderFileList();
        _renderList();
        setTimeout(() => {
            const inp = document.getElementById('prjNameInput');
            if (inp) inp.focus();
        }, 50);
    }

    // ── file list in edit panel ──

    function _renderFileList() {
        const el = document.getElementById('prjFileList');
        if (!el) return;
        if (_editFiles.length === 0) {
            el.innerHTML = '<div class="prj-list-empty" style="padding:8px 10px;">' +
                _esc(_t('No files', '파일 없음')) + '</div>';
            return;
        }
        el.innerHTML = _editFiles.map((f, i) => {
            const name = f.split('/').pop() || f;
            return `<div class="prj-file-item">` +
                `<span class="prj-file-name">${_esc(name)}</span>` +
                `<button class="prj-file-remove" data-idx="${i}">✕</button>` +
                `</div>`;
        }).join('');
        el.querySelectorAll('.prj-file-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                _editFiles.splice(parseInt(btn.dataset.idx), 1);
                _renderFileList();
            });
        });
    }

    function addCurrentTabs() {
        // Add all open tabs that have a real file path and are not already in list
        const tabs = EXP.getTabs();
        tabs.forEach(t => {
            if (t.path && !_editFiles.includes(t.path)) {
                _editFiles.push(t.path);
            }
        });
        _renderFileList();
    }

    // ── save / delete ──

    function _showToast(msg) {
        const el = document.getElementById('prjToast');
        if (!el) return;
        el.textContent = msg;
        el.classList.add('visible');
        setTimeout(() => el.classList.remove('visible'), 2000);
    }

    function saveProject() {
        const name = (document.getElementById('prjNameInput').value || '').trim();
        if (!name) {
            document.getElementById('prjNameInput').focus();
            return;
        }
        const desc = (document.getElementById('prjDescInput').value || '').trim();
        const payload = {
            id:          _editingId || '',
            name:        name,
            description: desc,
            files:       _editFiles.slice(),
        };
        callPython('project_save', payload).then(res => {
            if (res && res.success) {
                _editingId = res.project.id;
                _load(function() {
                    _renderList();
                    _renderFileList();
                    _showToast(_t('Project saved.', '저장되었습니다.'));
                });
            }
        }).catch(() => {});
    }

    async function switchProject() {
        if (!_editingId) return;
        const p = _projects.find(x => x.id === _editingId);
        if (!p || !p.files || p.files.length === 0) return;
        const msg = _t(
            `Close all tabs and switch to project "${p.name}"?`,
            `현재 탭을 모두 닫고 "${p.name}" 프로젝트로 전환할까요?`
        );
        if (!await parent.showConfirmDialog(_t('Switch Project', '프로젝트 전환'), msg)) return;
        closeDialog();
        // Close all existing tabs, then open project files in order
        const tabs = EXP.getTabs().slice();
        for (const t of tabs) {
            await EXP.closeTab(t.id);
        }
        for (const path of p.files) {
            await EXP.openFile(path);
        }
        // Activate the first tab
        const opened = EXP.getTabs();
        if (opened.length > 0) EXP.switchTab(opened[0].id);
        _activeProjectId = p.id;
    }

    async function deleteProject() {
        if (!_editingId) return;
        const name = (_projects.find(p => p.id === _editingId) || {}).name || '';
        const msg = _t(`Delete project "${name}"?`, `"${name}" 프로젝트를 삭제할까요?`);
        if (!await parent.showConfirmDialog(_t('Delete Project', '프로젝트 삭제'), msg)) return;
        callPython('project_delete', { id: _editingId }).then(res => {
            if (res && res.success) {
                _editingId = null;
                _load(function() {
                    _renderList();
                    if (_projects.length > 0) {
                        _selectProject(_projects[0].id);
                    } else {
                        startNew();
                    }
                });
            }
        }).catch(() => {});
    }

    // ── load from backend ──

    function _load(cb) {
        if (typeof callPython !== 'function') { setTimeout(() => _load(cb), 200); return; }
        callPython('project_list', {}).then(res => {
            if (res && res.success) _projects = res.projects || [];
            if (cb) cb();
        }).catch(() => { if (cb) cb(); });
    }

    // ── i18n helper for dialog ──

    function _applyI18n(root) {
        if (!root) return;
        root.querySelectorAll('[data-en]').forEach(el => {
            const txt = currentLanguage === 'ko' ? el.dataset.ko : el.dataset.en;
            if (txt !== undefined) el.textContent = txt;
        });
    }

    // Attach overlay click + ESC key to close (done once at module init)
    (function() {
        function _attach() {
            const ov = document.getElementById('prjOverlay');
            if (ov) { ov.addEventListener('click', closeDialog); }
            else { setTimeout(_attach, 200); }
        }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', _attach);
        } else {
            _attach();
        }
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && document.getElementById('prjDialog').classList.contains('visible')) {
                closeDialog();
            }
        });
    })();

    return {
        openDialog,
        closeDialog,
        startNew,
        addCurrentTabs,
        saveProject,
        deleteProject,
        switchProject,
    };
})();
