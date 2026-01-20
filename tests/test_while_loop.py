from tests.base import run


def test_while_loop_1():
    P = r"""
def main() -> int:
    while 1 < 10:
        print(1)

    return 0
"""

    C = r"""
int main(void) {
    while ((1 < 10)) {
        printf("%d\n", 1);
    }
    return 0;
}
"""
    run(P, C)


def test_while_loop_2():
    P = r"""
def main() -> int:
    while 1 > 10:
        print(1)

    return 0
"""

    C = r"""
int main(void) {
    while ((1 > 10)) {
        printf("%d\n", 1);
    }
    return 0;
}
"""
    run(P, C)


def test_while_loop_3():  # TODO
    P = r"""
def main() -> int:
    var i: int = 0
    while i >= 10:
        print(i)
        i = i + 1

    return 0
"""

    C = r"""
int main(void) {
    int i = 0;
    while ((i >= = 10)) {
        printf("%d\n", i);
        i = (i + 1);
    }
    return 0;
}
"""
    run(P, C)
