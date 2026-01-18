import os

from tests.constants import p_path, c_path, base_path, json_path
from main import main


def test_for_loop():
    P = r"""
cimport <stdio.h>
cimport <stdlib.h>
cimport <string.h>
cimport <stdbool.h>


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

    with open(p_path, "w") as file:
        file.write(P)

    main(base_path=base_path, p_path=p_path, json_path=json_path, c_path=c_path)

    os.remove(p_path)
    os.remove(json_path)

    with open(c_path, "r") as file:
        output = file.read()

    assert C in output

    os.remove(c_path)
