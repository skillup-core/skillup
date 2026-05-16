; test_code.il
; Comprehensive test file containing all error codes (W01-W03, E01-E07)
; This file demonstrates every type of error and warning that skillup can detect

; ============================================================================
; W01: undefined function call
; ============================================================================
procedure(testW01()
  undefinedFunction(123)  ; W01: calling a function that doesn't exist
)

; ============================================================================
; W02: using undeclared variable
; ============================================================================
procedure(testW02()
  undeclaredVar = 10  ; W02: using a variable that was never declared
)

; ============================================================================
; W03: assignment in condition (use == for comparison)
; ============================================================================
procedure(testW03()
  let(((x 5))
    if(x = 10 then  ; W03: using = instead of == in condition
      println("Wrong!")
    )
  )
)

; ============================================================================
; E01: declaring parameters as local variable
; ============================================================================
procedure(testE01(myParam)
  let(((myParam 100))  ; E01: redeclaring function parameter as local variable
    myParam
  )
)

; ============================================================================
; E02: function definition missing opening parenthesis after name
; ============================================================================
procedure (testE02()  ; E02: space between function keyword and opening paren
  println("test")
)

; ============================================================================
; E03: syntax error in if statement: multiple expressions require 'then' or 'else' keyword
; ============================================================================
procedure(testE03()
  if(t expr1 expr2 expr3)  ; E03: 4+ expressions without then/else keywords
)

; ============================================================================
; E04: mismatched parentheses
; ============================================================================
; Note: This error occurs at file level when parentheses don't match
; We can't include it here as it would prevent file parsing
; Example would be: (procedure(test() ... missing closing paren

; ============================================================================
; E05: parameter declaration with (name value) pair without @optional or @key
; ============================================================================
procedure(testE05((param 10))  ; E05: (param value) without @optional/@key
  param
)

; ============================================================================
; E06: non-identifier in variable binding position
; ============================================================================
procedure(testE06()
  let(((123 456))  ; E06: LPAREN followed by non-IDENT (number) in binding position
    x
  )
)

; ============================================================================
; E07: constant (number or string) in variable name position
; ============================================================================
procedure(testE07a()
  let(((123 "value"))  ; E07: number as variable name
    x
  )
)

procedure(testE07b()
  let((("string" 456))  ; E07: string as variable name
    x
  )
)

; ============================================================================
; E08: invalid cond clause syntax
; ============================================================================
procedure(testE08a()
  let(((a 1))
    cond(
      a == 1 printf("wrong")  ; E08: missing parentheses around clause
    )
  )
)

procedure(testE08b()
  let(((a 2))
    cond(
      ((a == 1) printf("ok"))
      a == 2 printf("wrong")  ; E08: missing parentheses around this clause
      ((a == 3) printf("ok"))
    )
  )
)

; ============================================================================
; E09: function parameter must be a symbol (identifier)
; ============================================================================
procedure(testE09a(b 1)  ; E09: number as parameter
let((c)
   printf("done\n")
))

procedure(testE09b(b c)
let((d e)
  d = lambda((e 1)  ; E09: number as lambda parameter
    foreach(i e~>?
      e += i
    )
  )
))

; ============================================================================
; Summary of all error codes in this file:
; - W01: Line 9  - undefined function call
; - W02: Line 16 - using undeclared variable
; - W03: Line 24 - assignment in condition
; - E01: Line 34 - declaring parameters as local variable
; - E02: Line 42 - function definition missing opening parenthesis after name
; - E03: Line 50 - if statement missing then/else
; - E04: (Excluded - would break parsing)
; - E05: Line 63 - parameter pair without @optional/@key
; - E06: Line 71 - non-identifier in binding position
; - E07: Line 80 and 86 - constant in variable name position
; - E08: Line 97 and 106 - invalid cond clause syntax
; - E09: Line 115 and 122 - function parameter must be a symbol
; ============================================================================
