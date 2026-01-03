cimport <stdio.h>
cimport <stdlib.h>
cimport <string.h>
cimport <stdbool.h>
cimport <math.h>



def main() -> int:
    
    var a: int = 100
    var result: str = ""

    if a > 101:
        result = "10"
    elif a == 10:
        result = "10"
    else:
        result = "undefined"
    
    print(result)


    return 0
