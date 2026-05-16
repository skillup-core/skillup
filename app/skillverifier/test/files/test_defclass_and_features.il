procedure(a(b c)
  foreach(i b
    i~>d = 1
    i->d = 1
  )
)

procedure(b(c d)
  foreach(i d
    if(i~>d == 1 e~>d = 1)
    if(i->d == 1 e->d = 1)
  )
)

procedure(c()
  if(z = z1 t) ; [skillverify]ignore_line
  if(z = z1 "[skillverify]ignore_line")
  if(z = z1 t) ; a [skillverify]ignore_line
  if(z = z1 t) ; [skillverify]ignore_line a
)

procedure(d(e f)
  if(e!=f t)
)

defclass(ccc
  (); base class
  (
    (m1 @initarg m1 @initform "-")
    (m2 @initarg m2 @initform "-")
  )
)

procedure(e(f)
let((i)
  i = makeInstance('ccc)
  i->m1 = "1"
  i~>m1 = "1"
))

procedure(f(g)
  (func1)~>cellName ; func1()~>cellName
  (func1)->cellName
)

procedure(g(h)
  z = func1()
  (if z==0 t)
)

procedure(h(i)
  z = func1()
  if(z=1 t)
  zz = func1()
  (if zz=1 t)
)

(procedure (func j)
  (if (isFile j) != t nil)
)

