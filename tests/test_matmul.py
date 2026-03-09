from tests.base import run


def test_list_add_number_to_list_item():
    P = r"""
def get_empty_result_matrix(rows: int, cols: int) -> list[list[int]]:
    var C: list[list[int]] = []
    var zeros: list[int] = []
    
    # Создаем одну строку с нулями
    for j in range(cols):
        zeros.append(0)

    # Копируем эту строку для всех строк матрицы
    for i in range(rows):
        # Создаем копию строки zeros
        var row: list[int] = []
        for j in range(cols):
            row.append(zeros[j])
        C.append(row)
    
    return C


def matmul(A: list[list[int]], B: list[list[int]]) -> list[list[int]]:
    var rows_A: int = len(A)
    var cols_A_list: list[int] = A[0]
    var cols_A: int = len(cols_A_list)

    var cols_B_list: list[int] = B[0]
    var cols_B: int = len(cols_B_list)
    
    var C: list[list[int]] = get_empty_result_matrix(rows_A, cols_B)

    for i in range(rows_A):
        var A_row: list[int] = A[i]  # Кешируем строку A
        var C_row: list[int] = C[i]  # Кешируем строку результата
        
        for k in range(cols_A):
            var A_ik: int = A_row[k]  # Элемент A[i][k]
            var B_row: list[int] = B[k]  # Кешируем строку B
            
            for j in range(cols_B):
                C_row[j] = C_row[j] + A_ik * B_row[j]
    
    return C


def main() -> int:
    var size: int = 100
    var A: list[list[int]] = []
    var B: list[list[int]] = []

    # Инициализация матриц
    for i in range(size):
        var row_a: list[int] = []
        var row_b: list[int] = []
        for j in range(size):
            row_a.append(i + j)
            row_b.append(i + j)
        A.append(row_a)
        B.append(row_b)

    print("Matrix created")

    # Кешируем размеры
    var rows_A: int = len(A)
    var cols_B_list: list[int] = B[0]
    var cols_B: int = len(cols_B_list)
    

    # Основной цикл
    for _ in range(1000):
        var result: list[list[int]] = matmul(A, B)
        del result

    return 0
"""

    C = r"""
list_list_int* get_empty_result_matrix(int rows, int cols) {
    list_list_int* C = create_list_list_int(4);
    list_int* zeros = create_list_int(4);
    for (int j = 0; j < cols; j += 1) {
        append_list_int(zeros, 0);
    }
    for (int i = 0; i < rows; i += 1) {
        list_int* row = create_list_int(4);
        for (int j = 0; j < cols; j += 1) {
            append_list_int(row, get_list_int(zeros, j));
        }
        append_list_list_int(C, row);
    }
    return C;
}

list_list_int* matmul(list_list_int* A, list_list_int* B) {
    int rows_A = builtin_len_list_list_int(A);
    list_int* cols_A_list = get_list_list_int(A, 0);
    int cols_A = builtin_len_list_int(cols_A_list);
    list_int* cols_B_list = get_list_list_int(B, 0);
    int cols_B = builtin_len_list_int(cols_B_list);
    list_list_int* C = get_empty_result_matrix(rows_A, cols_B);
    for (int i = 0; i < rows_A; i += 1) {
        list_int* A_row = get_list_list_int(A, i);
        list_int* C_row = get_list_list_int(C, i);
        for (int k = 0; k < cols_A; k += 1) {
            int A_ik = get_list_int(A_row, k);
            list_int* B_row = get_list_list_int(B, k);
            for (int j = 0; j < cols_B; j += 1) {
                set_list_int(C_row, j, (get_list_int(C_row, j) + (A_ik * get_list_int(B_row, j))));
            }
        }
    }
    return C;
}

int main(void) {
    int size = 100;
    list_list_int* A = create_list_list_int(4);
    list_list_int* B = create_list_list_int(4);
    for (int i = 0; i < size; i += 1) {
        list_int* row_a = create_list_int(4);
        list_int* row_b = create_list_int(4);
        for (int j = 0; j < size; j += 1) {
            append_list_int(row_a, (i + j));
            append_list_int(row_b, (i + j));
        }
        append_list_list_int(A, row_a);
        append_list_list_int(B, row_b);
    }
    printf("%s\n", "Matrix created");
    int rows_A = builtin_len_list_list_int(A);
    list_int* cols_B_list = get_list_list_int(B, 0);
    int cols_B = builtin_len_list_int(cols_B_list);
    for (int _ = 0; _ < 1000; _ += 1) {
        list_list_int* result = matmul(A, B);
        // del result
        if (result) {
            free_list_list_int(result);
        }
        result = NULL;
    }
    return 0;
}
"""
    run(P, C)
