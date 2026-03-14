from tests.base import run


def test_dict():
    P = r"""
def main() -> int:
    var a: dict[str, int] = {"a": 1}
    var a1: dict[int, str] = {1: "a"}
    var a2: dict[str, str] = {"1": "a"}

    var a3: list[dict[str, int]] = []
    a3.append(a)

    a["b"] = 2
    a1[2] = "b"

    var keys: list[str] = a.keys()
    var values: list[int] = a.values()

    var len_keys: int = len(keys)

    for i in range(len_keys):
        var key: str = keys[i]
        print(a[key])

    del a
    del a1
    del a2
    del a3

    return 0
"""

    C = r"""
int main(void) {
    dict_str_int* a = create_dict_str_int(16);
    set_dict_str_int(a, "a", 1);
    dict_int_str* a1 = create_dict_int_str(16);
    set_dict_int_str(a1, 1, "a");
    dict_str_str* a2 = create_dict_str_str(16);
    set_dict_str_str(a2, "1", "a");
    list_dict_str_int* a3 = create_list_dict_str_int(4);
    append_list_dict_str_int(a3, a);
    set_dict_str_int(a, "b", 2);
    set_dict_int_str(a1, 2, "b");
    list_str* keys = keys_dict_str_int(a);
    list_int* values = values_dict_str_int(a);
    int len_keys = builtin_len_list_str(keys);
    for (int i = 0; i < len_keys; i += 1) {
        char* key = get_list_str(keys, i);
        printf("%d\n", get_dict_str_int(a, key));
    }
    // del a
    if (a) {
        free_dict_str_int(a);
    }
    a = NULL;
    // del a1
    if (a1) {
        free_dict_int_str(a1);
    }
    a1 = NULL;
    // del a2
    if (a2) {
        free_dict_str_str(a2);
    }
    a2 = NULL;
    // del a3
    if (a3) {
        free_list_dict_str_int(a3);
    }
    a3 = NULL;
    return 0;
}
"""
    run(P, C)
