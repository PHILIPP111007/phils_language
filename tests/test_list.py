from tests.base import run


def test_list():
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
