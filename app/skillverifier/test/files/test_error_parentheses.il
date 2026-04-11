; Test case: Mismatched parentheses errors
; Expected: Parenthesis mismatch errors

; Error 1: Missing closing parenthesis in procedure
procedure(missingClose(x y)
  let((result))
    result = plus(x y)
    result
  ; Missing closing paren for procedure
)

; Valid function
procedure(validFunc1(a)
  plus(a 1)
)

; Error 2: Extra closing parenthesis
procedure(extraClose(x)
  let((val))
    val = times(x 2)
    val
  )
))  ; Extra closing paren

; Error 3: Missing closing in let
procedure(letMissingClose(x)
  let((a b)
    a = x
    b = times(x 2)
    plus(a b)
  ; Missing closing paren for let
)

; Error 4: Mismatched in nested expression
procedure(nestedMismatch(x)
  let((result))
    result = plus(times(x 2) minus(x 3)  ; Missing closing paren
    result
  )
)

; Valid function
procedure(validFunc2(x y)
  times(plus(x y) 2)
)
