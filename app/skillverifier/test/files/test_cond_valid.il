; test_cond_valid.il
; Test file for valid cond syntax patterns

; Valid: Modern form - multiple expressions without parentheses
procedure(testCondModern(a)
  cond(
    ((a == 1) printf("a=1\n") printf("A=1\n"))
    ((a == 2) printf("a=2\n"))
    (t printf("none\n"))
  )
)

; Valid: Old form - all expressions in parentheses
procedure(testCondOld(a)
  cond(
    ((a == 3) (printf "a=3\n") (printf "A=3\n"))
    ((a == 4) (printf "a=4\n"))
    (t (printf "default\n"))
  )
)

; Valid: Mixed form - old and modern mixed
procedure(testCondMixed(a)
  cond(
    ((a == 4) (printf "a=4\n") printf("A=4\n"))
    ((a == 5) printf("a=5\n") (printf "A=5\n"))
    (t printf("none\n"))
  )
)

; Valid: Parenthesized cond form
procedure(testCondParen(x)
  (cond
    ((x == 1) printf("one"))
    ((x == 2) printf("two"))
    (t printf("other"))
  )
)

; Valid: Default clause with symbol t
procedure(testCondDefault(n)
  cond(
    ((n < 0) printf("negative"))
    ((n > 0) printf("positive"))
    (t printf("zero"))
  )
)
