cimport <stdio.h>
cimport <stdlib.h>
cimport <string.h>
cimport <stdbool.h>


"""

class User:

    def __init__(self, age: int, a: int) -> None:
        self.age = age
        self.a: int = a
    
    def get_age(self) -> int:
        return self.age
    

    def get_future_age(self) -> int:
        if self.age > 10:
            return 100
        else:
            return 20




def main() -> int:

    var u: User = User(10, 1)
    # print(u.age)

    # var age: int = u.get_future_age()
    # print(age)

    del u

    return 0





class LinearLayer:
    def __init__(self, in_dim: int, out_dim: int):
        self.w = 1
        self.weights = 1
        self.bias = in_dim * out_dim
    
    def forward(self, x: int) -> int:
        return x * self.weights + self.bias

    def get_forward(self) -> int:
        return self.w

def main() -> int:
    # Создание модели
    var layer1: LinearLayer = LinearLayer(784, 256)
    var layer2: LinearLayer = LinearLayer(256, 10)


    var batch: int = 10

    var aaa: int = layer1.forward(batch)
    return 0
"""


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