; Test nested function definitions

; This should pass - function defined before use
procedure(test1()
  procedure(helper() ())
  helper()
)

; This should pass with two-pass - forward reference
procedure(test2()
  helper()
  procedure(helper() ())
)

; This should fail - helper not defined
procedure(test3()
  helper()
)

; Nested within nested
procedure(test4()
  procedure(outer()
    procedure(inner() ())
    inner()
  )
  outer()
)
