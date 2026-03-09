from tests.base import run


def test_global_var_declaration():
    P = r"""
var A: int = 1000
var B: float = 1.1

def main() -> int:
    return 0
"""

    C = r"""
int A = 1000;
float B = 1.1;
int main(void) {
    return 0;
}
"""
    run(P, C)
