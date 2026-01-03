"""
import "./module.p"


def main() -> int:
    var a: int = 10
    var b: int = 100
    
    var c: int = 0
    c = mul(a, b)
    # var x: int = dd
    print(c)

    var s: str = 10 * "asff"

    var x: int = 0
    x = 1 + 1 / 10

    var xx: dict = {}
    var xxx: dict = {"a": 1}


    var p: *int = &x
    *p = 10
    print(p)

    var ddd: list = [1, 2, 3, 4]

    var aaa: float = 1.001



    var x: int = 10
    var result: str = ""

    if x > 20:
        result = "больше 20"
    elif x > 10:
        result = "больше 10"
    elif x > 0:
        result = "положительное"
    else:
        result = "меньше или равно 0"
        var xx: int = 100
    
    return 0


def main() -> None:
    var x: int = 0
    del x
    var x: int = 100

    var r: str = "woef"

    var s: int = x * 10

    return 1


cimport "my_header.h"
cimport <my_header.h>
import "./module.p"


def main() -> None:
    var x: int = 0

    x = x + 1

"""







def func() -> int:
    var x: int = 5
    var y: int = 10           # ← y не используется

    return x                  # Возвращаем только x