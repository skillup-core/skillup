; Test case: Valid basic SKILL syntax
; Expected: No errors

; Global variable assignment
globalVar = 10

; Simple procedure with parameters
procedure(addNumbers(a b)
  plus(a b)
)

; Procedure with local variables
procedure(calculateSum(x y)
  let((result temp)
    result = plus(x y)
    temp = times(result 2)
    temp
  )
)

; Using let with initialized variables
procedure(testLet()
  let(((counter 0) (name "test") flag)
    counter = plus(counter 1)
    flag = t
    counter
  )
)

; Foreach loop
procedure(iterateList(myList)
  let((sum)
    sum = 0
    foreach(item myList
      sum = plus(sum item)
    )
    sum
  )
)

; Conditional statements
procedure(testConditional(val)
  if(val > 10 then
    println("Greater than 10")
  else
    println("Less or equal to 10")
  )
)

; When statement
procedure(testWhen(x)
  when(x > 0
    println("Positive")
    x
  )
)

; Cond statement
procedure(testCond(n)
  cond(
    (n == 0 "zero")
    (n > 0 "positive")
    (t "negative")
  )
)

; Nested functions
procedure(outerFunc(a)
  procedure(innerFunc(b)
    plus(a b)
  )
  innerFunc(5)
)

; Property access
procedure(testProperty(obj)
  let((val1 val2)
    val1 = obj~>name
    val2 = obj->value
    list(val1 val2)
  )
)

; If statement with cons cell comparison (3-parameter form without then/else keywords)
procedure(a(b c)
  let((d)
    if(b:b == c:c printf("done\n") printf("fail\n"))
  )
)

; Function with @optional parameters
procedure(a(b c @optional (d 3) (e 0))
let((f)
  printf("%L %L %L %L\n" b c d e)
))
