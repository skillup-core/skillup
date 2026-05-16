procedure(testParenthesizedExpressions()
  let( ((shape nil) (x "test") (y 0) (a 1) (b 2) (c 3))
    ; Test 1: Simple parenthesized expression with binary operator
    if((nil == shape->pin) then
      y = 1
    )

    ; Test 2: Multiple parenthesized expressions with &&
    if((nil == shape->pin) && (x != "metal") then
      y = 2
    )

    ; Test 3: Complex nested expressions
    if((a > 0) && (b < 10) || (c == 3) then
      y = 3
    )

    ; Test 4: Mixed operators
    if((a + b) > 5 && (c * 2) < 10 then
      y = 4
    )

    ; Test 5: Parenthesized expression as function argument
    when((a == 1) && (b == 2)
      y = 5
    )
  )
)
