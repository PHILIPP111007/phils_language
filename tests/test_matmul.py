from tests.base import run


def test_list_add_number_to_list_item():
    P = r"""
def get_empty_result_matrix(len_A: int, len_B_0: int) -> list[list[int]]:
    var C: list[list[int]] = []
    
    for i in range(len_A):
        var row: list[int] = []
        for j in range(len_B_0):
            row.append(0)
        C.append(row)
    
    return C


def matmul(A: list[list[int]], B: list[list[int]], len_A: int, len_B: int, len_B_0: int) -> list[list[int]]:
    var C: list[list[int]] = get_empty_result_matrix(len_A, len_B_0)

    for i in range(len_A):
        for j in range(len_B_0):
            for k in range(len_B):
                var A_i_k: int = A[i][k]
                var B_k_j: int = B[k][j]
                C[i][j] = C[i][j] + A_i_k * B_k_j
    return C


def main() -> int:
    var A: list[list[int]] = []

    var a1: list[int] = [1, 2, 3]
    var a2: list[int] = [4, 5, 6]
    A.append(a1)
    A.append(a2)


    var B: list[list[int]] = []

    var b1: list[int] = [7, 8]
    var b2: list[int] = [9, 10]
    var b3: list[int] = [11, 12]
    B.append(b1)
    B.append(b2)
    B.append(b3)

    var len_A: int = len(A)
    var len_B: int = len(B)
    var B_0: list[int] = B[0]
    var len_B_0: int = len(B_0)

    var C: list[list[int]] = matmul(A, B, len_A, len_B, len_B_0)

    for i in range(len_A):
        for j in range(len_B_0):
            print(C[i][j])

    return 0
"""

    C = r"""
list_list_int* get_empty_result_matrix(int len_A, int len_B_0) {
    list_list_int* C = create_list_list_int(4);
    for (int i = 0; i < len_A; i += 1) {
        list_int* row = create_list_int(4);
        for (int j = 0; j < len_B_0; j += 1) {
            append_list_int(row, 0);
        }
        append_list_list_int(C, row);
    }
    return C;
}

list_list_int* matmul(list_list_int* A, list_list_int* B, int len_A, int len_B, int len_B_0) {
    list_list_int* C = get_empty_result_matrix(len_A, len_B_0);
    for (int i = 0; i < len_A; i += 1) {
        for (int j = 0; j < len_B_0; j += 1) {
            for (int k = 0; k < len_B; k += 1) {
                int A_i_k = get_list_int(get_list_list_int(A, i), k);
                int B_k_j = get_list_int(get_list_list_int(B, k), j);
                // Доступ к элементу C[i][j]
                list_int* C_inner_0 = get_list_list_int(C, i);
                set_list_int(C_inner_0, j, (get_list_int(get_list_list_int(C, i), j) + (A_i_k * B_k_j)));
            }
        }
    }
    return C;
}

int main(void) {
    list_list_int* A = create_list_list_int(4);
    list_int* a1 = create_list_int(4);
    append_list_int(a1, 1);
    append_list_int(a1, 2);
    append_list_int(a1, 3);
    list_int* a2 = create_list_int(4);
    append_list_int(a2, 4);
    append_list_int(a2, 5);
    append_list_int(a2, 6);
    append_list_list_int(A, a1);
    append_list_list_int(A, a2);
    list_list_int* B = create_list_list_int(4);
    list_int* b1 = create_list_int(4);
    append_list_int(b1, 7);
    append_list_int(b1, 8);
    list_int* b2 = create_list_int(4);
    append_list_int(b2, 9);
    append_list_int(b2, 10);
    list_int* b3 = create_list_int(4);
    append_list_int(b3, 11);
    append_list_int(b3, 12);
    append_list_list_int(B, b1);
    append_list_list_int(B, b2);
    append_list_list_int(B, b3);
    int len_A = builtin_len_list_list_int(A);
    int len_B = builtin_len_list_list_int(B);
    list_int* B_0 = get_list_list_int(B, 0);
    int len_B_0 = builtin_len_list_int(B_0);
    list_list_int* C = matmul(A, B, len_A, len_B, len_B_0);
    for (int i = 0; i < len_A; i += 1) {
        for (int j = 0; j < len_B_0; j += 1) {
            printf("%d\n", get_list_int(get_list_list_int(C, i), j));
        }
    }
    return 0;
}
"""
    run(P, C)
