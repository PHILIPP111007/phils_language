from tests.base import run


def test_import():
    P = r"""
cimport <stdio.h>
cimport <stdlib.h>
cimport <string.h>
cimport <stdbool.h>
cimport "my_header.h"
import "./module.p"
"""

    C = """#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include "my_header.h"
"""
    run(P, C)
