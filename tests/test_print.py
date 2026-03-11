from tests.base import run


def test_print():
    P = r"""
def main() -> int:
    for i in range(10):
        print(i, i, i, end="\n", sep="_")

    return 0
"""

    C = r"""
int main(void) {
    for (int i = 0; i < 10; i += 1) {
        printf("%d_%d_%d\n", i, i, i);
    }
    return 0;
}
"""
    run(P, C)
