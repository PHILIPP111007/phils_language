from tests.base import run


def test_variables():
    P = r"""
def main() -> int:
    var a: int = 1000000
    var b: str = "ewpfkeof"

    var c: bool = True
    var c1: bool = False

    var d: list[int] = [1, 2, 3]
    var d1: list[str] = ["bbb", "aaa"]
    var d2: list[list[int]] = [d, d]

    var e: tuple[int] = (1, 2, 3, 4)
    var d3: list[tuple[int]] = [e, e, e]

    var f: None = None

    return 0
"""

    C = r"""
int main(void) {
    int a = 1000000;
    char* b = "ewpfkeof";
    bool c = true;
    bool c1 = false;
    list_int* d = create_list_int(4);
    append_list_int(d, 1);
    append_list_int(d, 2);
    append_list_int(d, 3);
    list_str* d1 = create_list_str(4);
    append_list_str(d1, "bbb");
    append_list_str(d1, "aaa");
    list_list_int* d2 = create_list_list_int(4);
    append_list_list_int(d2, d);
    append_list_list_int(d2, d);
    int temp_0[4] = {
        1,
        2,
        3,
        4
    };
    tuple_int* e = create_tuple_int(temp_0, 4);
    list_tuple_int* d3 = create_list_tuple_int(4);
    append_list_tuple_int(d3, e);
    append_list_tuple_int(d3, e);
    append_list_tuple_int(d3, e);
    void* f = NULL;
    return 0;
}
"""
    run(P, C)
