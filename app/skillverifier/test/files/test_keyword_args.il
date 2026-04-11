procedure(testKeywordArgs()
  let(((layer "metal1") (layerChoices '("metal1" "metal2")) (form nil))
    ; Test keyword argument syntax - ? parameters are parameter names, not variables
    form = hiCreateCyclicField(
        ?name concat(layer)
        ?prompt layer
        ?choices layerChoices
        ?value "default"
        ?callback "myCallback"
    )

    ; Regular function call - should detect undeclared variable
    when(undeclaredVar == 1
        printf("This should error\n")
    )
  )
)
