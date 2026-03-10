from tests.base import run


def test_matmul_1():
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


def test_matmul_2():
    P = r"""
class Matrix:
    def __init__(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        self.size = rows * cols
        self.data: list[int] = []

    def init_matrix(self) -> None:
        var size: int = self.size
        var data: list[int] = []

        for _ in range(size):
            data.append(0)
        
        self.data = data
    
    def get(self, i: int, j: int) -> int:
        return self.data[i * self.cols + j]

    def set(self, i: int, j: int, value: int) -> None:
        self.data[i * self.cols + j] = value


def matmul(A: Matrix, B: Matrix, C: Matrix) -> None:
    var rows_A: int = A.rows
    var cols_A: int = A.cols
    var cols_B: int = B.cols

    # Оптимизация 1: кешируем указатели на data для быстрого доступа
    var A_data: list[int] = A.data
    var B_data: list[int] = B.data
    var C_data: list[int] = C.data

    var cols_A_local: int = cols_A
    var cols_B_local: int = cols_B

    # Оптимизация 3: изменение порядка циклов для лучшей локальности кеша
    # Вместо i-k-j используем i-j-k с разверткой
    for i in range(rows_A):
        var row_offset_A: int = i * cols_A_local
        var row_offset_C: int = i * cols_B_local

        for j in range(cols_B_local):
            var sum_val: int = 0
            var offset_C: int = row_offset_C + j

            for k in range(cols_A_local):
                sum_val = sum_val + A_data[row_offset_A + k] * B_data[k * cols_B_local + j]

            C_data[offset_C] = sum_val


def main() -> int:
    var data: list[int] = []

    var rows: int = 100
    var cols: int = 100

    var A: Matrix = Matrix(rows, cols)
    var B: Matrix = Matrix(rows, cols)

    A.init_matrix()
    B.init_matrix()

    print("Matrix created")

    var C: Matrix = Matrix(rows, cols)
    C.init_matrix()

    # Основной цикл
    for _ in range(1000):
        matmul(A, B, C)

    return 0
"""

    C = r"""
typedef struct Matrix Matrix;

struct Matrix {
    void** vtable;
    // Поля класса Matrix
    int rows;
    int cols;
    int size;
    list_int* data;
};

void* Matrix_init_matrix(Matrix* self);
int Matrix_get(Matrix* self, int i, int j);
void* Matrix_set(Matrix* self, int i, int j, int value);
int main(void);

// Конструктор для Matrix
Matrix* create_Matrix(int rows, int cols) {
    Matrix* obj = malloc(sizeof(Matrix));
    if (!obj) {
        fprintf(stderr, "Memory allocation failed for Matrix\n");
        exit(1);
    }

    // Инициализация полей класса Matrix
    obj->vtable = malloc(sizeof(void*) * 16);
    if (!obj->vtable) {
        fprintf(stderr, "Memory allocation failed for vtable\n");
        free(obj);
        exit(1);
    }
    obj->rows = rows;
    obj->cols = cols;
    obj->size = rows * cols;
    obj->data = 0; // default value
    return obj;
}

void* Matrix_init_matrix(Matrix* self) {
    int size = self->size;
    list_int* data = create_list_int(4);
    for (int _ = 0; _ < size; _ += 1) {
        append_list_int(data, 0);
    }
    self->data = data;
}

int Matrix_get(Matrix* self, int i, int j) {
    return get_list_int(self->data, ((i * self->cols) + j));
}

void* Matrix_set(Matrix* self, int i, int j, int value) {
    set_list_int(self->data, ((i * self->cols) + j), value);
}

void* matmul(Matrix* A, Matrix* B, Matrix* C) {
    int rows_A = A->rows;
    int cols_A = A->cols;
    int cols_B = B->cols;
    list_int* A_data = A->data;
    list_int* B_data = B->data;
    list_int* C_data = C->data;
    int cols_A_local = cols_A;
    int cols_B_local = cols_B;
    for (int i = 0; i < rows_A; i += 1) {
        int row_offset_A = (i * cols_A_local);
        int row_offset_C = (i * cols_B_local);
        for (int j = 0; j < cols_B_local; j += 1) {
            int sum_val = 0;
            int offset_C = (row_offset_C + j);
            for (int k = 0; k < cols_A_local; k += 1) {
                sum_val = (sum_val + (get_list_int(A_data, (row_offset_A + k)) * get_list_int(B_data, ((k * cols_B_local) + j))));
            }
            set_list_int(C_data, offset_C, sum_val);
        }
    }
}

int main(void) {
    list_int* data = create_list_int(4);
    int rows = 100;
    int cols = 100;
    Matrix* A = create_Matrix(rows, cols);
    Matrix* B = create_Matrix(rows, cols);
    Matrix_init_matrix(A);
    Matrix_init_matrix(B);
    printf("%s\n", "Matrix created");
    Matrix* C = create_Matrix(rows, cols);
    Matrix_init_matrix(C);
    for (int _ = 0; _ < 1000; _ += 1) {
        matmul(A, B, C);
    }
    return 0;
}
"""
    run(P, C)
