from tests.base import run


def test_for_loop_1():
    P = r"""
def main() -> int:
    for i in range(0, 100):
        print(i)

    return 0
"""

    C = r"""
int main(void) {
    for (int i = 0; i < 100; i += 1) {
        printf("%d\n", i);
    }
    return 0;
}
"""
    run(P, C)


def test_for_loop_2():
    P = r"""
def main() -> int:
    for i in range(0, 100, -10):
        print(i)

    return 0
"""

    C = r"""
int main(void) {
    for (int i = 0; i < 100; i += -10) {
        printf("%d\n", i);
    }
    return 0;
}
"""
    run(P, C)


def test_for_loop_3():  # TODO
    P = r"""
def main() -> int:
    for i in range(0, 100, 10):
        if i % 10 == 0:
            main()
        else:
            break

    return 0
"""

    C = r"""
int main(void) {
    for (int i = 0; i < 100; i += 10) {
        if ((i % (10 == = 0))) {
            main();
        }
        else {
            break;
            // break statement
        }
    }
    return 0;
}
"""
    run(P, C)


def test_for_loop_4():
    P = r"""
def main() -> int:
    for i in range(0, 100, 10):
        for j in range(0, 100):
            print(i * j)

    return 0
"""

    C = r"""
int main(void) {
    for (int i = 0; i < 100; i += 10) {
        for (int j = 0; j < 100; j += 1) {
            printf("%d\n", (i * j));
        }
    }
    return 0;
}
"""
    run(P, C)
