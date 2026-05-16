; Test case: Parameter redeclaration errors
; Expected: Multiple redeclaration errors

; Error 1: Duplicate parameter names
procedure(duplicateParams(x y x)  ; 'x' appears twice
  plus(x y)
)

; Error 2: Parameter redeclared in let
procedure(paramInLet(a b)
  let((a c)
    a = b + c
    a
  )
)

; Error 3: Multiple parameters with same name
procedure(tripleParam(value value value)  ; 'value' appears three times
  times(value 2)
)

; Error 4: Optional parameter redeclaration
procedure(optionalDup(x @optional x y)  ; 'x' appears twice
  plus(x y)
)

; Error 5: Key parameter redeclaration
procedure(keyDup(@key (name "default") name)  ; 'name' appears twice
  println(name)
)

; Error 6: Nested function parameter shadow
procedure(outerRedecl(param1)
  let((param1)
    procedure(innerFunc(param1)
      param1
    )
    param1
  )
)

; Valid function for reference
procedure(validParams(a b c)
  let((x y z)
    x = a
    y = b
    z = c
    plus(plus(x y) z)
  )
)
