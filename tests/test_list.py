from tests.base import run


def test_list_append():
    P = r"""
def main() -> int:
    var a: list[int] = [1, 2, 3]
    a.append(1)
    del a

    var b: list[list[int]] = []
    var b_1: list[int] = [1, 2, 3, 4]
    b.append(b_1)
    del b

    return 0
"""

    C = """
int main(void) {
    list_int* a = create_list_int(4);
    append_list_int(a, 1);
    append_list_int(a, 2);
    append_list_int(a, 3);
    append_list_int(a, 1);
    // del a
    if (a) {
        free_list_int(a);
    }
    a = NULL;
    list_list_int* b = create_list_list_int(4);
    list_int* b_1 = create_list_int(4);
    append_list_int(b_1, 1);
    append_list_int(b_1, 2);
    append_list_int(b_1, 3);
    append_list_int(b_1, 4);
    append_list_list_int(b, b_1);
    // del b
    if (b) {
        free_list_list_int(b);
    }
    b = NULL;
    return 0;
}
"""
    run(P, C)


def test_list_pop_1():
    P = r"""
def main() -> int:
    var a: list[int] = [1, 2, 3]
    
    a.pop(0)
    a.pop()

    return 0
"""

    C = r"""
int main(void) {
    list_int* a = create_list_int(4);
    append_list_int(a, 1);
    append_list_int(a, 2);
    append_list_int(a, 3);
    if (a && 0 >= 0 && 0 < a->size) {
        int temp_0 = a->data[0];
        for (int i = 0; i < a->size - 1; i++) {
            a->data[i] = a->data[i + 1];
        }
        a->size--;
        // Результат pop() используется, но не присвоен
    } else {
        fprintf(stderr, "IndexError: pop index out of range\n");
        exit(1);
    }
    if (a && a->size > 0) {
        int temp_1 = a->data[a->size - 1];
        a->size--;
        // Результат pop() используется, но не присвоен
    } else {
        fprintf(stderr, "IndexError: pop from empty list\n");
        exit(1);
    }
    return 0;
}
"""
    run(P, C)


def test_list_pop_2():
    P = r"""
def main() -> int:
    var a: list[int] = [1, 2, 3]
    
    var b: int = 0
    b = a.pop(0)

    print(b)

    return 0
"""

    C = r"""
int main(void) {
    list_int* a = create_list_int(4);
    append_list_int(a, 1);
    append_list_int(a, 2);
    append_list_int(a, 3);
    int b = 0;
    if (a && 0 >= 0 && 0 < a->size) {
        int temp_0 = a->data[0];
        for (int i = 0; i < a->size - 1; i++) {
            a->data[i] = a->data[i + 1];
        }
        a->size--;
        b = temp_0;
    } else {
        fprintf(stderr, "IndexError: pop index out of range\n");
        exit(1);
    }
    printf("%d\n", b);
    return 0;
}
"""
    run(P, C)


def test_list_set_list_int():
    P = r"""
def main() -> int:
    var a: list[int] = [1, 2, 3]
    a[0] = 10
    return 0
"""

    C = r"""
int main(void) {
    list_int* a = create_list_int(4);
    append_list_int(a, 1);
    append_list_int(a, 2);
    append_list_int(a, 3);
    set_list_int(a, 0, 10);
    return 0;
}
"""
    run(P, C)


def test_list_get_list_int():
    P = r"""
def main() -> int:
    var a: list[int] = [1, 2, 3]
    var a1: int = a[0]
    return 0
"""

    C = r"""
int main(void) {
    list_int* a = create_list_int(4);
    append_list_int(a, 1);
    append_list_int(a, 2);
    append_list_int(a, 3);
    int a1 = get_list_int(a, 0);
    return 0;
}
"""
    run(P, C)


def test_list_get_list_str():
    P = r"""
def main() -> int:
    var a: list[str] = ["1", "2"]
    var a1: str = a[0]
    return 0
"""

    C = r"""
int main(void) {
    list_str* a = create_list_str(4);
    append_list_str(a, "1");
    append_list_str(a, "2");
    char* a1 = get_list_str(a, 0);
    return 0;
}
"""
    run(P, C)


def test_list_set_list_str():
    P = r"""
def main() -> int:
    var a: list[str] = ["1", "2"]
    a[0] = "100"
    return 0
"""

    C = r"""
int main(void) {
    list_str* a = create_list_str(4);
    append_list_str(a, "1");
    append_list_str(a, "2");
    set_list_str(a, 0, "100");
    return 0;
}
"""
    run(P, C)


def test_list_add_number_to_list_item():
    P = r"""
def main() -> int:
    var a: list[int] = [1, 2, 3]
    a[1] += 1
    return 0
"""

    C = r"""
int main(void) {
    list_int* a = create_list_int(4);
    append_list_int(a, 1);
    append_list_int(a, 2);
    append_list_int(a, 3);
    int temp_0 = get_list_int(a, 1);
    temp_0 += 1;
    set_list_int(a, 1, temp_0);
    return 0;
}
"""
    run(P, C)


def test_list_indexes():
    P = r"""
def main() -> int:
    var A: list[list[list[int]]] = []
    var a: list[list[int]] = []
    var a1: list[int] = [1, 2, 3, 4, 5]

    a.append(a1)
    A.append(a)

    a1[0] = 100
    a[0][0] = 100
    A[0][0][0] = 100 + 1

    var b: int = A[0][0][0]
    print(b)

    b = A[0][0][0] + A[0][0][1]
    A[0][0][2] = A[0][0][0] + A[0][0][1]

    return 0
"""

    C = r"""
int main(void) {
    list_list_list_int* A = create_list_list_list_int(4);
    list_list_int* a = create_list_list_int(4);
    list_int* a1 = create_list_int(5);
    append_list_int(a1, 1);
    append_list_int(a1, 2);
    append_list_int(a1, 3);
    append_list_int(a1, 4);
    append_list_int(a1, 5);
    append_list_list_int(a, a1);
    append_list_list_list_int(A, a);
    set_list_int(a1, 0, 100);
    list_int* temp_0 = get_list_list_int(a, 0);
    set_list_int(temp_0, 0, 100);
    list_list_int* temp_1 = get_list_list_list_int(A, 0);
    list_int* temp_2 = get_list_list_int(temp_1, 0);
    set_list_int(temp_2, 0, (100 + 1));
    int b = get_list_int(get_list_list_int(get_list_list_list_int(A, 0), 0), 0);
    printf("%d\n", b);
    b = (get_list_int(get_list_list_int(get_list_list_list_int(A, 0), 0), 0) + get_list_int(get_list_list_int(get_list_list_list_int(A, 0), 0), 1));
    list_list_int* temp_3 = get_list_list_list_int(A, 0);
    list_int* temp_4 = get_list_list_int(temp_3, 0);
    set_list_int(temp_4, 2, (get_list_int(get_list_list_int(get_list_list_list_int(A, 0), 0), 0) + get_list_int(get_list_list_int(get_list_list_list_int(A, 0), 0), 1)));
    return 0;
}
"""
    run(P, C)
