(procedure myFunction1()
    let((x y z myList)
        for( i 1 10000
           myList = myFunction2(i)
        )
        myList
    )
)

(procedure myFunction2(object myList)
    if(myTest(object)
        then printf("Starting with object %d...\n" object)
    )
    if(object == 1000
        then printf("Ending with object %d...\n" object)
    )
    if(object < 1000
        then append(myList ncons(object ))
        else myList
    )
)
