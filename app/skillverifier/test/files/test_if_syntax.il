; global_variable
x = 0

; Test cases for if statement syntax validation

; Valid: basic if with 2 parameters (condition, then)
procedure(test1()
  if(x > 0 x = 1)
)

; Valid: basic if with 3 parameters (condition, then, else)
procedure(test2()
  if(x > 0 x = 1 x = -1)
)

; Valid: if with 'then' keyword and multiple expressions
procedure(test3()
  if(x > 0 then x = 1 x = 2 x = 3)
)

; Valid: if with 'then' and 'else' keywords
procedure(test4()
  if(x > 0 then x = 1 x = 2 else x = -1 x = -2)
)

; Valid: if with only 'else' keyword
procedure(test5()
  if(x > 0 x = 1 else x = -1 x = -2)
)

; INVALID: 4 parameters without 'then' or 'else'
procedure(test6()
  if(x > 0 x = 1 x = -1 x = 3)
)

; INVALID: 5 parameters without 'then' or 'else'
procedure(test7()
  if(x > 0 x = 1 x = -1 x = 3 x = 4)
)

; Valid: parenthesized form with 'then'
procedure(test8()
  (if x > 0 then x = 1 x = 2)
)

; INVALID: parenthesized form with 4 parameters, no 'then'/'else'
procedure(test9()
  (if x > 0 x = 1 x = -1 x = 3)
)
