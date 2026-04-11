; Test file for define feature - without define file
; This should report all 4 errors: func1, func2, variable1, variable2

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
