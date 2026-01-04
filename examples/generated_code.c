#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

Object* create_Object(int age);
User* create_User(int age, int a);
int User_get_age(User* self);
int main(void);

typedef struct Object {
    void** vtable;
    // Нет явных полей для Object
} Object;

typedef struct User {
    void** vtable;
    // Поля класса User
    int age;
} User;

// Конструктор для Object
Object* create_Object(int age) {
    Object* obj = malloc(sizeof(Object));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for Object\n");
        exit(1);
    }

    // Инициализация таблицы виртуальных методов
    obj->vtable = malloc(sizeof(void*) * 16);

    // Инициализация полей класса Object
    return obj;
}

// Конструктор для User
User* create_User(int age, int a) {
    User* obj = malloc(sizeof(User));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for User\n");
        exit(1);
    }

    // Инициализация таблицы виртуальных методов
    obj->vtable = malloc(sizeof(void*) * 16);

    // Инициализация полей класса User
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
