from tests.base import run


def test_import():
    P = r"""
cimport <stdio.h>
cimport <stdlib.h>
cimport <string.h>
cimport <stdbool.h>
"""

    C = """#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
"""
    run(P, C)
