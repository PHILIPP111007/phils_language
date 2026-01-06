# Phils language v1.0.0

## Info

This program is a Python-like implementation of the C language.

Because it's similar to Python, the entry barrier is low. My goal is to make it as memory-safe as possible, which is something C lacks.

I'm creating this language for specialists working primarily with neural networks. But it can be used anywhere, as it's almost a complete copy of C.

## Examples

### Imports

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

### Input

```python
def main() -> int:
    var name: str = input("Enter your name: ")
    print("Hello, ", name)
    return 0
```

### Cycles

```python
def main() -> int:
    for i in range(0, 10, -1):
        print("i = ", i)
    return 0
```

### del

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

### C code -> function should starts with @

```python
cimport <math.h>

def main() -> float:
    var a: float = @sqrt(16)   # C code -> function should starts with @
    return a
```

### Tuples and lists

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



def main() -> int:
    var my_list: list[int] = [1, 2, 3, 4, 5]
    var my_tuple: tuple[int] = (1, 2, 3, 4, 5)

    var xxxx: list[int] = my_list[2:]

    # 1. Обращение по индексу (чтение)
    var x: int = my_list[0]
    var x1: int = my_tuple[1]

    # 2. Присваивание по индексу
    my_list[0] = 10
    my_list[1:3] = [20, 30]

    # 3. Составные операции с индексами
    my_list[0] += 5
    my_list[1] *= 2

    # 4. Срезы
    var sub_list: list[int] = my_list[1:4]
    var sub_tuple: tuple[int] = my_tuple[2:]

    return 0
```

### Methods

```python
def main() -> int:
    var a: str = "Hello world"
    a = a.upper()
    a = a.lower()
    var a_list: list[str] = a.split(" ")

    var c: int = 100
    var c1: str = str(c)

    var d: str = "10"
    var d1: int = int(d)

    return 0

def main() -> int:
    var a: str = "Hello "
    a = a.format("world")
    return 0
```

### OOP

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

```python
class A:
    def get_age_2(self) -> int:
        return 1

class B:
    def get_age(self) -> int:
        return 1
    
    def get_age_1(self) -> int:
        return 10

class User(A, B):
    def __init__(self, age: int, a: int) -> None:
        self.age = age
    
    def get_age(self) -> int:
        return self.age

def main() -> int:
    var u: User = User(10, 1)
    var age: int = u.get_age_2()

    print(age)

    return 0
```

#### Note

Don't use self.ATTRIBUTE directly in your expressions.

```python
class Matrix:
    def __init__(self, data: list[int]):
        self.data = data
    
    def get(self) -> int:
        var a: list[int] = self.data
        var item: int = a[10]
        return item
```

Converts to

```c
int Matrix_get(Matrix* self) {
    list_int* a = self->data;
    int item = get_list_int(a, 10);
    return item;
}
```

And

```python
class Matrix:
    def __init__(self, data: list[int]):
        self.data = data
    
    def get(self) -> int:
        var item: int = self.data[10]
        return item
```

Converts to

```c
int Matrix_get(Matrix* self) {
    int item = self->data[10];  // Here is an error
    return item;
}

// a value of type "list_int" (aka "struct <unnamed>") cannot be used to initialize an entity of type "int"
```

### Pthread

```python
cimport <stdio.h>
cimport <stdlib.h>
cimport <string.h>
cimport <stdbool.h>
cimport <pthread.h>

class Object:
    def __init__(self, a: int):
        self.a = a
    
    def get_a(self) -> int:
        return self.a

def backward_worker(arg: None) -> None:
    var a: Object = arg
    var b: int = a.get_a()
    print(b)
    return None

def main() -> int:
    var thread: pthread_t = None
    var backward_thread_data: Object = Object(100)

    @pthread_create(&thread, NULL, backward_worker, backward_thread_data)
    @pthread_join(thread, NULL)
    return 0
```
