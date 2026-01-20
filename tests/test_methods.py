from tests.base import run


def test_methods():
    P = r"""
def main() -> int:
    var a: str = "Hello {}"
    a = a.upper()
    a = a.lower()
    a = a.format("world")
    var a_list: list[str] = a.split(" ")

    var b: int = 100
    var b1: str = str(b)

    var c: str = "10"
    var c1: int = int(c)

    var d: list[int] = []
    d.append(1)
    d.append(2)
    d.pop()

    var d1: list[list[int]] = []
    d1.append(d)
    d1.append(d)

    var e: int = len(d)
    var e1: int = len(d1)

    return 0
"""

    C = """
int main(void) {
    char* a = "Hello {}";
    a = string_upper(a);
    a = string_lower(a);
    a = string_format(a, "world");
    list_str* a_list = string_split(a, " ");
    int b = 100;
    char* b1 = builtin_str(b);
    char* c = "10";
    int c1 = builtin_int(c);
    list_int* d = create_list_int(4);
    append_list_int(d, 1);
    append_list_int(d, 2);
    if (d->size > 0) {
        int temp_0 = d->data[d->size - 1];
        d->size--;
    }
    list_list_int* d1 = create_list_list_int(4);
    append_list_list_int(d1, d);
    append_list_list_int(d1, d);
    int e = builtin_len_list_int(d);
    int e1 = builtin_len_list_list_int(d1);
    return 0;
}
"""
    run(P, C)
