; Test file for invalid cond syntax patterns (should trigger E08)

; Invalid: Missing parentheses around entire clause
procedure(testCondInvalid1(a)
  cond(
    a == 1 printf("wrong")  ; E08: missing outer parentheses
  )
)

; Invalid: Mixed valid and invalid clauses
procedure(testCondInvalid2(a)
  cond(
    ((a == 1) printf("ok"))  ; valid
    a == 2 printf("wrong")   ; E08: invalid
    ((a == 3) printf("ok"))  ; valid
  )
)

; Invalid: Condition without parentheses
procedure(testCondInvalid3(a)
  cond(
    (a == 1 printf("wrong"))  ; This is actually valid - wrapped in parens
    a printf("wrong")         ; E08: not wrapped in parens
  )
)
