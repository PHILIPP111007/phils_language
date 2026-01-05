# Phils language

## Info

This program is a Python-like implementation of the C language.

Because it's similar to Python, the entry barrier is low. My goal is to make it as memory-safe as possible, which is something C lacks.

I'm creating this language for specialists working primarily with neural networks. But it can be used anywhere, as it's almost a complete copy of C.

In the future, I'll implement object-oriented programming in it.

## Examples

Imports:

```python
cimport "my_header.h" # your module in C
cimport <my_header.h> # system import
import "./module.p" # your module
```

```python
def main() -> None:
    var x: int = 0
    x = x + 1

def main() -> None:
    def func() -> int:
        return 1
    var x: int = 10
    if x < 10:
        if 1 < 10:
            func()
        else:
            func()
    return
```

Input:

```python
def main() -> int:
    var name: str = input("Enter your name: ")
    print("Hello, ", name)
    return 0
```

Cycles:

```python
def main() -> int:
    for i in range(0, 10, -1):
        print("i = ", i)
    return 0
```

del:

```python
def func() -> str:
    return "qepfko"

def main() -> int:
    var a: int = 1 + 10

    del_pointer a

    var b: str = func()

    del b
    var b: str = "1"

    return 0
```

C code -> function should starts with @:

```python
cimport <math.h>

def main() -> float:
    var a: float = @sqrt(16)   # C code -> function should starts with @
    return a
```

Tuples and lists:

```python
def main() -> int:

    var a: tuple[int] = (1, 2)
    var b: int = len(a)

    var c: list[int] = [1, 2, 3,]
    var x: int = len(c)

    return 0

def main() -> int:
    var A: list[list[list[int]]] = [[[1], [2]], [[1], [2]]]

    del A

    var A: list[list[int]] = [[1, 2], [1, 2]]

    var a: list[int] = [1, 2]
    var b: tuple[int] = (1, 2)
    var c: list[tuple[int]] = [ (1, 2), (1, 2) ]

    return 0

def main() -> int:
    var t1: tuple[int] = (1, 2, 3)
    var l: list[tuple[int]] = []
    l.append(t1)
    return 0
```

Methods:

```python
def main() -> int:
    var a: str = "pdked"
    a.upper()
    var b: list[str] = a.split(" ")
    return 0
```

OOP:

```python
class Object:
    def __init__(self, age: int) -> None:
        pass

class User(Object):
    def __init__(self, age: int, a: int) -> None:
        self.age = age
    
    def get_age(self) -> int:
        return self.age


def main() -> int:
    var u: User = User(10, 1)
    print(u.age)

    var age: int = u.get_age()
    print(age)

    return 0
```