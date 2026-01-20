from tests.base import run


def test_c_code_math():
    P = r"""
cimport <math.h>

def main() -> float:
    var a: float = @sqrt(16)   # C code -> function should starts with @
    return a
"""

    C = """
float main(void) {
    float a = sqrt(16);
    return a;
}
"""
    run(P, C)


def test_c_code_pthread():
    P = r"""
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
"""

    C = r"""
struct Object {
    void** vtable;
    // Поля класса Object
    int a;
};

int Object_get_a(Object* self);
int main(void);

// Конструктор для Object
Object* create_Object(int a) {
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
    obj->a = a;
    return obj;
}

int Object_get_a(Object* self) {
    return self->a;
}

void* backward_worker(void* arg) {
    Object* a = arg;
    int b = Object_get_a(a);
    printf("%d\n", b);
    return NULL;
}

int main(void) {
    pthread_t thread = NULL;
    Object* backward_thread_data = create_Object(100);
    pthread_create(&thread, NULL, backward_worker, backward_thread_data);
    pthread_join(thread, NULL);
    return 0;
}
"""
    run(P, C)
