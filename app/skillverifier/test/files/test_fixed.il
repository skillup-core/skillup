procedure(child1()
  parent1()
)

procedure(child2()
  parent1()
  procedure(parent1() ())
)

procedure(child3()
  procedure(parent1() ())
  parent1()
)

procedure(fn1()
let((var1 var3)
  var1 = 1
  var2 = 2
))

procedure(fn2() ()
)
