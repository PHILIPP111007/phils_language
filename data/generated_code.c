#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <math.h>

int main(void);

int main(void) {
    int a;
    a = 100;
    char* result;
    result = "";
    if ((a > 101)) {
        result = "10";
    }
    else if ((a == 10)) {
        result = "10";
    }
    else {
        result = "undefined";
    }
    printf("%d\n", result);
    return 0;
}
