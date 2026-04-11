procedure(test1(x)
  if(x > 0
  then
     printf("A\n")
     printf("B\n")
  else
     printf("C\n")
  )
)

procedure(test2(x)
  if(x > 0
  then
     if(x > 10 printf("Big\n"))
     if(x > 5 printf("Medium\n"))
  else
     printf("Small\n")
  )
)
