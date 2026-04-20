;;; caller.il - Example: SKILL caller for skillform GUI
;;;
;;; Prerequisites:
;;;   - libform.il must be loaded first
;;;   - Set SKILLUP_PY env var, or pass skillup.py path explicitly
;;;
;;; Run from Virtuoso CIW:
;;;   load("/path/to/skillup-full/app/skillform/lib/skill/libform.il")
;;;   load("/path/to/skillup-full/app/skillform/example/caller/skill/caller.il")
;;;   sfExampleRun("/path/to/form01.json")
;;;   sfExampleRun("/path/to/form01.json" "/path/to/skillup.py" "/path/to/python3")

_sfExSaveFile = "/tmp/skillform_example.json"

procedure(sfExampleRun(formPath @optional skillupPy pythonBin)
  skillformRun(formPath 'sfExampleHandler skillupPy pythonBin))

procedure(sfExampleHandler(form ev)
  let((evType btnId vals newCount saved)
    evType = ev->type
    cond(

      (equal(evType "ready")
       printf("Form window opened.\n"))

      (equal(evType "button_click")
       btnId = ev->button_id
       vals  = ev->values
       printf("\nButton pressed: %s\n" btnId)
       cond(
         (equal(btnId "btn_save")
          progn(
            skillformSaveValues(vals _sfExSaveFile)
            printf("  -> saved to %s\n" _sfExSaveFile)))

         (equal(btnId "btn_load")
          progn(
            saved = skillformLoadValues(_sfExSaveFile)
            if(saved
              then
                printf("  -> loaded: %L\n" saved)
                skillformSetValues(form saved)
              else
                printf("  -> no saved file found\n"))))

         (equal(btnId "btn_count_plus")
          progn(
            newCount = vals->count
            newCount = newCount + 1
            printf("  -> count+1=%L\n" newCount)
            skillformSetValues(form list(list("count" newCount)))))

         (or(equal(btnId "btn_ok") equal(btnId "btn_cancel"))
          skillformClose(form))))

      (equal(evType "window_closed")
       printf("Form window closed.\n")))))
