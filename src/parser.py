import re
import os
import json


KEYS = ["const", "var", "def", "del", "del_pointer", "return", "while", "for", "if"]
DATA_TYPES = [
    "bool",
    "int",
    "float",
    "str",
    "None",
    "list",
    "dict",
    "set",
    "tuple",
    "list[int]",
    "list[float]",
    "list[str]",
    "list[bool]",
    "list[tuple]",
    "tuple[int]",
    "tuple[float]",
    "tuple[str]",
    "tuple[bool]",
    "dict[str]",
    "dict[int]",
    "dict[float]",
    "set[int]",
    "set[str]",
    "set[float]",
    "*int",
    "*float",
    "*str",
    "*bool",
    "*tuple",  # указатели
]


class CImportProcessor:
    def __init__(self, base_path=""):
        self.base_path = base_path

    def resolve_cimport(
        self, import_statement: str, current_file_path: str = ""
    ) -> dict:
        """Просто регистрирует C импорт без парсинга"""
        patterns = [
            r"cimport\s+<(.+?)>",  # cimport <stdio.h>
            r'cimport\s+"(.+?)"',  # cimport "my_header.h"
        ]

        for pattern in patterns:
            match = re.match(pattern, import_statement.strip())
            if match:
                header_path = match.group(1)

                # Определяем тип импорта
                is_system = import_statement.strip().startswith("cimport <")

                return {
                    "type": "c_import",
                    "header": header_path,
                    "is_system": is_system,
                    "original_statement": import_statement.strip(),
                }

        return {}


class ImportProcessor:
    def __init__(self, base_path=""):
        self.base_path = base_path
        self.processed_files = set()  # Чтобы избежать циклических импортов

    def resolve_import(self, import_statement: str, current_file_path: str = "") -> str:
        """Обрабатывает импорт и возвращает содержимое импортируемого файла"""
        pattern = r'import\s+["\'](.+?)["\']'
        match = re.match(pattern, import_statement.strip())

        if not match:
            return ""

        import_path = match.group(1)

        # Определяем полный путь к файлу
        if import_path.startswith("./"):
            # Относительный путь
            if current_file_path:
                current_dir = os.path.dirname(current_file_path)
                full_path = os.path.join(current_dir, import_path[2:])
            else:
                full_path = os.path.join(self.base_path, import_path[2:])
        else:
            # Абсолютный или относительный путь от base_path
            full_path = os.path.join(self.base_path, import_path)

        # # Добавляем расширение если его нет
        # if not full_path.endswith('.p'):
        #     full_path += '.p'

        # Проверяем, не обрабатывали ли уже этот файл
        if full_path in self.processed_files:
            print(f"Предупреждение: циклический импорт файла {full_path}")
            return ""

        self.processed_files.add(full_path)

        # Читаем содержимое файла
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            print(f"Импортирован файл: {full_path}")
            return content
        except FileNotFoundError:
            print(f"Ошибка: файл не найден {full_path}")
            return ""
        except Exception as e:
            print(f"Ошибка при чтении файла {full_path}: {str(e)}")
            return ""

    def process_imports(self, code: str, current_file_path: str = "") -> str:
        """Обрабатывает все импорты в коде и вставляет содержимое файлов"""
        lines = code.split("\n")
        result_lines = []

        i = 0
        while i < len(lines):
            line = lines[i].rstrip()

            # Проверяем, является ли строка импортом
            if line.strip().startswith("import"):
                # Обрабатываем импорт
                imported_content = self.resolve_import(line, current_file_path)

                if imported_content:
                    # Рекурсивно обрабатываем импорты в импортированном файле
                    processed_import = self.process_imports(
                        imported_content, current_file_path
                    )
                    result_lines.append(f"# Импорт из {line.strip()}")
                    result_lines.extend(processed_import.split("\n"))
                    result_lines.append("# Конец импорта")
                else:
                    result_lines.append(f"# Ошибка импорта: {line.strip()}")
            else:
                result_lines.append(line)

            i += 1

        return "\n".join(result_lines)


class SymbolTable:
    def __init__(self):
        self.symbols = {}
        self.deleted_symbols = set()  # Множество удаленных символов

    def add_symbol(self, name, key, var_type, value=None, is_constant=False, **kwargs):
        symbol_id = name

        symbol_data = {
            "name": name,
            "key": key,
            "type": var_type,
            "value": value,
            "id": symbol_id,
            "is_deleted": False,
        }

        # Добавляем дополнительные атрибуты из kwargs
        for key, val in kwargs.items():
            if val is not None:  # Не добавляем None значения
                symbol_data[key] = val

        # Добавляем информацию об указателе
        if var_type.startswith("*"):
            symbol_data["is_pointer"] = True
            symbol_data["pointed_type"] = var_type[1:]  # Убираем звездочку

            # Если значение начинается с &, это адрес другой переменной
            if isinstance(value, str) and value.startswith("&"):
                pointed_var = value[1:].strip()
                symbol_data["points_to"] = pointed_var

        if is_constant:
            symbol_data["key"] = "const"

        self.symbols[symbol_id] = symbol_data

        return symbol_id

    def get_symbol(self, name):
        symbol = self.symbols.get(name)
        return symbol if symbol and not symbol.get("is_deleted", False) else None

    def get_symbol_for_validation(self, name):
        return self.symbols.get(name)

    def update_symbol(self, name, updates):
        if name in self.symbols:
            self.symbols[name].update(updates)
            return True
        return False

    def delete_symbol(self, name):
        if name in self.symbols:
            self.symbols[name]["is_deleted"] = True
            self.deleted_symbols.add(name)
            return True
        return False

    def is_deleted(self, name):
        return name in self.deleted_symbols


class Parser:
    def __init__(self, base_path: str = ""):
        self.scopes = []  # Список всех областей видимости
        self.scope_stack = []  # Стек текущих областей видимости
        self.symbol_counter = 0
        self.current_indent = 0
        self.indent_size = None  # Размер отступа (4 пробела или 1 таб)
        self.indent_char = None  # Тип отступа ('space' или 'tab')
        self.builtin_functions = {
            "print",
            "len",
            "str",
            "int",
            "bool",
            "range",
        }  # Добавили встроенные функции
        self.import_processor = ImportProcessor(
            base_path=base_path
        )  # Добавляем процессор импортов
        self.c_import_processor = CImportProcessor(base_path=base_path)

    def detect_indent_type(self, line: str):
        if not line.startswith((" ", "\t")):
            return None

        first_char = line[0]
        if first_char == "\t":
            return ("tab", 1)
        elif first_char == " ":
            space_count = 0
            for char in line:
                if char == " ":
                    space_count += 1
                else:
                    break

            common_indents = [2, 4, 8]
            for indent in common_indents:
                if space_count % indent == 0:
                    return ("space", indent)

            return ("space", space_count)

        return None

    def analyze_indent_pattern(self, lines: list) -> tuple:
        tab_lines = 0
        space_lines = 0
        space_counts = {}

        for line in lines:
            if line.startswith("\t"):
                tab_lines += 1
            elif line.startswith(" "):
                space_lines += 1
                space_count = 0
                for char in line:
                    if char == " ":
                        space_count += 1
                    else:
                        break

                if space_count > 0:
                    # Фиксируем размер отступа на 4 пробела
                    # (или определите по первому ненулевому отступу)
                    if space_count >= 4:
                        space_count = 4  # предполагаем, что отступ 4 пробела
                    space_counts[space_count] = space_counts.get(space_count, 0) + 1

        # Всегда используем 4 пробела, если нет табов
        if space_lines > 0:
            return ("space", 4)

        return ("tab", 1)

    def handle_indent_change(self, indent: int):
        if indent > self.current_indent:
            self.current_indent = indent
        elif indent < self.current_indent:
            while self.current_indent > indent and len(self.scope_stack) > 1:
                self.scope_stack.pop()
                self.current_indent -= 1

    def parse_cimport(
        self, line: str, scope: dict, all_lines: list, current_index: int
    ):
        """Парсит C импорт"""
        import_info = self.c_import_processor.resolve_cimport(line)

        if import_info:
            # Добавляем узел C импорта
            scope["graph"].append(
                {
                    "node": "c_import",
                    "content": line,
                    "header": import_info["header"],
                    "is_system": import_info["is_system"],
                    "operations": [
                        {
                            "type": "C_IMPORT",
                            "header": import_info["header"],
                            "is_system": import_info["is_system"],
                        }
                    ],
                }
            )
            print(
                f"Добавлен C импорт: {import_info['header']} (системный: {import_info['is_system']})"
            )

        return current_index + 1

    def parse_code(self, code: str, file_path: str = "") -> list[dict]:
        if file_path:
            base_dir = os.path.dirname(file_path)
            self.import_processor.base_path = base_dir

        processed_code = self.import_processor.process_imports(code, file_path)

        return self._parse_processed_code(processed_code)

    def _parse_processed_code(self, code: str) -> list[dict]:
        code = re.sub(r"#.*", "", code)
        code = re.sub(r"'''.*?'''", "", code, flags=re.DOTALL)
        code = re.sub(r'""".*?"""', "", code, flags=re.DOTALL)

        lines = code.split("\n")

        if any(line.startswith((" ", "\t")) for line in lines if line.strip()):
            self.indent_char, self.indent_size = self.analyze_indent_pattern(lines)

        global_scope = {
            "level": 0,
            "type": "module",
            "parent_scope": None,
            "local_variables": [],
            "graph": [],
            "symbol_table": SymbolTable(),
        }
        self.scopes.append(global_scope)
        self.scope_stack = [global_scope]
        self.current_indent = 0

        i = 0
        while i < len(lines):
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            indent = self.calculate_indent_level(line)
            line_content = line.strip()

            # Обработка отступов
            if indent < self.current_indent:
                # Уменьшаем стек scope'ов при уменьшении отступа
                while len(self.scope_stack) > 1 and self.current_indent > indent:
                    self.scope_stack.pop()
                    self.current_indent -= 1

            self.current_indent = indent

            if line_content:
                # Получаем текущую область видимости
                current_scope = (
                    self.scope_stack[-1] if self.scope_stack else global_scope
                )

                i = self.parse_line(line_content, current_scope, lines, i, indent)
            else:
                i += 1

        # Преобразуем SymbolTable в словарь для JSON
        for scope in self.scopes:
            if hasattr(scope["symbol_table"], "symbols"):
                scope["symbol_table"] = scope["symbol_table"].symbols

        return self.scopes

    def get_current_scope_for_indent(self, indent: int):
        """Возвращает область видимости для заданного уровня отступа"""
        # Если отступ 0 - возвращаем глобальную область
        if indent == 0:
            # Находим глобальную область в стеке
            for scope in self.scope_stack:
                if scope["level"] == 0:
                    return scope
            return self.scope_stack[0] if self.scope_stack else None

        # Находим область с нужным уровнем
        for scope in reversed(self.scope_stack):
            if scope["level"] <= indent:
                return scope

        # Если не нашли, возвращаем последнюю область
        return self.scope_stack[-1] if self.scope_stack else None

    def calculate_indent_level(self, line: str) -> int:
        if not line.startswith((" ", "\t")):
            return 0

        if self.indent_size is None:
            indent_info = self.detect_indent_type(line)
            if indent_info:
                self.indent_char, self.indent_size = indent_info

        if self.indent_char == "tab":
            tab_count = 0
            for char in line:
                if char == "\t":
                    tab_count += 1
                else:
                    break
            return tab_count
        elif self.indent_char == "space":
            space_count = 0
            for char in line:
                if char == " ":
                    space_count += 1
                else:
                    break

            # ВАЖНО: Используем целочисленное деление
            if self.indent_size > 0:
                level = space_count // self.indent_size
                return level
            else:
                return 0

        return 0

    def get_current_scope(self, indent):
        """Определяет текущий scope на основе отступа"""
        if indent == 0:
            return self.scopes[0]  # Глобальная область

        # Ищем самую глубокую функцию
        for scope in reversed(self.scopes):
            if scope["type"] == "function":
                return scope

        return self.scopes[0]

    def parse_line(
        self, line: str, scope: dict, all_lines: list, current_index: int, indent: int
    ):
        parsed = False

        if line == "pass":
            scope["graph"].append(
                {"node": "pass", "content": "pass", "operations": [{"type": "PASS"}]}
            )
            return current_index + 1

        if line.startswith("cimport "):
            return self.parse_cimport(line, scope, all_lines, current_index)

        # ПРОВЕРЯЕМ elif и else ПЕРВЫМИ
        if line.startswith("elif "):
            # elif должен обрабатываться только внутри parse_if_statement
            print(
                f"Error: elif без предшествующего if в строке {current_index}: {line}"
            )
            return current_index + 1

        if line == "else:":
            # else должен обрабатываться только внутри parse_if_statement
            print(f"Error: else без предшествующего if в строке {current_index}")
            return current_index + 1

        for key in KEYS:
            if line.startswith(key + " ") or line == key:
                if key == "const":
                    parsed = self.parse_const(line, scope)
                    break
                elif key == "var":
                    parsed = self.parse_var(line, scope)
                    break
                elif key == "def":
                    return self.parse_function_declaration(
                        line, scope, all_lines, current_index
                    )
                elif key == "del":
                    parsed = self.parse_delete(line, scope)
                    break
                elif key == "del_pointer":  # НОВОЕ
                    parsed = self.parse_del_pointer(line, scope)
                    break
                elif key == "return":
                    parsed = self.parse_return(line, scope)
                    break
                elif key == "while":
                    return self.parse_while_loop(
                        line, scope, all_lines, current_index, indent
                    )
                elif key == "for":
                    return self.parse_for_loop(
                        line, scope, all_lines, current_index, indent
                    )
                elif key == "if":
                    return self.parse_if_statement(
                        line, scope, all_lines, current_index, indent
                    )

        if not parsed:
            # Проверяем, является ли строка вызовом встроенной функции
            for func_name in self.builtin_functions:
                if line.startswith(f"{func_name}("):
                    parsed = self.parse_builtin_function_call(line, scope, func_name)
                    break

            if not parsed:
                # Проверяем другие варианты
                if re.match(r"[a-zA-Z_][a-zA-Z0-9_]*\s*\(", line) and "var " in line:
                    parsed = self.parse_function_call_assignment(line, scope)
                elif re.match(r"[a-zA-Z_][a-zA-Z0-9_]*\s*\(", line):
                    parsed = self.parse_function_call(line, scope)
                elif "=" in line and not any(
                    line.startswith(k + " ") for k in ["const", "var", "def"]
                ):
                    parsed = self.parse_assignment(line, scope)
                elif "+=" in line or "-=" in line or "*=" in line or "/=" in line:
                    parsed = self.parse_augmented_assignment(line, scope)

        return current_index + 1

    def parse_builtin_function_call(self, line: str, scope: dict, func_name: str):
        """Парсит вызов встроенной функции"""
        pattern = rf"{func_name}\s*\((.*?)\)"
        match = re.match(pattern, line)

        if not match:
            return False

        args_str = match.group(1)
        args = self.parse_function_arguments(args_str)

        # Определяем тип возвращаемого значения
        return_type = self.get_builtin_return_type(func_name, args)

        # Создаем узел для встроенной функции
        operations = [
            {
                "type": "BUILTIN_FUNCTION_CALL",
                "function": func_name,
                "arguments": args,
                "return_type": return_type,
            }
        ]

        # Собираем зависимости
        dependencies = []
        for arg in args:
            if (
                arg
                and not arg.startswith('"')
                and not arg.endswith('"')
                and not arg.startswith("'")
                and not arg.endswith("'")
                and not arg.isdigit()
                and arg not in ["True", "False", "None"]
            ):
                # Извлекаем переменные из аргументов
                var_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)"
                vars_in_arg = re.findall(var_pattern, arg)
                for var in vars_in_arg:
                    if (
                        var not in KEYS
                        and var not in DATA_TYPES
                        and var not in dependencies
                    ):
                        dependencies.append(var)

        scope["graph"].append(
            {
                "node": "builtin_function_call",
                "content": line,
                "function": func_name,
                "arguments": args,
                "return_type": return_type,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def parse_function_arguments(self, args_str: str) -> list:
        """Разбирает аргументы функции с учетом строк и вложенных вызовов"""
        if not args_str.strip():
            return []

        args = []
        current_arg = ""
        in_string = False
        string_char = None
        paren_depth = 0
        bracket_depth = 0

        for char in args_str:
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
                current_arg += char
            elif in_string and char == string_char and current_arg[-1] != "\\":
                in_string = False
                current_arg += char
            elif not in_string and char == "(":
                paren_depth += 1
                current_arg += char
            elif not in_string and char == ")":
                paren_depth -= 1
                current_arg += char
            elif not in_string and char == "[":
                bracket_depth += 1
                current_arg += char
            elif not in_string and char == "]":
                bracket_depth -= 1
                current_arg += char
            elif (
                not in_string
                and paren_depth == 0
                and bracket_depth == 0
                and char == ","
            ):
                args.append(current_arg.strip())
                current_arg = ""
            else:
                current_arg += char

        if current_arg.strip():
            args.append(current_arg.strip())

        return [arg.strip() for arg in args]

    def parse_tuple_literal(self, value: str) -> dict:
        """Парсит литерал кортежа"""
        value = value.strip()

        # Проверяем, что это действительно кортеж
        if not (value.startswith("(") and value.endswith(")")):
            return {"type": "unknown", "value": value}

        # Проверяем, что это не выражение в скобках
        inner = value[1:-1].strip()
        if "," not in inner:
            # Это выражение в скобках, а не кортеж
            inner_ast = self.parse_expression_to_ast(inner)
            return {
                "type": "tuple_literal",
                "items": [inner_ast],
                "length": 1,
                "is_immutable": True,
            }

        # Парсим элементы кортежа
        items = []
        current_item = ""
        depth = 0
        in_string = False
        string_char = None

        i = 0
        while i < len(inner):
            char = inner[i]

            # Обработка строк
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
                current_item += char
            elif in_string and char == string_char:
                # Проверяем экранирование
                if i > 0 and inner[i - 1] == "\\":
                    current_item += char
                else:
                    in_string = False
                    current_item += char
            # Обработка скобок
            elif not in_string and char == "(":
                depth += 1
                current_item += char
            elif not in_string and char == ")":
                depth -= 1
                current_item += char
            elif not in_string and char == "[":
                depth += 1
                current_item += char
            elif not in_string and char == "]":
                depth -= 1
                current_item += char
            elif not in_string and char == "{":
                depth += 1
                current_item += char
            elif not in_string and char == "}":
                depth -= 1
                current_item += char
            # Разделитель элементов
            elif not in_string and depth == 0 and char == ",":
                if current_item.strip():
                    item_ast = self.parse_expression_to_ast(current_item.strip())
                    items.append(item_ast)
                current_item = ""
            else:
                current_item += char

            i += 1

        # Последний элемент
        if current_item.strip():
            item_ast = self.parse_expression_to_ast(current_item.strip())
            items.append(item_ast)

        # Особый случай: кортеж из одного элемента должен иметь запятую
        if len(items) == 1 and not inner.endswith(","):
            print(f"Warning: кортеж из одного элемента должен иметь запятую: {value}")

        return {
            "type": "tuple_literal",
            "items": items,
            "length": len(items),
            "is_immutable": True,
        }

    def get_builtin_return_type(self, func_name: str, args: list) -> str:
        """Определяет тип возвращаемого значения для встроенной функции"""
        if func_name == "len":
            return "int"
        elif func_name == "str":
            return "str"
        elif func_name == "int":
            return "int"
        elif func_name == "bool":
            return "bool"
        elif func_name == "print":
            return "None"
        elif func_name == "range":
            return "range"
        return "unknown"

    def parse_global_line(
        self, line: str, scope: dict, all_lines: list, current_index: int
    ):
        """Парсит строку в глобальной области видимости"""
        if not line:
            return

        for key in KEYS:
            if line.startswith(key + " ") or line == key:
                if key == "const":
                    self.parse_const(line, scope)
                elif key == "var":
                    self.parse_var(line, scope)
                elif key == "def":
                    self.parse_function_declaration(
                        line, scope, all_lines, current_index
                    )
                return

        # В глобальной области только объявления
        print(f"Warning: Unexpected line in global scope: {line}")

    def parse_function_line(self, line: str, scope: dict):
        """Парсит строку внутри функции"""
        if not line:
            return

        parsed = False

        for key in KEYS:
            if line.startswith(key + " ") or line == key:
                if key == "const":
                    parsed = self.parse_const(line, scope)
                elif key == "var":
                    parsed = self.parse_var(line, scope)
                elif key == "def":
                    # Вложенные функции пока не поддерживаем
                    parsed = False
                elif key == "del":
                    parsed = self.parse_delete(line, scope)
                elif key == "return":
                    parsed = self.parse_return(line, scope)
                elif key == "print":  # <-- Добавляем обработку print
                    parsed = self.parse_print(line, scope)
                break

        if not parsed:
            if re.match(r"[a-zA-Z_][a-zA-Z0-9_]*\s*\(", line) and "var " in line:
                parsed = self.parse_function_call_assignment(line, scope)
            elif re.match(r"[a-zA-Z_][a-zA-Z0-9_]*\s*\(", line):
                parsed = self.parse_function_call(line, scope)
            elif "=" in line and not any(
                line.startswith(k + " ") for k in ["const", "var", "def"]
            ):
                parsed = self.parse_assignment(line, scope)
            elif "+=" in line or "-=" in line or "*=" in line or "/=" in line:
                parsed = self.parse_augmented_assignment(line, scope)

    def parse_function_declaration(
        self, line: str, parent_scope: dict, all_lines: list, current_index: int
    ):
        """Обрабатывает объявление функции"""
        pattern = r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*(?:->\s*([a-zA-Z_][a-zA-Z0-9_]*))?\s*:"
        match = re.match(pattern, line)

        if not match:
            return current_index + 1

        func_name, params_str, return_type = match.groups()
        return_type = return_type if return_type else "None"

        # Парсим параметры
        parameters = []
        if params_str.strip():
            param_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)"
            params = re.findall(param_pattern, params_str)
            for param_name, param_type in params:
                parameters.append({"name": param_name, "type": param_type})

        # Определяем уровень вложенности функции
        parent_level = parent_scope["level"]
        func_level = parent_level + 1

        # Получаем отступ текущей строки
        indent = (
            self.calculate_indent_level(all_lines[current_index])
            if current_index < len(all_lines)
            else 0
        )

        # Добавляем функцию в таблицу символов родительской области
        symbol_id = parent_scope["symbol_table"].add_symbol(
            name=func_name,
            key="function",
            var_type="function",
            value=None,
            parameters=parameters,  # ← ЭТО ВАЖНО
            return_type=return_type,  # ← И ЭТО ТОЖЕ
        )

        # Создаем узел объявления функции
        func_decl_node = {
            "node": "function_declaration",
            "content": line,
            "function_name": func_name,
            "symbol_id": symbol_id,
            "parameters": parameters,
            "return_type": return_type,
            "body_level": func_level,
            "is_stub": False,  # По умолчанию - не заглушка
        }

        parent_scope["graph"].append(func_decl_node)

        # Находим тело функции
        body_start = current_index + 1

        # Проверяем, есть ли следующая строка
        if body_start < len(all_lines):
            next_line = all_lines[body_start]
            next_line_content = next_line.strip()
            next_line_indent = self.calculate_indent_level(next_line)

            # Если следующая строка - это 'pass' с правильным отступом
            if next_line_content == "pass" and next_line_indent == indent + 1:
                print(f"  Функция {func_name} имеет только 'pass' - создаем заглушку")

                # Помечаем функцию как заглушку
                func_decl_node["is_stub"] = True
                func_decl_node["body"] = []

                # Создаем узел для pass
                pass_node = {
                    "node": "pass",
                    "content": "pass",
                    "operations": [{"type": "PASS"}],
                }

                # Создаем область видимости для функции-заглушки
                func_scope = {
                    "level": func_level,
                    "type": "function",
                    "parent_scope": parent_scope["level"],
                    "function_name": func_name,
                    "parameters": parameters,
                    "return_type": return_type,
                    "local_variables": [],
                    "graph": [pass_node],  # Добавляем только pass
                    "symbol_table": SymbolTable(),
                    "return_info": {
                        "has_return": False,
                        "return_value": None,
                        "return_type": return_type,
                    },
                    "is_stub": True,
                }

                # Добавляем параметры в таблицу символов функции
                for param in parameters:
                    func_scope["symbol_table"].add_symbol(
                        name=param["name"], key="var", var_type=param["type"]
                    )
                    func_scope["local_variables"].append(param["name"])

                # Добавляем scope функции в общий список
                self.scopes.append(func_scope)

                # Возвращаем индекс строки ПОСЛЕ 'pass'
                return body_start + 1
            else:
                # Обычная функция с телом
                body_end = self.find_indented_block_end(all_lines, body_start, indent)

                # Создаем область видимости для функции
                func_scope = {
                    "level": func_level,
                    "type": "function",
                    "parent_scope": parent_scope["level"],
                    "function_name": func_name,
                    "parameters": parameters,
                    "return_type": return_type,
                    "local_variables": [],
                    "graph": [],
                    "symbol_table": SymbolTable(),
                    "return_info": {
                        "has_return": False,
                        "return_value": None,
                        "return_type": return_type,
                    },
                    "is_stub": False,
                }

                # Добавляем параметры в таблицу символов функции
                for param in parameters:
                    func_scope["symbol_table"].add_symbol(
                        name=param["name"], key="var", var_type=param["type"]
                    )
                    func_scope["local_variables"].append(param["name"])

                # Добавляем scope функции в общий список и в стек
                self.scopes.append(func_scope)
                self.scope_stack.append(func_scope)

                # Сохраняем текущие значения
                saved_indent = self.current_indent

                # Устанавливаем отступ для тела функции
                self.current_indent = indent + 1

                # Парсим тело функции
                i = body_start
                while i < body_end:
                    body_line = all_lines[i]
                    if not body_line.strip():
                        i += 1
                        continue

                    body_indent = self.calculate_indent_level(body_line)
                    body_content = body_line.strip()

                    # Рекурсивно парсим строки в теле функции
                    i = self.parse_line(
                        body_content, func_scope, all_lines, i, body_indent
                    )

                # Восстанавливаем отступ
                self.current_indent = saved_indent

                # Удаляем scope функции из стека
                self.scope_stack.pop()

                # Возвращаем индекс строки ПОСЛЕ тела функции
                return body_end
        else:
            # Нет следующей строки - пустая функция
            print(f"  Функция {func_name} без тела")
            func_decl_node["is_stub"] = True

            # Создаем пустую область видимости для функции
            func_scope = {
                "level": func_level,
                "type": "function",
                "parent_scope": parent_scope["level"],
                "function_name": func_name,
                "parameters": parameters,
                "return_type": return_type,
                "local_variables": [],
                "graph": [],
                "symbol_table": SymbolTable(),
                "return_info": {
                    "has_return": False,
                    "return_value": None,
                    "return_type": return_type,
                },
                "is_stub": True,
            }

            self.scopes.append(func_scope)
            return current_index + 1

    def find_indented_block_end(
        self, lines: list, start_index: int, base_indent: int
    ) -> int:
        """Находит конец блока с отступом"""
        if start_index >= len(lines):
            return start_index

        i = start_index
        while i < len(lines):
            line = lines[i]

            # Пропускаем пустые строки
            if not line.strip():
                i += 1
                continue

            current_indent = self.calculate_indent_level(line)

            # Если отступ стал меньше или равен базовому - конец блока
            if current_indent <= base_indent:
                return i

            i += 1

        return len(lines)  # Дошли до конца файла

    def parse_const(self, line: str, scope: dict):
        pattern = r"const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
        match = re.match(pattern, line)

        if match:
            name, var_type, value = match.groups()
            value = self.clean_value(value)

            symbol_id = scope["symbol_table"].add_symbol(
                name=name, key="const", var_type=var_type, value=value, is_constant=True
            )

            scope["local_variables"].append(symbol_id)

            scope["graph"].append(
                {
                    "node": "declaration",
                    "content": line,
                    "symbols": [symbol_id],
                    "operations": [
                        {
                            "type": "NEW_CONST",
                            "target": symbol_id,
                            "const_type": var_type,
                        },
                        {"type": "ASSIGN", "target": symbol_id, "value": value},
                    ],
                }
            )

            return True
        return False

    def extract_list_element_type(self, list_type: str) -> str:
        """Извлекает тип элементов из объявления типа списка"""
        if "[" in list_type and "]" in list_type:
            match = re.search(r"\[([^\]]+)\]", list_type)
            if match:
                return match.group(1).strip()
        return "any"  # Тип по умолчанию

    def parse_var(self, line: str, scope: dict):
        """Парсит объявление переменной с поддержкой tuple и list"""
        # Упрощенный паттерн для захвата всей строки
        pattern = r"var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+)"
        match = re.match(pattern, line)

        if not match:
            return False

        name, type_and_value = match.groups()

        # Разделяем тип и значение
        if "=" not in type_and_value:
            return False

        # Ищем последний = перед значением (но не внутри <> или [])
        parts = type_and_value.split("=", 1)
        if len(parts) != 2:
            return False

        var_type_str, value_str = parts[0].strip(), parts[1].strip()

        # Обрабатываем разные варианты типов
        is_pointer = var_type_str.startswith("*")
        if is_pointer:
            var_type_str = var_type_str[1:].strip()

        # Определяем базовый тип
        var_type = var_type_str
        is_tuple_uniform = False  # tuple[T]
        is_tuple_fixed = False  # tuple[T1, T2, ...]
        element_type = None
        tuple_element_types = []

        # Проверяем tuple[T]
        tuple_uniform_pattern = r"tuple\[([a-zA-Z_][a-zA-Z0-9_]*)\]"
        tuple_uniform_match = re.match(tuple_uniform_pattern, var_type_str)

        if tuple_uniform_match:
            is_tuple_uniform = True
            element_type = tuple_uniform_match.group(1)
            print(f"DEBUG: Обнаружен tuple[{element_type}]")

        # Проверяем tuple[T1, T2, ...]
        elif var_type_str.startswith("tuple["):
            # Извлекаем содержимое скобок
            bracket_content = var_type_str[6:-1]  # убираем "tuple[" и "]"
            if "," in bracket_content:
                is_tuple_fixed = True
                # Разделяем по запятым, но учитываем вложенные скобки
                tuple_element_types = []
                current_type = ""
                depth = 0

                for char in bracket_content:
                    if char == "[":
                        depth += 1
                        current_type += char
                    elif char == "]":
                        depth -= 1
                        current_type += char
                    elif char == "," and depth == 0:
                        tuple_element_types.append(current_type.strip())
                        current_type = ""
                    else:
                        current_type += char

                if current_type:
                    tuple_element_types.append(current_type.strip())

                print(
                    f"DEBUG: Обнаружен tuple с фиксированными типами: {tuple_element_types}"
                )

        # Парсим значение
        value_ast = self.parse_expression_to_ast(value_str)

        # Проверяем существование переменной
        existing_symbol = scope["symbol_table"].get_symbol_for_validation(name)
        was_deleted = False

        if existing_symbol:
            was_deleted = existing_symbol.get("is_deleted", False)

            if not was_deleted:
                print(f"Error: переменная '{name}' уже объявлена")
                return False

            # Восстанавливаем удаленную переменную
            scope["symbol_table"].update_symbol(
                name,
                {
                    "type": var_type,
                    "value": value_ast,
                    "is_deleted": False,
                },
            )

            if hasattr(scope["symbol_table"], "deleted_symbols"):
                scope["symbol_table"].deleted_symbols.discard(name)
        else:
            # Новая переменная
            scope["symbol_table"].add_symbol(
                name=name,
                key="var",
                var_type=var_type,
                value=value_ast,
            )

        # Добавляем в local_variables если нужно
        if name not in scope["local_variables"]:
            scope["local_variables"].append(name)

        # Определяем тип операции и узла
        if was_deleted:
            creation_op_type = "RESTORE_VAR"
            node_type = "redeclaration"
        else:
            creation_op_type = "NEW_VAR"
            node_type = "declaration"

        # Создаем базовые операции
        operations = [
            {
                "type": creation_op_type,
                "target": name,
                "var_type": var_type,
                "was_deleted": was_deleted,
            }
        ]

        # Обработка в зависимости от типа
        if is_tuple_uniform:
            # tuple[T] - универсальный кортеж
            if value_ast.get("type") == "tuple_literal":
                items = value_ast.get("items", [])

                # Проверяем типы элементов (опционально)
                for i, item in enumerate(items):
                    if item.get("type") == "literal":
                        item_type = item.get("data_type", "")
                        if element_type == "int" and item_type not in ["int", "float"]:
                            print(
                                f"Warning: элемент {i} кортежа '{name}' должен быть {element_type}, а не {item_type}"
                            )
                        elif element_type == "str" and item_type != "str":
                            print(
                                f"Warning: элемент {i} кортежа '{name}' должен быть {element_type}, а не {item_type}"
                            )

                operations.append(
                    {
                        "type": "CREATE_TUPLE_UNIFORM",
                        "target": name,
                        "items": items,
                        "size": len(items),
                        "element_type": element_type,
                        "is_immutable": True,
                        "is_uniform": True,  # Все элементы одного типа
                    }
                )
            else:
                operations.append(
                    {"type": "INITIALIZE", "target": name, "value": value_ast}
                )

        elif is_tuple_fixed:
            # tuple[T1, T2, ...] - кортеж с фиксированными типами
            if value_ast.get("type") == "tuple_literal":
                items = value_ast.get("items", [])

                # Проверяем соответствие количества элементов
                if len(items) != len(tuple_element_types):
                    print(
                        f"Error: кортеж '{name}' должен содержать {len(tuple_element_types)} элементов, а не {len(items)}"
                    )
                    return False

                operations.append(
                    {
                        "type": "CREATE_TUPLE_FIXED",
                        "target": name,
                        "items": items,
                        "size": len(items),
                        "element_types": tuple_element_types,
                        "is_immutable": True,
                        "is_uniform": False,  # Элементы разных типов
                    }
                )
            else:
                operations.append(
                    {"type": "INITIALIZE", "target": name, "value": value_ast}
                )

        elif var_type_str.startswith("list["):
            # list[T]
            match = re.match(r"list\[([^\]]+)\]", var_type_str)
            if match:
                element_type = match.group(1)

                if value_ast.get("type") == "list_literal":
                    operations.append(
                        {
                            "type": "CREATE_LIST",
                            "target": name,
                            "items": value_ast.get("items", []),
                            "size": len(value_ast.get("items", [])),
                            "element_type": element_type,
                            "is_pointer_array": True,
                        }
                    )
                else:
                    operations.append(
                        {"type": "INITIALIZE", "target": name, "value": value_ast}
                    )

        elif var_type_str in ["list", "dict", "set"]:
            # Простые структуры данных
            if value_ast.get("type") == "list_literal":
                operations.append(
                    {
                        "type": "CREATE_LIST",
                        "target": name,
                        "items": value_ast.get("items", []),
                        "size": len(value_ast.get("items", [])),
                        "element_type": "any",
                    }
                )
            elif value_ast.get("type") == "dict_literal":
                operations.append(
                    {
                        "type": "CREATE_DICT",
                        "target": name,
                        "pairs": value_ast.get("pairs", {}),
                        "size": len(value_ast.get("pairs", {})),
                    }
                )
            elif value_ast.get("type") == "set_literal":
                operations.append(
                    {
                        "type": "CREATE_SET",
                        "target": name,
                        "items": value_ast.get("items", []),
                        "size": len(value_ast.get("items", [])),
                    }
                )
            else:
                operations.append(
                    {"type": "INITIALIZE", "target": name, "value": value_ast}
                )

        elif is_pointer:
            # Указатели
            if value_ast.get("type") == "address_of":
                operations.append(
                    {
                        "type": "GET_ADDRESS",
                        "target": name,
                        "of": value_ast.get("variable"),
                        "operation": "&",
                    }
                )
            elif value_ast.get("type") == "literal" and value_ast.get("value") is None:
                operations.append(
                    {"type": "ASSIGN_NULL", "target": name, "is_null": True}
                )
            else:
                operations.append(
                    {"type": "ASSIGN_POINTER", "target": name, "value": value_ast}
                )

        else:
            # Обычные переменные
            operations.append({"type": "ASSIGN", "target": name, "value": value_ast})

        # Собираем зависимости
        dependencies = []
        if value_ast:
            dependencies = self.extract_dependencies_from_ast(value_ast)

        # Определяем структуру данных
        data_structure = None
        if is_tuple_uniform or is_tuple_fixed:
            data_structure = "tuple"
        elif var_type_str.startswith("list["):
            data_structure = "list"
        elif var_type_str in ["list", "dict", "set"]:
            data_structure = var_type_str
        elif is_pointer:
            data_structure = "pointer"

        # Создаем узел
        scope["graph"].append(
            {
                "node": node_type,
                "content": line,
                "symbols": [name],
                "var_name": name,
                "var_type": var_type,
                "is_pointer": is_pointer,
                "operations": operations,
                "dependencies": dependencies,
                "expression_ast": value_ast,
                "data_structure": data_structure,
                "tuple_info": {
                    "is_uniform": is_tuple_uniform,
                    "is_fixed": is_tuple_fixed,
                    "element_type": element_type if is_tuple_uniform else None,
                    "element_types": tuple_element_types if is_tuple_fixed else None,
                }
                if is_tuple_uniform or is_tuple_fixed
                else None,
            }
        )

        return True

    def extract_element_type(self, type_str: str, container: str) -> str:
        """Извлекает тип элементов из объявления типа"""
        pattern = rf"{container}\[([^\]]+)\]"
        match = re.search(pattern, type_str)
        if match:
            return match.group(1).strip()
        return "any"

    def extract_tuple_size(self, tuple_ast: dict) -> int:
        """Извлекает размер кортежа из AST"""
        return len(tuple_ast.get("items", []))

    def parse_delete(self, line: str, scope: dict):
        """Парсит оператор del (полное удаление)"""
        pattern = r"del\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        match = re.match(pattern, line)

        if not match:
            return False

        name = match.group(1)

        symbol = scope["symbol_table"].get_symbol(name)
        if not symbol:
            return False  # Переменная не существует или уже удалена

        deleted = scope["symbol_table"].delete_symbol(name)

        if deleted:
            # Добавляем флаг, что это полное удаление (не del_pointer)
            scope["graph"].append(
                {
                    "node": "delete",
                    "content": line,
                    "symbols": [name],
                    "operations": [
                        {
                            "type": "DELETE_FULL",
                            "target": name,
                        }  # Изменено с DELETE на DELETE_FULL
                    ],
                    "is_full_delete": True,  # Добавляем флаг
                }
            )

        return deleted

    def parse_del_pointer(self, line: str, scope: dict):
        """Парсит оператор del_pointer"""
        pattern = r"del_pointer\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        match = re.match(pattern, line)

        if not match:
            return False

        name = match.group(1)

        symbol = scope["symbol_table"].get_symbol(name)
        if not symbol:
            return False  # Переменная не существует или уже удалена

        # ПОМЕЧАЕМ как удаленный указатель (но данные остаются)
        scope["symbol_table"].delete_symbol(name)

        # ИСПРАВЛЕНИЕ: Создаем узел del_pointer с правильными операциями
        scope["graph"].append(
            {
                "node": "del_pointer",  # Важно: node должен быть "del_pointer", а не "delete"
                "content": line,  # Сохраняем оригинальную строку "del_pointer x"
                "symbols": [name],
                "operations": [
                    {
                        "type": "DELETE_POINTER",
                        "target": name,
                    }  # DELETE_POINTER, а не DELETE_FULL
                ],
                "is_full_delete": False,  # Не полное удаление
            }
        )

        return True

    def parse_return(self, line: str, scope: dict):
        """Парсит оператор return"""
        pattern = r"return\s+(.+)"
        match = re.match(pattern, line)

        if not match:
            return False

        expression = match.group(1).strip()

        dependencies = []
        var_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)"
        vars_in_value = re.findall(var_pattern, expression)
        for var in vars_in_value:
            if var not in KEYS and var not in DATA_TYPES:
                dependencies.append(var)

        # Парсим выражение
        expression_ast = self.parse_expression_to_ast(expression)

        scope["graph"].append(
            {
                "node": "return",
                "content": line,
                "symbols": [expression] if expression.isalpha() else [],
                "operations": [
                    {
                        "type": "RETURN",
                        "value": expression_ast,  # Используем AST вместо строки
                        "expression": expression,
                    }
                ],
                "dependencies": dependencies,
            }
        )

        if "return_info" in scope:
            scope["return_info"]["has_return"] = True
            scope["return_info"]["return_value"] = expression_ast

        return True

    def parse_expression_to_ast(self, expression: str) -> dict:
        """Парсит выражение в AST (Abstract Syntax Tree)"""
        expression = expression.strip()

        # Если пустая строка
        if not expression:
            return {"type": "empty", "value": ""}

        if expression.startswith("(") and expression.endswith(")"):
            # Проверяем, что это не просто выражение в скобках
            if "," in expression[1:-1]:
                return self.parse_tuple_literal(expression)
            else:
                # Выражение в скобках
                inner = expression[1:-1].strip()
                return self.parse_expression_to_ast(inner)

        # 1. Сначала проверяем литералы и простые конструкции

        # 1.1 Пустая строка
        if expression == '""' or expression == "''":
            return {"type": "literal", "value": "", "data_type": "str"}

        # 1.2 Строковые литералы
        if (expression.startswith('"') and expression.endswith('"')) or (
            expression.startswith("'") and expression.endswith("'")
        ):
            # Проверяем, что это не часть более сложного выражения
            if len(expression) > 1 and expression[0] == expression[-1]:
                return {
                    "type": "literal",
                    "value": expression[1:-1],
                    "data_type": "str",
                }

        # 1.3 Числа с плавающей точкой
        if re.match(r"^-?\d+\.\d+$", expression) or re.match(
            r"^-?\d+\.\d+[eE][+-]?\d+$", expression
        ):
            try:
                return {
                    "type": "literal",
                    "value": float(expression),
                    "data_type": "float",
                }
            except ValueError:
                pass

        # 1.4 Целые числа
        if re.match(r"^-?\d+$", expression):
            return {"type": "literal", "value": int(expression), "data_type": "int"}

        # 1.5 Шестнадцатеричные числа
        if re.match(r"^0[xX][0-9a-fA-F]+$", expression):
            return {"type": "literal", "value": int(expression, 16), "data_type": "int"}

        # 1.6 Булевы значения
        if expression == "True":
            return {"type": "literal", "value": True, "data_type": "bool"}
        if expression == "False":
            return {"type": "literal", "value": False, "data_type": "bool"}

        # 1.7 None
        if expression == "None":
            return {"type": "literal", "value": None, "data_type": "None"}

        # 1.8 null для указателей
        if expression == "null":
            return {"type": "literal", "value": None, "data_type": "null"}

        # 2. Сложные литералы

        # 2.1 Литералы списков
        if expression.startswith("[") and expression.endswith("]"):
            return self.parse_list_literal(expression)

        # 2.2 Литералы словарей/множеств
        if expression.startswith("{") and expression.endswith("}"):
            content = expression[1:-1].strip()

            # Проверяем, является ли это словарем
            if self.is_dict_literal(content):
                return self.parse_dict_literal(expression)
            else:
                # Иначе это множество
                return self.parse_set_literal(expression)

        # 3. Операции с указателями

        # 3.1 Адрес переменной (&x)
        if expression.startswith("&"):
            var_name = expression[1:].strip()
            # Проверяем, что это не часть более сложного выражения
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", var_name):
                return {"type": "address_of", "variable": var_name, "value": expression}

        # 3.2 Разыменование указателя (*p)
        if expression.startswith("*"):
            pointer_name = expression[1:].strip()
            # Проверяем, что это не умножение
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", pointer_name):
                return {
                    "type": "dereference",
                    "pointer": pointer_name,
                    "value": expression,
                }

        # 4. Вызовы функций

        # 4.1 Простые вызовы функций: func()
        func_pattern_simple = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*\)$"
        simple_match = re.match(func_pattern_simple, expression)
        if simple_match:
            func_name = simple_match.group(1)
            return {"type": "function_call", "function": func_name, "arguments": []}

        # 4.2 Вызовы функций с аргументами
        func_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$"
        func_match = re.match(func_pattern, expression)
        if func_match:
            func_name = func_match.group(1)
            args_str = func_match.group(2)

            # Проверяем, что нет лишних скобок после
            if not self.has_unbalanced_parentheses(args_str):
                args = self.parse_function_arguments_to_ast(args_str)
                return {
                    "type": "function_call",
                    "function": func_name,
                    "arguments": args,
                }

        # 5. Переменные
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", expression):
            return {"type": "variable", "value": expression}

        # 6. Сложные выражения с операторами

        # 6.1 Выражение в скобках - убираем внешние скобки и парсим заново
        if expression.startswith("(") and expression.endswith(")"):
            # Проверяем баланс скобок
            if self.is_fully_parenthesized(expression):
                inner = expression[1:-1].strip()
                return self.parse_expression_to_ast(inner)

        # 6.2 Бинарные операции
        # Ищем оператор с наименьшим приоритетом

        # Сначала логические OR
        or_index = self.find_operator_outside_parentheses(expression, "or")
        if or_index != -1:
            left = expression[:or_index].strip()
            right = expression[or_index + 2 :].strip()
            return {
                "type": "binary_operation",
                "operator": "OR",
                "operator_symbol": "or",
                "left": self.parse_expression_to_ast(left),
                "right": self.parse_expression_to_ast(right),
            }

        # Затем логические AND
        and_index = self.find_operator_outside_parentheses(expression, "and")
        if and_index != -1:
            left = expression[:and_index].strip()
            right = expression[and_index + 3 :].strip()
            return {
                "type": "binary_operation",
                "operator": "AND",
                "operator_symbol": "and",
                "left": self.parse_expression_to_ast(left),
                "right": self.parse_expression_to_ast(right),
            }

        # Сравнения
        comparison_ops = [
            ("==", "EQUAL"),
            ("!=", "NOT_EQUAL"),
            ("<", "LESS_THAN"),
            (">", "GREATER_THAN"),
            ("<=", "LESS_EQUAL"),
            (">=", "GREATER_EQUAL"),
            ("is", "IS"),
            ("is not", "IS_NOT"),
            ("in", "IN"),
            ("not in", "NOT_IN"),
        ]

        for op_symbol, op_type in comparison_ops:
            index = self.find_operator_outside_parentheses(expression, op_symbol)
            if index != -1:
                left = expression[:index].strip()
                right = expression[index + len(op_symbol) :].strip()
                return {
                    "type": "binary_operation",
                    "operator": op_type,
                    "operator_symbol": op_symbol,
                    "left": self.parse_expression_to_ast(left),
                    "right": self.parse_expression_to_ast(right),
                }

        # Битовая OR
        bitwise_or_index = self.find_operator_outside_parentheses(expression, "|")
        if bitwise_or_index != -1:
            left = expression[:bitwise_or_index].strip()
            right = expression[bitwise_or_index + 1 :].strip()
            return {
                "type": "binary_operation",
                "operator": "BITWISE_OR",
                "operator_symbol": "|",
                "left": self.parse_expression_to_ast(left),
                "right": self.parse_expression_to_ast(right),
            }

        # Битовая XOR
        bitwise_xor_index = self.find_operator_outside_parentheses(expression, "^")
        if bitwise_xor_index != -1:
            left = expression[:bitwise_xor_index].strip()
            right = expression[bitwise_xor_index + 1 :].strip()
            return {
                "type": "binary_operation",
                "operator": "BITWISE_XOR",
                "operator_symbol": "^",
                "left": self.parse_expression_to_ast(left),
                "right": self.parse_expression_to_ast(right),
            }

        # Битовая AND
        bitwise_and_index = self.find_operator_outside_parentheses(expression, "&")
        if bitwise_and_index != -1:
            # Проверяем, что это не оператор адреса (&x)
            if bitwise_and_index > 0 and expression[bitwise_and_index - 1] != " ":
                # Возможно, это адресная операция
                pass
            else:
                left = expression[:bitwise_and_index].strip()
                right = expression[bitwise_and_index + 1 :].strip()
                return {
                    "type": "binary_operation",
                    "operator": "BITWISE_AND",
                    "operator_symbol": "&",
                    "left": self.parse_expression_to_ast(left),
                    "right": self.parse_expression_to_ast(right),
                }

        # Сдвиги
        shift_ops = [("<<", "LEFT_SHIFT"), (">>", "RIGHT_SHIFT")]
        for op_symbol, op_type in shift_ops:
            index = self.find_operator_outside_parentheses(expression, op_symbol)
            if index != -1:
                left = expression[:index].strip()
                right = expression[index + len(op_symbol) :].strip()
                return {
                    "type": "binary_operation",
                    "operator": op_type,
                    "operator_symbol": op_symbol,
                    "left": self.parse_expression_to_ast(left),
                    "right": self.parse_expression_to_ast(right),
                }

        # Сложение и вычитание
        add_sub_ops = [("+", "ADD"), ("-", "SUBTRACT")]
        for op_symbol, op_type in add_sub_ops:
            index = self.find_operator_outside_parentheses(expression, op_symbol)
            if index != -1:
                # Проверяем, что это не унарный оператор
                if index == 0 and op_symbol == "-":
                    # Унарный минус
                    operand = expression[1:].strip()
                    return {
                        "type": "unary_operation",
                        "operator": "NEGATIVE",
                        "operator_symbol": "-",
                        "operand": self.parse_expression_to_ast(operand),
                    }
                elif index == 0 and op_symbol == "+":
                    # Унарный плюс (обычно игнорируется)
                    operand = expression[1:].strip()
                    return self.parse_expression_to_ast(operand)
                else:
                    left = expression[:index].strip()
                    right = expression[index + len(op_symbol) :].strip()
                    return {
                        "type": "binary_operation",
                        "operator": op_type,
                        "operator_symbol": op_symbol,
                        "left": self.parse_expression_to_ast(left),
                        "right": self.parse_expression_to_ast(right),
                    }

        # Умножение, деление и остальные
        mul_div_ops = [
            ("*", "MULTIPLY"),
            ("/", "DIVIDE"),
            ("//", "INTEGER_DIVIDE"),
            ("%", "MODULO"),
        ]
        for op_symbol, op_type in mul_div_ops:
            index = self.find_operator_outside_parentheses(expression, op_symbol)
            if index != -1:
                left = expression[:index].strip()
                right = expression[index + len(op_symbol) :].strip()
                return {
                    "type": "binary_operation",
                    "operator": op_type,
                    "operator_symbol": op_symbol,
                    "left": self.parse_expression_to_ast(left),
                    "right": self.parse_expression_to_ast(right),
                }

        # Возведение в степень
        power_index = self.find_operator_outside_parentheses(expression, "**")
        if power_index != -1:
            left = expression[:power_index].strip()
            right = expression[power_index + 2 :].strip()
            return {
                "type": "binary_operation",
                "operator": "POWER",
                "operator_symbol": "**",
                "left": self.parse_expression_to_ast(left),
                "right": self.parse_expression_to_ast(right),
            }

        # 7. Унарные операции

        # 7.1 Унарный not
        if expression.startswith("not "):
            operand = expression[4:].strip()
            return {
                "type": "unary_operation",
                "operator": "NOT",
                "operator_symbol": "not",
                "operand": self.parse_expression_to_ast(operand),
            }

        # 7.2 Унарный ~ (битовое НЕ)
        if expression.startswith("~"):
            operand = expression[1:].strip()
            return {
                "type": "unary_operation",
                "operator": "BITWISE_NOT",
                "operator_symbol": "~",
                "operand": self.parse_expression_to_ast(operand),
            }

        # 8. Индексация (массивы, словари)
        index_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(.+)\]$"
        index_match = re.match(index_pattern, expression)
        if index_match:
            var_name = index_match.group(1)
            index_expr = index_match.group(2)
            return {
                "type": "index_access",
                "variable": var_name,
                "index": self.parse_expression_to_ast(index_expr),
            }

        # 9. Атрибуты (объекты)
        attr_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$"
        attr_match = re.match(attr_pattern, expression)
        if attr_match:
            obj_name = attr_match.group(1)
            attr_name = attr_match.group(2)
            return {
                "type": "attribute_access",
                "object": obj_name,
                "attribute": attr_name,
            }

        # 10. Тернарный оператор (x if cond else y)
        ternary_match = re.search(r"\sif\s", expression)
        if ternary_match:
            else_match = re.search(r"\selse\s", expression)
            if else_match and ternary_match.start() < else_match.start():
                condition = expression[: ternary_match.start()].strip()
                true_expr = expression[ternary_match.end() : else_match.start()].strip()
                false_expr = expression[else_match.end() :].strip()
                return {
                    "type": "ternary_operation",
                    "condition": self.parse_expression_to_ast(condition),
                    "true_expr": self.parse_expression_to_ast(true_expr),
                    "false_expr": self.parse_expression_to_ast(false_expr),
                }

        # Если ничего не распознано
        return {"type": "unknown", "value": expression, "original": expression}

    def is_dict_literal(self, content: str) -> bool:
        """Определяет, является ли содержимое литералом словаря"""
        if not content:
            # Пустой {} - может быть и словарем и множеством
            # По умолчанию считаем словарем
            return True

        # Проверяем наличие хотя бы одного ':' вне строк и вложенных структур
        in_string = False
        string_char = None
        depth = 0  # Для вложенных структур

        i = 0
        while i < len(content):
            char = content[i]

            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                if i > 0 and content[i - 1] == "\\":
                    pass  # Экранированная кавычка
                else:
                    in_string = False
            elif not in_string:
                if char in ["[", "{", "("]:
                    depth += 1
                elif char in ["]", "}", ")"]:
                    depth -= 1
                elif char == ":" and depth == 0:
                    return True  # Нашли ':' на верхнем уровне - это словарь

            i += 1

        return False  # Не нашли ':' - вероятно множество

    def is_set_literal(self, content: str) -> bool:
        """Проверяет, является ли содержимое литералом множества"""
        # Множество не содержит двоеточий
        if ":" in content:
            return False

        # Проверяем баланс скобок
        balance = 0
        in_string = False
        string_char = None

        for char in content:
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                in_string = False
            elif not in_string:
                if char == "{":
                    balance += 1
                elif char == "}":
                    balance -= 1

        return balance == 0

    def has_unbalanced_parentheses(self, s: str) -> bool:
        """Проверяет, есть ли несбалансированные скобки"""
        balance = 0
        in_string = False
        string_char = None

        for char in s:
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                in_string = False
            elif not in_string:
                if char == "(":
                    balance += 1
                elif char == ")":
                    balance -= 1
                    if balance < 0:
                        return True

        return balance != 0

    def is_fully_parenthesized(self, expression: str) -> bool:
        """Проверяет, полностью ли выражение заключено в скобки"""
        if not expression.startswith("(") or not expression.endswith(")"):
            return False

        # Проверяем баланс скобок
        balance = 0
        in_string = False
        string_char = None

        for i, char in enumerate(expression):
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                in_string = False
            elif not in_string:
                if char == "(":
                    balance += 1
                elif char == ")":
                    balance -= 1
                    # Если баланс стал 0 до конца строки
                    if balance == 0 and i < len(expression) - 1:
                        return False

        return balance == 0

    def parse_assignment(self, line: str, scope: dict):
        print(
            f"      parse_assignment: парсим '{line}' в scope {scope.get('type', 'unknown')}"
        )

        # Проверяем, является ли это разыменованием указателя (*p = значение)
        deref_pattern = r"\*\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
        deref_match = re.match(deref_pattern, line)

        if deref_match:
            # Это запись через указатель: *p = значение
            pointer_name, value = deref_match.groups()
            print(
                f"      parse_assignment: запись через указатель '{pointer_name}' = '{value}'"
            )

            # Ищем указатель в scope'ах
            result = self.find_symbol_recursive(scope, pointer_name)
            if not result:
                print(f"      parse_assignment: указатель '{pointer_name}' не найден")
                return False

            pointer_symbol, found_scope = result

            # Проверяем, что это действительно указатель
            if not pointer_symbol["type"].startswith("*"):
                print(
                    f"      parse_assignment: '{pointer_name}' не является указателем"
                )
                return False

            # Парсим значение в AST
            value_ast = self.parse_expression_to_ast(value)

            operations = [
                {
                    "type": "WRITE_POINTER",
                    "pointer": pointer_name,
                    "value": value_ast,
                    "operation": "*=",
                }
            ]

            dependencies = self.extract_dependencies_from_ast(value_ast)

            scope["graph"].append(
                {
                    "node": "dereference_write",
                    "content": line,
                    "symbols": [pointer_name],
                    "operations": operations,
                    "dependencies": dependencies,
                    "is_dereference_write": True,
                }
            )

            return True

        # Обычное присваивание: переменная = выражение
        pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
        match = re.match(pattern, line)

        if not match:
            print(f"      parse_assignment: не удалось распарсить")
            return False

        name, expression = match.groups()

        print(f"      parse_assignment: name='{name}', expression='{expression}'")

        # Проверяем, является ли выражение разыменованием указателя (*p)
        if expression.strip().startswith("*"):
            # Это чтение через указатель: x = *p
            pointer_name = expression.strip()[1:].strip()
            print(f"      parse_assignment: чтение через указатель '{pointer_name}'")

            # Ищем указатель в scope'ах
            result = self.find_symbol_recursive(scope, pointer_name)
            if not result:
                print(f"      parse_assignment: указатель '{pointer_name}' не найден")
                return False

            pointer_symbol, found_scope = result

            # Проверяем, что это действительно указатель
            if not pointer_symbol["type"].startswith("*"):
                print(
                    f"      parse_assignment: '{pointer_name}' не является указателем"
                )
                return False

            # Ищем целевую переменную
            target_result = self.find_symbol_recursive(scope, name)
            if not target_result:
                print(f"      parse_assignment: целевая переменная '{name}' не найдена")
                return False

            target_symbol, target_scope = target_result

            # Создаем AST для разыменования
            deref_ast = {"type": "dereference", "pointer": pointer_name}

            operations = [
                {
                    "type": "READ_POINTER",
                    "target": name,
                    "from": pointer_name,
                    "operation": "*",
                    "value": deref_ast,
                    "pointed_type": pointer_symbol["type"][1:],  # Убираем звездочку
                }
            ]

            dependencies = [pointer_name]

            # Обновляем значение в symbol table
            scope["symbol_table"].add_symbol(
                name=name,
                key=target_symbol["key"],
                var_type=target_symbol["type"],
                value=deref_ast,
            )

            scope["graph"].append(
                {
                    "node": "dereference_read",
                    "content": line,
                    "symbols": [name],
                    "operations": operations,
                    "dependencies": dependencies,
                    "is_dereference_read": True,
                }
            )

            return True

        # Обычное присваивание с выражением
        # Ищем символ в текущем scope или в родительских scopes
        symbol = None
        current_scope = scope

        def find_symbol_recursive(current_scope, target_name, visited=None):
            if visited is None:
                visited = set()

            scope_id = id(current_scope)
            if scope_id in visited:
                return None
            visited.add(scope_id)

            # Ищем символ в текущем scope
            symbol = current_scope["symbol_table"].get_symbol(target_name)
            if symbol:
                return symbol, current_scope

            # Если не нашли и есть родительский scope, ищем там
            if "parent_scope" in current_scope:
                parent_level = current_scope["parent_scope"]
                # Ищем scope с нужным уровнем
                for parent in self.scopes:
                    if parent["level"] == parent_level:
                        result = find_symbol_recursive(parent, target_name, visited)
                        if result:
                            return result

            return None

        # Ищем символ рекурсивно
        result = find_symbol_recursive(scope, name)
        if result:
            symbol, found_scope = result
            print(
                f"      parse_assignment: нашли символ '{name}' типа {symbol['type']} в scope {found_scope.get('type', 'unknown')}"
            )
        else:
            print(f"      parse_assignment: символ '{name}' не найден ни в одном scope")
            return False

        # Парсим выражение в AST
        expression_ast = self.parse_expression_to_ast(expression)

        # Обновляем значение в symbol table
        scope["symbol_table"].add_symbol(
            name=name, key=symbol["key"], var_type=symbol["type"], value=expression_ast
        )

        # Создаем операции
        operations = []
        dependencies = self.extract_dependencies_from_ast(expression_ast)

        # Для простых присваиваний создаем ASSIGN операцию
        if expression_ast["type"] in ["variable", "literal", "function_call"]:
            operations.append(
                {"type": "ASSIGN", "target": name, "value": expression_ast}
            )
        else:
            # Для сложных выражений используем build_operations_from_ast
            self.build_operations_from_ast(
                expression_ast, name, operations, dependencies, scope
            )

        # Добавляем узел в граф
        scope["graph"].append(
            {
                "node": "assignment",
                "content": line,
                "symbols": [name],
                "operations": operations,
                "dependencies": dependencies,
                "expression_ast": expression_ast,
            }
        )

        print(
            f"      parse_assignment: добавлен узел в граф scope {scope.get('type', 'unknown')}"
        )

        return True

    def parse_augmented_assignment(self, line: str, scope: dict):
        """Парсит составные операции присваивания"""
        pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(\+=|-=|\*=|/=|//=|\%=|\*\*=|>>=|<<=|&=|\|=|\^=)\s*(.+)"
        match = re.match(pattern, line)

        if not match:
            return False

        name, operator, value = match.groups()

        # Используем тот же поиск, что и в parse_assignment
        def find_symbol_recursive(current_scope, target_name, visited=None):
            if visited is None:
                visited = set()

            scope_id = id(current_scope)
            if scope_id in visited:
                return None
            visited.add(scope_id)

            symbol = current_scope["symbol_table"].get_symbol(target_name)
            if symbol:
                return symbol, current_scope

            if "parent_scope" in current_scope:
                parent_level = current_scope["parent_scope"]
                for parent in self.scopes:
                    if parent["level"] == parent_level:
                        result = find_symbol_recursive(parent, target_name, visited)
                        if result:
                            return result

            return None

        result = find_symbol_recursive(scope, name)
        if not result:
            return False

        symbol, found_scope = result

        # Определяем тип операции
        operator_map = {
            "+=": "ADD",
            "-=": "SUBTRACT",
            "*=": "MULTIPLY",
            "/=": "DIVIDE",
            "//=": "INTEGER_DIVIDE",
            "%=": "MODULO",
            "**=": "POWER",
            ">>=": "RIGHT_SHIFT",
            "<<=": "LEFT_SHIFT",
            "&=": "BITWISE_AND",
            "|=": "BITWISE_OR",
            "^=": "BITWISE_XOR",
        }

        op_type = operator_map.get(operator, "UNKNOWN_AUGMENTED")

        operations = [
            {
                "type": "AUGMENTED_ASSIGN",
                "target": name,
                "operator": op_type,
                "operator_symbol": operator,
                "value": value,
            }
        ]

        dependencies = []
        if value.isalpha() and value not in KEYS and value not in DATA_TYPES:
            dependencies.append(value)

        # Обновляем значение переменной
        scope["symbol_table"].add_symbol(
            name=name,
            key="var",
            var_type=symbol["type"],
            value=f"{name} {operator} {value}",
        )

        scope["graph"].append(
            {
                "node": "augmented_assignment",
                "content": line,
                "symbols": [name],
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def parse_expression(self, expression: str, target_var: str, scope: dict):
        """Парсит сложные выражения с несколькими операциями"""
        # Упрощенная версия - поддерживает только одну операцию
        # Для полной поддержки нужно реализовать парсер выражений с учетом приоритета

        operators = [
            ("**", "POWER", 10),
            ("*", "MULTIPLY", 9),
            ("/", "DIVIDE", 9),
            ("//", "INTEGER_DIVIDE", 9),
            ("%", "MODULO", 9),
            ("+", "ADD", 8),
            ("-", "SUBTRACT", 8),
            ("<<", "LEFT_SHIFT", 7),
            (">>", "RIGHT_SHIFT", 7),
            ("&", "BITWISE_AND", 6),
            ("^", "BITWISE_XOR", 5),
            ("|", "BITWISE_OR", 4),
        ]

        # Ищем оператор с наивысшим приоритетом
        for op_symbol, op_type, priority in operators:
            if op_symbol in expression:
                parts = expression.split(
                    op_symbol, 1
                )  # Разделяем только по первому вхождению
                if len(parts) == 2:
                    left, right = parts[0].strip(), parts[1].strip()

                    operations = [
                        {
                            "type": "BINARY_OPERATION",
                            "target": target_var,
                            "operator": op_type,
                            "operator_symbol": op_symbol,
                            "left": left,
                            "right": right,
                        }
                    ]

                    dependencies = []
                    if left.isalpha() and left not in KEYS and left not in DATA_TYPES:
                        dependencies.append(left)
                    if (
                        right.isalpha()
                        and right not in KEYS
                        and right not in DATA_TYPES
                    ):
                        dependencies.append(right)

                    return operations, dependencies

        # Если операций нет - простое присваивание
        return [
            {
                "type": "ASSIGN",
                "target": target_var,
                "value": self.clean_value(expression),
            }
        ], []

    def parse_complex_expression(
        self,
        target: str,
        expression: str,
        operations: list,
        dependencies: list,
        scope: dict,
    ):
        """Разбирает сложные выражения с несколькими операторами и скобками"""
        expression = expression.strip()

        # Убираем внешние скобки, если выражение полностью в них
        while self.is_fully_parenthesized(expression):
            expression = expression[1:-1].strip()

        # Проверяем, содержит ли выражение операторы
        if not self.contains_operator(expression):
            # Нет операторов - это простое значение или переменная
            clean_expr = expression.strip("() ")
            if (
                clean_expr
                and clean_expr.isalpha()
                and clean_expr not in KEYS
                and clean_expr not in DATA_TYPES
            ):
                dependencies.append(clean_expr)

            operations.append(
                {
                    "type": "ASSIGN",
                    "target": target,
                    "value": self.clean_value(expression),
                }
            )
            return

        # Находим оператор с наименьшим приоритетом
        operator_info = self.find_lowest_priority_operator(expression)

        if not operator_info:
            # Если не нашли оператор, возможно выражение в скобках содержит операторы
            # Попробуем разобрать как есть
            clean_expr = expression.strip("() ")
            if clean_expr:
                temp_var = f"{target}_inner"
                self.parse_complex_expression(
                    temp_var, clean_expr, operations, dependencies, scope
                )
                operations.append(
                    {"type": "ASSIGN", "target": target, "value": temp_var}
                )
            return

        op_symbol, op_type, op_index = operator_info
        left = expression[:op_index].strip()
        right = expression[op_index + len(op_symbol) :].strip()

        # Добавляем основную операцию
        operations.append(
            {
                "type": "BINARY_OPERATION",
                "target": target,
                "operator": op_type,
                "operator_symbol": op_symbol,
                "left": left,
                "right": right,
            }
        )

        # Вспомогательная функция для разбора части выражения
        def parse_subexpression(subexpr: str, side: str):
            subexpr = subexpr.strip()
            if not subexpr:
                return

            # Убираем внешние скобки
            while self.is_fully_parenthesized(subexpr):
                subexpr = subexpr[1:-1].strip()

            if self.contains_operator(subexpr):
                # Создаем временную переменную для подвыражения
                temp_var = f"{target}_{side}_{len(operations)}"
                self.parse_complex_expression(
                    temp_var, subexpr, operations, dependencies, scope
                )
                # Обновляем ссылку в основной операции
                for op in operations:
                    if (
                        op.get("target") == target
                        and op.get("type") == "BINARY_OPERATION"
                    ):
                        if side == "left":
                            op["left"] = temp_var
                        else:
                            op["right"] = temp_var
            else:
                # Проверяем зависимости
                clean_subexpr = subexpr.strip("() ")
                if (
                    clean_subexpr
                    and clean_subexpr.isalpha()
                    and clean_subexpr not in KEYS
                    and clean_subexpr not in DATA_TYPES
                ):
                    dependencies.append(clean_subexpr)

        # Рекурсивно разбираем левую и правую части
        parse_subexpression(left, "left")
        parse_subexpression(right, "right")

    def is_fully_parenthesized(self, expression: str) -> bool:
        """Проверяет, полностью ли выражение заключено в скобки"""
        if not expression.startswith("(") or not expression.endswith(")"):
            return False

        # Проверяем баланс скобок
        balance = 0
        for i, char in enumerate(expression):
            if char == "(":
                balance += 1
            elif char == ")":
                balance -= 1
                # Если баланс стал 0 до конца строки, это не полное обрамление
                if balance == 0 and i < len(expression) - 1:
                    return False

        return balance == 0

    def find_lowest_priority_operator(self, expression: str):
        """Находит оператор с наименьшим приоритетом вне скобок"""
        # Приоритет операций (от низшего к высшему)
        operator_levels = [
            # Уровень 1 (наименьший приоритет)
            [("|", "BITWISE_OR")],
            # Уровень 2
            [("^", "BITWISE_XOR")],
            # Уровень 3
            [("&", "BITWISE_AND")],
            # Уровень 4
            [("<<", "LEFT_SHIFT"), (">>", "RIGHT_SHIFT")],
            # Уровень 5
            [("+", "ADD"), ("-", "SUBTRACT")],
            # Уровень 6
            [
                ("*", "MULTIPLY"),
                ("/", "DIVIDE"),
                ("//", "INTEGER_DIVIDE"),
                ("%", "MODULO"),
            ],
            # Уровень 7 (наивысший приоритет)
            [("**", "POWER")],
        ]

        # Ищем операторы от низшего приоритета к высшему
        for level in operator_levels:
            for op_symbol, op_type in level:
                # Ищем оператор вне скобок
                index = self.find_operator_outside_parentheses(expression, op_symbol)
                if index != -1:
                    return (op_symbol, op_type, index)

        return None

    def find_operator_outside_parentheses(self, expression: str, operator: str) -> int:
        """Находит позицию оператора вне скобок и строк"""
        balance = 0
        brace_balance = 0
        bracket_balance = 0
        in_string = False
        string_char = None

        i = 0
        while i < len(expression):
            char = expression[i]

            # Обработка строк
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                # Проверяем экранирование
                if i == 0 or expression[i - 1] != "\\":
                    in_string = False

            # Обработка скобок (только вне строк)
            if not in_string:
                if char == "(":
                    balance += 1
                elif char == ")":
                    balance -= 1
                elif char == "{":
                    brace_balance += 1
                elif char == "}":
                    brace_balance -= 1
                elif char == "[":
                    bracket_balance += 1
                elif char == "]":
                    bracket_balance -= 1
                elif balance == 0 and brace_balance == 0 and bracket_balance == 0:
                    # Проверяем оператор
                    if expression[i : i + len(operator)] == operator:
                        # Проверяем контекст (чтобы не было части другого оператора)
                        before_ok = i == 0 or not expression[i - 1].isalnum()
                        after_ok = (
                            i + len(operator) >= len(expression)
                            or not expression[i + len(operator)].isalnum()
                        )

                        if before_ok and after_ok:
                            return i

            i += 1

        return -1

    def contains_operator(self, expression: str) -> bool:
        """Проверяет, содержит ли выражение какой-либо оператор"""
        expression = expression.strip()

        # Сначала убираем внешние скобки
        while self.is_fully_parenthesized(expression):
            expression = expression[1:-1].strip()

        operators = ["+", "-", "*", "/", "//", "%", "**", ">>", "<<", "&", "|", "^"]

        balance = 0
        for i, char in enumerate(expression):
            if char == "(":
                balance += 1
            elif char == ")":
                balance -= 1
            elif balance == 0:  # Мы вне скобок
                for op in operators:
                    if expression[i : i + len(op)] == op:
                        # Проверяем контекст
                        before_ok = i == 0 or not expression[i - 1].isalnum()
                        after_ok = (
                            i + len(op) >= len(expression)
                            or not expression[i + len(op)].isalnum()
                        )

                        if before_ok and after_ok:
                            return True

        return False

    def parse_function_call(self, line: str, scope: dict):
        """Парсит вызов функции"""
        pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)"
        match = re.match(pattern, line)

        if not match:
            return False

        func_name, args_str = match.groups()
        args = []
        if args_str.strip():
            args = [arg.strip() for arg in args_str.split(",")]

        operations = [
            {"type": "FUNCTION_CALL", "function": func_name, "arguments": args}
        ]

        dependencies = []
        for arg in args:
            if arg.isalpha() and arg not in KEYS and arg not in DATA_TYPES:
                dependencies.append(arg)

        scope["graph"].append(
            {
                "node": "function_call",
                "content": line,
                "function": func_name,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def parse_function_call_assignment(self, line: str, scope: dict):
        """Парсит присваивание результата вызова функции"""
        pattern = (
            r"var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
        )
        match = re.match(pattern, line)

        if not match:
            return False

        var_name, var_type, value = match.groups()

        # Проверяем, является ли значение вызовом функции
        func_call_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)"
        func_match = re.match(func_call_pattern, value.strip())

        if func_match:
            func_name, args_str = func_match.groups()
            args = self.parse_function_arguments(args_str) if args_str.strip() else []

            # Определяем, является ли функция встроенной
            if func_name in self.builtin_functions:
                return self.parse_builtin_function_assignment(
                    line, scope, var_name, var_type, func_name, args
                )
            else:
                # Пользовательская функция
                return self.parse_user_function_assignment(
                    line, scope, var_name, var_type, func_name, args
                )

        return False

    def parse_builtin_function_assignment(
        self,
        line: str,
        scope: dict,
        var_name: str,
        var_type: str,
        func_name: str,
        args: list,
    ):
        """Парсит присваивание результата встроенной функции"""
        # Добавляем переменную
        symbol_id = scope["symbol_table"].add_symbol(
            name=var_name, key="var", var_type=var_type
        )

        scope["local_variables"].append(symbol_id)

        # Определяем тип возвращаемого значения
        return_type = self.get_builtin_return_type(func_name, args)

        # Проверяем совместимость типов
        if var_type != return_type and return_type != "unknown":
            print(
                f"Warning: тип переменной '{var_name}' ({var_type}) не совпадает с возвращаемым типом '{func_name}' ({return_type})"
            )

        operations = [
            {"type": "NEW_VAR", "target": var_name, "var_type": var_type},
            {
                "type": "BUILTIN_FUNCTION_CALL_ASSIGN",
                "function": func_name,
                "arguments": args,
                "target": var_name,
                "return_type": return_type,
            },
        ]

        # Собираем зависимости
        dependencies = []
        for arg in args:
            if (
                arg
                and not arg.startswith('"')
                and not arg.endswith('"')
                and not arg.startswith("'")
                and not arg.endswith("'")
                and not arg.isdigit()
                and arg not in ["True", "False", "None"]
            ):
                var_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)"
                vars_in_arg = re.findall(var_pattern, arg)
                for var in vars_in_arg:
                    if (
                        var not in KEYS
                        and var not in DATA_TYPES
                        and var not in dependencies
                    ):
                        dependencies.append(var)

        scope["graph"].append(
            {
                "node": "builtin_function_call_assignment",
                "content": line,
                "symbols": [var_name],
                "function": func_name,
                "arguments": args,
                "return_type": return_type,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def parse_user_function_assignment(
        self,
        line: str,
        scope: dict,
        var_name: str,
        var_type: str,
        func_name: str,
        args: list,
    ):
        """Парсит присваивание результата пользовательской функции"""
        # Добавляем переменную
        symbol_id = scope["symbol_table"].add_symbol(
            name=var_name, key="var", var_type=var_type
        )

        scope["local_variables"].append(symbol_id)

        operations = [
            {"type": "NEW_VAR", "target": var_name, "var_type": var_type},
            {
                "type": "FUNCTION_CALL_ASSIGN",
                "function": func_name,
                "arguments": args,
                "target": var_name,
            },
        ]

        dependencies = []
        for arg in args:
            if arg.isalpha() and arg not in KEYS and arg not in DATA_TYPES:
                dependencies.append(arg)

        scope["graph"].append(
            {
                "node": "function_call_assignment",
                "content": line,
                "symbols": [var_name],
                "function": func_name,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    # def parse_condition(self, condition: str) -> dict:
    #     """Парсит условие для циклов и if"""
    #     operators = ['<', '>', '<=', '>=', '==', '!=', 'and', 'or']

    #     # Простая реализация - ищем операторы сравнения
    #     for op in operators:
    #         if op in condition:
    #             parts = condition.split(op, 1)
    #             if len(parts) == 2:
    #                 left, right = parts[0].strip(), parts[1].strip()
    #                 return {
    #                     "type": "COMPARISON",
    #                     "operator": op,
    #                     "left": left,
    #                     "right": right
    #                 }

    #     # Если не нашли оператор сравнения, предполагаем булевое выражение
    #     return {
    #         "type": "EXPRESSION",
    #         "value": condition
    #     }

    def parse_condition(self, condition: str) -> dict:
        """Парсит условие для циклов и if"""
        # Используем AST парсер для сложных условий
        return self.parse_expression_to_ast(condition)

    def parse_iterable(self, iterable_expr: str) -> dict:
        """Парсит итерируемое выражение для for цикла"""
        # Проверяем range вызов с 1, 2 или 3 аргументами
        range_pattern = r"range\s*\(\s*(.+?)\s*\)"
        range_match = re.match(range_pattern, iterable_expr)

        if range_match:
            args_str = range_match.group(1)
            # Разделяем аргументы по запятым, но учитываем возможные вложенные вызовы
            args = []
            current_arg = ""
            depth = 0  # Для отслеживания вложенных скобок

            for char in args_str:
                if char == "(":
                    depth += 1
                    current_arg += char
                elif char == ")":
                    depth -= 1
                    current_arg += char
                elif char == "," and depth == 0:
                    args.append(current_arg.strip())
                    current_arg = ""
                else:
                    current_arg += char

            if current_arg:
                args.append(current_arg.strip())

            # Очищаем аргументы от лишних пробелов
            args = [arg.strip() for arg in args]

            # Определяем количество аргументов
            if len(args) == 1:
                # range(stop)
                return {
                    "type": "RANGE_CALL",
                    "function": "range",
                    "arguments": {"start": "0", "stop": args[0], "step": "1"},
                }
            elif len(args) == 2:
                # range(start, stop)
                return {
                    "type": "RANGE_CALL",
                    "function": "range",
                    "arguments": {"start": args[0], "stop": args[1], "step": "1"},
                }
            elif len(args) == 3:
                # range(start, stop, step)
                return {
                    "type": "RANGE_CALL",
                    "function": "range",
                    "arguments": {"start": args[0], "stop": args[1], "step": args[2]},
                }
            else:
                # Некорректное количество аргументов
                return {"type": "RANGE_CALL", "function": "range", "arguments": args}

        # Другие итерируемые объекты
        return {"type": "ITERABLE", "expression": iterable_expr}

    def find_loop_body_end(
        self, lines: list, start_index: int, base_indent: int
    ) -> int:
        """Находит конец тела цикла"""
        if start_index >= len(lines):
            return start_index

        # Преобразуем base_indent в реальный отступ
        base_real_indent = base_indent + 1

        i = start_index
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue

            current_indent = self.calculate_indent_level(line)

            # Если отступ стал меньше или равен базовому отступу (не включая увеличение для тела)
            if current_indent <= base_indent:
                return i

            i += 1

        return len(lines)

    def parse_while_loop(
        self, line: str, scope: dict, all_lines: list, current_index: int, indent: int
    ):
        """Парсит while цикл"""
        pattern = r"while\s+(.+?)\s*:"
        match = re.match(pattern, line)

        if not match:
            return current_index + 1

        condition = match.group(1).strip()

        # Парсим условие
        condition_ast = self.parse_condition(condition)

        # Находим тело цикла
        body_start = current_index + 1
        body_end = self.find_indented_block_end(all_lines, body_start, indent)

        # Создаем узел цикла с ПУСТЫМ телом
        loop_node = {
            "node": "while_loop",
            "content": line,
            "condition": condition_ast,
            "body_level": scope["level"] + 1,
            "body": [],  # Пока пустое
        }

        scope["graph"].append(loop_node)

        # НЕ создаем отдельный scope для тела цикла
        # Вместо этого парсим тело прямо в текущем scope
        # но сохраняем его отдельно для узла цикла

        # Сохраняем текущие значения
        saved_indent = self.current_indent
        self.current_indent = indent + 1

        # Создаем временный список для хранения тела цикла
        body_graph = []

        # Парсим тело цикла
        i = body_start
        while i < body_end:
            body_line = all_lines[i]
            if not body_line.strip():
                i += 1
                continue

            body_indent = self.calculate_indent_level(body_line)
            body_content = body_line.strip()

            # Парсим строку в текущем scope, но сохраняем результат отдельно
            current_graph_len = len(scope["graph"])
            i = self.parse_line(body_content, scope, all_lines, i, body_indent)

            # Извлекаем только что добавленные узлы в тело цикла
            if len(scope["graph"]) > current_graph_len:
                # Берем последние добавленные узлы
                new_nodes = scope["graph"][current_graph_len:]
                body_graph.extend(new_nodes)
                # Удаляем их из основного графа scope
                scope["graph"] = scope["graph"][:current_graph_len]

        # Добавляем собранное тело в узел цикла
        loop_node["body"] = body_graph

        # Восстанавливаем отступ
        self.current_indent = saved_indent

        return body_end

    def parse_for_loop(
        self, line: str, scope: dict, all_lines: list, current_index: int, indent: int
    ):
        """Парсит for цикл"""
        pattern = r"for\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+in\s+(.+?)\s*:"
        match = re.match(pattern, line)

        if not match:
            return current_index + 1

        loop_var, iterable_expr = match.groups()
        loop_var = loop_var.strip()
        iterable_expr = iterable_expr.strip()

        # Парсим итерируемое выражение
        iterable_ast = self.parse_iterable(iterable_expr)

        # Находим тело цикла
        body_start = current_index + 1
        body_end = self.find_indented_block_end(all_lines, body_start, indent)

        # Создаем узел цикла с ПУСТЫМ телом
        loop_node = {
            "node": "for_loop",
            "content": line,
            "loop_variable": loop_var,
            "iterable": iterable_ast,
            "body_level": scope["level"] + 1,
            "body": [],  # Пока пустое
        }

        # Добавляем узел цикла в граф текущего scope
        scope["graph"].append(loop_node)

        # Добавляем переменную цикла в таблицу символов текущего scope
        scope["symbol_table"].add_symbol(name=loop_var, key="var", var_type="int")
        if loop_var not in scope["local_variables"]:
            scope["local_variables"].append(loop_var)

        # Сохраняем текущие значения
        saved_indent = self.current_indent
        self.current_indent = indent + 1

        # Создаем временный список для хранения тела цикла
        body_graph = []

        # Парсим тело цикла
        i = body_start
        while i < body_end:
            body_line = all_lines[i]
            if not body_line.strip():
                i += 1
                continue

            body_indent = self.calculate_indent_level(body_line)
            body_content = body_line.strip()

            # Парсим строку в текущем scope, но сохраняем результат отдельно
            current_graph_len = len(scope["graph"])
            i = self.parse_line(body_content, scope, all_lines, i, body_indent)

            # Извлекаем только что добавленные узлы в тело цикла
            if len(scope["graph"]) > current_graph_len:
                # Берем последние добавленные узлы (после узла for_loop)
                new_nodes = scope["graph"][current_graph_len:]
                body_graph.extend(new_nodes)
                # Удаляем их из основного графа scope
                scope["graph"] = scope["graph"][:current_graph_len]

        # Добавляем собранное тело в узел цикла
        loop_node["body"] = body_graph

        # Восстанавливаем отступ
        self.current_indent = saved_indent

        return body_end

    def parse_print(self, line: str, scope: dict):
        """Парсит вызов функции print"""
        pattern = r"print\s*\((.*?)\)"
        match = re.match(pattern, line)

        if not match:
            return False

        args_str = match.group(1)

        # Разбираем аргументы
        args = []
        if args_str.strip():
            # Разделяем аргументы по запятым, но учитываем строки и вложенные вызовы
            current_arg = ""
            in_string = False
            string_char = None
            paren_depth = 0

            for char in args_str:
                if not in_string and char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_arg += char
                elif in_string and char == string_char and current_arg[-1] != "\\":
                    in_string = False
                    current_arg += char
                elif not in_string and char == "(":
                    paren_depth += 1
                    current_arg += char
                elif not in_string and char == ")":
                    paren_depth -= 1
                    current_arg += char
                elif not in_string and paren_depth == 0 and char == ",":
                    args.append(current_arg.strip())
                    current_arg = ""
                else:
                    current_arg += char

            if current_arg.strip():
                args.append(current_arg.strip())

        # Очищаем аргументы от лишних пробелов
        args = [arg.strip() for arg in args]

        operations = [{"type": "PRINT", "arguments": args}]

        # Собираем зависимости для валидации
        dependencies = []
        for arg in args:
            # Проверяем, является ли аргумент переменной (а не строкой или числом)
            if (
                arg
                and not arg.startswith('"')
                and not arg.endswith('"')
                and not arg.startswith("'")
                and not arg.endswith("'")
                and not arg.isdigit()
                and arg not in ["True", "False", "None"]
            ):
                # Извлекаем имя переменной (может быть сложным выражением)
                # Простая проверка: если аргумент - просто имя переменной
                if arg.isalpha():
                    dependencies.append(arg)
                else:
                    # Для сложных выражений извлекаем все переменные
                    var_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)"
                    vars_in_arg = re.findall(var_pattern, arg)
                    for var in vars_in_arg:
                        if (
                            var not in KEYS
                            and var not in DATA_TYPES
                            and var not in dependencies
                        ):
                            dependencies.append(var)

        scope["graph"].append(
            {
                "node": "print",
                "content": line,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def parse_function_arguments_to_ast(self, args_str: str) -> list:
        """Разбирает аргументы функции в AST"""
        if not args_str.strip():
            return []

        args = []
        current_arg = ""
        depth = 0  # Для скобок
        brace_depth = 0  # Для фигурных скобок
        bracket_depth = 0  # Для квадратных скобок
        in_string = False
        string_char = None

        i = 0
        while i < len(args_str):
            char = args_str[i]

            # Обработка строк
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
                current_arg += char
            elif in_string and char == string_char:
                # Проверяем экранирование
                if i > 0 and args_str[i - 1] == "\\":
                    current_arg += char
                else:
                    in_string = False
                    current_arg += char
            # Обработка скобок
            elif not in_string:
                if char == "(":
                    depth += 1
                    current_arg += char
                elif char == ")":
                    depth -= 1
                    current_arg += char
                elif char == "{":
                    brace_depth += 1
                    current_arg += char
                elif char == "}":
                    brace_depth -= 1
                    current_arg += char
                elif char == "[":
                    bracket_depth += 1
                    current_arg += char
                elif char == "]":
                    bracket_depth -= 1
                    current_arg += char
                elif (
                    char == ","
                    and depth == 0
                    and brace_depth == 0
                    and bracket_depth == 0
                ):
                    if current_arg.strip():
                        args.append(self.parse_expression_to_ast(current_arg.strip()))
                    current_arg = ""
                else:
                    current_arg += char
            else:
                current_arg += char

            i += 1

        # Последний аргумент
        if current_arg.strip():
            args.append(self.parse_expression_to_ast(current_arg.strip()))

        return args

    def extract_dependencies_from_ast(self, ast: dict) -> list:
        """Извлекает зависимости (используемые переменные) из AST"""
        dependencies = []

        def traverse(node):
            if not isinstance(node, dict):
                return

            node_type = node.get("type")

            if node_type == "variable":
                var_name = node.get("value")
                if var_name and var_name not in dependencies:
                    # Игнорируем строки в кавычках
                    if (
                        isinstance(var_name, str)
                        and not (var_name.startswith('"') and var_name.endswith('"'))
                        and not (var_name.startswith("'") and var_name.endswith("'"))
                        and var_name not in KEYS
                        and var_name not in DATA_TYPES
                        and var_name not in self.builtin_functions
                    ):
                        dependencies.append(var_name)

            elif node_type == "function_call":
                func_name = node.get("function")
                # Только пользовательские функции
                if func_name and func_name not in self.builtin_functions:
                    if func_name not in dependencies:
                        dependencies.append(func_name)

                for arg in node.get("arguments", []):
                    traverse(arg)

            elif node_type == "binary_operation":
                traverse(node.get("left"))
                traverse(node.get("right"))

            elif node_type == "unary_operation":
                traverse(node.get("operand"))

            elif node_type == "address_of":
                var_name = node.get("variable")
                if var_name and var_name not in dependencies:
                    dependencies.append(var_name)

            elif node_type == "dereference":
                pointer_name = node.get("pointer")
                if pointer_name and pointer_name not in dependencies:
                    dependencies.append(pointer_name)

            elif node_type == "list_literal":
                for item in node.get("items", []):
                    traverse(item)

            elif node_type == "dict_literal":
                for key, value in node.get("pairs", {}).items():
                    traverse(value)  # Ключи обычно литералы

            elif node_type == "set_literal":
                for item in node.get("items", []):
                    traverse(item)

            # Литералы НЕ добавляем в зависимости!
            # node_type == "literal" - пропускаем

        traverse(ast)
        return dependencies

    def parse_literal_to_ast(self, value: str) -> dict:
        """Парсит литералы в AST"""
        if value.startswith('"') and value.endswith('"'):
            return {"type": "literal", "value": value[1:-1], "data_type": "str"}
        elif value.startswith("'") and value.endswith("'"):
            return {"type": "literal", "value": value[1:-1], "data_type": "str"}
        elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return {"type": "literal", "value": int(value), "data_type": "int"}
        elif value == "True":
            return {"type": "literal", "value": True, "data_type": "bool"}
        elif value == "False":
            return {"type": "literal", "value": False, "data_type": "bool"}
        elif value == "None":
            return {"type": "literal", "value": None, "data_type": "None"}
        elif value == "null":
            return {"type": "literal", "value": "null", "data_type": "null"}
        elif value.startswith("&"):
            return {"type": "address_of", "variable": value[1:].strip(), "value": value}
        elif value.startswith("*"):
            return {"type": "dereference", "pointer": value[1:].strip(), "value": value}

        # Если это не литерал, пытаемся парсить как выражение
        return self.parse_expression_to_ast(value)

    def build_operations_from_ast(
        self, ast: dict, target: str, operations: list, dependencies: list, scope: dict
    ):
        """Строит операции из AST выражения"""

        if ast["type"] == "variable":
            operations.append({"type": "ASSIGN", "target": target, "value": ast})
            if ast["value"] not in dependencies:
                dependencies.append(ast["value"])

        elif ast["type"] == "literal":
            operations.append({"type": "ASSIGN", "target": target, "value": ast})

        elif ast["type"] == "binary_operation":
            # Создаем временные переменные для левой и правой частей
            left_temp = f"{target}_left"
            right_temp = f"{target}_right"

            # Рекурсивно обрабатываем левую часть
            self.build_operations_from_ast(
                ast["left"], left_temp, operations, dependencies, scope
            )

            # Рекурсивно обрабатываем правую часть
            self.build_operations_from_ast(
                ast["right"], right_temp, operations, dependencies, scope
            )

            # Добавляем бинарную операцию
            operations.append(
                {
                    "type": "BINARY_OPERATION",
                    "target": target,
                    "operator": ast["operator"],
                    "operator_symbol": ast["operator_symbol"],
                    "left": {"type": "variable", "value": left_temp},
                    "right": {"type": "variable", "value": right_temp},
                }
            )

        elif ast["type"] == "function_call":
            # Обрабатываем аргументы
            arg_operations = []
            for i, arg_ast in enumerate(ast["arguments"]):
                arg_temp = f"{target}_arg_{i}"
                self.build_operations_from_ast(
                    arg_ast, arg_temp, arg_operations, dependencies, scope
                )

            # Добавляем операции аргументов
            operations.extend(arg_operations)

            # Добавляем вызов функции
            arg_values = [
                {"type": "variable", "value": f"{target}_arg_{i}"}
                for i in range(len(ast["arguments"]))
            ]

            operations.append(
                {
                    "type": "FUNCTION_CALL_ASSIGN",
                    "target": target,
                    "function": ast["function"],
                    "arguments": arg_values,
                }
            )

        elif ast["type"] == "dereference":
            operations.append(
                {
                    "type": "READ_POINTER",
                    "target": target,
                    "from": ast["pointer"],
                    "operation": "*",
                    "value": ast,
                }
            )
            if ast["pointer"] not in dependencies:
                dependencies.append(ast["pointer"])

    def find_symbol_recursive(self, current_scope, target_name, visited=None):
        """Рекурсивно ищет символ в текущем и родительских scope'ах"""
        if visited is None:
            visited = set()

        # Проверяем, не посещали ли мы уже этот scope
        scope_id = id(current_scope)
        if scope_id in visited:
            return None
        visited.add(scope_id)

        # Ищем символ в текущем scope
        symbol = current_scope["symbol_table"].get_symbol(target_name)
        if symbol:
            return symbol, current_scope

        # Если не нашли и есть родительский scope, ищем там
        if "parent_scope" in current_scope:
            parent_level = current_scope["parent_scope"]
            # Ищем scope с нужным уровнем
            for parent in self.scopes:
                if parent["level"] == parent_level:
                    result = self.find_symbol_recursive(parent, target_name, visited)
                    if result:
                        return result

        return None

    def parse_list_literal(self, value: str) -> dict:
        """Парсит литерал списка: [1, 2, 3]"""
        if not (value.startswith("[") and value.endswith("]")):
            return {"type": "unknown", "value": value}

        items_str = value[1:-1].strip()
        items = []

        if items_str:
            current_item = ""
            depth = 0
            in_string = False
            string_char = None

            i = 0
            while i < len(items_str):
                char = items_str[i]

                if not in_string and char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_item += char
                elif in_string and char == string_char:
                    if i > 0 and items_str[i - 1] == "\\":
                        current_item += char
                    else:
                        in_string = False
                        current_item += char
                elif not in_string and char == "[":
                    depth += 1
                    current_item += char
                elif not in_string and char == "]":
                    depth -= 1
                    current_item += char
                elif not in_string and char == "{":
                    depth += 1
                    current_item += char
                elif not in_string and char == "}":
                    depth -= 1
                    current_item += char
                elif not in_string and char == "(":
                    depth += 1
                    current_item += char
                elif not in_string and char == ")":
                    depth -= 1
                    current_item += char
                elif not in_string and depth == 0 and char == ",":
                    if current_item.strip():
                        items.append(self.parse_expression_to_ast(current_item.strip()))
                    current_item = ""
                else:
                    current_item += char

                i += 1

            if current_item.strip():
                items.append(self.parse_expression_to_ast(current_item.strip()))

        return {"type": "list_literal", "items": items, "length": len(items)}

    def parse_dict_literal(self, value: str) -> dict:
        """Парсит литерал словаря: {"key": "value", "num": 42}"""
        if not (value.startswith("{") and value.endswith("}")):
            return {"type": "unknown", "value": value}

        content = value[1:-1].strip()
        pairs = {}

        if content:
            current_key = ""
            current_value = ""
            parsing_key = True
            depth = 0
            in_string = False
            string_char = None

            i = 0
            while i < len(content):
                char = content[i]

                if not in_string and char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    if parsing_key:
                        current_key += char
                    else:
                        current_value += char
                elif in_string and char == string_char:
                    # Проверяем экранирование
                    if i > 0 and content[i - 1] == "\\":
                        if parsing_key:
                            current_key += char
                        else:
                            current_value += char
                    else:
                        in_string = False
                        if parsing_key:
                            current_key += char
                        else:
                            current_value += char
                elif not in_string and char == ":":
                    if parsing_key and depth == 0:
                        parsing_key = False
                        # Парсим ключ как AST
                        key_ast = self.parse_expression_to_ast(current_key.strip())
                        current_key = key_ast  # Сохраняем AST ключа
                        current_value = ""  # Начинаем собирать значение
                    elif not parsing_key:
                        current_value += char
                elif not in_string and char == "," and depth == 0:
                    if not parsing_key:
                        # Парсим значение как AST
                        value_ast = self.parse_expression_to_ast(current_value.strip())

                        # Ключ должен быть хешируемым (строковый литерал)
                        if (
                            isinstance(current_key, dict)
                            and current_key.get("type") == "literal"
                        ):
                            key_value = current_key.get("value", "")
                            pairs[key_value] = value_ast
                        elif isinstance(current_key, str):
                            # Если ключ еще строка, парсим его
                            key_ast = self.parse_expression_to_ast(current_key.strip())
                            if key_ast.get("type") == "literal":
                                pairs[key_ast.get("value", "")] = value_ast
                            else:
                                # Не литерал - используем строковое представление
                                pairs[str(current_key)] = value_ast

                        # Сбрасываем для следующей пары
                        current_key = ""
                        current_value = ""
                        parsing_key = True
                elif not in_string and char in ["[", "{", "("]:
                    depth += 1
                    if parsing_key:
                        current_key += char
                    else:
                        current_value += char
                elif not in_string and char in ["]", "}", ")"]:
                    depth -= 1
                    if parsing_key:
                        current_key += char
                    else:
                        current_value += char
                else:
                    if parsing_key:
                        current_key += char
                    else:
                        current_value += char

                i += 1

            # Последняя пара
            if current_key and not parsing_key:
                value_ast = self.parse_expression_to_ast(current_value.strip())

                # Обработка ключа
                if (
                    isinstance(current_key, dict)
                    and current_key.get("type") == "literal"
                ):
                    key_value = current_key.get("value", "")
                    pairs[key_value] = value_ast
                elif isinstance(current_key, str):
                    key_ast = self.parse_expression_to_ast(current_key.strip())
                    if key_ast.get("type") == "literal":
                        pairs[key_ast.get("value", "")] = value_ast
                    else:
                        pairs[str(current_key)] = value_ast

        return {"type": "dict_literal", "pairs": pairs, "size": len(pairs)}

    def parse_set_literal(self, value: str) -> dict:
        """Парсит литерал множества: {1, 2, 3}"""
        if not (value.startswith("{") and value.endswith("}") and ":" not in value):
            return {"type": "unknown", "value": value}

        items_str = value[1:-1].strip()
        items = []
        seen_values = set()  # Для уникальности

        if items_str:
            current_item = ""
            depth = 0
            in_string = False
            string_char = None

            i = 0
            while i < len(items_str):
                char = items_str[i]

                if not in_string and char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_item += char
                elif in_string and char == string_char:
                    if i > 0 and items_str[i - 1] == "\\":
                        current_item += char
                    else:
                        in_string = False
                        current_item += char
                elif not in_string and char in ["[", "{", "("]:
                    depth += 1
                    current_item += char
                elif not in_string and char in ["]", "}", ")"]:
                    depth -= 1
                    current_item += char
                elif not in_string and depth == 0 and char == ",":
                    if current_item.strip():
                        item_ast = self.parse_expression_to_ast(current_item.strip())
                        # Проверяем уникальность по строковому представлению
                        item_str = json.dumps(item_ast, sort_keys=True)
                        if item_str not in seen_values:
                            items.append(item_ast)
                            seen_values.add(item_str)
                    current_item = ""
                else:
                    current_item += char

                i += 1

            if current_item.strip():
                item_ast = self.parse_expression_to_ast(current_item.strip())
                item_str = json.dumps(item_ast, sort_keys=True)
                if item_str not in seen_values:
                    items.append(item_ast)

        return {"type": "set_literal", "items": items, "size": len(items)}

    def parse_if_statement(
        self, line: str, scope: dict, all_lines: list, current_index: int, indent: int
    ):
        """Парсит if-elif-else конструкцию - РАБОЧАЯ ВЕРСИЯ без бесконечного цикла"""
        pattern = r"if\s+(.+?)\s*:"
        match = re.match(pattern, line)

        if not match:
            return current_index + 1

        condition = match.group(1).strip()
        condition_ast = self.parse_expression_to_ast(condition)

        # Создаем узел if (пока НЕ добавляем в граф)
        if_node = {
            "node": "if_statement",
            "content": line,
            "condition": condition_ast,
            "condition_ast": condition_ast,
            "body_level": scope["level"] + 1,
            "body": [],
            "elif_blocks": [],
            "else_block": None,
        }

        # Начинаем парсинг с текущей строки
        i = current_index

        # Парсим тело if
        body_start = i + 1
        body_end = self.find_indented_block_end(all_lines, body_start, indent)

        # Сохраняем оригинальный граф
        original_graph_len = len(scope["graph"])

        # Парсим тело if
        saved_indent = self.current_indent
        self.current_indent = indent + 1

        body_i = body_start
        while body_i < body_end:
            body_line = all_lines[body_i]
            if not body_line.strip():
                body_i += 1
                continue

            body_indent = self.calculate_indent_level(body_line)
            body_content = body_line.strip()

            # Парсим строку тела if
            body_i = self.parse_line(
                body_content, scope, all_lines, body_i, body_indent
            )

        # Извлекаем узлы тела if
        if len(scope["graph"]) > original_graph_len:
            if_node["body"] = scope["graph"][original_graph_len:]
            # Удаляем эти узлы из основного графа
            scope["graph"] = scope["graph"][:original_graph_len]

        # Теперь i указывает на строку ПОСЛЕ тела if
        i = body_end

        # Парсим elif блоки (если есть)
        while i < len(all_lines):
            current_line = all_lines[i]

            if not current_line.strip():
                i += 1
                continue

            current_line_indent = self.calculate_indent_level(current_line)
            current_line_content = current_line.strip()

            # Проверяем, что это на том же уровне, что и if
            if current_line_indent != indent:
                # Не тот же уровень - выходим
                break

            # Проверяем elif
            if current_line_content.startswith("elif"):
                # Парсим условие elif
                elif_pattern = r"elif\s+(.+?)\s*:"
                elif_match = re.match(elif_pattern, current_line_content)

                if not elif_match:
                    i += 1
                    continue

                elif_condition = elif_match.group(1).strip()
                elif_condition_ast = self.parse_expression_to_ast(elif_condition)

                # Создаем блок elif
                elif_block = {
                    "node": "elif_statement",
                    "content": current_line_content,
                    "condition": elif_condition_ast,
                    "condition_ast": elif_condition_ast,
                    "body_level": scope["level"] + 1,
                    "body": [],
                }

                if_node["elif_blocks"].append(elif_block)

                # Парсим тело elif
                elif_body_start = i + 1
                elif_body_end = self.find_indented_block_end(
                    all_lines, elif_body_start, indent
                )

                # Сохраняем текущую длину графа
                current_graph_len = len(scope["graph"])

                # Парсим тело elif
                self.current_indent = indent + 1

                elif_body_i = elif_body_start
                while elif_body_i < elif_body_end:
                    elif_body_line = all_lines[elif_body_i]
                    if not elif_body_line.strip():
                        elif_body_i += 1
                        continue

                    elif_body_indent = self.calculate_indent_level(elif_body_line)
                    elif_body_content = elif_body_line.strip()

                    # Парсим строку тела elif
                    elif_body_i = self.parse_line(
                        elif_body_content,
                        scope,
                        all_lines,
                        elif_body_i,
                        elif_body_indent,
                    )

                # Извлекаем узлы тела elif
                if len(scope["graph"]) > current_graph_len:
                    elif_block["body"] = scope["graph"][current_graph_len:]
                    # Удаляем эти узлы из основного графа
                    scope["graph"] = scope["graph"][:current_graph_len]

                # Переходим к строке после тела elif
                i = elif_body_end

            # Проверяем else
            elif current_line_content == "else:":
                # Создаем блок else
                else_block = {
                    "node": "else_statement",
                    "content": current_line_content,
                    "body_level": scope["level"] + 1,
                    "body": [],
                }

                if_node["else_block"] = else_block

                # Парсим тело else
                else_body_start = i + 1
                else_body_end = self.find_indented_block_end(
                    all_lines, else_body_start, indent
                )

                # Сохраняем текущую длину графа
                current_graph_len = len(scope["graph"])

                # Парсим тело else
                self.current_indent = indent + 1

                else_body_i = else_body_start
                while else_body_i < else_body_end:
                    else_body_line = all_lines[else_body_i]
                    if not else_body_line.strip():
                        else_body_i += 1
                        continue

                    else_body_indent = self.calculate_indent_level(else_body_line)
                    else_body_content = else_body_line.strip()

                    # Парсим строку тела else
                    else_body_i = self.parse_line(
                        else_body_content,
                        scope,
                        all_lines,
                        else_body_i,
                        else_body_indent,
                    )

                # Извлекаем узлы тела else
                if len(scope["graph"]) > current_graph_len:
                    else_block["body"] = scope["graph"][current_graph_len:]
                    # Удаляем эти узлы из основного графа
                    scope["graph"] = scope["graph"][:current_graph_len]

                # Переходим к строке после тела else
                i = else_body_end
                break  # После else заканчиваем

            else:
                # Не elif и не else - выходим
                break

        # Восстанавливаем отступ
        self.current_indent = saved_indent

        # Теперь добавляем узел if в граф scope
        scope["graph"].append(if_node)

        return i

    def parse_elif_block(
        self,
        line: str,
        scope: dict,
        all_lines: list,
        current_index: int,
        base_indent: int,
        if_node: dict,
    ):
        """Парсит блок elif"""
        pattern = r"elif\s+(.+?)\s*:"
        match = re.match(pattern, line)

        if not match:
            return current_index + 1

        condition = match.group(1).strip()

        # Парсим условие в AST
        condition_ast = self.parse_expression_to_ast(condition)

        # Находим тело elif
        body_start = current_index + 1
        body_end = self.find_indented_block_end(all_lines, body_start, base_indent)

        # Создаем блок elif
        elif_block = {
            "node": "elif_statement",
            "content": line,
            "condition": condition_ast,  # AST вместо простого условия
            "condition_ast": condition_ast,  # Дублируем для совместимости
            "body_level": scope["level"] + 1,
            "body": [],  # Пока пустое
        }

        if_node["elif_blocks"].append(elif_block)

        # Сохраняем текущие значения
        saved_indent = self.current_indent
        self.current_indent = base_indent + 1

        # Создаем временный список для хранения тела elif
        body_graph = []

        # Парсим тело elif
        i = body_start
        while i < body_end:
            body_line = all_lines[i]
            if not body_line.strip():
                i += 1
                continue

            body_indent = self.calculate_indent_level(body_line)
            body_content = body_line.strip()

            # Проверяем, является ли строка elif или else
            if body_indent == base_indent:  # Та же глубина отступа, что и if
                if body_content.startswith("elif"):
                    # Сохраняем текущее тело elif
                    elif_block["body"] = body_graph
                    body_graph = []

                    # Рекурсивно парсим следующий elif
                    i = self.parse_elif_block(
                        body_content, scope, all_lines, i, base_indent, if_node
                    )
                    continue
                elif body_content.startswith("else"):
                    # Сохраняем текущее тело elif
                    elif_block["body"] = body_graph
                    body_graph = []

                    # Парсим else блок
                    i = self.parse_else_block(
                        body_content, scope, all_lines, i, base_indent, if_node
                    )
                    break

            # Парсим строку в текущем scope, но сохраняем результат отдельно
            current_graph_len = len(scope["graph"])
            i = self.parse_line(body_content, scope, all_lines, i, body_indent)

            # Извлекаем только что добавленные узлы в тело elif
            if len(scope["graph"]) > current_graph_len:
                new_nodes = scope["graph"][current_graph_len:]
                body_graph.extend(new_nodes)
                scope["graph"] = scope["graph"][:current_graph_len]

        # Сохраняем тело elif
        elif_block["body"] = body_graph

        # Восстанавливаем отступ
        self.current_indent = saved_indent

        return i

    def parse_else_block(
        self,
        line: str,
        scope: dict,
        all_lines: list,
        current_index: int,
        base_indent: int,
        if_node: dict,
    ):
        """Парсит блок else"""
        pattern = r"else\s*:"
        match = re.match(pattern, line)

        if not match:
            return current_index + 1

        # Находим тело else
        body_start = current_index + 1
        body_end = self.find_indented_block_end(all_lines, body_start, base_indent)

        # Создаем блок else
        else_block = {
            "node": "else_statement",
            "content": line,
            "body_level": scope["level"] + 1,
            "body": [],  # Пока пустое
        }

        if_node["else_block"] = else_block

        # Сохраняем текущие значения
        saved_indent = self.current_indent
        self.current_indent = base_indent + 1

        # Создаем временный список для хранения тела else
        body_graph = []

        # Парсим тело else
        i = body_start
        while i < body_end:
            body_line = all_lines[i]
            if not body_line.strip():
                i += 1
                continue

            body_indent = self.calculate_indent_level(body_line)
            body_content = body_line.strip()

            # Парсим строку в текущем scope, но сохраняем результат отдельно
            current_graph_len = len(scope["graph"])
            i = self.parse_line(body_content, scope, all_lines, i, body_indent)

            # Извлекаем только что добавленные узлы в тело else
            if len(scope["graph"]) > current_graph_len:
                new_nodes = scope["graph"][current_graph_len:]
                body_graph.extend(new_nodes)
                scope["graph"] = scope["graph"][:current_graph_len]

        # Сохраняем тело else
        else_block["body"] = body_graph

        # Восстанавливаем отступ
        self.current_indent = saved_indent

        return i

    def parse_nested_if(
        self, line: str, scope: dict, all_lines: list, current_index: int, indent: int
    ):
        """Парсит вложенные if внутри других блоков (while, for, других if)"""
        # Используем ту же логику, что и для обычного if
        return self.parse_if_statement(line, scope, all_lines, current_index, indent)

    def clean_value(self, value: str):
        """Очищает значение от лишних пробелов, но для сложных выражений возвращает AST"""
        value = value.strip()

        if not value:
            return {"type": "empty", "value": ""}

        ast = self.parse_literal_to_ast(value)
        if ast["type"] != "literal" or ast["data_type"] not in [
            "int",
            "str",
            "bool",
            "None",
            "null",
        ]:
            # Если это не простой литерал, парсим как выражение
            ast = self.parse_expression_to_ast(value)

        return ast
