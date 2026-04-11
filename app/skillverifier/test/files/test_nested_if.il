procedure(test(masterId edgeNum)
  if(masterId~>prBoundary
  then
     if(masterId~>prBoundary~>isRectangle
     then
          printf("rect\n")
          return(nil)
     )
     if(edgeNum > 0
     then
        printf("edge\n")
        return(nil)
     )
  else
     printf("no boundary\n")
     return(nil)
  )
)
