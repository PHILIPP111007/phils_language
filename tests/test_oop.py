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
