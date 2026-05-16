; SkillBot Virtuoso Integration Module
; No ipcBeginProcess needed.
; Python → CIW : X11 keyboard injection
; CIW → Python : system("curl http://127.0.0.1:__sbPort/...")

; ── Runtime state ─────────────────────────────────────────────────────────────
unless( boundp('__sbPort)   __sbPort   = 0   )  ; Python REST API port (set by debug_start)

; ── Debug state (global variables used by breakpoint guards) ──────────────────
unless( boundp('__sbk_bp)   __sbk_bp   = nil )  ; Breakpoint line list (legacy single-file)
unless( boundp('__sbk_ln)   __sbk_ln   = 0   )  ; Current break line
unless( boundp('__sbk_fid)  __sbk_fid  = 0   )  ; Current break file id

; ── Base64 decoder ─────────────────────────────────────────────────────────────
_sb_b64chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

procedure( _sbB64CharVal(ch)
  let( (pos)
    if( ch == "="
      then -1
      else
        pos = index(_sb_b64chars ch)
        if( pos then strlen(_sb_b64chars) - strlen(pos) else -1)
    )
  )
)

procedure( _sbB64Decode(s)
  let( (result len i v0 v1 v2 v3 b0 b1 b2)
    result = ""
    len    = strlen(s)
    i      = 1
    while( i + 3 <= len
      v0 = _sbB64CharVal(getchar(s i))
      v1 = _sbB64CharVal(getchar(s i+1))
      v2 = _sbB64CharVal(getchar(s i+2))
      v3 = _sbB64CharVal(getchar(s i+3))
      when( v0 >= 0 && v1 >= 0
        b0 = band(bor(lsh(v0 2) fix(v1 / 16)) 255)
        result = strcat(result intToChar(b0))
      )
      when( v2 >= 0
        b1 = band(bor(lsh(band(v1 15) 4) fix(v2 / 4)) 255)
        result = strcat(result intToChar(b1))
      )
      when( v2 >= 0 && v3 >= 0
        b2 = band(bor(lsh(band(v2 3) 6) v3) 255)
        result = strcat(result intToChar(b2))
      )
      i = i + 4
    )
    result
  )
)

; ── JSON escape ────────────────────────────────────────────────────────────────
procedure( _sbJsonEscape(s)
  let( (result len i ch)
    result = ""
    len    = strlen(s)
    i      = 1
    while( i <= len
      ch = getchar(s i)
      cond(
        ( ch == "\\" result = strcat(result "\\\\") )
        ( ch == "\"" result = strcat(result "\\\"") )
        ( ch == "\n" result = strcat(result "\\n")  )
        ( ch == "\r" result = strcat(result "\\r")  )
        ( ch == "\t" result = strcat(result "\\t")  )
        ( t          result = strcat(result ch)     )
      )
      i = i + 1
    )
    result
  )
)

; ── curl helper ────────────────────────────────────────────────────────────────
; All CIW→Python communication goes via curl to http://127.0.0.1:__sbPort/...
; Curl runs in background (&) so it never blocks SKILL execution.

procedure( _sbCurl(path)
  ; Fire-and-forget GET request to Python REST API
  system(sprintf(nil "curl -s --max-time 2 http://127.0.0.1:%d%s >/dev/null &" __sbPort path))
)

procedure( _sbCurlPost(path body)
  ; Fire-and-forget POST request to Python REST API
  system(sprintf(nil "curl -s --max-time 2 -X POST -H 'Content-Type: application/json' -d '%s' http://127.0.0.1:%d%s >/dev/null &"
                 body __sbPort path))
)

; ── Debug breakpoint handler ──────────────────────────────────────────────────
; Called from breakpoint guards: when(member(N __sbk_bp) _sbDbgBreak(N))
; Notifies Python of the break via curl, then calls break() to pause execution.
; Python resumes by injecting "continue()" via X11.
procedure( _sbDbgBreak(lineNum @optional (fileId 0))
  let( ()
    setq(__sbk_ln lineNum)
    setq(__sbk_fid fileId)
    ; Notify Python: GET /debug_break/<fileId>/<line>
    ; This curl runs synchronously (no &) so the notification is sent BEFORE
    ; break() is called — Python gets it, sets the event, then waits for
    ; the injected continue() to arrive via X11.
    system(sprintf(nil "curl -s --max-time 2 http://127.0.0.1:%d/debug_break/%d/%d"
                   __sbPort fileId lineNum))
    ; Pause execution — Python will inject "continue()" via X11 to resume
    break()
  )
)

; ── Debug eval handler (called while in break toplevel) ───────────────────────
; Python injects: _sbDbgEval("<b64-encoded-expr>")
; Result is sent back via POST /debug_eval_result
procedure( _sbDbgEval(b64expr)
  let( (evalCode evalResult errResult bodyStr)
    evalCode = _sbB64Decode(b64expr)
    errResult = errset( (evalResult = evalstring(evalCode)) t )
    if( errResult != nil
      then
        bodyStr = sprintf(nil "{\"success\":true,\"result\":\"%s\"}"
                          _sbJsonEscape(sprintf(nil "%L" car(errResult))))
      else
        bodyStr = "{\"success\":false,\"result\":\"eval error\"}"
    )
    _sbCurlPost("/debug_eval_result" bodyStr)
  )
)

; ── Module loaded ──────────────────────────────────────────────────────────────
printf("\n[SkillBot] loaded - connect from SkillBot UI (F5 to debug)\n\n")
