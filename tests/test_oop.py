from tests.base import run


def test_oop_1():
    P = r"""
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
"""

    C = r"""
typedef struct Object Object;

struct Object {
    void** vtable;
    // Поля не найдены для Object
};

typedef struct User User;

struct User {
    // Наследование от Object
    Object base;
    // Поля класса User
    int age;
};

int User_get_age(User* self);
int main(void);

// Конструктор для Object
Object* create_Object(int age) {
    Object* obj = malloc(sizeof(Object));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for Object\n");
        exit(1);
    }

    // Инициализация полей класса Object
    obj->vtable = malloc(sizeof(void*) * 16);
    if (!obj->vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    return obj;
}

// Конструктор для User
User* create_User(int age, int a) {
    User* obj = malloc(sizeof(User));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for User\n");
        exit(1);
    }

    // Инициализация полей класса User
    obj->base.vtable = malloc(sizeof(void*) * 16);
    if (!obj->base.vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    obj->age = age;
    return obj;
}

int User_get_age(User* self) {
    return self->age;
}

int main(void) {
    User* u = create_User(10, 1);
    printf("%d\n", u->age);
    int age = User_get_age(u);
    printf("%d\n", age);
    return 0;
}
"""
    run(P, C)


def test_oop_2():
    P = r"""
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
"""

    C = r"""
typedef struct A A;

struct A {
    void** vtable;
    // Поля не найдены для A
};

typedef struct B B;

struct B {
    void** vtable;
    // Поля не найдены для B
};

typedef struct User User;

struct User {
    // Наследование от A
    A base;
    // Поля класса User
    int age;
};

int A_get_age_2(A* self);
int B_get_age(B* self);
int B_get_age_1(B* self);
int User_get_age(User* self);
int main(void);

// Конструктор для A
A* create_A(void) {
    A* obj = malloc(sizeof(A));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for A\n");
        exit(1);
    }

    obj->vtable = malloc(sizeof(void*) * 16);
    if (!obj->vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    return obj;
}

// Конструктор для B
B* create_B(void) {
    B* obj = malloc(sizeof(B));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for B\n");
        exit(1);
    }

    obj->vtable = malloc(sizeof(void*) * 16);
    if (!obj->vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    return obj;
}

// Конструктор для User
User* create_User(int age, int a) {
    User* obj = malloc(sizeof(User));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for User\n");
        exit(1);
    }

    // Инициализация полей класса User
    obj->base.vtable = malloc(sizeof(void*) * 16);
    if (!obj->base.vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    obj->age = age;
    return obj;
}

int User_get_age_2(User* self) {
    // Вызов унаследованного метода из A
    A* base_obj = (A*)self;
    return A_get_age_2(base_obj);
}

int User_get_age_1(User* self) {
    // Вызов унаследованного метода из B
    B* base_obj = (B*)self;
    return B_get_age_1(base_obj);
}

int A_get_age_2(A* self) {
    return 1;
}

int B_get_age(B* self) {
    return 1;
}

int B_get_age_1(B* self) {
    return 10;
}

int User_get_age(User* self) {
    return self->age;
}

int main(void) {
    User* u = create_User(10, 1);
    int age = User_get_age_2(u);
    printf("%d\n", age);
    return 0;
}
"""
    run(P, C)


def test_oop_3():
    P = r"""
class Matrix:
    def __init__(self, data: list[int]):
        self.data = data
    
    def get(self) -> int:
        var item: int = self.data[10]
        return item
"""

    C = r"""
typedef struct Matrix Matrix;

struct Matrix {
    void** vtable;
    // Поля класса Matrix
    list_int* data;
};

int Matrix_get(Matrix* self);
int main(void);

// Конструктор для Matrix
Matrix* create_Matrix(list_int* data) {
    Matrix* obj = malloc(sizeof(Matrix));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for Matrix\n");
        exit(1);
    }

    // Инициализация полей класса Matrix
    obj->vtable = malloc(sizeof(void*) * 16);
    if (!obj->vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    obj->data = data;
    return obj;
}

int Matrix_get(Matrix* self) {
    int item = get_list_int(self->data, 10);
    return item;
}
"""
    run(P, C)


def test_oop_4():
    P = r"""
class A:
    def __init__(self) -> None:
        self.value: int = 100

    def get_value(self) -> int:
        return self.value


class B:
    def __init__(self) -> None:
        pass

    def get_A_value(self) -> int:
        var a: A = A()
        var value: int = a.value
        value = a.get_value()
        return value

    def set_A_value(self, new_value: int) -> None:
        var a: A = A()
        a.value = new_value


class C(A):
    def __init__(self) -> None:
        pass        


def main() -> int:
    var c: C = C()
    print(c.get_value())
    return 0
"""

    C = r"""
typedef struct A A;

struct A {
    void** vtable;
    // Поля класса A
    int value;
};

typedef struct B B;

struct B {
    void** vtable;
    // Поля не найдены для B
};

typedef struct C C;

struct C {
    // Наследование от A
    A base;
    // Поля не найдены для C
};

int A_get_value(A* self);
int B_get_A_value(B* self);
void* B_set_A_value(B* self, int new_value);
int main(void);

// Конструктор для A
A* create_A(void) {
    A* obj = malloc(sizeof(A));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for A\n");
        exit(1);
    }

    // Инициализация полей класса A
    obj->vtable = malloc(sizeof(void*) * 16);
    if (!obj->vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    obj->value = 100;
    return obj;
}

// Конструктор для B
B* create_B(void) {
    B* obj = malloc(sizeof(B));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for B\n");
        exit(1);
    }

    // Инициализация полей класса B
    obj->vtable = malloc(sizeof(void*) * 16);
    if (!obj->vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    return obj;
}

// Конструктор для C
C* create_C(void) {
    C* obj = malloc(sizeof(C));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for C\n");
        exit(1);
    }

    // Инициализация полей класса C
    obj->base.vtable = malloc(sizeof(void*) * 16);
    if (!obj->base.vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    return obj;
}

int C_get_value(C* self) {
    // Вызов унаследованного метода из A
    A* base_obj = (A*)self;
    return A_get_value(base_obj);
}

int A_get_value(A* self) {
    return self->value;
}

int B_get_A_value(B* self) {
    A* a = create_A();
    int value = a->value;
    value = A_get_value(a);
    return value;
}

void* B_set_A_value(B* self, int new_value) {
    A* a = create_A();
    a->value = new_value;
}

int main(void) {
    C* c = create_C();
    printf("%d\n", C_get_value(c));
    return 0;
}
"""
    run(P, C)
