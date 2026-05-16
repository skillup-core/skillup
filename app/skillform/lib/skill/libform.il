;;; libform.il - SkillForm SKILL caller library
;;;
;;; Launches a skillform GUI window from inside Virtuoso without blocking
;;; the Virtuoso UI. Uses ipcBeginProcess for non-blocking subprocess I/O.
;;;
;;; Setup:
;;;   Set SKILLUP_PY environment variable to the full path of skillup.py,
;;;   OR pass skillupPy as the third argument to skillformRun.
;;;
;;; Usage:
;;;   (load "libform.il")
;;;
;;;   procedure(myHandler(form ev)
;;;     let((evType)
;;;       evType = ev->type
;;;       cond(
;;;         (equal(evType "ready")      println("Form is ready"))
;;;         (equal(evType "button_click")
;;;          let((btnId vals)
;;;            btnId = ev->button_id
;;;            vals  = ev->values
;;;            when(equal(btnId "btn_ok") skillformClose(form))))
;;;         (equal(evType "window_closed") println("Form closed")))))
;;;
;;;   skillformRun("/path/to/form.json" 'myHandler)

;;; ---------------------------------------------------------------------------
;;; Minimal JSON encoder
;;; ---------------------------------------------------------------------------
procedure(_sfJsonEncode(val)
  let((parts ch i out)
    cond(
      (null(val)    "null")
      (equal(val t) "true")
      (stringp(val)
       out = "\""
       i = 1
       while(i <= length(val)
         ch = substring(val i 1)
         cond(
           (equal(ch "\\") out = strcat(out "\\\\"))
           (equal(ch "\"") out = strcat(out "\\\""))
           (equal(ch "\n") out = strcat(out "\\n"))
           (equal(ch "\r") out = strcat(out "\\r"))
           (t              out = strcat(out ch)))
         i++
       )
       strcat(out "\""))
      (numberp(val)
       if(equal(val fix(val))
         sprintf(nil "%d" fix(val))
         sprintf(nil "%L" val)))
      (listp(val)
       if(and(listp(car(val)) stringp(caar(val)))
         progn(
           parts = nil
           foreach(pair val
             parts = append(parts list(strcat(_sfJsonEncode(car(pair)) ":" _sfJsonEncode(cadr(pair))))))
           strcat("{" buildString(parts ",") "}"))
         progn(
           parts = nil
           foreach(item val
             parts = append(parts list(_sfJsonEncode(item))))
           strcat("[" buildString(parts ",") "]"))))
      (t sprintf(nil "%L" val)))))

;;; ---------------------------------------------------------------------------
;;; Split string on newline, return list of non-empty lines
;;; substring(s pos len) - pos is 1-based, len is character count
;;; ---------------------------------------------------------------------------
procedure(_sfSplitLines(chunk)
  let((result start i len ch line)
    result = nil
    len = length(chunk)
    i = 1
    start = 1
    while(i <= len
      ch = substring(chunk i 1)
      when(equal(ch "\n")
        when((i - start) > 0
          line = substring(chunk start (i - start))
          result = append(result list(line)))
        start = i + 1)
      i++
    )
    when((i - start) > 0
      line = substring(chunk start (i - start))
      result = append(result list(line)))
    result))

;;; ---------------------------------------------------------------------------
;;; Unescape JSON string escape sequences
;;; ---------------------------------------------------------------------------
procedure(_sfUnescapeStr(s)
  let((out i len ch next)
    out = ""
    i = 1
    len = length(s)
    while(i <= len
      ch = substring(s i 1)
      if(equal(ch "\\")
        then
          progn(
            next = if(i < len substring(s i+1 1) "")
            cond(
              (equal(next "n")  out = strcat(out "\n") i = i + 2)
              (equal(next "r")  out = strcat(out "\r") i = i + 2)
              (equal(next "t")  out = strcat(out "\t") i = i + 2)
              (equal(next "\"") out = strcat(out "\"") i = i + 2)
              (equal(next "\\") out = strcat(out "\\") i = i + 2)
              (t                out = strcat(out ch)   i++)))
        else
          progn(
            out = strcat(out ch)
            i++)))
    out))

;;; ---------------------------------------------------------------------------
;;; Minimal JSON decoder for flat objects
;;; substring(s pos len): pos=1-based, len=char count
;;; Returns association list or nil on parse error
;;; ---------------------------------------------------------------------------
procedure(_sfJsonDecode(line)
  let((result i len s ch key rawVal depth open close vs done)
    result = nil
    s   = line
    len = length(s)
    i   = 1
    while(i <= len && equal(substring(s i 1) " ") i++)
    unless(equal(substring(s i 1) "{")
      len = 0)
    i++
    done = nil
    while(!done && i <= len
      while(i <= len && member(substring(s i 1) list(" " "\n" "\r" "\t")) i++)
      ch = substring(s i 1)
      cond(
        (equal(ch "}") done = t)
        (equal(ch "\"")
         i++
         vs = i
         while(i <= len && !equal(substring(s i 1) "\"") i++)
         key = substring(s vs (i - vs))
         i++
         while(i <= len && member(substring(s i 1) list(" " ":")) i++)
         ch = substring(s i 1)
         cond(
           (equal(ch "\"")
            i++
            vs = i
            while(i <= len && !equal(substring(s i 1) "\"")
              when(equal(substring(s i 1) "\\") i++)
              i++)
            rawVal = _sfUnescapeStr(substring(s vs (i - vs)))
            i++)
           (equal(ch "t")
            rawVal = t
            i = i + 4)
           (equal(ch "f")
            rawVal = nil
            i = i + 5)
           (equal(ch "n")
            rawVal = nil
            i = i + 4)
           (or(equal(ch "{") equal(ch "["))
            open  = ch
            close = if(equal(ch "{") "}" "]")
            depth = 1
            vs = i
            i++
            while(depth > 0 && i <= len
              ch = substring(s i 1)
              when(equal(ch open)  depth++)
              when(equal(ch close) depth--)
              i++)
            rawVal = substring(s vs (i - vs - 1)))
           (t
            vs = i
            while(i <= len && !member(substring(s i 1) list("," "}" "]" " " "\n" "\r"))
              i++)
            rawVal = atof(substring(s vs (i - vs)))))
         result = cons(list(key rawVal) result)
         while(i <= len && member(substring(s i 1) list(" " ",")) i++))
        (t done = t)))
    reverse(result)))

;;; ---------------------------------------------------------------------------
;;; Convert association list to disembodied property list
;;; ---------------------------------------------------------------------------
procedure(_sfAssocToPlist(alist)
  let((pl)
    pl = list(nil)
    foreach(pair alist
      putprop(pl cadr(pair) car(pair)))
    pl))

procedure(_sfDecodeEv(alist)
  let((pl rawVals)
    unless(alist return(nil))
    pl = _sfAssocToPlist(alist)
    rawVals = pl->values
    when(and(rawVals stringp(rawVals))
      pl->values = _sfAssocToPlist(_sfJsonDecode(rawVals)))
    pl))

;;; Global state - single active form (one at a time)
_sfCurHandler = nil
_sfCurForm    = nil
_sfCurPid     = nil
_sfCurCmdPort = nil

;;; ---------------------------------------------------------------------------
;;; ipcBeginProcess callbacks
;;; ---------------------------------------------------------------------------
procedure(_sfOnData(pid chunk)
  let((ev evType lines)
    lines = _sfSplitLines(chunk)
    foreach(line lines
      ev = _sfDecodeEv(_sfJsonDecode(line))
      evType = ev && ev->type
      when(evType
        if(equal(evType "_init")
          then
            _sfCurPid     = ev->pid
            _sfCurCmdPort = ev->cmd_port
          else
            when(_sfCurHandler
              funcall(_sfCurHandler _sfCurForm ev)))))))

procedure(_sfOnError(pid data)
  printf("skillform stderr: %s\n" data))

procedure(_sfOnFinish(pid code)
  _sfCurHandler = nil
  _sfCurForm    = nil
  _sfCurPid     = nil
  _sfCurCmdPort = nil)

;;; ---------------------------------------------------------------------------
;;; Public API
;;; ---------------------------------------------------------------------------

procedure(skillformClose(form)
  when(_sfCurPid
    system(strcat("kill " sprintf(nil "%d" fix(_sfCurPid))))
    _sfCurPid = nil))

procedure(_sfSendCmd(msg)
  let((tmpFile port)
    when(_sfCurCmdPort
      tmpFile = "/tmp/_sf_cmd.json"
      port = sprintf(nil "%d" fix(_sfCurCmdPort))
      let((p)
        p = outfile(tmpFile "w")
        when(p
          fprintf(p "%s\n" msg)
          close(p)))
      system(strcat("nc --send-only 127.0.0.1 " port " < " tmpFile)))))

procedure(skillformSetValues(form values)
  _sfSendCmd(strcat("{\"type\":\"set_values\",\"values\":" _sfJsonEncode(values) "}")))

procedure(skillformSaveValues(values path)
  let((port)
    port = outfile(path "w")
    when(port
      fprintf(port "%s\n" _sfJsonEncode(values))
      close(port)
      t)))

procedure(skillformLoadValues(path)
  let((port ch line result)
    result = nil
    port = infile(path)
    when(port
      line = ""
      ch = getc(port)
      while(ch && !equal(ch "\n")
        line = strcat(line ch)
        ch = getc(port))
      close(port)
      when(nequal(line "") result = _sfJsonDecode(line)))
    result))

procedure(skillformRunWithExecutor(formPath skillupPy handler)
  let((selectorSh tmpFile pyBin port ch line parts repoRoot)
    parts      = parseString(skillupPy "/")
    repoRoot   = strcat("/" buildString(reverse(cdr(reverse(parts))) "/"))
    selectorSh = strcat(repoRoot "/../skillup-tool/skillup-python-selector.sh")
    unless(isFile(selectorSh)
      error("skillformRunWithExecutor: skillup-python-selector.sh not found: %s" selectorSh))
    tmpFile = "/tmp/_sf_pybin.txt"
    system(strcat("bash " selectorSh " | tr -d '\\r\\n' > " tmpFile " 2>/dev/null"))
    port = infile(tmpFile)
    unless(port
      error("skillformRunWithExecutor: could not read %s" tmpFile))
    line = ""
    ch = getc(port)
    while(ch && !equal(ch "\n")
      line = strcat(line ch)
      ch = getc(port))
    close(port)
    pyBin = line
    unless(nequal(pyBin "")
      error("skillformRunWithExecutor: skillup-python-selector.sh returned empty path"))
    skillformRun(formPath skillupPy pyBin handler)))

procedure(skillformRun(formPath skillupPy pythonBin handler)
  let((pyBin pyPath pid formHandle logFile cmd parts repoRoot bridgePy)
    pyBin  = pythonBin
    pyPath = skillupPy
    unless(pyPath
      error("skillformRun: skillup.py path required as 2nd argument."))
    unless(isFile(pyPath)
      error("skillformRun: skillup.py not found: %s" pyPath))
    unless(isFile(formPath)
      error("skillformRun: form file not found: %s" formPath))

    parts    = parseString(pyPath "/")
    parts    = reverse(cdr(reverse(parts)))
    repoRoot = strcat("/" buildString(parts "/"))
    bridgePy = strcat(repoRoot "/app/skillform/lib/skill/bridge.py")

    logFile = "/tmp/skillform_bridge.log"
    cmd     = strcat(pyBin " " bridgePy " " formPath " " pyPath " " pyBin)
    pid     = ipcBeginProcess(cmd "" '_sfOnData '_sfOnError '_sfOnFinish logFile)
    unless(pid error("skillformRun: ipcBeginProcess failed"))

    formHandle    = list(pid pyPath)
    _sfCurHandler = handler
    _sfCurForm    = formHandle
    formHandle))

printf("libform.il loaded v18.\n")
