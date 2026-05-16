; Test case: Valid advanced SKILL syntax
; Expected: No errors

; Procedure with optional and key parameters
procedure(advancedProc(required @optional opt1 (opt2 10) @key (key1 "default") key2)
  let((result)
    result = list(required opt1 opt2 key1 key2)
    result
  )
)

; Prog with multiple variables
procedure(testProg()
  prog((x y z result)
    x = 1
    y = 2
    z = 3
    result = plus(plus(x y) z)
    return(result)
  )
)

; For loop
procedure(testFor()
  let((sum)
    sum = 0
    for(i 1 10
      sum = plus(sum i)
    )
    sum
  )
)

; While loop
procedure(testWhile()
  let(((counter 0) (result 0))
    while(counter < 10
      result = plus(result counter)
      counter = plus(counter 1)
    )
    result
  )
)

; Case statement
procedure(testCase(n)
  case(n
    (1 "one")
    (2 "two")
    (3 "three")
    (t "other")
  )
)

; Unless statement
procedure(testUnless(flag)
  unless(flag
    println("Flag is false")
    nil
  )
)

; Map-like operation using foreach
procedure(testMap(myList)
  let((result)
    result = nil
    foreach(x myList
      when(x > 0
        result = cons(x result)
      )
    )
    result
  )
)

; Filter operation using foreach
procedure(testFilter(myList)
  let((result)
    result = nil
    foreach(x myList
      when(x > 5
        result = cons(x result)
      )
    )
    result
  )
)

; List operations
procedure(testListOps()
  let((lst1 lst2 result)
    lst1 = list(1 2 3)
    lst2 = cons(0 lst1)
    result = append(lst1 lst2)
    result
  )
)

; Complex nested structures
procedure(complexNesting(data)
  let(((total 0) item)
    foreach(group data
      foreach(value group
        when(value
          total = plus(total value)
        )
      )
    )
    total
  )
)

; Multiple return points
procedure(multiReturn(x)
  cond(
    (x < 0
      return("negative")
    )
    (x == 0
      return("zero")
    )
    (t
      "positive"
    )
  )
)
