procedure(testQuoteAndBacktick()
  let(((x 'symbol) (y `atom) (z 10))
    ; Test 1: Quote in if condition
    if( x == 'symbol then
      printf("quote works\n")
    )

    ; Test 2: Backtick in if condition
    if( y == `atom then
      printf("backtick works\n")
    )

    ; Test 3: Quote with parenthesized expression
    if( (x == 'symbol) && (y == `atom) then
      printf("combined works\n")
    )

    ; Test 4: Complex expression with multiple quotes
    when( x == 'foo || y == `bar
      printf("multiple quotes work\n")
    )
  )
)
