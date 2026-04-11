; Test file for define feature - with define file
; This should only report 2 errors: func2 and variable2
; func1 and variable1 are in test_define.txt

procedure(testDefineFeature()
  let(()
    ; Call undefined functions
    func1(123)
    func2(456)

    ; Assign to undeclared variables
    variable1 = 100
    variable2 = 200
  )
)
