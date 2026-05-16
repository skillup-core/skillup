; Test case: Undeclared variable errors
; Expected: Multiple undeclared variable errors

; Error 1: Using undeclared variable in global scope
globalResult = undeclaredVar + 10

; Error 2: Using undeclared variable in procedure
procedure(testUndeclared(x)
  let((result)
    result = x + missingVariable
    result
  )
)

; Error 3: Undeclared variable in loop
procedure(loopError(myList)
  foreach(item myList
    total = total + item  ; 'total' not declared
  )
)

; Error 4: Undeclared in conditional
procedure(conditionalError(val)
  if(val > threshold then
    println("High")
  )
  t
)

; Error 5: Property access on undeclared object
procedure(propertyError()
  let((name)
    name = unknownObject~>name
    name
  )
)

; Error 6: Multiple undeclared in expression
procedure(multipleErrors(a)
  let((result)
    result = a + b + c + d
    result
  )
)

; Valid function for reference
procedure(validFunction(x y)
  let((sum)
    sum = x + y
    sum
  )
)
