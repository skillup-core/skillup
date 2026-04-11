procedure(test1()
  let( ((x 1))
    if(x > 0
    then
       printf("A\n")
       printf("B\n")
    else
       printf("C\n")
       printf("D\n")
    )
  )
)

procedure(test2()
  let( ((x 1))
    if(x > 0
    then
       if(x > 10 printf("Big\n"))
       if(x > 5 printf("Medium\n"))
    else
       printf("Small\n")
    )
  )
)
