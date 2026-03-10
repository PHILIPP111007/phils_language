from tests.base import run


def test_input_1():
    P = r"""
def main() -> int:
    for _ in range(10):
        var name: str = input("Enter your name: ")
        print("Name is: ", name)

    return 0
"""

    C = r"""
int main(void) {
    for (int _ = 0; _ < 10; _ += 1) {
        char* temp_0 = NULL;
        printf("Enter your name: ");
        char temp_0_buffer[256];
        if (fgets(temp_0_buffer, sizeof(temp_0_buffer), stdin) == NULL) {
            // Достигнут конец файла (EOF)
            temp_0 = NULL;
        } else {
            // Успешно прочитали строку
            temp_0_buffer[strcspn(temp_0_buffer, "\n")] = 0;
            if (temp_0 != NULL) {
                free(temp_0);
            }
            temp_0 = malloc(strlen(temp_0_buffer) + 1);
            if (!temp_0) {
                fprintf(stderr, "Memory allocation failed for input result\n");
                exit(1);
            }
            strcpy(temp_0, temp_0_buffer);
        }
        char* name = temp_0;
        printf("%s %s\n", "Name is: ", name);
    }
    return 0;
}
"""
    run(P, C)


def test_input_2():
    P = r"""
# For pipelines
def main() -> int:
    var a: str = input()
    var b: str = ""

    while True:
        print(a)
        b = input()
        if b == None:  # Проверка на конец ввода
            break
        a = b
    return 0
"""

    C = r"""
int main(void) {
    char* temp_0 = NULL;
    char temp_0_buffer[256];
    if (fgets(temp_0_buffer, sizeof(temp_0_buffer), stdin) == NULL) {
        // Достигнут конец файла (EOF)
        temp_0 = NULL;
    } else {
        // Успешно прочитали строку
        temp_0_buffer[strcspn(temp_0_buffer, "\n")] = 0;
        if (temp_0 != NULL) {
            free(temp_0);
        }
        temp_0 = malloc(strlen(temp_0_buffer) + 1);
        if (!temp_0) {
            fprintf(stderr, "Memory allocation failed for input result\n");
            exit(1);
        }
        strcpy(temp_0, temp_0_buffer);
    }
    char* a = temp_0;
    char* b = "";
    while (true) {
        printf("%s\n", a);
        char* temp_1 = NULL;
        char temp_1_buffer[256];
        if (fgets(temp_1_buffer, sizeof(temp_1_buffer), stdin) == NULL) {
            // Достигнут конец файла (EOF)
            temp_1 = NULL;
        } else {
            // Успешно прочитали строку
            temp_1_buffer[strcspn(temp_1_buffer, "\n")] = 0;
            if (temp_1 != NULL) {
                free(temp_1);
            }
            temp_1 = malloc(strlen(temp_1_buffer) + 1);
            if (!temp_1) {
                fprintf(stderr, "Memory allocation failed for input result\n");
                exit(1);
            }
            strcpy(temp_1, temp_1_buffer);
        }
        b = temp_1;
        if ((b == NULL)) {
            break;
            // break statement
        }
        a = b;
    }
    return 0;
}
"""
    run(P, C)
