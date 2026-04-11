procedure(test()
  let(((shape nil) (x "test") (y 0))
    ; Test parenthesized expressions with binary operators
    if((nil == shape->pin) && (x != "metal") then
      y = 1
    )
  )
)
