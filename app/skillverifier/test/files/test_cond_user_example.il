; Test file based on user's example
procedure(testCondExample(a)
  cond(
    ((a == 1) printf("a=1\n") printf("A=1\n"))
    ((a == 2) printf("a=2\n"))
    ((a == 3) (printf "a=3\n") (printf "A=3\n"))
    ((a == 4) (printf "a=4\n") printf("A=4\n"))
    (t printf("none\n"))
  )
)
