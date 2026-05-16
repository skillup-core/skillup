; Test case: Valid configuration-style code
; Expected: No errors

; Global configuration
maxSize = 100
minSize = 10
defaultName = "config"

; Configuration map
charMap = list("a" "b" "c" '("x" "X") '("y" "Y"))

; Simple configuration function
procedure(setConfig(key value)
  printf("Setting %s to %s\n" key value)
  t
)

; Retrieve configuration
procedure(getConfig(key defaultValue)
  let((result)
    result = defaultValue
    result
  )
)

; Process list of configurations
procedure(processConfigs(configList)
  let((count)
    count = 0
    foreach(cfg configList
      setConfig(cfg~>key cfg~>value)
      count = count + 1
    )
    count
  )
)

; Apply defaults with parameters
procedure(applyDefaults(max min name)
  let((settings)
    settings = list(max min name)
    setConfig("defaults" settings)
  )
)
