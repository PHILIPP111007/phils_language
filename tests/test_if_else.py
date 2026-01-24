from tests.base import run


def test_if_else_1():
    P = r"""
def main() -> int:
    var a: int = 10

    if a > 10:
        print(a)

    if a >= 10:
        print(a)

    if a < 10:
        print(a)

    if a <= 10:
        print(a)

    if a > 10 and a > 100:
        print(a)

    if 1 % 10 == 0 and 1 % 10 == 0:
        print(a)

    if 1 % 10 == 0 and 1 % 10 == 0 or 1 < 10:
        print(a)

    return 0
"""

    C = r"""
int main(void) {
    int a = 10;
    if ((a > 10)) {
        printf("%d\n", a);
    }
    if ((a >= 10)) {
        printf("%d\n", a);
    }
    if ((a < 10)) {
        printf("%d\n", a);
    }
    if ((a <= 10)) {
        printf("%d\n", a);
    }
    if (((a > 10) && (a > 100))) {
        printf("%d\n", a);
    }
    if ((((1 % 10) == 0) && ((1 % 10) == 0))) {
        printf("%d\n", a);
    }
    if (((((1 % 10) == 0) && ((1 % 10) == 0)) || (1 < 10))) {
        printf("%d\n", a);
    }
    return 0;
}
"""
    run(P, C)
