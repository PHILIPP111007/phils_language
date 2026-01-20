from tests.base import run


def test_del():
    P = r"""
def main() -> int:
    var a: int = 100
    var b: str = "kkofrkfor"
    var c: bool = False
    var d: list[int] = [1, 2, 3]
    var e: tuple[int] = (1, 2, 3)
    var f: list[list[int]] = [d, d]
    var g: list[tuple[int]] = [e, e, e]

    del a
    del b
    del c
    del d
    del e
    del f
    del g

    return 0
"""

    C = """
int main(void) {
    int a = 100;
    char* b = "kkofrkfor";
    bool c = false;
    list_int* d = create_list_int(4);
    append_list_int(d, 1);
    append_list_int(d, 2);
    append_list_int(d, 3);
    int temp_0[3] = {
        1,
        2,
        3
    };
    tuple_int* e = create_tuple_int(temp_0, 3);
    list_list_int* f = create_list_list_int(4);
    append_list_list_int(f, d);
    append_list_list_int(f, d);
    list_tuple_int* g = create_list_tuple_int(4);
    append_list_tuple_int(g, e);
    append_list_tuple_int(g, e);
    append_list_tuple_int(g, e);
    // del a
    a = 0;
    // del b
    b = NULL;
    // del c
    c = false;
    // del d
    if (d) {
        free_list_int(d);
    }
    d = NULL;
    // del e
    free_tuple_int(&e);
    // del f
    if (f) {
        free_list_list_int(f);
    }
    f = NULL;
    // del g
    if (g) {
        free_list_tuple_int(g);
    }
    g = NULL;
    return 0;
}
"""
    run(P, C)
