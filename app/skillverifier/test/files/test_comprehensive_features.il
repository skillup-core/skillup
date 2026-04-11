procedure(a()
prog((b)
  b = lambda((p1 p2)
    p1+p2
  )
))

procedure(b(c d e)
  funcall(reducer mapcar(e setof(i c funcall(d i))))
)

global_variable = 0

procedure(c()
prog(()
  abs(g)
  abs(global_variable)
  abs(function_as_variable) ; it's ok!
  abs(z)
))

procedure(function_as_variable()
  t
)

procedure(d(e g)
  if(e == g-1 then g = 0)
)

procedure(f(g h v)
  v = setof(i g[1]~>a i~>b == 1 && (i[2]~>c=="d"))
  v = setof(i g[1]->a i->b == 1 && (i[2]->c=="d"))
)

procedure(g(h i)
  if(f(h) > f(h) - 1 || f(h) < f(h)+1 then
    printf("a")
  )
)

procedure(h(i j)
prog((k)
  k = 1
  let((l)
    l = k
  )
  l = 999
))

procedure(i(a b)
  for(j 0 1 printf("%d\n" j))
  foreach(j a printf("%L\n" j))
  c = lambda((a b) a+b)
  d = a + b
)

; ==============================================================================
; TEST SUMMARY
; ==============================================================================
; This comprehensive test file covers multiple advanced SKILL features:
;
; 1. Lambda functions (lines 3-5)
;    - Lambda with parameters that create local scope
;    - Parameters p1, p2 should NOT generate undeclared errors
;
; 2. Setof loops (lines 9, 31-32)
;    - Setof loop variable 'i' creates local scope
;    - Variable 'i' should NOT generate undeclared errors
;    - Complex expressions with array access and property operators
;
; 3. Global variables (line 12)
;    - Top-level assignment 'global_variable = 0' declares global variable
;    - Can be used in any function after declaration (line 17)
;
; 4. Function names as variables (lines 16, 18, 22-24)
;    - Function 'g' can be referenced as a variable (line 16)
;    - Function 'function_as_variable' can be referenced (line 18)
;    - This is valid SKILL behavior
;
; 5. Property access with array indexing (lines 31-32)
;    - g[1]~>a : array access followed by property access
;    - i[2]->c : array access followed by different property operator
;    - Parenthesized: (i[2]~>c=="d")
;
; 6. For/Foreach loops (lines 51-52)
;    - Loop variable 'j' creates local scope
;    - Should NOT generate undeclared errors
;
; 7. Tokenizer fix for minus operator (line 27)
;    - 'g-1' should be parsed as 'g - 1' (binary minus)
;    - NOT as 'g' followed by '-1' (negative number)
;
; 8. Let/Prog scoping (lines 42-48)
;    - Variable 'l' declared in let scope (line 44)
;    - Using 'l' outside let scope generates error (line 47)
;
; 9. Assignment to function names (lines 53-54)
;    - Assigning to 'c' which is a function name (not variable)
;    - Assigning to 'd' which is a function name (not variable)
;    - These should generate undeclared variable errors
;
; Expected errors:
; - Undefined builtin functions: funcall, mapcar, abs
; - Undeclared variables: reducer, z, l, c, d
