    // ── SKILL Custom CodeMirror Mode ─────────────────────────────────────────
    (function(CodeMirror) {
        "use strict";

        // Control-flow keywords and special forms
        var KEYWORDS = (function() {
            var kw = {};
            ("procedure lambda nlambda mprocedure nprocedure macro define defun defmacro " +
             "let letseq letrec letseq prog prog1 prog2 progn " +
             "if when unless cond case caseq " +
             "for foreach forall while loop do " +
             "return go break continue " +
             "setq set setf " +
             "and or not " +
             "quote backquote " +
             "errset error warn catch throw unwindProtect " +
             "begin block then else " +
             "nil t").split(" ").forEach(function(w) { if (w) kw[w] = true; });
            return kw;
        })();

        // Builtin set — populated at runtime via initSKILLBuiltins()
        var BUILTINS = {};

        // Public: call this once with array from get_skill_syntax handler
        CodeMirror.initSKILLBuiltins = function(names) {
            BUILTINS = {};
            for (var i = 0; i < names.length; i++) BUILTINS[names[i]] = true;
            // Also expose to outer scope for _updateUndefWarnings
            if (typeof _skillBuiltins !== 'undefined') {
                _skillBuiltins.clear();
                for (var i = 0; i < names.length; i++) _skillBuiltins.add(names[i]);
            }
            // Re-highlight all open SKILL editors
            CodeMirror.findModeByName && CodeMirror.findModeByName("skill");
        };

        // Expose keyword set to outer scope for _updateUndefWarnings
        CodeMirror.skillKeywords = KEYWORDS;

        var BRACKET_DEPTH_COUNT = 6; // number of rainbow colors

        // Keywords that introduce a parameter list as their first (...)
        var PARAM_LIST_KEYWORDS = (function() {
            var kw = {};
            ("procedure lambda nlambda mprocedure nprocedure macro define defun defmacro " +
             "let letseq letrec").split(" ").forEach(function(w) { if (w) kw[w] = true; });
            return kw;
        })();

        CodeMirror.defineMode("skill", function() {
            return {
                startState: function() {
                    return {
                        inBlockComment: false,   // /* ... */
                        inString:       false,   // "..."
                        depth:          0,       // bracket nesting depth
                        afterParamKw:   false,   // just saw procedure/lambda/etc
                        paramDepth:     -1       // bracket depth of the param list (-1 = not in one)
                    };
                },

                token: function(stream, state) {
                    // ── Block comment /* ... */ ──────────────────────────────
                    if (state.inBlockComment) {
                        if (stream.match(/.*?\*\//)) { state.inBlockComment = false; }
                        else { stream.skipToEnd(); }
                        return "comment";
                    }
                    if (stream.match("/*")) { state.inBlockComment = true; return "comment"; }

                    // ── Line comment ; ───────────────────────────────────────
                    if (stream.peek() === ";") { stream.skipToEnd(); return "comment"; }

                    // ── String "..." ─────────────────────────────────────────
                    if (stream.peek() === '"') {
                        stream.next();
                        while (!stream.eol()) {
                            var ch = stream.next();
                            if (ch === '\\') { stream.next(); continue; }
                            if (ch === '"') break;
                        }
                        return "string";
                    }

                    // ── Whitespace ───────────────────────────────────────────
                    if (stream.eatSpace()) return null;

                    // ── Number ───────────────────────────────────────────────
                    if (stream.match(/^[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?(?=[\s\(\)\[\];,:]|$)/)) {
                        return "number";
                    }

                    // ── Brackets (rainbow by depth) ───────────────────────────
                    var bch = stream.peek();
                    if (bch === '(' || bch === '[') {
                        var d = state.depth % BRACKET_DEPTH_COUNT;
                        state.depth++;
                        // afterParamKw=2: this '(' is the actual param list
                        if (state.afterParamKw === 2) {
                            state.paramDepth = state.depth - 1;
                            state.afterParamKw = 0;
                        }
                        // afterParamKw=1: outer '(' of procedure( — keep state, wait for func name
                        stream.next();
                        return "bracket-d" + d;
                    }
                    if (bch === ')' || bch === ']') {
                        state.depth = Math.max(0, state.depth - 1);
                        // Leaving the param list bracket
                        if (state.depth === state.paramDepth) {
                            state.paramDepth = -1;
                        }
                        var d = state.depth % BRACKET_DEPTH_COUNT;
                        stream.next();
                        return "bracket-d" + d;
                    }

                    // ── Keyword arg  ?argname ─────────────────────────────────
                    if (stream.peek() === '?') {
                        stream.eat('?');
                        stream.eatWhile(/[\w_?!]/);
                        return "attribute";
                    }

                    // ── Identifiers ───────────────────────────────────────────
                    if (stream.match(/^[a-zA-Z_][a-zA-Z0-9_?!]*/)) {
                        var word = stream.current();
                        var ahead = stream.string.slice(stream.pos);

                        if (KEYWORDS[word]) {
                            if (PARAM_LIST_KEYWORDS[word]) state.afterParamKw = 1;
                            return "keyword";
                        }
                        // Saw keyword, then func name identifier → next '(' is param list
                        if (state.afterParamKw === 1) {
                            state.afterParamKw = 2;
                        }
                        // Inside a parameter list: treat all plain identifiers as variables
                        if (state.paramDepth >= 0 && state.depth === state.paramDepth + 1) {
                            return "variable";
                        }
                        if (BUILTINS[word])  return "builtin";
                        // identifier immediately followed by '(' → user function call
                        if (ahead[0] === '(') return "def";
                        return "variable";
                    }

                    // ── Operators & punctuation ───────────────────────────────
                    if (stream.eat(/[=+\-*\/!@#$%^&~<>|,.:`']/)) return "operator";

                    stream.next();
                    return null;
                },

                copyState: function(state) {
                    return {
                        inBlockComment: state.inBlockComment,
                        inString:       state.inString,
                        depth:          state.depth,
                        afterParamKw:   state.afterParamKw,  // 0=no, 1=saw keyword, 2=saw funcname
                        paramDepth:     state.paramDepth
                    };
                },

                lineComment: ";",
                blockCommentStart: "/*",
                blockCommentEnd: "*/",
                fold: "brace"
            };
        });

        CodeMirror.defineMIME("text/x-skill", "skill");
    })(CodeMirror);
