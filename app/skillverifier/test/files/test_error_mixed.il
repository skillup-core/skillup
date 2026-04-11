; Test case: Mixed errors (undeclared, redeclaration, parentheses)
; Expected: Multiple types of errors

; Error: Undeclared variable in global scope
config = unknownVar

; Error: Duplicate parameters
procedure(mixedError1(x y x)
  let((result)
    result = x + y + z
    result
  )
)

; Error: Parameter redeclaration and undeclared in loop
procedure(mixedError2(counter)
  let((counter sum)
    sum = 0
    foreach(item myList
      sum = sum + item
    )
    sum
  )
)

; Error: Undeclared variable
procedure(mixedError3(x)
  let((result)
    result = plus(x undeclaredValue)
    result
  )
)

; Multiple errors in one function
procedure(messyFunction(a b a)
  let((c)
    c = a + b + missing1
    when(c > threshold
      println(c)
    )
  )
)

; Valid function for contrast
procedure(cleanFunction(x y z)
  let((result)
    result = plus(plus(x y) z)
    result
  )
)
