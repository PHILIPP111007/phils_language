from tests.base import run


def test_input():
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
        fgets(temp_0_buffer, sizeof(temp_0_buffer), stdin);
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
        char* name = temp_0;
        printf("%s %s\n", "Name is: ", name);
    }
    return 0;
}
"""
    run(P, C)
