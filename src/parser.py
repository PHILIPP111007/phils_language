import re
import os
import json

from src.modules.imports import CImportProcessor, ImportProcessor
from src.modules.constants import KEYS, DATA_TYPES, METHOD_DECORATORS
from src.modules.symbol_table import SymbolTable


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
            "input",  # ДОБАВЛЕНО
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
        """Основной метод парсинга строки с поддержкой всех конструкций"""
        line = line.strip()
        if not line:
            return current_index + 1

        # Определяем реальный отступ текущей строки
        actual_indent = (
            self.calculate_indent_level(all_lines[current_index])
            if current_index < len(all_lines)
            else 0
        )

        # Обрабатываем изменение отступа
        self.handle_indent_change(actual_indent)

        # Получаем текущую область видимости для данного отступа
        current_scope = self.get_current_scope_for_indent(actual_indent)
        if not current_scope:
            current_scope = scope

        # ========== СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ КОНСТРУКТОРА ==========
        # Если мы в конструкторе класса и строка начинается с "var self."
        if current_scope.get("type") == "constructor" and line.startswith("self."):
            # Парсим инициализацию атрибута в конструкторе
            pattern = r"self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
            match = re.match(pattern, line)

            if match:
                # Это инициализация атрибута
                result = self.parse_class_attribute_initialization(line, current_scope)
                return current_index + 1 if result else current_index + 1

            # result = self.parse_class_attribute_initialization(line, current_scope)
            # if result:
            #     return current_index + 1

        # ========== ОБРАБОТКА ДЕКОРАТОРОВ И СПЕЦИАЛЬНЫХ СИМВОЛОВ ==========

        # Декораторы методов
        if line in METHOD_DECORATORS:
            # Декораторы обрабатываются в parse_class_method_declaration
            return current_index + 1

        # C-вызовы (@func())
        if line.startswith("@"):
            parsed = self.parse_c_call(line, current_scope)
            return current_index + 1 if parsed else current_index + 1

        # ========== ОБРАБОТКА КЛЮЧЕВЫХ СЛОВ ==========

        for key in KEYS:
            if line.startswith(key + " ") or line == key:
                if key == "const":
                    parsed = self.parse_const(line, current_scope)
                    return current_index + 1
                elif key == "var":
                    parsed = self.parse_var(line, current_scope)
                    return current_index + 1
                elif key == "def":
                    # Проверяем, не является ли это методом класса
                    if current_scope.get("type") in [
                        "class_body",
                        "class_method",
                        "static_method",
                        "classmethod",
                    ]:
                        # Метод класса уже обрабатывается в parse_class_declaration
                        return current_index + 1
                    else:
                        return self.parse_function_declaration(
                            line, current_scope, all_lines, current_index
                        )
                elif key == "class":
                    return self.parse_class_declaration(
                        line, current_scope, all_lines, current_index
                    )
                elif key == "del":
                    parsed = self.parse_delete(line, current_scope)
                    return current_index + 1
                elif key == "del_pointer":
                    parsed = self.parse_del_pointer(line, current_scope)
                    return current_index + 1
                elif key == "return":
                    parsed = self.parse_return(line, current_scope)
                    return current_index + 1
                elif key == "while":
                    return self.parse_while_loop(
                        line, current_scope, all_lines, current_index, actual_indent
                    )
                elif key == "for":
                    return self.parse_for_loop(
                        line, current_scope, all_lines, current_index, actual_indent
                    )
                elif key == "if":
                    # Проверяем, не вложен ли if в другой блок
                    if current_scope.get("type") in [
                        "while_loop_body",
                        "for_loop_body",
                        "if_body",
                        "elif_body",
                        "else_body",
                    ]:
                        return self.parse_nested_if(
                            line, current_scope, all_lines, current_index, actual_indent
                        )
                    else:
                        return self.parse_if_statement(
                            line, current_scope, all_lines, current_index, actual_indent
                        )
                elif key == "break":
                    parsed = self.parse_break(line, current_scope)
                    return current_index + 1
                elif key == "continue":
                    parsed = self.parse_continue(line, current_scope)
                    return current_index + 1

        # ========== ОБРАБОТКА C ИМПОРТОВ ==========

        if line.startswith("cimport "):
            return self.parse_cimport(line, current_scope, all_lines, current_index)

        # ========== ОБРАБОТКА PASS ==========

        if line == "pass":
            current_scope["graph"].append(
                {"node": "pass", "content": "pass", "operations": [{"type": "PASS"}]}
            )
            return current_index + 1

        # ========== ОБРАБОТКА ВЫЗОВОВ МЕТОДОВ И ФУНКЦИЙ ==========

        # 1. Вызов метода объекта: obj.method(args)
        object_method_pattern = (
            r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$"
        )
        object_method_match = re.match(object_method_pattern, line)

        # 2. Статический вызов метода: Class.method(args)
        static_method_pattern = (
            r"^([A-Z][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$"
        )
        static_method_match = re.match(static_method_pattern, line)

        # 3. Обычный вызов функции: func(args)
        function_call_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$"
        function_call_match = re.match(function_call_pattern, line)

        # 4. Присваивание результата вызова: var x: type = func(args)
        func_assignment_pattern = r"^var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$"
        func_assignment_match = re.match(func_assignment_pattern, line)

        # 5. Присваивание с созданием объекта: var x: Class = Class(args)
        obj_creation_pattern = r"^var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([A-Z][a-zA-Z0-9_]*)\s*=\s*([A-Z][a-zA-Z0-9_]*)\s*\((.*)\)$"
        obj_creation_match = re.match(obj_creation_pattern, line)

        # Приоритет проверок:
        # 1. Создание объекта с присваиванием
        if obj_creation_match:
            var_name, var_type, class_name, args_str = obj_creation_match.groups()
            if var_type == class_name:  # Проверяем соответствие типов
                parsed = self.parse_object_creation_assignment(
                    line, current_scope, var_name, class_name, args_str
                )
                return current_index + 1

        # 2. Присваивание результата вызова функции
        if func_assignment_match:
            var_name, var_type, func_name, args_str = func_assignment_match.groups()
            # Создаем выражение для вызова функции
            func_call_expr = f"{func_name}({args_str})"
            # Парсим как обычное присваивание с выражением
            modified_line = f"var {var_name}: {var_type} = {func_call_expr}"
            parsed = self.parse_var(modified_line, current_scope)
            return current_index + 1

        # 3. Вызов статического метода
        if static_method_match:
            class_name, method_name, args_str = static_method_match.groups()
            # Упрощенная проверка - начинается с заглавной буквы
            if class_name and class_name[0].isupper():
                parsed = self.parse_static_method_call_node(
                    line, current_scope, class_name, method_name, args_str
                )
                return current_index + 1

        # 4. Вызов метода объекта
        if object_method_match:
            obj_name, method_name, args_str = object_method_match.groups()
            parsed = self.parse_object_method_call_node(
                line, current_scope, obj_name, method_name, args_str
            )
            return current_index + 1

        # 5. Обычный вызов функции
        if function_call_match:
            func_name, args_str = function_call_match.groups()
            # Проверяем, не является ли это вызовом конструктора без присваивания
            if func_name and func_name[0].isupper():
                # Это возможный вызов конструктора
                parsed = self.parse_constructor_call(
                    line, current_scope, func_name, args_str
                )
                return current_index + 1
            else:
                parsed = self.parse_function_call(line, current_scope)
                return current_index + 1

        # ========== ОБРАБОТКА ВСТРОЕННЫХ ФУНКЦИЙ ==========

        # Проверяем встроенные функции (print, len, str, int, bool, range)
        for func_name in self.builtin_functions:
            if line.startswith(f"{func_name}("):
                parsed = self.parse_builtin_function_call(
                    line, current_scope, func_name
                )
                return current_index + 1

        # ========== ОБРАБОТКА ПРИСВАИВАНИЙ ==========

        # Проверяем различные виды присваиваний

        # 1. Доступ к атрибуту с присваиванием: obj.attr = value
        attr_assignment_pattern = (
            r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$"
        )
        attr_assignment_match = re.match(attr_assignment_pattern, line)

        if attr_assignment_match:
            obj_name, attr_name, value = attr_assignment_match.groups()
            parsed = self.parse_attribute_assignment(
                line, current_scope, obj_name, attr_name, value
            )
            return current_index + 1

        # 2. Обычное присваивание: var = value
        simple_assignment_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$"
        simple_assignment_match = re.match(simple_assignment_pattern, line)

        if simple_assignment_match:
            var_name, value = simple_assignment_match.groups()

            # Проверяем, не является ли это разыменованием указателя (*p = value)
            if var_name.startswith("*"):
                parsed = self.parse_pointer_dereference_assignment(
                    line, current_scope, var_name, value
                )
                return current_index + 1

            # Проверяем, не является ли значение разыменованием (*p)
            if value.strip().startswith("*"):
                parsed = self.parse_pointer_to_variable_assignment(
                    line, current_scope, var_name, value
                )
                return current_index + 1

            # Обычное присваивание
            parsed = self.parse_assignment(line, current_scope)
            return current_index + 1

        # 3. Составные операции присваивания: var += value
        augmented_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*(\+=|-=|\*=|/=|//=|\%=|\*\*=|>>=|<<=|&=|\|=|\^=)\s*(.+)$"
        augmented_match = re.match(augmented_pattern, line)

        if augmented_match:
            var_name, operator, value = augmented_match.groups()
            parsed = self.parse_augmented_assignment(line, current_scope)
            return current_index + 1

        # ========== ОБРАБОТКА ДОСТУПА К АТРИБУТАМ ==========

        # Доступ к атрибуту без вызова: obj.attr
        attr_access_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$"
        attr_access_match = re.match(attr_access_pattern, line)

        if attr_access_match:
            # В изолированном виде это выражение не имеет смысла,
            # но может быть частью более сложного выражения
            # Парсим как выражение
            expression_ast = self.parse_expression_to_ast(line)
            current_scope["graph"].append(
                {
                    "node": "expression",
                    "content": line,
                    "expression_ast": expression_ast,
                    "operations": [
                        {"type": "EXPRESSION_EVAL", "expression": expression_ast}
                    ],
                    "dependencies": self.extract_dependencies_from_ast(expression_ast),
                }
            )
            return current_index + 1

        # ========== ОБРАБОТКА ВЫРАЖЕНИЙ ==========

        # Если ничего не распознано, пробуем парсить как выражение
        expression_ast = self.parse_expression_to_ast(line)
        if expression_ast["type"] not in ["unknown", "empty"]:
            current_scope["graph"].append(
                {
                    "node": "expression",
                    "content": line,
                    "expression_ast": expression_ast,
                    "operations": [
                        {"type": "EXPRESSION_EVAL", "expression": expression_ast}
                    ],
                    "dependencies": self.extract_dependencies_from_ast(expression_ast),
                }
            )
            return current_index + 1

        # ========== НЕРАСПОЗНАННАЯ СТРОКА ==========

        # Если строка не распознана, создаем узел с ошибкой
        print(f"Warning: Не удалось распарсить строку: {line}")
        current_scope["graph"].append(
            {
                "node": "unparsed",
                "content": line,
                "operations": [{"type": "UNPARSED", "content": line}],
                "dependencies": [],
            }
        )

        return current_index + 1

    def parse_object_creation_assignment(
        self, line: str, scope: dict, var_name: str, class_name: str, args_str: str
    ) -> bool:
        """Парсит создание объекта с присваиванием: var x: Class = Class(args)"""
        # Парсим аргументы
        args = []
        if args_str.strip():
            args = self.parse_function_arguments_to_ast(args_str)

        # Проверяем существование класса (упрощенная проверка)
        class_symbol = scope["symbol_table"].get_symbol(class_name)
        is_class = class_symbol and class_symbol.get("key") == "class"

        # Добавляем переменную в таблицу символов
        scope["symbol_table"].add_symbol(name=var_name, key="var", var_type=class_name)

        if var_name not in scope["local_variables"]:
            scope["local_variables"].append(var_name)

        # Создаем AST для вызова конструктора
        constructor_ast = {
            "type": "constructor_call",
            "class_name": class_name,
            "arguments": args,
        }

        # Создаем операции
        operations = [
            {"type": "NEW_VAR", "target": var_name, "var_type": class_name},
            {
                "type": "CONSTRUCTOR_CALL",
                "class_name": class_name,
                "target": var_name,
                "arguments": args,
            },
        ]

        # Собираем зависимости
        dependencies = []
        for arg in args:
            deps = self.extract_dependencies_from_ast(arg)
            dependencies.extend(deps)

        # Создаем узел
        scope["graph"].append(
            {
                "node": "object_creation",
                "content": line,
                "symbols": [var_name],
                "var_name": var_name,
                "var_type": class_name,
                "class_name": class_name,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
                "expression_ast": constructor_ast,
            }
        )

        return True

    def parse_constructor_call(
        self, line: str, scope: dict, class_name: str, args_str: str
    ) -> bool:
        """Парсит вызов конструктора без присваивания: Class(args)"""
        # Парсим аргументы
        args = []
        if args_str.strip():
            args = self.parse_function_arguments_to_ast(args_str)

        operations = [
            {"type": "CONSTRUCTOR_CALL", "class_name": class_name, "arguments": args}
        ]

        # Собираем зависимости
        dependencies = []
        for arg in args:
            deps = self.extract_dependencies_from_ast(arg)
            dependencies.extend(deps)

        scope["graph"].append(
            {
                "node": "constructor_call",
                "content": line,
                "class_name": class_name,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def parse_attribute_assignment(
        self, line: str, scope: dict, obj_name: str, attr_name: str, value: str
    ) -> bool:
        """Парсит присваивание атрибуту: obj.attr = value"""
        # Парсим значение
        value_ast = self.parse_expression_to_ast(value)

        # Проверяем существование объекта
        obj_symbol = scope["symbol_table"].get_symbol(obj_name)
        if not obj_symbol:
            print(f"Error: Объект '{obj_name}' не определен")
            return False

        operations = [
            {
                "type": "ATTRIBUTE_ASSIGN",
                "object": obj_name,
                "attribute": attr_name,
                "value": value_ast,
            }
        ]

        # Собираем зависимости
        dependencies = [obj_name]
        deps = self.extract_dependencies_from_ast(value_ast)
        dependencies.extend(deps)

        scope["graph"].append(
            {
                "node": "attribute_assignment",
                "content": line,
                "object": obj_name,
                "attribute": attr_name,
                "value": value_ast,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def parse_pointer_dereference_assignment(
        self, line: str, scope: dict, pointer_expr: str, value: str
    ) -> bool:
        """Парсит присваивание через разыменование указателя: *p = value"""
        # Извлекаем имя указателя
        pointer_name = pointer_expr[1:].strip()

        # Парсим значение
        value_ast = self.parse_expression_to_ast(value)

        # Проверяем существование указателя
        pointer_symbol = scope["symbol_table"].get_symbol(pointer_name)
        if not pointer_symbol:
            print(f"Error: Указатель '{pointer_name}' не определен")
            return False

        if not pointer_symbol["type"].startswith("*"):
            print(f"Error: '{pointer_name}' не является указателем")
            return False

        operations = [
            {
                "type": "WRITE_POINTER",
                "pointer": pointer_name,
                "value": value_ast,
                "operation": "*=",
            }
        ]

        # Собираем зависимости
        dependencies = [pointer_name]
        deps = self.extract_dependencies_from_ast(value_ast)
        dependencies.extend(deps)

        scope["graph"].append(
            {
                "node": "dereference_write",
                "content": line,
                "pointer": pointer_name,
                "value": value_ast,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def parse_pointer_to_variable_assignment(
        self, line: str, scope: dict, var_name: str, pointer_expr: str
    ) -> bool:
        """Парсит присваивание значения указателя переменной: x = *p"""
        # Извлекаем имя указателя
        pointer_name = pointer_expr[1:].strip()

        # Проверяем существование указателя
        pointer_symbol = scope["symbol_table"].get_symbol(pointer_name)
        if not pointer_symbol:
            print(f"Error: Указатель '{pointer_name}' не определен")
            return False

        if not pointer_symbol["type"].startswith("*"):
            print(f"Error: '{pointer_name}' не является указателем")
            return False

        # Проверяем существование переменной
        var_symbol = scope["symbol_table"].get_symbol(var_name)
        if not var_symbol:
            print(f"Error: Переменная '{var_name}' не определена")
            return False

        # Создаем AST для разыменования
        deref_ast = {"type": "dereference", "pointer": pointer_name}

        operations = [
            {
                "type": "READ_POINTER",
                "target": var_name,
                "from": pointer_name,
                "operation": "*",
                "value": deref_ast,
                "pointed_type": pointer_symbol["type"][1:],  # Убираем звездочку
            }
        ]

        # Обновляем значение переменной
        scope["symbol_table"].update_symbol(var_name, {"value": deref_ast})

        dependencies = [pointer_name]

        scope["graph"].append(
            {
                "node": "dereference_read",
                "content": line,
                "target": var_name,
                "pointer": pointer_name,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

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
        elif func_name == "input":  # ДОБАВЛЕНО
            return "str"  # input всегда возвращает строку
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

    def parse_break(self, line: str, scope: dict):
        """Парсит оператор break"""
        scope["graph"].append(
            {
                "node": "break",
                "content": line,
                "operations": [{"type": "BREAK"}],
            }
        )
        return True

    def parse_continue(self, line: str, scope: dict):
        """Парсит оператор continue"""
        scope["graph"].append(
            {
                "node": "continue",
                "content": line,
                "operations": [{"type": "CONTINUE"}],
            }
        )
        return True

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
        """Извлекает тип элементов из объявления типа списка, учитывая вложенность"""
        # Убираем "list[" в начале и "]" в конце
        if list_type.startswith("list[") and list_type.endswith("]"):
            inner = list_type[5:-1]  # Убираем "list[" и "]"

            # Теперь нужно найти баланс скобок
            balance = 0
            end_index = -1

            for i, char in enumerate(inner):
                if char == "[":
                    balance += 1
                elif char == "]":
                    balance -= 1
                    if balance < 0:
                        # Недопустимая строка
                        return "any"

                # Когда баланс становится 0, мы нашли конец
                if balance == 0:
                    end_index = i
                    break

            if end_index != -1:
                return inner[: end_index + 1]

        return "any"

    def find_equals_outside_brackets(self, s: str) -> int:
        """Находит позицию символа '=', которая не находится внутри скобок"""
        depth = 0
        in_string = False
        string_char = None

        for i, char in enumerate(s):
            # Обработка строк
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                # Проверяем экранирование
                if i == 0 or s[i - 1] != "\\":
                    in_string = False
            # Обработка скобок (только вне строк)
            elif not in_string:
                if char == "[":
                    depth += 1
                elif char == "]":
                    depth -= 1
                elif char == "=" and depth == 0:
                    return i

        return -1

    def extract_content_inside_brackets(
        self, s: str, prefix: str, closing_bracket: str
    ) -> str:
        """Извлекает содержимое внутри скобок, учитывая вложенность"""
        if not s.startswith(prefix):
            return ""

        content = s[len(prefix) :]
        depth = 0
        result = []

        for i, char in enumerate(content):
            if char == "[":
                depth += 1
                result.append(char)
            elif char == "]":
                if depth == 0:
                    # Нашли закрывающую скобку
                    return "".join(result)
                depth -= 1
                result.append(char)
            else:
                result.append(char)

        return "".join(result)

    def parse_var(self, line: str, scope: dict):
        """Парсит объявление переменной с поддержкой tuple и list"""
        # Упрощенный паттерн для захвата всей строки
        pattern = r"var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+)"
        match = re.match(pattern, line)

        if not match:
            return False

        name, type_and_value = match.groups()

        # Разделяем тип и значение - ищем первый "=", который не находится внутри скобок
        equals_pos = self.find_equals_outside_brackets(type_and_value)
        if equals_pos == -1:
            return False

        var_type_str = type_and_value[:equals_pos].strip()
        value_str = type_and_value[equals_pos + 1 :].strip()

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
        tuple_uniform_pattern = r"tuple\[([^\]]+)\]"
        tuple_uniform_match = re.match(tuple_uniform_pattern, var_type_str)

        if tuple_uniform_match:
            is_tuple_uniform = True
            element_type = tuple_uniform_match.group(1)
            print(f"DEBUG: Обнаружен tuple[{element_type}]")

        # Проверяем tuple[T1, T2, ...]
        elif var_type_str.startswith("tuple["):
            # Извлекаем содержимое скобок
            inner_content = self.extract_content_inside_brackets(
                var_type_str, "tuple[", "]"
            )
            if inner_content and "," in inner_content:
                is_tuple_fixed = True
                # Разделяем по запятым, но учитываем вложенные скобки
                tuple_element_types = []
                current_type = ""
                depth = 0

                for char in inner_content:
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
            # list[T] - может быть вложенным list[list[int]]
            inner_content = self.extract_content_inside_brackets(
                var_type_str, "list[", "]"
            )
            if inner_content:
                element_type = inner_content.strip()

                if value_ast.get("type") == "list_literal":
                    # Проверяем вложенность
                    items = value_ast.get("items", [])
                    is_nested = all(
                        item.get("type") == "list_literal" for item in items
                    )

                    operations.append(
                        {
                            "type": "CREATE_LIST",
                            "target": name,
                            "items": items,
                            "size": len(items),
                            "element_type": element_type,  # Сохраняем полный тип элемента
                            "is_pointer_array": True,
                            "is_nested": is_nested,  # Добавляем информацию о вложенности
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
        """Парсит выражение в AST (Abstract Syntax Tree) с поддержкой всех конструкций"""
        expression = expression.strip()

        # Если пустая строка
        if not expression:
            return {"type": "empty", "value": ""}

        # Убираем лишние пробелы, но сохраняем для строк
        if not self.is_string_literal(expression):
            expression = re.sub(r"\s+", " ", expression)

        # ========== 1. ПРОВЕРКА НА ЛИТЕРАЛЫ ==========

        # 1.1 Строковые литералы
        if (expression.startswith('"') and expression.endswith('"')) or (
            expression.startswith("'") and expression.endswith("'")
        ):
            if len(expression) > 1 and expression[0] == expression[-1]:
                # Проверяем экранирование
                content = expression[1:-1]
                # Заменяем экранированные кавычки
                content = content.replace('\\"', '"').replace("\\'", "'")
                return {"type": "literal", "value": content, "data_type": "str"}

        # 1.2 Числа с плавающей точкой
        float_patterns = [
            r"^-?\d+\.\d+$",  # 3.14
            r"^-?\d+\.\d+[eE][+-]?\d+$",  # 3.14e10
            r"^-?\d+[eE][+-]?\d+$",  # 3e10
        ]
        for pattern in float_patterns:
            if re.match(pattern, expression):
                try:
                    return {
                        "type": "literal",
                        "value": float(expression),
                        "data_type": "float",
                    }
                except ValueError:
                    pass

        # 1.3 Целые числа (десятичные, шестнадцатеричные, бинарные, восьмеричные)
        if re.match(r"^-?\d+$", expression):
            try:
                return {"type": "literal", "value": int(expression), "data_type": "int"}
            except ValueError:
                pass

        if re.match(r"^0[xX][0-9a-fA-F]+$", expression):
            try:
                return {
                    "type": "literal",
                    "value": int(expression, 16),
                    "data_type": "int",
                }
            except ValueError:
                pass

        if re.match(r"^0[bB][01]+$", expression):
            try:
                return {
                    "type": "literal",
                    "value": int(expression[2:], 2),
                    "data_type": "int",
                }
            except ValueError:
                pass

        if re.match(r"^0[oO]?[0-7]+$", expression):
            try:
                base = 8
                if expression.startswith("0o") or expression.startswith("0O"):
                    expression = expression[2:]
                elif expression.startswith("0") and len(expression) > 1:
                    expression = expression[1:]
                return {
                    "type": "literal",
                    "value": int(expression, base),
                    "data_type": "int",
                }
            except ValueError:
                pass

        # 1.4 Булевы значения и None
        if expression == "True":
            return {"type": "literal", "value": True, "data_type": "bool"}
        if expression == "False":
            return {"type": "literal", "value": False, "data_type": "bool"}
        if expression == "None":
            return {"type": "literal", "value": None, "data_type": "None"}
        if expression == "null":
            return {"type": "literal", "value": "null", "data_type": "null"}

        # ========== 2. КОМПЛЕКСНЫЕ ЛИТЕРАЛЫ ==========

        # 2.1 Литералы списков
        if expression.startswith("[") and expression.endswith("]"):
            return self.parse_list_literal(expression)

        # 2.2 Литералы кортежей
        if expression.startswith("(") and expression.endswith(")"):
            # Проверяем, действительно ли это кортеж или выражение в скобках
            inner = expression[1:-1].strip()
            if "," in inner or inner.endswith(","):
                return self.parse_tuple_literal(expression)
            # Иначе это выражение в скобках - рекурсивно парсим внутреннее выражение
            return self.parse_expression_to_ast(inner)

        # 2.3 Литералы словарей/множеств
        if expression.startswith("{") and expression.endswith("}"):
            content = expression[1:-1].strip()
            if self.is_dict_literal(content):
                return self.parse_dict_literal(expression)
            else:
                return self.parse_set_literal(expression)

        # ========== 3. ОПЕРАЦИИ С УКАЗАТЕЛЯМИ ==========

        # 3.1 Адрес переменной (&x)
        if expression.startswith("&"):
            rest = expression[1:].strip()
            # Проверяем, что это просто имя переменной
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", rest):
                return {"type": "address_of", "variable": rest, "operation": "&"}
            # Или более сложное выражение
            inner_ast = self.parse_expression_to_ast(rest)
            return {"type": "address_of", "expression": inner_ast, "operation": "&"}

        # 3.2 Разыменование указателя (*p)
        if expression.startswith("*"):
            rest = expression[1:].strip()
            # Проверяем, что это просто имя указателя
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", rest):
                return {"type": "dereference", "pointer": rest, "operation": "*"}
            # Или более сложное выражение
            inner_ast = self.parse_expression_to_ast(rest)
            return {"type": "dereference", "expression": inner_ast, "operation": "*"}

        # ========== 4. ВЫЗОВЫ ФУНКЦИЙ И МЕТОДОВ ==========

        # 4.1 Вызов метода объекта: obj.method(args)
        obj_method_pattern = (
            r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$"
        )
        obj_method_match = re.match(obj_method_pattern, expression)

        if obj_method_match:
            obj_name, method_name, args_str = obj_method_match.groups()
            args = []
            if args_str.strip():
                args = self.parse_function_arguments_to_ast(args_str)

            return {
                "type": "method_call",
                "object": obj_name,
                "method": method_name,
                "arguments": args,
            }

        # 4.2 Статический вызов метода: Class.method(args)
        static_method_pattern = (
            r"^([A-Z][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$"
        )
        static_method_match = re.match(static_method_pattern, expression)

        if static_method_match:
            class_name, method_name, args_str = static_method_match.groups()
            args = []
            if args_str.strip():
                args = self.parse_function_arguments_to_ast(args_str)

            return {
                "type": "static_method_call",
                "class_name": class_name,
                "method": method_name,
                "arguments": args,
            }

        # 4.3 Вызов конструктора: ClassName(args)
        constructor_pattern = r"^([A-Z][a-zA-Z0-9_]*)\s*\((.*)\)$"
        constructor_match = re.match(constructor_pattern, expression)

        if constructor_match:
            class_name, args_str = constructor_match.groups()
            args = []
            if args_str.strip():
                args = self.parse_function_arguments_to_ast(args_str)

            return {
                "type": "constructor_call",
                "class_name": class_name,
                "arguments": args,
            }

        # 4.4 Обычный вызов функции: func(args)
        func_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$"
        func_match = re.match(func_pattern, expression)

        if func_match:
            func_name, args_str = func_match.groups()
            args = []
            if args_str.strip():
                args = self.parse_function_arguments_to_ast(args_str)

            return {"type": "function_call", "function": func_name, "arguments": args}

        # ========== 5. ДОСТУП К АТРИБУТАМ И ИНДЕКСАЦИЯ ==========

        # 5.1 Доступ к атрибуту объекта: obj.attr
        attr_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$"
        attr_match = re.match(attr_pattern, expression)

        if attr_match:
            obj_name, attr_name = attr_match.groups()
            # Проверяем, что это не часть более сложного выражения
            # Простая проверка - нет операторов
            if not re.search(r"[+\-*/=<>!&|^%~]", expression):
                return {
                    "type": "attribute_access",
                    "object": obj_name,
                    "attribute": attr_name,
                }

        # 5.2 Индексация: obj[index] или obj[start:end:step]
        index_pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(.+)\]$"
        index_match = re.match(index_pattern, expression)

        if index_match:
            var_name, index_expr = index_match.groups()

            # Проверяем, является ли это срезом
            if ":" in index_expr:
                # Парсим срез
                slice_parts = index_expr.split(":")
                if len(slice_parts) == 2:
                    start, stop = slice_parts
                    step = None
                elif len(slice_parts) == 3:
                    start, stop, step = slice_parts
                else:
                    # Некорректный срез
                    return {
                        "type": "index_access",
                        "variable": var_name,
                        "index": self.parse_expression_to_ast(index_expr),
                    }

                # Парсим части среза
                start_ast = (
                    self.parse_expression_to_ast(start.strip())
                    if start.strip()
                    else None
                )
                stop_ast = (
                    self.parse_expression_to_ast(stop.strip()) if stop.strip() else None
                )
                step_ast = (
                    self.parse_expression_to_ast(step.strip())
                    if step and step.strip()
                    else None
                )

                return {
                    "type": "slice_access",
                    "variable": var_name,
                    "start": start_ast,
                    "stop": stop_ast,
                    "step": step_ast,
                }
            else:
                # Обычная индексация
                return {
                    "type": "index_access",
                    "variable": var_name,
                    "index": self.parse_expression_to_ast(index_expr),
                }

        # ========== 6. ТЕРНАРНЫЙ ОПЕРАТОР ==========

        # x if condition else y
        if " if " in expression and " else " in expression:
            # Находим позиции if и else
            if_pos = expression.find(" if ")
            else_pos = expression.find(" else ")

            if if_pos < else_pos:
                true_expr = expression[:if_pos].strip()
                condition = expression[if_pos + 4 : else_pos].strip()
                false_expr = expression[else_pos + 6 :].strip()

                return {
                    "type": "ternary_operator",
                    "condition": self.parse_expression_to_ast(condition),
                    "true_expr": self.parse_expression_to_ast(true_expr),
                    "false_expr": self.parse_expression_to_ast(false_expr),
                    "operator": "if-else",
                }

        # ========== 7. БИНАРНЫЕ И УНАРНЫЕ ОПЕРАЦИИ ==========

        # Определяем приоритеты операторов
        OPERATOR_PRECEDENCE = [
            # Логические OR
            ("or", "LOGICAL_OR"),
            # Логические AND
            ("and", "LOGICAL_AND"),
            # Сравнения
            ("==", "EQUAL"),
            ("!=", "NOT_EQUAL"),
            ("<", "LESS_THAN"),
            ("<=", "LESS_EQUAL"),
            (">", "GREATER_THAN"),
            (">=", "GREATER_EQUAL"),
            ("is", "IS"),
            ("is not", "IS_NOT"),
            ("in", "IN"),
            ("not in", "NOT_IN"),
            # Битовая OR
            ("|", "BITWISE_OR"),
            # Битовая XOR
            ("^", "BITWISE_XOR"),
            # Битовая AND
            ("&", "BITWISE_AND"),
            # Сдвиги
            ("<<", "LEFT_SHIFT"),
            (">>", "RIGHT_SHIFT"),
            # Сложение/вычитание
            ("+", "ADD"),
            ("-", "SUBTRACT"),
            # Умножение/деление/остаток
            ("*", "MULTIPLY"),
            ("/", "DIVIDE"),
            ("//", "INTEGER_DIVIDE"),
            ("%", "MODULO"),
            # Возведение в степень
            ("**", "POWER"),
        ]

        # Сначала проверяем выражения в скобках
        if self.is_fully_parenthesized(expression):
            inner = expression[1:-1].strip()
            return self.parse_expression_to_ast(inner)

        # Ищем оператор с наименьшим приоритетом (начинаем с конца списка)
        for op_symbol, op_type in reversed(OPERATOR_PRECEDENCE):
            # Для операторов из двух слов ищем их как целое
            if " " in op_symbol:
                if op_symbol in expression:
                    # Находим позицию оператора вне скобок и строк
                    pos = self.find_operator_outside_parentheses(expression, op_symbol)
                    if pos != -1:
                        left = expression[:pos].strip()
                        right = expression[pos + len(op_symbol) :].strip()

                        return {
                            "type": "binary_operation",
                            "operator": op_type,
                            "operator_symbol": op_symbol,
                            "left": self.parse_expression_to_ast(left),
                            "right": self.parse_expression_to_ast(right),
                        }
            else:
                # Для односимвольных операторов нужно быть аккуратнее
                # чтобы не перепутать с унарными операциями или другими контекстами
                pos = self.find_operator_outside_parentheses(expression, op_symbol)

                if pos != -1:
                    # Проверяем специальные случаи

                    # 1. Унарный минус/плюс в начале выражения
                    if pos == 0 and op_symbol in "+-":
                        operand = expression[1:].strip()
                        return {
                            "type": "unary_operation",
                            "operator": "NEGATIVE" if op_symbol == "-" else "POSITIVE",
                            "operator_symbol": op_symbol,
                            "operand": self.parse_expression_to_ast(operand),
                        }

                    # 2. Оператор не должен быть частью другого оператора (например, ** содержит *)
                    if op_symbol == "*":
                        # Проверяем, не является ли это частью **
                        if pos + 1 < len(expression) and expression[pos + 1] == "*":
                            continue  # Пропускаем, это часть **

                    # 3. Проверяем, что слева и справа есть корректные выражения
                    left = expression[:pos].strip()
                    right = expression[pos + len(op_symbol) :].strip()

                    if left and right:
                        # Проверяем, что оператор не внутри имени или числа
                        if (pos > 0 and expression[pos - 1].isalnum()) or (
                            pos + len(op_symbol) < len(expression)
                            and expression[pos + len(op_symbol)].isalnum()
                        ):
                            continue

                        return {
                            "type": "binary_operation",
                            "operator": op_type,
                            "operator_symbol": op_symbol,
                            "left": self.parse_expression_to_ast(left),
                            "right": self.parse_expression_to_ast(right),
                        }

        # ========== 8. УНАРНЫЕ ОПЕРАЦИИ ==========

        # 8.1 Унарный not
        if expression.startswith("not "):
            operand = expression[4:].strip()
            return {
                "type": "unary_operation",
                "operator": "NOT",
                "operator_symbol": "not",
                "operand": self.parse_expression_to_ast(operand),
            }

        # 8.2 Унарный ~ (битовое НЕ)
        if expression.startswith("~"):
            operand = expression[1:].strip()
            return {
                "type": "unary_operation",
                "operator": "BITWISE_NOT",
                "operator_symbol": "~",
                "operand": self.parse_expression_to_ast(operand),
            }

        # 8.3 Унарные + и - (уже обработаны в бинарных операциях)

        # ========== 9. ПЕРЕМЕННЫЕ ==========

        # Если это просто имя переменной
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", expression):
            return {"type": "variable", "name": expression, "value": expression}

        # ========== 10. ФОРМАТИРОВАННЫЕ СТРОКИ ==========

        # f"Hello {name}"
        f_string_pattern = r'^f["\'](.*)["\']$'
        f_string_match = re.match(f_string_pattern, expression)

        if f_string_match:
            content = f_string_match.group(1)
            # Находим все выражения в фигурных скобках
            import re as regex

            pattern = r"\{(.+?)\}"
            parts = []
            last_end = 0

            for match in regex.finditer(pattern, content):
                # Добавляем текст до выражения
                if match.start() > last_end:
                    text_part = content[last_end : match.start()]
                    parts.append({"type": "string_part", "value": text_part})

                # Добавляем выражение
                expr = match.group(1).strip()
                parts.append(
                    {
                        "type": "fstring_expr",
                        "expression": self.parse_expression_to_ast(expr),
                    }
                )

                last_end = match.end()

            # Добавляем остаток строки
            if last_end < len(content):
                text_part = content[last_end:]
                parts.append({"type": "string_part", "value": text_part})

            return {"type": "fstring", "parts": parts}

        # ========== 11. ВЫРАЖЕНИЯ СО СКОБКАМИ (повторная проверка) ==========

        if expression.startswith("(") and ")" in expression:
            # Находим соответствующую закрывающую скобку
            balance = 0
            in_string = False
            string_char = None
            escaped = False

            for i, char in enumerate(expression):
                # Обработка экранирования
                if escaped:
                    escaped = False
                    continue

                if char == "\\":
                    escaped = True
                    continue

                # Обработка строк
                if not in_string and char in ['"', "'"]:
                    in_string = True
                    string_char = char
                elif in_string and char == string_char:
                    in_string = False
                    string_char = None

                # Обработка скобок (только вне строк)
                if not in_string:
                    if char == "(":
                        balance += 1
                    elif char == ")":
                        balance -= 1
                        if balance == 0:
                            # Нашли закрывающую скобку
                            if i == len(expression) - 1:
                                # Весь expression в скобках
                                inner = expression[1:-1].strip()
                                return self.parse_expression_to_ast(inner)
                            else:
                                # Часть выражения в скобках
                                left = expression[: i + 1].strip()
                                rest = expression[i + 1 :].strip()

                                # Парсим оставшуюся часть как бинарную операцию
                                # Находим первый оператор после скобок
                                for op_symbol, op_type in reversed(OPERATOR_PRECEDENCE):
                                    if rest.startswith(op_symbol) or (
                                        len(op_symbol) > 1 and rest.find(op_symbol) == 0
                                    ):
                                        right = rest[len(op_symbol) :].strip()
                                        return {
                                            "type": "binary_operation",
                                            "operator": op_type,
                                            "operator_symbol": op_symbol,
                                            "left": self.parse_expression_to_ast(left),
                                            "right": self.parse_expression_to_ast(
                                                right
                                            ),
                                        }

                                # Если не нашли оператор, возвращаем как неизвестное выражение
                                break

            # Если дошли сюда, значит не смогли корректно распарсить
            return {"type": "unknown", "value": expression, "original": expression}

        # ========== 12. НЕРАСПОЗНАННОЕ ВЫРАЖЕНИЕ ==========

        # Если ничего не распознано
        return {"type": "unknown", "value": expression, "original": expression}

    def is_string_literal(self, expression: str) -> bool:
        """Проверяет, является ли выражение строковым литералом"""
        return (expression.startswith('"') and expression.endswith('"')) or (
            expression.startswith("'") and expression.endswith("'")
        )

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
        escaped = False

        for i, char in enumerate(expression):
            # Обработка экранирования
            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            # Обработка строк
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                in_string = False
                string_char = None

            # Обработка скобок (только вне строк)
            if not in_string:
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

    def is_identifier_char(self, char: str) -> bool:
        """Проверяет, является ли символ частью идентификатора"""
        return char.isalnum() or char == "_"

    def find_operator_outside_parentheses(self, expression: str, operator: str) -> int:
        """Находит позицию оператора вне скобок, строк и комментариев"""
        balance = 0  # Баланс круглых скобок
        brace_balance = 0  # Баланс фигурных скобок
        bracket_balance = 0  # Баланс квадратных скобок
        in_string = False  # Находимся ли внутри строки
        string_char = None  # Символ, открывший строку
        escaped = False  # Экранирован ли текущий символ

        i = 0
        while i < len(expression):
            char = expression[i]

            # Обработка экранирования
            if escaped:
                escaped = False
                i += 1
                continue

            if char == "\\":
                escaped = True
                i += 1
                continue

            # Обработка строк
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
            elif in_string and char == string_char:
                in_string = False
                string_char = None

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

                # Проверяем оператор, если мы на верхнем уровне всех скобок
                if balance == 0 and brace_balance == 0 and bracket_balance == 0:
                    # Проверяем совпадение оператора
                    if expression[i : i + len(operator)] == operator:
                        # Проверяем контекст, чтобы не перепутать с частью другого оператора или идентификатора
                        before_ok = i == 0 or not self.is_identifier_char(
                            expression[i - 1]
                        )
                        after_ok = i + len(operator) >= len(
                            expression
                        ) or not self.is_identifier_char(expression[i + len(operator)])

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
            # Парсим аргументы в AST, а не оставляем строкой
            args = self.parse_function_arguments_to_ast(args_str)

        operations = [
            {"type": "FUNCTION_CALL", "function": func_name, "arguments": args}
        ]

        dependencies = []
        for arg in args:
            deps = self.extract_dependencies_from_ast(arg)
            dependencies.extend(deps)

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

    def parse_function_call_assignment(self, line: str, scope: dict) -> bool:
        """Парсит присваивание результата вызова функции: var x: type = func(args)"""
        # Используем более простой паттерн, так как сложный не всегда работает
        pattern = (
            r"var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
        )
        match = re.match(pattern, line)

        if not match:
            return False

        var_name, var_type, value_expr = match.groups()

        # Парсим значение как выражение
        value_ast = self.parse_expression_to_ast(value_expr)

        # Проверяем, является ли значение вызовом функции
        if value_ast.get("type") in [
            "function_call",
            "method_call",
            "static_method_call",
            "constructor_call",
        ]:
            # Добавляем переменную
            scope["symbol_table"].add_symbol(
                name=var_name, key="var", var_type=var_type
            )

            if var_name not in scope["local_variables"]:
                scope["local_variables"].append(var_name)

            operations = [
                {"type": "NEW_VAR", "target": var_name, "var_type": var_type},
                {"type": "ASSIGN", "target": var_name, "value": value_ast},
            ]

            # Собираем зависимости из выражения
            dependencies = self.extract_dependencies_from_ast(value_ast)

            # Определяем тип узла
            node_type = "function_call_assignment"
            if value_ast.get("type") == "constructor_call":
                node_type = "object_creation"
            elif value_ast.get("type") == "static_method_call":
                node_type = "static_method_assignment"
            elif value_ast.get("type") == "method_call":
                node_type = "method_call_assignment"

            scope["graph"].append(
                {
                    "node": node_type,
                    "content": line,
                    "symbols": [var_name],
                    "var_name": var_name,
                    "var_type": var_type,
                    "value_ast": value_ast,
                    "operations": operations,
                    "dependencies": dependencies,
                }
            )

            return True

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
        """Парсит аргументы функции в список AST"""
        if not args_str.strip():
            return []

        args = []
        current_arg = ""
        depth = 0
        in_string = False
        string_char = None
        escaped = False

        i = 0
        while i < len(args_str):
            char = args_str[i]

            # Обработка экранирования
            if escaped:
                current_arg += char
                escaped = False
                i += 1
                continue

            if char == "\\":
                escaped = True
                current_arg += char
                i += 1
                continue

            # Обработка строк
            if not in_string and char in ['"', "'"]:
                in_string = True
                string_char = char
                current_arg += char
            elif in_string and char == string_char:
                in_string = False
                string_char = None
                current_arg += char
            elif in_string:
                current_arg += char

            # Обработка скобок (только вне строк)
            elif not in_string:
                if char == "(":
                    depth += 1
                    current_arg += char
                elif char == ")":
                    depth -= 1
                    current_arg += char
                elif char == "[":
                    depth += 1
                    current_arg += char
                elif char == "]":
                    depth -= 1
                    current_arg += char
                elif char == "{":
                    depth += 1
                    current_arg += char
                elif char == "}":
                    depth -= 1
                    current_arg += char
                elif char == "," and depth == 0:
                    # Нашли разделитель аргументов на верхнем уровне
                    if current_arg.strip():
                        args.append(self.parse_expression_to_ast(current_arg.strip()))
                    current_arg = ""
                else:
                    current_arg += char
            else:
                current_arg += char

            i += 1

        # Обрабатываем последний аргумент
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
                var_name = node.get("name") or node.get("value")
                if var_name and var_name not in dependencies:
                    # Проверяем, что это не ключевое слово или тип данных
                    if (
                        var_name not in KEYS
                        and var_name not in DATA_TYPES
                        and var_name not in self.builtin_functions
                        and not var_name.startswith('"')
                        and not var_name.endswith('"')
                    ):
                        dependencies.append(var_name)

            elif node_type == "attribute_access":
                obj_name = node.get("object")
                if obj_name and obj_name not in dependencies:
                    # Проверяем, что это не ключевое слово
                    if (
                        obj_name not in KEYS
                        and obj_name not in DATA_TYPES
                        and obj_name not in self.builtin_functions
                    ):
                        dependencies.append(obj_name)

            elif node_type == "method_call":
                obj_name = node.get("object")
                if obj_name and obj_name not in dependencies:
                    dependencies.append(obj_name)

                for arg in node.get("arguments", []):
                    traverse(arg)

            elif node_type == "static_method_call":
                # Статические методы не требуют зависимостей от объектов
                for arg in node.get("arguments", []):
                    traverse(arg)

            elif node_type == "constructor_call":
                for arg in node.get("arguments", []):
                    traverse(arg)

            elif node_type == "function_call":
                func_name = node.get("function")
                # Только пользовательские функции добавляем как зависимости
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

            elif node_type == "ternary_operator":
                traverse(node.get("condition"))
                traverse(node.get("true_expr"))
                traverse(node.get("false_expr"))

            elif node_type == "address_of":
                expr = node.get("expression") or node.get("variable")
                if isinstance(expr, dict):
                    traverse(expr)
                elif expr and expr not in dependencies:
                    dependencies.append(expr)

            elif node_type == "dereference":
                expr = node.get("expression") or node.get("pointer")
                if isinstance(expr, dict):
                    traverse(expr)
                elif expr and expr not in dependencies:
                    dependencies.append(expr)

            elif node_type == "index_access":
                var_name = node.get("variable")
                if var_name and var_name not in dependencies:
                    dependencies.append(var_name)
                traverse(node.get("index"))

            elif node_type == "slice_access":
                var_name = node.get("variable")
                if var_name and var_name not in dependencies:
                    dependencies.append(var_name)
                traverse(node.get("start"))
                traverse(node.get("stop"))
                traverse(node.get("step"))

            elif node_type == "list_literal":
                for item in node.get("items", []):
                    traverse(item)

            elif node_type == "tuple_literal":
                for item in node.get("items", []):
                    traverse(item)

            elif node_type == "dict_literal":
                for key, value in node.get("pairs", {}).items():
                    traverse(value)

            elif node_type == "set_literal":
                for item in node.get("items", []):
                    traverse(item)

            elif node_type == "fstring":
                for part in node.get("parts", []):
                    if part.get("type") == "fstring_expr":
                        traverse(part.get("expression"))

        traverse(ast)
        return list(set(dependencies))  # Убираем дубликаты

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
        """Парсит литерал списка: [1, 2, 3] или [[1, 2], [3, 4]]"""
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
                elif not in_string:
                    if char == "[":
                        depth += 1
                        current_item += char
                    elif char == "]":
                        depth -= 1
                        current_item += char
                    elif char == "(":
                        depth += 1
                        current_item += char
                    elif char == ")":
                        depth -= 1
                        current_item += char
                    elif char == "{":
                        depth += 1
                        current_item += char
                    elif char == "}":
                        depth -= 1
                        current_item += char
                    elif depth == 0 and char == ",":
                        if current_item.strip():
                            item_ast = self.parse_expression_to_ast(
                                current_item.strip()
                            )
                            items.append(item_ast)
                        current_item = ""
                    else:
                        current_item += char
                else:
                    current_item += char

                i += 1

            if current_item.strip():
                item_ast = self.parse_expression_to_ast(current_item.strip())
                items.append(item_ast)

        return {
            "type": "list_literal",
            "items": items,
            "length": len(items),
            "is_nested": any(item.get("type") == "list_literal" for item in items),
        }

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

    def parse_c_call(self, line: str, scope: dict):
        """Парсит прямой вызов C-функции"""
        # Убираем @ в начале
        c_call = line[1:].strip()

        # Паттерн для вызова C-функции: func_name(arg1, arg2, ...)
        pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)"
        match = re.match(pattern, c_call)

        if not match:
            return False

        func_name, args_str = match.groups()

        # Разбираем аргументы
        args = []
        if args_str.strip():
            args = self.parse_function_arguments(args_str)

        operations = [{"type": "C_CALL", "function": func_name, "arguments": args}]

        # Собираем зависимости из аргументов
        dependencies = []
        for arg in args:
            if isinstance(arg, dict):
                # Если аргумент - AST, извлекаем зависимости
                deps = self.extract_dependencies_from_ast(arg)
                dependencies.extend(deps)
            elif arg.isalpha() and arg not in KEYS and arg not in DATA_TYPES:
                dependencies.append(arg)

        # Создаем узел для C-вызова
        scope["graph"].append(
            {
                "node": "c_call",
                "content": line,
                "function": func_name,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def clean_value(self, value: str):
        """Очищает значение от лишних пробелов, но для сложных выражений возвращает AST"""
        value = value.strip()

        if not value:
            return {"type": "empty", "value": ""}

        # Сначала проверяем простые литералы
        if value.isdigit():
            return {"type": "literal", "value": int(value), "data_type": "int"}
        elif value == "True":
            return {"type": "literal", "value": True, "data_type": "bool"}
        elif value == "False":
            return {"type": "literal", "value": False, "data_type": "bool"}
        elif value == "None":
            return {"type": "literal", "value": None, "data_type": "None"}
        elif value == "null":
            return {"type": "literal", "value": "null", "data_type": "null"}
        elif (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            content = value[1:-1]
            content = content.replace('\\"', '"').replace("\\'", "'")
            return {"type": "literal", "value": content, "data_type": "str"}

        # Если это не простой литерал, парсим как выражение
        ast = self.parse_expression_to_ast(value)

        # Если парсинг не удался, возвращаем как неизвестное
        if ast["type"] == "unknown":
            return {"type": "literal", "value": value, "data_type": "any"}

        return ast

    # CLASS

    def parse_class_declaration(
        self, line: str, scope: dict, all_lines: list, current_index: int
    ):
        """Парсит объявление класса"""
        pattern = r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(([^)]*)\))?\s*:"
        match = re.match(pattern, line)

        if not match:
            return current_index + 1

        class_name = match.group(1)
        base_classes_str = match.group(2)

        # Парсим родительские классы
        base_classes = []
        if base_classes_str:
            base_classes = [bc.strip() for bc in base_classes_str.split(",")]

        # Добавляем класс в таблицу символов
        symbol_id = scope["symbol_table"].add_class(
            name=class_name, base_classes=base_classes
        )

        # Находим тело класса
        body_start = current_index + 1
        base_indent = self.calculate_indent_level(all_lines[current_index])
        body_end = self.find_indented_block_end(all_lines, body_start, base_indent)

        # Создаем узел объявления класса
        class_node = {
            "node": "class_declaration",
            "content": line,
            "class_name": class_name,
            "symbol_id": symbol_id,
            "base_classes": base_classes,
            "body_level": scope["level"] + 1,
            "methods": [],
            "attributes": [],
            "static_methods": [],
            "class_methods": [],
        }

        scope["graph"].append(class_node)

        # Парсим тело класса
        saved_indent = self.current_indent
        self.current_indent = base_indent + 1

        # Создаем временную область видимости для тела класса
        class_body_scope = {
            "level": scope["level"] + 1,
            "type": "class_body",
            "parent_scope": scope["level"],
            "class_name": class_name,
            "graph": [],
            "symbol_table": SymbolTable(),
            "methods": [],
            "attributes": [],
        }

        i = body_start
        current_decorator = None

        while i < body_end:
            body_line = all_lines[i]
            if not body_line.strip():
                i += 1
                continue

            body_indent = self.calculate_indent_level(body_line)
            body_content = body_line.strip()

            # Проверяем декораторы методов
            if body_content.startswith("@"):
                current_decorator = body_content
                i += 1
                continue

            # Парсим методы класса
            if body_content.startswith("def "):
                # Определяем тип метода
                is_static = current_decorator == "@staticmethod"
                is_classmethod = current_decorator == "@classmethod"

                # Парсим объявление метода
                method_index = self.parse_class_method_declaration(
                    body_content,
                    scope,
                    all_lines,
                    i,
                    body_indent,
                    class_name,
                    is_static,
                    is_classmethod,
                    class_node,
                )

                if method_index > i:
                    i = method_index
                    current_decorator = None
                    continue

            # Парсим атрибуты класса (var self.attr: type = value)
            elif body_content.startswith("var ") and "self." in body_content:
                self.parse_class_attribute(
                    body_content, class_body_scope, class_name, class_node
                )
                i += 1
                continue

            i += 1

        # Восстанавливаем отступ
        self.current_indent = saved_indent

        return body_end

    def parse_class_method_declaration(
        self,
        line: str,
        parent_scope: dict,
        all_lines: list,
        current_index: int,
        indent: int,
        class_name: str,
        is_static: bool,
        is_classmethod: bool,
        class_node: dict,
    ):
        """Парсит объявление метода класса"""
        # Определяем паттерн для метода
        pattern = r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*(?:->\s*([a-zA-Z_][a-zA-Z0-9_]*))?\s*:"
        match = re.match(pattern, line)

        if not match:
            return current_index + 1

        method_name, params_str, return_type = match.groups()
        return_type = return_type if return_type else "None"

        # Парсим параметры (упрощенная версия)
        parameters = []
        if params_str.strip():
            # Разделяем параметры по запятым
            param_parts = []
            current = ""
            depth = 0

            for char in params_str:
                if char == "[":
                    depth += 1
                    current += char
                elif char == "]":
                    depth -= 1
                    current += char
                elif char == "," and depth == 0:
                    if current.strip():
                        param_parts.append(current.strip())
                    current = ""
                else:
                    current += char

            if current.strip():
                param_parts.append(current.strip())

            # Обрабатываем каждый параметр
            for param_str in param_parts:
                param_str = param_str.strip()
                if not param_str:
                    continue

                # Упрощенная обработка параметра
                if ":" in param_str:
                    parts = param_str.split(":", 1)
                    name = parts[0].strip()
                    param_type = parts[1].strip()
                else:
                    name = param_str
                    param_type = "any"

                # Убираем значение по умолчанию если есть
                if "=" in name:
                    name = name.split("=")[0].strip()
                if "=" in param_type:
                    param_type = param_type.split("=")[0].strip()

                parameters.append({"name": name, "type": param_type})

        # Для обычных методов добавляем self как первый параметр
        if not is_static and not is_classmethod and method_name != "__init__":
            has_self = any(p["name"] == "self" for p in parameters)
            if not has_self:
                parameters.insert(0, {"name": "self", "type": class_name})

        # Для __init__ также добавляем self если его нет
        if method_name == "__init__":
            has_self = any(p["name"] == "self" for p in parameters)
            if not has_self:
                parameters.insert(0, {"name": "self", "type": class_name})

            # Обновляем тип self для конструктора
            for i, param in enumerate(parameters):
                if param["name"] == "self":
                    parameters[i]["type"] = class_name
                    break
        # Для обычных методов (не статических и не classmethod) обновляем тип self
        elif not is_static and not is_classmethod:
            for i, param in enumerate(parameters):
                if param["name"] == "self":
                    parameters[i]["type"] = class_name
                    break

        # Добавляем метод в класс
        parent_scope["symbol_table"].add_class_method(
            class_name=class_name,
            method_name=method_name,
            is_static=is_static,
            is_classmethod=is_classmethod,
            parameters=parameters,
            return_type=return_type,
        )

        # Обновляем узел класса
        method_info = {
            "name": method_name,
            "parameters": parameters,
            "return_type": return_type,
            "is_static": is_static,
            "is_classmethod": is_classmethod,
        }

        if is_static:
            class_node["static_methods"].append(method_info)
        elif is_classmethod:
            class_node["class_methods"].append(method_info)
        else:
            class_node["methods"].append(method_info)

        # Находим тело метода
        body_start = current_index + 1
        body_end = self.find_indented_block_end(all_lines, body_start, indent)

        # Определяем тип области видимости метода
        if is_static:
            scope_type = "static_method"
        elif is_classmethod:
            scope_type = "classmethod"
        elif method_name == "__init__":
            scope_type = "constructor"
        else:
            scope_type = "class_method"  # Значение по умолчанию

        # Создаем область видимости для метода
        method_level = parent_scope["level"] + 2  # класс + метод
        method_scope = {
            "level": method_level,
            "type": scope_type,
            "parent_scope": parent_scope["level"],
            "class_name": class_name,
            "method_name": method_name,
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
        }

        # Добавляем параметры в таблицу символов метода
        for param in parameters:
            param_type = param["type"]
            method_scope["symbol_table"].add_symbol(
                name=param["name"], key="parameter", var_type=param_type
            )
            method_scope["local_variables"].append(param["name"])

        # Добавляем область видимости метода в общий список
        self.scopes.append(method_scope)

        # Для конструктора добавляем в стек scope'ов для парсинга тела
        self.scope_stack.append(method_scope)

        # Парсим тело метода
        saved_indent = self.current_indent
        self.current_indent = indent + 1

        i = body_start
        while i < body_end:
            method_line = all_lines[i]
            if not method_line.strip():
                i += 1
                continue

            method_indent = self.calculate_indent_level(method_line)
            method_content = method_line.strip()

            # Особые проверки для конструктора
            if (
                method_name == "__init__"
                and method_content.startswith("var ")
                and "self." in method_content
            ):
                # В конструкторе парсим объявления атрибутов self
                # Паттерны для разных форматов:
                # 1. var self.attr: type = value
                # 2. self.attr = value
                patterns = [
                    r"var\s+self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_\[\]]*)\s*=\s*(.+)",
                    r"self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)",
                ]

                for pattern in patterns:
                    match_pattern = re.match(pattern, method_content)
                    if match_pattern:
                        if pattern == patterns[0]:  # var self.attr: type = value
                            attr_name, attr_type, value = match_pattern.groups()
                        else:  # self.attr = value
                            attr_name, value = match_pattern.groups()
                            attr_type = "any"  # Определяем тип из контекста

                        # Добавляем атрибут в класс
                        parent_scope["symbol_table"].add_class_attribute(
                            class_name=class_name,
                            attribute_name=attr_name,
                            attribute_type=attr_type,
                        )

                        # Добавляем в узел класса
                        class_node["attributes"].append(
                            {
                                "name": attr_name,
                                "type": attr_type,
                                "access": "public",
                            }
                        )

                        # Парсим значение
                        value_ast = self.parse_expression_to_ast(value)

                        # Создаем узел для инициализации атрибута
                        attr_node = {
                            "node": "class_attribute_init",
                            "content": method_content,
                            "class_name": class_name,
                            "attribute_name": attr_name,
                            "attribute_type": attr_type,
                            "value": value_ast,
                            "operations": [
                                {
                                    "type": "CLASS_ATTRIBUTE_INIT",
                                    "class_name": class_name,
                                    "attribute": attr_name,
                                    "value": value_ast,
                                }
                            ],
                        }

                        method_scope["graph"].append(attr_node)

                        # Пропускаем стандартный парсинг для этой строки
                        i += 1
                        break  # Важно: break, чтобы не продолжать проверку других паттернов
                else:
                    # Если не нашли атрибут, парсим как обычную строку
                    i = self.parse_line(
                        method_content, method_scope, all_lines, i, method_indent
                    )
            else:
                # Стандартный парсинг строки метода
                i = self.parse_line(
                    method_content, method_scope, all_lines, i, method_indent
                )

        # Восстанавливаем отступ и удаляем scope метода из стека
        self.current_indent = saved_indent
        if method_scope in self.scope_stack:
            self.scope_stack.remove(method_scope)

        return body_end

    def parse_single_parameter(self, param_str: str) -> dict:
        """Парсит один параметр: name: type = default_value"""
        param_str = param_str.strip()
        if not param_str:
            return None

        # Проверяем наличие типа и значения по умолчанию
        if ":" in param_str and "=" in param_str:
            # name: type = value
            name_type_part, value_part = param_str.split("=", 1)
            if ":" in name_type_part:
                name, type_part = name_type_part.split(":", 1)
                return {
                    "name": name.strip(),
                    "type": type_part.strip(),
                    "default_value": value_part.strip(),
                }
        elif ":" in param_str:
            # name: type
            name, type_part = param_str.split(":", 1)
            return {"name": name.strip(), "type": type_part.strip()}
        elif "=" in param_str:
            # name = value
            name, value = param_str.split("=", 1)
            return {"name": name.strip(), "type": "any", "default_value": value.strip()}
        else:
            # Просто name
            return {"name": param_str.strip(), "type": "any"}

        return None

    def parse_class_attribute(
        self, line: str, scope: dict, class_name: str, class_node: dict
    ):
        """Парсит атрибут класса (var self.attr: type = value)"""
        # Расширенный паттерн для поддержки разных форматов
        patterns = [
            r"var\s+self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_\[\]]*)\s*=\s*(.+)",  # с типом и значением
            r"var\s+self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_\[\]]*)",  # только с типом
            r"var\s+self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)",  # только со значением
            r"self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)",  # простое присваивание в конструкторе
        ]

        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                if pattern == patterns[0]:  # с типом и значением
                    attr_name, attr_type, value = match.groups()
                    value_ast = self.parse_expression_to_ast(value)
                elif pattern == patterns[1]:  # только с типом
                    attr_name, attr_type = match.groups()
                    value_ast = None
                elif pattern == patterns[2]:  # только со значением
                    attr_name, value = match.groups()
                    attr_type = "any"
                    value_ast = self.parse_expression_to_ast(value)
                else:  # простое присваивание в конструкторе
                    attr_name, value = match.groups()
                    attr_type = "any"
                    value_ast = self.parse_expression_to_ast(value)

                # Добавляем атрибут в класс
                scope["symbol_table"].add_class_attribute(
                    class_name=class_name,
                    attribute_name=attr_name,
                    attribute_type=attr_type,
                )

                # Добавляем в узел класса
                class_node["attributes"].append(
                    {
                        "name": attr_name,
                        "type": attr_type,
                        "access": "public",
                    }
                )

                # Создаем узел для инициализации атрибута
                attr_node = {
                    "node": "class_attribute_init",
                    "content": line,
                    "class_name": class_name,
                    "attribute_name": attr_name,
                    "attribute_type": attr_type,
                    "value": value_ast,
                    "operations": [
                        {
                            "type": "CLASS_ATTRIBUTE_INIT",
                            "class_name": class_name,
                            "attribute": attr_name,
                            "value": value_ast,
                        }
                    ],
                }

                scope["graph"].append(attr_node)
                return True

        return False

    def parse_object_creation(self, expression: str) -> dict:
        """Парсит создание объекта: ClassName(arg1, arg2, ...)"""
        pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)"
        match = re.match(pattern, expression)

        if not match:
            return {"type": "unknown", "value": expression}

        class_name, args_str = match.groups()

        # Парсим аргументы
        args = []
        if args_str.strip():
            args = self.parse_function_arguments_to_ast(args_str)

        return {"type": "constructor_call", "class_name": class_name, "arguments": args}

    def parse_attribute_access(self, expression: str) -> dict:
        """Парсит доступ к атрибуту: obj.attr или obj.method()"""
        # Проверяем доступ к атрибуту
        if "." in expression:
            parts = expression.split(".", 1)
            if len(parts) == 2:
                obj_name, rest = parts

                # Проверяем, является ли rest вызовом метода
                method_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)"
                method_match = re.match(method_pattern, rest)

                if method_match:
                    # Это вызов метода: obj.method(args)
                    method_name, args_str = method_match.groups()
                    args = []
                    if args_str.strip():
                        args = self.parse_function_arguments_to_ast(args_str)

                    return {
                        "type": "method_call_expression",
                        "object": obj_name,
                        "method": method_name,
                        "arguments": args,
                    }
                else:
                    # Просто доступ к атрибуту: obj.attr
                    return {
                        "type": "attribute_access",
                        "object": obj_name,
                        "attribute": rest,
                    }

        return {"type": "unknown", "value": expression}

    def parse_static_method_call(self, expression: str) -> dict:
        """Парсит вызов статического метода: ClassName.method(args)"""
        pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)"
        match = re.match(pattern, expression)

        if not match:
            return {"type": "unknown", "value": expression}

        class_name, method_name, args_str = match.groups()

        args = []
        if args_str.strip():
            args = self.parse_function_arguments_to_ast(args_str)

        return {
            "type": "static_method_call",
            "class_name": class_name,
            "method": method_name,
            "arguments": args,
        }

    def parse_object_creation_node(
        self, line: str, scope: dict, var_name: str, class_name: str, args_str: str
    ):
        """Создает узел для создания объекта"""
        args = []
        if args_str.strip():
            args = self.parse_function_arguments_to_ast(args_str)

        # Добавляем переменную в таблицу символов
        scope["symbol_table"].add_symbol(name=var_name, key="var", var_type=class_name)

        # Создаем AST для вызова конструктора
        constructor_ast = {
            "type": "constructor_call",
            "class_name": class_name,
            "arguments": args,
        }

        operations = [
            {"type": "NEW_VAR", "target": var_name, "var_type": class_name},
            {
                "type": "CONSTRUCTOR_CALL",
                "class_name": class_name,
                "target": var_name,
                "arguments": args,
            },
        ]

        # Собираем зависимости из аргументов
        dependencies = []
        for arg in args:
            deps = self.extract_dependencies_from_ast(arg)
            dependencies.extend(deps)

        # Создаем узел
        scope["graph"].append(
            {
                "node": "object_creation",
                "content": line,
                "symbols": [var_name],
                "var_name": var_name,
                "var_type": class_name,
                "class_name": class_name,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
                "expression_ast": constructor_ast,
            }
        )

        return True

    def parse_object_method_call_node(
        self, line: str, scope: dict, obj_name: str, method_name: str, args_str: str
    ) -> bool:
        # Проверяем, является ли это частью присваивания
        # Это сложно, так как нужно знать контекст

        # Вместо этого предлагаю:
        # 1. Для простых вызовов методов без присваивания генерировать код с присваиванием обратно в объект
        # 2. Для вызовов внутри выражений - generate_expression сам разберется

        args = []
        if args_str.strip():
            args = self.parse_function_arguments_to_ast(args_str)

        operations = [
            {
                "type": "METHOD_CALL",
                "object": obj_name,
                "method": method_name,
                "arguments": args,
                # Добавляем флаг: is_standalone=True для отдельного вызова
                "is_standalone": True,
            }
        ]

        dependencies = [obj_name]
        for arg in args:
            deps = self.extract_dependencies_from_ast(arg)
            dependencies.extend(deps)

        scope["graph"].append(
            {
                "node": "method_call",
                "content": line,
                "object": obj_name,
                "method": method_name,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
                "is_standalone": True,  # Флаг для компилятора
            }
        )

        return True

    def parse_static_method_call_node(
        self, line: str, scope: dict, class_name: str, method_name: str, args_str: str
    ) -> bool:
        """Парсит вызов статического метода: Class.method(args)"""
        # Парсим аргументы из строки в список AST
        args = []
        if args_str.strip():
            args = self.parse_function_arguments_to_ast(args_str)

        operations = [
            {
                "type": "STATIC_METHOD_CALL",
                "class_name": class_name,
                "method": method_name,
                "arguments": args,
            }
        ]

        # Собираем зависимости
        dependencies = []
        for arg in args:
            deps = self.extract_dependencies_from_ast(arg)
            dependencies.extend(deps)

        scope["graph"].append(
            {
                "node": "static_method_call",
                "content": line,
                "class_name": class_name,
                "method": method_name,
                "arguments": args,
                "operations": operations,
                "dependencies": dependencies,
            }
        )

        return True

    def is_class_name(self, name: str, scope: dict) -> bool:
        """Проверяет, является ли имя именем класса"""
        # Простая проверка - начинается с заглавной буквы
        if name and name[0].isupper():
            # Дополнительно проверяем в таблице символов
            symbol = scope["symbol_table"].get_symbol(name)
            if symbol and symbol.get("key") == "class":
                return True
            # Если символ не найден, все равно считаем это именем класса
            # (может быть определен в другом модуле)
            return True

        # Проверяем в родительских scope'ах
        if "parent_scope" in scope:
            parent_level = scope["parent_scope"]
            for parent in self.scopes:
                if parent["level"] == parent_level:
                    if self.is_class_name(name, parent):
                        return True

        return False

    def parse_class_attribute_initialization(self, line: str, scope: dict) -> bool:
        """Парсит инициализацию атрибута класса в конструкторе"""
        print(f"DEBUG: Парсим инициализацию атрибута: {line}")

        # Паттерн 1: self.attr = value
        pattern_simple = r"self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
        match_simple = re.match(pattern_simple, line)

        if match_simple:
            attr_name, value = match_simple.groups()
            print(f"DEBUG: Найден атрибут простой: {attr_name}, значение: {value}")

            # Парсим значение
            value_ast = self.parse_expression_to_ast(value)
            print(f"DEBUG: Значение как AST: {value_ast}")

            # Получаем имя класса из scope
            class_name = scope.get("class_name", "")
            print(f"DEBUG: Имя класса: {class_name}")

            # Определяем тип атрибута из AST значения
            attr_type = self._infer_type_from_ast(value_ast)
            print(f"DEBUG: Выведенный тип: {attr_type}")

            # Находим глобальную область и обновляем информацию о классе
            for global_scope in self.scopes:
                if global_scope.get("level") == 0:  # Глобальная область
                    class_symbol = global_scope["symbol_table"].get_symbol(class_name)
                    if class_symbol:
                        # Добавляем атрибут в класс
                        class_symbol["attributes"].append(
                            {"name": attr_name, "type": attr_type, "access": "public"}
                        )
                        print(
                            f"DEBUG: Добавлен атрибут {attr_name} в класс {class_name}"
                        )

                        # Обновляем узел класса в графе
                        for node in global_scope["graph"]:
                            if (
                                node.get("node") == "class_declaration"
                                and node.get("class_name") == class_name
                            ):
                                if attr_name not in [
                                    a["name"] for a in node["attributes"]
                                ]:
                                    node["attributes"].append(
                                        {
                                            "name": attr_name,
                                            "type": attr_type,
                                            "access": "public",
                                        }
                                    )
                                    print(
                                        f"DEBUG: Обновлен узел класса с атрибутом {attr_name}"
                                    )
                                break
                    break

            # Создаем узел для инициализации атрибута
            attr_node = {
                "node": "attribute_assignment",  # ИЗМЕНЕНО: было "class_attribute_init"
                "content": line,
                "object": "self",
                "attribute": attr_name,
                "value": value_ast,
                "operations": [
                    {
                        "type": "ATTRIBUTE_ASSIGN",
                        "object": "self",
                        "attribute": attr_name,
                        "value": value_ast,
                    }
                ],
                "dependencies": self.extract_dependencies_from_ast(value_ast),
            }

            scope["graph"].append(attr_node)
            print(f"DEBUG: Добавлен узел attribute_assignment в граф scope")
            return True

        # Паттерн 2: var self.attr: type = value
        pattern_with_type = (
            r"self\.([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
        )
        match_with_type = re.match(pattern_with_type, line)

        if match_with_type:
            attr_name, attr_type, value = match_with_type.groups()
            print(
                f"DEBUG: Найден атрибут с типом: {attr_name}, тип: {attr_type}, значение: {value}"
            )

            # Парсим значение
            value_ast = self.parse_expression_to_ast(value)
            print(f"DEBUG: Значение как AST: {value_ast}")

            # Получаем имя класса из scope
            class_name = scope.get("class_name", "")
            print(f"DEBUG: Имя класса: {class_name}")

            # Находим глобальную область и обновляем информацию о классе
            for global_scope in self.scopes:
                if global_scope.get("level") == 0:  # Глобальная область
                    class_symbol = global_scope["symbol_table"].get_symbol(class_name)
                    if class_symbol:
                        # Добавляем атрибут в класс
                        class_symbol["attributes"].append(
                            {"name": attr_name, "type": attr_type, "access": "public"}
                        )
                        print(
                            f"DEBUG: Добавлен атрибут {attr_name} в класс {class_name}"
                        )

                        # Обновляем узел класса в графе
                        for node in global_scope["graph"]:
                            if (
                                node.get("node") == "class_declaration"
                                and node.get("class_name") == class_name
                            ):
                                if attr_name not in [
                                    a["name"] for a in node["attributes"]
                                ]:
                                    node["attributes"].append(
                                        {
                                            "name": attr_name,
                                            "type": attr_type,
                                            "access": "public",
                                        }
                                    )
                                    print(
                                        f"DEBUG: Обновлен узел класса с атрибутом {attr_name}"
                                    )
                                break
                    break

            # Создаем узел для инициализации атрибута
            attr_node = {
                "node": "attribute_assignment",  # ИЗМЕНЕНО: было "class_attribute_init"
                "content": line,
                "object": "self",
                "attribute": attr_name,
                "value": value_ast,
                "operations": [
                    {
                        "type": "ATTRIBUTE_ASSIGN",
                        "object": "self",
                        "attribute": attr_name,
                        "value": value_ast,
                    }
                ],
                "dependencies": self.extract_dependencies_from_ast(value_ast),
            }

            scope["graph"].append(attr_node)
            print(f"DEBUG: Добавлен узел attribute_assignment в граф scope")
            return True

        print(f"DEBUG: Не удалось распарсить строку как инициализацию атрибута: {line}")
        return False

    def _infer_type_from_ast(self, ast: dict) -> str:
        """Выводит тип из AST выражения"""
        if not ast:
            return "int"

        node_type = ast.get("type", "")

        if node_type == "literal":
            data_type = ast.get("data_type", "")
            return data_type
        elif node_type == "binary_operation":
            # Для операций предполагаем int
            return "int"
        elif node_type == "variable":
            # Пытаемся определить тип переменной по имени
            return "int"
        else:
            return "int"
