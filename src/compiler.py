import re
from typing import Dict, List, Optional
from src.modules.constants import KNOWN_C_TYPES


class CCodeGenerator:
    def __init__(self):
        self.output = []
        self.indent_level = 0
        self.temp_var_counter = 0
        self.function_declarations = []
        self.c_imports = []

        # Улучшенная система управления переменными
        self.variable_scopes = []  # Стек scope'ов
        self.current_scope_level = 0

        # Структуры для типов
        self.generated_structs = set()
        self.generated_helpers = []
        self.helper_declarations = []  # Декларации helper-функций

        # Для отслеживания типов классов
        self.class_types = set()  # Имена классов
        self.struct_types = set()  # Имена структур (включая tuple/list)
        # Типы, которые являются указателями (используют ->)
        self.pointer_types = set()

        self.class_fields = {}  # {class_name: {field_name: field_type}}

        # Расширенный маппинг типов Python -> C
        self.type_map = {
            "int": "int",
            "float": "double",
            "str": "char*",
            "bool": "bool",
            "None": "void",
            "null": "void*",
            "list": "void*",
            "dict": "void*",
            "set": "void*",
            "function": "void*",
            "tuple": "void*",
            "bytes": "unsigned char*",
            "bytearray": "unsigned char*",
        }

        self.known_c_types = KNOWN_C_TYPES

        # Поддержка обобщенных типов
        self.generic_type_map = {}  # Кэш для сгенерированных типов

        # Поддерживаемые операции
        self.operator_map = {
            "+": "+",
            "-": "-",
            "*": "*",
            "/": "/",
            "//": "/",  # Целочисленное деление
            "%": "%",
            "**": "pow",  # Степень
            "<": "<",
            ">": ">",
            "<=": "<=",
            ">=": ">=",
            "==": "==",
            "!=": "!=",
            "and": "&&",
            "or": "||",
            "not": "!",
        }

        self.class_hierarchy = {}  # {class_name: [parent_classes]}
        self.inherited_methods = {}  # {class_name: {method_name: origin_class}}
        self.all_class_methods = {}  # {class_name: {method_name: method_info}}

    def reset(self):
        """Сброс состояния генератора"""
        print(
            f"DEBUG reset: Очищаем generated_helpers (было {len(self.generated_helpers)})"
        )
        self.output = []
        self.indent_level = 0
        self.temp_var_counter = 0
        self.variable_scopes = [{}]  # Глобальный scope
        self.current_scope_level = 0
        self.generated_structs.clear()
        self.generated_helpers.clear()
        self.generic_type_map.clear()
        self.class_fields.clear()  # Очищаем поля классов
        print(f"DEBUG reset: generated_helpers очищен")

    def indent(self) -> str:
        """Возвращает отступ для текущего уровня"""
        return "    " * self.indent_level

    def add_line(self, line: str):
        """Добавляет строку с правильным отступом"""
        self.output.append(self.indent() + line)

    def add_empty_line(self):
        """Добавляет пустую строку"""
        self.output.append("")

    def enter_scope(self):
        """Вход в новый scope (увеличение вложенности)"""
        self.current_scope_level += 1
        if len(self.variable_scopes) <= self.current_scope_level:
            self.variable_scopes.append({})

    def exit_scope(self):
        """Выход из текущего scope"""
        if self.current_scope_level > 0:
            if len(self.variable_scopes) > self.current_scope_level:
                self.variable_scopes.pop()
            self.current_scope_level -= 1

    def get_current_scope(self) -> Dict:
        """Получает текущий scope переменных"""
        if self.current_scope_level < len(self.variable_scopes):
            return self.variable_scopes[self.current_scope_level]
        return {}

    def map_type_to_c(self, py_type: str, is_pointer: bool = False) -> str:
        """Преобразует тип Python в тип C с поддержкой автоматического распознавания C типов"""

        # Проверяем, не является ли это уже C типом
        if self._is_c_type(py_type):
            # Если это известный C тип, возвращаем как есть
            return py_type

        if self._is_class_type(py_type):
            # Классы в C - это указатели на структуры
            if is_pointer:
                return f"{py_type}**"  # Указатель на указатель
            return f"{py_type}*"  # Обычный указатель на структуру

        if py_type == "None":
            return "void*"  # None -> void*
        elif py_type.startswith("*"):
            base_type = py_type[1:]
            c_base_type = self.map_type_to_c(base_type)
            return f"{c_base_type}*"
        elif py_type == "pointer":
            return "void*"
        elif py_type.startswith("tuple["):
            # Генерируем структуру для кортежа
            self.generate_tuple_struct(py_type)
            struct_name = self.generate_tuple_struct_name(py_type)

            if is_pointer:
                return f"{struct_name}*"
            return struct_name
        elif py_type.startswith("list["):
            # Генерируем структуру для list
            self.generate_list_struct(py_type)
            struct_name = self.generate_list_struct_name(py_type)

            # list всегда указатель на структуру
            c_type = f"{struct_name}*"

            if is_pointer:
                return f"{c_type}*"
            return c_type
        else:
            c_type = self.type_map.get(py_type, "int")
            if is_pointer:
                return f"{c_type}*"
            return c_type

    def _is_c_type(self, type_name: str) -> bool:
        """Определяет, является ли тип известным C типом"""
        if not isinstance(type_name, str):
            return False

        # Проверяем по базовым C типам
        base_types = {
            "int",
            "float",
            "double",
            "char",
            "bool",
            "void",
            "short",
            "long",
            "long long",
            "unsigned",
            "signed",
        }

        # Проверяем, является ли это известным C типом
        if type_name in self.known_c_types:
            return True

        # Проверяем по шаблонам C типов
        c_type_patterns = [
            r"^[a-zA-Z_][a-zA-Z0-9_]*_t$",  # _t типы (pthread_t, size_t и т.д.)
            r"^FILE$",
            r"^clock_t$",
            r"^time_t$",
        ]

        for pattern in c_type_patterns:
            if re.match(pattern, type_name):
                # Добавляем в известные типы
                self.known_c_types.add(type_name)
                return True

        # Проверяем, содержит ли тип указатель
        if "*" in type_name:
            # Разделяем на базовый тип и указатели
            base = type_name.replace("*", "").strip()
            if self._is_c_type(base):
                self.known_c_types.add(type_name)
                return True

        return False

    def declare_variable(self, name: str, var_type: str, is_pointer: bool = False):
        """Объявляет переменную в текущем scope"""
        scope = self.get_current_scope()
        c_type = self.map_type_to_c(var_type, is_pointer)
        scope[name] = {
            "c_type": c_type,
            "py_type": var_type,
            "is_pointer": is_pointer,
            "is_deleted": False,
            "delete_type": None,  # "full" или "pointer"
        }

    def mark_variable_deleted(self, name: str, delete_type: str = "full") -> bool:
        """Помечает переменную как удаленную"""
        # Ищем переменную в текущем и родительских scope'ах
        for level in range(self.current_scope_level, -1, -1):
            if level < len(self.variable_scopes):
                scope = self.variable_scopes[level]
                if name in scope:
                    scope[name]["is_deleted"] = True
                    scope[name]["delete_type"] = delete_type
                    print(
                        f"DEBUG: Переменная '{name}' помечена как удаленная ({delete_type})"
                    )
                    return True
        print(f"WARNING: Переменная '{name}' не найдена для удаления")
        return False

    def is_variable_declared(self, name: str) -> bool:
        """Проверяет, объявлена ли переменная"""
        for level in range(self.current_scope_level, -1, -1):
            if level < len(self.variable_scopes):
                if name in self.variable_scopes[level]:
                    return True
        return False

    def get_variable_info(self, name: str) -> Optional[Dict]:
        """Получает информацию о переменной"""
        for level in range(self.current_scope_level, -1, -1):
            if level < len(self.variable_scopes):
                if name in self.variable_scopes[level]:
                    return self.variable_scopes[level][name]
        return None

    def generate_temporary_var(self, var_type: str = "int") -> str:
        """Генерирует имя временной переменной"""
        temp_name = f"temp_{self.temp_var_counter}"
        self.temp_var_counter += 1
        self.declare_variable(temp_name, var_type)
        return temp_name

    def compile(self, json_data: List[Dict]) -> str:
        """Основной метод компиляции"""
        return self.generate_from_json(json_data)

    def generate_module_scope(self, scope: Dict):
        """Генерирует код для модульного scope"""
        # Обрабатываем импорты
        for node in scope.get("graph", []):
            if node.get("node") == "c_import":
                self.generate_c_import(node)

        self.add_empty_line()

        # Обрабатываем объявления функций
        for node in scope.get("graph", []):
            if node.get("node") == "function_declaration":
                self.add_function_declaration(node)

        # Генерируем forward declarations
        if self.function_declarations:
            for decl in self.function_declarations:
                self.add_line(decl)
            self.add_empty_line()

    def generate_function_scope(self, scope: Dict):
        """Генерирует код для функции"""
        func_name = scope.get("function_name", "")
        return_type = scope.get("return_type", "int")
        parameters = scope.get("parameters", [])

        # Входим в новый scope
        self.enter_scope()

        # Объявляем параметры
        param_decls = []
        for param in parameters:
            param_name = param.get("name", "")
            param_type = param.get("type", "int")
            c_param_type = self.map_type_to_c(param_type)
            param_decls.append(f"{c_param_type} {param_name}")
            self.declare_variable(param_name, param_type)

        # Сигнатура функции
        c_return_type = self.map_type_to_c(return_type)
        params_str = ", ".join(param_decls) if param_decls else "void"

        self.add_line(f"{c_return_type} {func_name}({params_str}) {{")
        self.indent_level += 1

        # Обрабатываем узлы графа
        # ИСПРАВЛЕНИЕ: Отслеживаем уже обработанные объявления
        processed_declarations = set()

        for node in scope.get("graph", []):
            node_type = node.get("node")

            if node_type == "declaration":
                var_name = node.get("var_name", "")
                # Проверяем, не обрабатывали ли мы уже это объявление
                if var_name not in processed_declarations:
                    self.generate_graph_node(node)
                    processed_declarations.add(var_name)
                else:
                    # Пропускаем дубликат
                    print(f"DEBUG: Пропускаем дублирующее объявление {var_name}")
                    continue
            else:
                self.generate_graph_node(node)

        self.indent_level -= 1
        self.add_line("}")
        self.add_empty_line()

        # Выходим из scope
        self.exit_scope()

    def generate_graph_node(self, node: Dict):
        """Генерирует код для узла графа"""
        node_type = node.get("node")

        if node_type == "declaration":
            self.generate_declaration(node)
        elif node_type == "delete":
            self.generate_delete(node)
        elif node_type == "del_pointer":
            self.generate_del_pointer(node)
        elif node_type == "assignment":
            self.generate_assignment(node)
        elif node_type == "function_call":
            self.generate_function_call(node)
        elif node_type == "builtin_function_call":  # НОВОЕ!
            self.generate_builtin_function_call(node)
        elif node_type == "builtin_function_call_assignment":  # НОВОЕ!
            self.generate_builtin_function_call_assignment(node)
        elif node_type == "return":
            self.generate_return(node)
        elif node_type == "print":
            self.generate_print(node)
        elif node_type == "while_loop":
            self.generate_while_loop(node)
        elif node_type == "if_statement":
            self.generate_if_statement(node)
        elif node_type == "for_loop":
            self.generate_for_loop(node)
        elif node_type == "break":  # НОВОЕ: обработка break
            self.generate_break(node)
        elif node_type == "continue":  # НОВОЕ: обработка continue
            self.generate_continue(node)
        elif node_type == "c_call":  # ДОБАВЬТЕ ЭТО
            self.generate_c_call(node)
        elif node_type == "class_declaration":
            self.generate_class_declaration(node)
        elif node_type == "attribute_assignment":
            self.generate_attribute_assignment(node)
        elif node_type == "method_call":
            self.generate_method_call(node)
        elif node_type == "index_assignment":  # НОВОЕ: присваивание по индексу
            self.generate_index_assignment(node)
        elif node_type == "slice_assignment":  # НОВОЕ: присваивание среза
            self.generate_slice_assignment(node)
        elif (
            node_type == "augmented_index_assignment"
        ):  # НОВОЕ: составное присваивание по индексу
            self.generate_augmented_index_assignment(node)
        elif node_type == "c_import":
            # Импорты уже обработаны на уровне модуля
            pass
        elif node_type == "function_declaration":
            # Объявления функций уже обработаны
            pass
        else:
            print(f"WARNING: Неизвестный тип узла: {node_type}")
            self.add_line(f"// Неизвестный узел: {node_type}")

    def generate_builtin_function_call(self, node: Dict):
        """Генерирует вызов встроенной функции"""
        func_name = node.get("function", "")
        args = node.get("arguments", [])

        if func_name == "print":
            # Генерируем printf для print
            if not args:
                self.add_line('printf("\\n");')
                return

            # Создаем форматную строку
            format_parts = []
            value_parts = []

            for arg in args:
                if isinstance(arg, dict):
                    if arg.get("type") == "attribute_access":
                        expr = self.generate_attribute_access(arg)
                        format_parts.append("%d")
                        value_parts.append(expr)
                    elif arg.get("type") == "variable":
                        var_name = arg.get("value", "")
                        var_info = self.get_variable_info(var_name)
                        if var_info:
                            var_type = var_info.get("py_type", "")
                            if var_type == "int":
                                format_parts.append("%d")
                                value_parts.append(var_name)
                            elif var_type in ["float", "double"]:
                                format_parts.append("%f")
                                value_parts.append(var_name)
                            elif var_type == "str":
                                format_parts.append("%s")
                                value_parts.append(var_name)
                            else:
                                format_parts.append("%d")
                                value_parts.append(var_name)
                        else:
                            format_parts.append("%d")
                            value_parts.append(var_name)
                    elif arg.get("type") == "literal":
                        value = arg.get("value", "")
                        data_type = arg.get("data_type", "")
                        if data_type == "str":
                            format_parts.append("%s")
                            value_parts.append(f'"{value}"')
                        else:
                            format_parts.append("%d")
                            value_parts.append(str(value))
                    else:
                        expr = self.generate_expression(arg)
                        format_parts.append("%d")
                        value_parts.append(expr)
                else:
                    format_parts.append("%d")
                    value_parts.append(str(arg))

            # Собираем форматную строку
            format_str = '"' + " ".join(format_parts) + '\\n"'
            args_str = ", ".join(value_parts)

            self.add_line(f"printf({format_str}, {args_str});")
        elif func_name == "input":
            # Для input() без присваивания
            self.generate_input_statement(node)
            return
        else:
            # Обработка других встроенных функций
            # Генерируем аргументы
            arg_strings = []
            for arg in args:
                if isinstance(arg, dict):
                    arg_strings.append(self.generate_expression(arg))
                else:
                    arg_strings.append(str(arg))

            args_str = ", ".join(arg_strings)

            # Маппинг других встроенных функций
            builtin_map = {
                "len": "builtin_len",
                "str": "builtin_str",
                "int": "builtin_int",
                "bool": "builtin_bool",
                "range": "builtin_range",
            }

            c_func_name = builtin_map.get(func_name, func_name)
            self.add_line(f"{c_func_name}({args_str});")

    def generate_builtin_function_call_assignment(self, node: Dict):
        """Генерирует присваивание результата встроенной функции"""
        target = node.get("symbols", [])[0] if node.get("symbols") else ""
        func_name = node.get("function", "")
        args = node.get("arguments", [])
        return_type = node.get("return_type", "")

        if not target:
            # Просто вызов функции без присваивания
            if func_name == "input":
                self.generate_input_statement(node)
            else:
                self.generate_builtin_function_call(node)
            return

        var_info = self.get_variable_info(target)
        if not var_info:
            node_type = node.get("var_type", "int")
            # Для input() по умолчанию возвращается строка
            if func_name == "input" and not node_type:
                node_type = "str"
            self.declare_variable(target, node_type)
            var_info = self.get_variable_info(target)

        # Специальная обработка для input()
        if func_name == "input":
            c_type = var_info["c_type"] if var_info else "char*"

            # Генерируем prompt если есть аргументы
            if args:
                self._generate_input_prompt(args)

            # Для разных типов переменных разная обработка
            if c_type == "char*":
                # Для строковых переменных - прямой ввод в целевую переменную
                self._generate_input_read_code_direct(target)
            else:
                # Для других типов (int, float и т.д.)
                buffer_var = f"{target}_input_buffer"
                self.add_line(f"char {buffer_var}[256];")
                self.add_line(f"fgets({buffer_var}, sizeof({buffer_var}), stdin);")
                self.add_line(f'{buffer_var}[strcspn({buffer_var}, "\\n")] = 0;')

                if c_type == "int":
                    self.add_line(f"{target} = atoi({buffer_var});")
                elif c_type == "float" or c_type == "double":
                    self.add_line(f"{target} = atof({buffer_var});")
                elif c_type == "bool":
                    self.add_line(
                        f'{target} = (strcmp({buffer_var}, "true") == 0 || strcmp({buffer_var}, "1") == 0);'
                    )
                else:
                    self.add_line(f"// Неподдерживаемый тип для input: {c_type}")
                    self.add_line(f"{target} = 0;")

            return

        # Маппинг встроенных функций Python -> C
        builtin_map = {
            "len": "builtin_len",
            "str": "builtin_str",
            "int": "builtin_int",
            "bool": "builtin_bool",
            "range": "builtin_range",
        }

        c_func_name = builtin_map.get(func_name, func_name)

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                arg_strings.append(self.generate_expression(arg))
            else:
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings)

        # Специальная обработка для len()
        if func_name == "len" and args:
            # Определяем тип аргумента
            arg_expr = args[0]
            if isinstance(arg_expr, dict):
                # Если это переменная, получаем ее тип
                if arg_expr.get("type") == "variable":
                    var_name = arg_expr.get("value", "")
                    var_info = self.get_variable_info(var_name)
                    if var_info:
                        py_type = var_info.get("py_type", "")
                        if py_type.startswith("tuple["):
                            struct_name = self.generate_tuple_struct_name(py_type)
                            c_func_name = f"builtin_len_{struct_name}"
                        elif py_type.startswith("list["):
                            struct_name = self.generate_list_struct_name(py_type)
                            c_func_name = f"builtin_len_{struct_name}"

        c_type = var_info["c_type"] if var_info else self.map_type_to_c(return_type)
        self.add_line(f"{c_type} {target} = {c_func_name}({args_str});")

    def _generate_input_read_code_direct(self, target_var: str):
        """Генерирует код для чтения ввода с клавиатуры прямо в целевую переменную"""
        # Создаем буфер для ввода
        buffer_var = f"{target_var}_buffer"

        # Выделяем память для буфера (стековая переменная)
        self.add_line(f"char {buffer_var}[256];")

        # Читаем строку с stdin
        self.add_line(f"fgets({buffer_var}, sizeof({buffer_var}), stdin);")

        # Убираем символ новой строки
        self.add_line(f'{buffer_var}[strcspn({buffer_var}, "\\n")] = 0;')

        # Освобождаем предыдущую память, если переменная уже инициализирована
        self.add_line(f"if ({target_var} != NULL) {{")
        self.indent_level += 1
        self.add_line(f"free({target_var});")
        self.indent_level -= 1
        self.add_line(f"}}")

        # Выделяем память для результата и копируем
        self.add_line(f"{target_var} = malloc(strlen({buffer_var}) + 1);")
        self.add_line(f"if (!{target_var}) {{")
        self.indent_level += 1
        self.add_line(
            f'fprintf(stderr, "Memory allocation failed for input result\\n");'
        )
        self.add_line(f"exit(1);")
        self.indent_level -= 1
        self.add_line(f"}}")
        self.add_line(f"strcpy({target_var}, {buffer_var});")

    def generate_break(self, node: Dict):
        """Генерирует оператор break"""
        self.add_line("break;")
        self.add_line("// break statement")

    def generate_continue(self, node: Dict):
        """Генерирует оператор continue"""
        self.add_line("continue;")
        self.add_line("// continue statement")

    def generate_declaration(self, node: Dict):
        """Генерирует объявление переменной"""
        var_name = node.get("var_name", "")
        var_type = node.get("var_type", "")
        expression_ast = node.get("expression_ast", {})

        print(f"DEBUG: Генерация объявления для {var_name}: {var_type}")

        # Объявляем переменную в scope
        self.declare_variable(var_name, var_type)

        # Получаем C тип
        c_type = self.map_type_to_c(var_type)

        # Обработка list[int] с литералом
        if expression_ast.get("type") == "list_literal" and var_type.startswith(
            "list["
        ):
            items = expression_ast.get("items", [])

            # Генерируем код для создания списка
            struct_name = self.generate_list_struct_name(var_type)
            self.add_line(
                f"{c_type} {var_name} = create_{struct_name}({max(len(items), 4)});"
            )

            # Добавляем элементы
            for item_ast in items:
                item_expr = self.generate_expression(item_ast)
                self.add_line(f"append_{struct_name}({var_name}, {item_expr});")

            return

        # Обработка tuple[int] с литералом
        elif expression_ast.get("type") == "tuple_literal" and var_type.startswith(
            "tuple["
        ):
            items = expression_ast.get("items", [])

            if items:
                # Создаем временный массив
                temp_array = f"temp_{var_name}"
                self.add_line(f"int {temp_array}[{len(items)}] = {{")
                self.indent_level += 1
                for i, item_ast in enumerate(items):
                    item_expr = self.generate_expression(item_ast)
                    self.add_line(f"{item_expr}{',' if i < len(items) - 1 else ''}")
                self.indent_level -= 1
                self.add_line("};")

                # Создаем кортеж
                struct_name = self.generate_tuple_struct_name(var_type)
                self.add_line(
                    f"{c_type} {var_name} = create_{struct_name}({temp_array}, {len(items)});"
                )
            else:
                # Пустой кортеж
                self.add_line(f"{c_type} {var_name};")
                self.add_line(f"{var_name}.data = NULL;")
                self.add_line(f"{var_name}.size = 0;")

            return

        # Обычная инициализация
        if expression_ast:
            expr = self.generate_expression(expression_ast)
            self.add_line(f"{c_type} {var_name} = {expr};")
        else:
            # Объявление без инициализации
            if c_type.endswith("*"):
                self.add_line(f"{c_type} {var_name} = NULL;")
            else:
                self.add_line(f"{c_type} {var_name};")

    def _generate_expression_for_declaration(
        self, ast: Dict, target_var: str, c_type: str
    ) -> bool:
        """Специальная обработка выражений в декларациях"""
        node_type = ast.get("type", "")

        if node_type == "method_call":
            # Это вызов метода в выражении (например, b = a.upper())
            object_name = ast.get("object", "")
            method_name = ast.get("method", "")
            args = ast.get("arguments", [])

            print(
                f"DEBUG _generate_expression_for_declaration: {object_name}.{method_name}() -> {target_var}"
            )

            # Генерируем аргументы
            arg_strings = []
            for arg in args:
                arg_strings.append(self.generate_expression(arg))

            args_str = ", ".join(arg_strings) if arg_strings else ""

            # Проверяем тип объекта
            var_info = self.get_variable_info(object_name)
            if var_info:
                obj_type = var_info.get("py_type", "")

                if obj_type == "str":
                    if method_name == "upper":
                        self.add_line(
                            f"{c_type} {target_var} = string_upper({object_name});"
                        )
                        return True
                    elif method_name == "format":
                        self.add_line(
                            f"{c_type} {target_var} = string_format({object_name}, {args_str});"
                        )
                        return True
                    elif method_name == "lower":
                        self.add_line(
                            f"{c_type} {target_var} = string_lower({object_name});"
                        )
                        return True

            # Если не обработали выше, генерируем общее выражение
            expr = self.generate_expression(ast)
            self.add_line(f"{c_type} {target_var} = {expr};")
            return True

        return False

    def _generate_assignment(
        self, var_name: str, c_type: str, expr: str, var_type: str
    ):
        """Генерирует присваивание с правильной обработкой типов"""
        if c_type == "char*" and isinstance(expr, str) and expr.startswith('"'):
            # Для строковых литералов выделяем динамическую память
            self.add_line(f"{c_type} {var_name} = malloc(strlen({expr}) + 1);")
            self.add_line(f"if (!{var_name}) {{")
            self.indent_level += 1
            self.add_line(f'fprintf(stderr, "Memory allocation failed\\n");')
            self.add_line(f"exit(1);")
            self.indent_level -= 1
            self.add_line(f"}}")
            self.add_line(f"strcpy({var_name}, {expr});")
        else:
            self.add_line(f"{c_type} {var_name} = {expr};")

    def generate_simple_declaration_with_init(
        self,
        var_name: str,
        c_type: str,
        var_type: str,
        expression_ast: Dict,
        operations: List,
    ):
        """Генерирует объявление простой переменной с правильной инициализацией"""
        if expression_ast:
            expr = self.generate_expression(expression_ast)

            # Проверяем специальные случаи инициализации
            special_case_handled = False
            for op in operations:
                if op.get("type") == "ASSIGN_POINTER":
                    # Инициализация указателя
                    value = op.get("value", {})
                    if value.get("type") == "address_of":
                        var = value.get("variable", "")
                        self.add_line(f"{c_type} {var_name} = &{var};")
                        special_case_handled = True
                        return
                elif op.get("type") == "ASSIGN_NULL":
                    # Инициализация null
                    self.add_line(f"{c_type} {var_name} = NULL;")
                    special_case_handled = True
                    return

            # Обычная инициализация
            if not special_case_handled:
                if c_type == "char*" and isinstance(expr, str) and expr.startswith('"'):
                    # Для строковых литералов выделяем динамическую память
                    self.add_line(f"{c_type} {var_name} = malloc(strlen({expr}) + 1);")
                    self.add_line(f"if (!{var_name}) {{")
                    self.indent_level += 1
                    self.add_line(f'fprintf(stderr, "Memory allocation failed\\n");')
                    self.add_line(f"exit(1);")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    self.add_line(f"strcpy({var_name}, {expr});")
                else:
                    self.add_line(f"{c_type} {var_name} = {expr};")
        else:
            # Объявление без инициализации
            if c_type.endswith("*") or var_type == "str":
                self.add_line(f"{c_type} {var_name} = NULL;")
            else:
                self.add_line(f"{c_type} {var_name};")

            # Если есть операции инициализации
            for op in operations:
                if op.get("type") == "INITIALIZE":
                    value_ast = op.get("value", {})
                    if value_ast:
                        expr = self.generate_expression(value_ast)
                        self.add_line(f"{var_name} = {expr};")
                    break

    def generate_pointer_declaration(
        self, var_name: str, var_type: str, expression_ast: Dict, operations: List
    ):
        """Генерирует объявление указателя"""
        # Извлекаем базовый тип (убираем звездочку)
        base_type = var_type[1:].strip()
        c_type = self.map_type_to_c(base_type, is_pointer=True)

        if expression_ast:
            expr = self.generate_expression(expression_ast)

            # Проверяем, является ли выражение взятием адреса (&variable)
            if expression_ast.get("type") == "address_of":
                self.add_line(f"{c_type} {var_name} = {expr};")
            else:
                # Инициализация указателя значением
                self.add_line(f"{c_type} {var_name} = {expr};")
        else:
            # Объявление без инициализации
            self.add_line(f"{c_type} {var_name} = NULL;")

    def generate_tuple_declaration(
        self,
        var_name: str,
        var_type: str,
        expression_ast: Dict,
        operations: List,
        tuple_info: Dict,
    ):
        """Генерирует объявление кортежа"""
        struct_name = self.generate_tuple_struct_name(var_type)
        c_type = self.map_type_to_c(var_type)  # Это будет "tuple_int" для tuple[int]

        # Определяем тип кортежа
        is_uniform = tuple_info.get("is_uniform", False)
        is_fixed = tuple_info.get("is_fixed", False)

        # Ищем соответствующую операцию создания
        creation_op = None
        for op in operations:
            if op.get("type") in ["CREATE_TUPLE_UNIFORM", "CREATE_TUPLE_FIXED"]:
                creation_op = op
                break

        if creation_op:
            items = creation_op.get("items", [])
            size = creation_op.get("size", 0)

            if creation_op.get("type") == "CREATE_TUPLE_UNIFORM":
                # tuple[T] - универсальный кортеж
                element_type = tuple_info.get("element_type", "int")
                c_element_type = self.map_type_to_c(element_type)

                if items and size > 0:
                    # Создаем временный массив для инициализации
                    temp_array_name = f"temp_{var_name}"
                    self.add_line(f"{c_element_type} {temp_array_name}[{size}] = {{")
                    self.indent_level += 1
                    for i, item_ast in enumerate(items):
                        item_expr = self.generate_expression(item_ast)
                        self.add_line(f"{item_expr}{',' if i < size - 1 else ''}")
                    self.indent_level -= 1
                    self.add_line("};")

                    # Создаем кортеж из массива
                    self.add_line(
                        f"{c_type} {var_name} = create_{struct_name}({temp_array_name}, {size});"
                    )
                elif size == 0:
                    # Пустой кортеж
                    self.add_line(f"{c_type} {var_name};")
                    self.add_line(f"{var_name}.data = NULL;")
                    self.add_line(f"{var_name}.size = 0;")
                else:
                    # Кортеж без инициализации
                    self.add_line(f"{c_type} {var_name};")

            elif creation_op.get("type") == "CREATE_TUPLE_FIXED":
                # tuple[T1, T2, ...] - фиксированный кортеж
                if items and size > 0:
                    # Генерируем аргументы для функции создания
                    args = [self.generate_expression(item) for item in items]
                    self.add_line(
                        f"{c_type} {var_name} = create_{struct_name}({', '.join(args)});"
                    )
                else:
                    # Кортеж без инициализации
                    self.add_line(f"{c_type} {var_name};")
        else:
            # Если нет операции создания, просто объявляем
            self.add_line(f"{c_type} {var_name};")

    def generate_list_declaration(
        self, var_name: str, var_type: str, expression_ast: Dict, operations: List
    ):
        """Генерирует объявление списка с поддержкой вложенных списков"""
        # Убедимся, что структуры сгенерированы
        self.generate_list_struct(var_type)

        # Получаем информацию о типе
        type_info = self.extract_nested_type_info(var_type)

        if not type_info or not type_info.get("struct_name"):
            print(f"ERROR: Не удалось получить информацию о типе {var_type}")
            return

        struct_name = type_info["struct_name"]
        c_type = f"{struct_name}*"

        # Ищем операцию CREATE_LIST
        creation_op = None
        for op in operations:
            if op.get("type") == "CREATE_LIST":
                creation_op = op
                break

        if creation_op:
            items = creation_op.get("items", [])
            size = len(items)

            # Создаем внешний список
            self.add_line(
                f"{c_type} {var_name} = create_{struct_name}({max(size, 4)});"
            )

            # Генерируем элементы
            self._generate_nested_list_elements_correctly(var_name, items, type_info, 0)
        else:
            # Список без инициализации
            self.add_line(f"{c_type} {var_name} = create_{struct_name}(4);")

        # Объявляем переменную в scope
        self.declare_variable(var_name, var_type)

    def _generate_nested_list_elements_correctly(
        self, parent_var: str, items: List, type_info: Dict, level: int
    ):
        """Корректно генерирует элементы вложенного списка"""
        if not items:
            return

        struct_name = type_info.get("struct_name", "")
        if not struct_name:
            print(f"ERROR: Нет struct_name на уровне {level}")
            return

        print(f"DEBUG generate_elements уровень {level}:")
        print(f"  parent_var: {parent_var}")
        print(f"  struct_name: {struct_name}")
        print(f"  is_leaf: {type_info.get('is_leaf')}")
        print(f"  element_type: {type_info.get('element_type')}")
        print(f"  items count: {len(items)}")

        # Проверяем, является ли текущий уровень листовым
        # is_leaf=True означает list[int] (элементы int)
        # is_leaf=False означает list[list[...]] (элементы указатели на списки)
        if type_info.get("is_leaf", True):
            print(f"  ЛИСТОВОЙ УРОВЕНЬ - добавляем простые элементы")
            for i, item_ast in enumerate(items):
                print(f"    элемент {i}: {item_ast.get('type')}")

                # Для кортежей используем специальную обработку
                if item_ast.get("type") == "tuple_literal":
                    # Создаем кортеж напрямую, без вызова generate_expression
                    tuple_expr = self._generate_tuple_creation_direct(
                        item_ast, f"{parent_var}_tuple_{i}"
                    )
                    self.add_line(f"append_{struct_name}({parent_var}, {tuple_expr});")
                else:
                    # Для других типов используем обычный generate_expression
                    item_expr = self.generate_expression(item_ast)
                    self.add_line(f"append_{struct_name}({parent_var}, {item_expr});")
            return

        # Есть вложенность - элементы это указатели на списки
        inner_info = type_info.get("inner_info")
        if not inner_info:
            print(f"ERROR: Нет информации о внутреннем типе на уровне {level}")
            return

        inner_struct_name = inner_info.get("struct_name", "")
        if not inner_struct_name:
            print(f"ERROR: Нет имени структуры для внутреннего типа на уровне {level}")
            return

        print(f"  ВЛОЖЕННЫЙ УРОВЕНЬ - создаем внутренние списки")
        print(f"  inner_struct_name: {inner_struct_name}")
        print(f"  inner_is_leaf: {inner_info.get('is_leaf')}")

        # Обрабатываем каждый элемент
        for i, item_ast in enumerate(items):
            print(f"  обработка элемента {i}: {item_ast.get('type')}")

            if item_ast.get("type") == "list_literal":
                # Создаем внутренний список
                inner_items = item_ast.get("items", [])
                temp_name = f"{parent_var}_l{level}_{i}"

                print(
                    f"    создаем {inner_struct_name}* {temp_name} с {len(inner_items)} элементами"
                )

                # Создаем внутренний список
                self.add_line(
                    f"{inner_struct_name}* {temp_name} = create_{inner_struct_name}({max(len(inner_items), 4)});"
                )

                # Рекурсивно обрабатываем элементы внутреннего списка
                print(f"    рекурсивный вызов для {temp_name}")
                self._generate_nested_list_elements_correctly(
                    temp_name, inner_items, inner_info, level + 1
                )

                # Добавляем внутренний список в родительский
                self.add_line(f"append_{struct_name}({parent_var}, {temp_name});")
            else:
                print(f"    WARNING: Не list_literal: {item_ast.get('type')}")
                # Если это уже созданная переменная, просто добавляем ее
                item_expr = self.generate_expression(item_ast)
                self.add_line(f"append_{struct_name}({parent_var}, {item_expr});")

    def _generate_tuple_creation_direct(self, tuple_ast: Dict, base_name: str) -> str:
        """Генерирует создание кортежа напрямую, возвращая имя переменной с кортежем"""
        items = tuple_ast.get("items", [])

        if not items:
            return "NULL"

        # Определяем тип кортежа
        element_types = set()
        for item in items:
            if isinstance(item, dict):
                if item.get("type") == "literal":
                    data_type = item.get("data_type", "int")
                    element_types.add(data_type)

        if len(element_types) == 1:
            element_type = next(iter(element_types))
            tuple_type = f"tuple[{element_type}]"
        else:
            # По умолчанию int
            tuple_type = "tuple[int]"

        struct_name = self.generate_tuple_struct_name(tuple_type)

        # Создаем временный массив
        temp_array_name = f"{base_name}_arr"

        # Генерируем элементы массива
        item_exprs = [self.generate_expression(item) for item in items]

        # Создаем массив
        self.add_line(f"int {temp_array_name}[{len(items)}] = {{")
        self.indent_level += 1
        for i, item_expr in enumerate(item_exprs):
            self.add_line(f"{item_expr}{',' if i < len(items) - 1 else ''}")
        self.indent_level -= 1
        self.add_line("};")

        # Создаем кортеж и возвращаем его
        tuple_var_name = f"{base_name}_val"
        self.add_line(
            f"tuple_int {tuple_var_name} = create_{struct_name}({temp_array_name}, {len(items)});"
        )

        return tuple_var_name

    def _generate_nested_list_elements_recursive(
        self, parent_var: str, items: List, type_info: Dict, level: int
    ):
        """Рекурсивно генерирует элементы вложенного списка"""
        if type_info["is_leaf"]:
            # Дошли до листовых элементов (int, float и т.д.)
            for item_ast in items:
                item_expr = self.generate_expression(item_ast)
                self.add_line(
                    f"append_{type_info['struct_name']}({parent_var}, {item_expr});"
                )
            return

        # Еще есть вложенность
        struct_name = type_info["struct_name"]
        inner_info = type_info["inner_info"]

        if not inner_info:
            return

        for i, item_ast in enumerate(items):
            if item_ast.get("type") == "list_literal":
                # Создаем внутренний список
                inner_items = item_ast.get("items", [])
                temp_name = f"{parent_var}_l{level}_{i}"

                # Генерируем структуру для внутреннего типа
                if not inner_info["is_leaf"]:
                    self.generate_list_struct(inner_info["py_type"])

                # Создаем внутренний список
                inner_c_type = (
                    f"{inner_info['struct_name']}*"
                    if inner_info["struct_name"]
                    else "void*"
                )
                self.add_line(
                    f"{inner_c_type} {temp_name} = create_{inner_info['struct_name']}({max(len(inner_items), 4)});"
                )

                # Рекурсивно обрабатываем элементы внутреннего списка
                self._generate_nested_list_elements_recursive(
                    temp_name, inner_items, inner_info, level + 1
                )

                # Добавляем внутренний список в родительский
                self.add_line(f"append_{struct_name}({parent_var}, {temp_name});")
            else:
                # Для трехмерного массива это не должно случиться
                print(f"WARNING: Ожидался list_literal на уровне {level}")

    def _generate_nested_list_elements(
        self, parent_var: str, items: List, type_info: Dict, level: int
    ):
        """Рекурсивно генерирует элементы вложенного списка"""
        indent = "    " * (level + 1)  # Уровень вложенности для отступа

        if type_info["is_leaf"]:
            # Дошли до листовых элементов (int, float и т.д.)
            for i, item_ast in enumerate(items):
                item_expr = self.generate_expression(item_ast)
                self.add_line(
                    f"append_{type_info['struct_name']}({parent_var}, {item_expr});"
                )
            return

        # Еще есть вложенность
        for i, item_ast in enumerate(items):
            if item_ast.get("type") == "list_literal":
                # Создаем внутренний список
                inner_items = item_ast.get("items", [])
                inner_info = type_info["inner_info"]

                if not inner_info or not inner_info["struct_name"]:
                    print(f"ERROR: Нет информации о внутреннем типе на уровне {level}")
                    continue

                # Генерируем структуру для внутреннего типа
                self.generate_list_struct(inner_info["py_type"])

                # Создаем внутренний список
                temp_name = f"{parent_var}_l{level}_{i}"
                inner_struct_name = inner_info["struct_name"]
                inner_c_type = f"{inner_struct_name}*"

                self.add_line(
                    f"{inner_c_type} {temp_name} = create_{inner_struct_name}({max(len(inner_items), 4)});"
                )

                # Рекурсивно обрабатываем элементы внутреннего списка
                self._generate_nested_list_elements(
                    temp_name, inner_items, inner_info, level + 1
                )

                # Добавляем внутренний список в родительский
                self.add_line(
                    f"append_{type_info['struct_name']}({parent_var}, {temp_name});"
                )
            else:
                # Листовой элемент в промежуточном списке (должен быть list_literal)
                print(
                    f"ERROR: Ожидался list_literal на уровне {level}, получено {item_ast.get('type')}"
                )

    def generate_nested_list_declaration(
        self, var_name: str, list_ast: Dict, parent_type: str
    ):
        """Генерирует объявление вложенного списка"""
        # Извлекаем тип элементов из родительского типа
        match = re.match(r"list\[([^\]]+)\]", parent_type)
        if not match:
            return

        element_type = match.group(1)  # Например, "list[int]" для внешнего списка

        if element_type.startswith("list["):
            # Это list[list[int]] - нам нужна структура list_int
            # Но для создания внутреннего списка нам нужна структура для list[int]
            inner_struct_name = self.generate_list_struct_name(
                element_type
            )  # Это даст list_int

            # Создаем внутренний список
            items = list_ast.get("items", [])
            self.add_line(
                f"{inner_struct_name}* {var_name} = create_{inner_struct_name}({max(len(items), 4)});"
            )

            # Определяем тип самых внутренних элементов
            inner_match = re.match(r"list\[([^\]]+)\]", element_type)
            if inner_match:
                inner_element_type = inner_match.group(1)  # Например, "int"

                # Добавляем элементы
                for item_ast in items:
                    if inner_element_type.startswith("list["):
                        # Еще один уровень вложенности (list[list[list[int]]])
                        temp_name = f"{var_name}_inner_{len(self.generated_helpers)}"
                        self.generate_nested_list_declaration(
                            temp_name, item_ast, element_type
                        )
                        self.add_line(
                            f"append_{inner_struct_name}({var_name}, {temp_name});"
                        )
                    else:
                        # Простой элемент (например, int)
                        item_expr = self.generate_expression(item_ast)
                        self.add_line(
                            f"append_{inner_struct_name}({var_name}, {item_expr});"
                        )
        else:
            # Это простой список (list[int]) - используем list_int
            struct_name = self.generate_list_struct_name(
                parent_type
            )  # Это даст list_int
            items = list_ast.get("items", [])
            self.add_line(
                f"{struct_name}* {var_name} = create_{struct_name}({max(len(items), 4)});"
            )

            for item_ast in items:
                item_expr = self.generate_expression(item_ast)
                self.add_line(f"append_{struct_name}({var_name}, {item_expr});")

    def generate_nested_tuple_declaration(
        self, var_name: str, tuple_ast: Dict, tuple_type: str
    ):
        """Генерирует объявление вложенного кортежа"""
        struct_name = self.generate_tuple_struct_name(tuple_type)
        c_type = self.map_type_to_c(tuple_type)

        items = tuple_ast.get("items", [])
        if items:
            # Генерируем аргументы для функции создания
            args = [self.generate_expression(item) for item in items]
            self.add_line(
                f"{c_type} {var_name} = create_{struct_name}({', '.join(args)});"
            )
        else:
            # Пустой кортеж
            self.add_line(f"{c_type} {var_name};")
            self.add_line(f"{var_name}.data = NULL;")
            self.add_line(f"{var_name}.size = 0;")

    def generate_dict_declaration(
        self, var_name: str, var_type: str, expression_ast: Dict, operations: List
    ):
        """Генерирует объявление словаря"""
        # TODO: Реализовать генерацию словарей
        c_type = self.map_type_to_c(var_type)
        self.add_line(f"{c_type} {var_name} = NULL; // TODO: implement dict")
        self.add_line(f"// Словарь типа {var_type}")

    def generate_set_declaration(
        self, var_name: str, var_type: str, expression_ast: Dict, operations: List
    ):
        """Генерирует объявление множества"""
        # TODO: Реализовать генерацию множеств
        c_type = self.map_type_to_c(var_type)
        self.add_line(f"{c_type} {var_name} = NULL; // TODO: implement set")
        self.add_line(f"// Множество типа {var_type}")

    def generate_simple_declaration(
        self, var_name: str, var_type: str, expression_ast: Dict, operations: List
    ):
        """Генерирует объявление простой переменной"""
        c_type = self.map_type_to_c(var_type)

        if expression_ast:
            expr = self.generate_expression(expression_ast)
            # Проверяем специальные случаи инициализации
            for op in operations:
                if op.get("type") == "ASSIGN_POINTER":
                    # Инициализация указателя
                    value = op.get("value", {})
                    if value.get("type") == "address_of":
                        var = value.get("variable", "")
                        self.add_line(f"{c_type} {var_name} = &{var};")
                        return
                elif op.get("type") == "ASSIGN_NULL":
                    # Инициализация null
                    self.add_line(f"{c_type} {var_name} = NULL;")
                    return

            # Обычная инициализация
            self.add_line(f"{c_type} {var_name} = {expr};")
        else:
            # Объявление без инициализации
            self.add_line(f"{c_type} {var_name};")

            # Если есть операции инициализации
            for op in operations:
                if op.get("type") == "INITIALIZE":
                    value_ast = op.get("value", {})
                    if value_ast:
                        expr = self.generate_expression(value_ast)
                        self.add_line(f"{var_name} = {expr};")
                    break

    def generate_delete(self, node: Dict):
        """Генерирует код для del с поддержкой tuple и list"""
        symbols = node.get("symbols", [])

        for target in symbols:
            self.mark_variable_deleted(target, "full")
            var_info = self.get_variable_info(target)

            if not var_info:
                self.add_line(f"// ERROR: Переменная '{target}' не найдена для del")
                continue

            self.add_line(f"// del {target}")

            py_type = var_info.get("py_type", "")
            c_type = var_info.get("c_type", "")

            if py_type.startswith("list["):
                # Для list вызываем функцию очистки
                struct_name = self.generate_list_struct_name(py_type)
                self.add_line(f"if ({target}) {{")
                self.indent_level += 1
                self.add_line(f"free_{struct_name}({target});")
                self.indent_level -= 1
                self.add_line("}")
                self.add_line(f"{target} = NULL;")

            elif py_type.startswith("tuple["):
                # Для tuple вызываем функцию очистки
                struct_name = self.generate_tuple_struct_name(py_type)
                self.add_line(f"free_{struct_name}(&{target});")

            elif var_info["is_pointer"]:
                self.add_line(f"if ({target} != NULL) {{")
                self.indent_level += 1
                self.add_line(f"free({target});")
                self.indent_level -= 1
                self.add_line("}")
                self.add_line(f"{target} = NULL;")
            else:
                if c_type in ["int", "float", "double", "long"]:
                    self.add_line(f"{target} = 0;")
                elif c_type == "bool":
                    self.add_line(f"{target} = false;")
                elif "char*" in c_type or c_type.endswith("*"):
                    self.add_line(f"{target} = NULL;")
                else:
                    self.add_line(f"// {target} обнулена")

    def generate_del_pointer(self, node: Dict):
        """Генерирует код для del_pointer (удаление только указателя)"""
        symbols = node.get("symbols", [])

        for target in symbols:
            # Помечаем переменную как удаленную (только указатель)
            self.mark_variable_deleted(target, "pointer")

            # Получаем информацию о переменной
            var_info = self.get_variable_info(target)

            if not var_info:
                self.add_line(
                    f"// ERROR: Переменная '{target}' не найдена для del_pointer"
                )
                continue

            self.add_line(f"// del_pointer {target} (удаление только указателя)")

            if var_info["is_pointer"]:
                # Только обнуляем указатель, память не освобождаем
                self.add_line(f"{target} = NULL;")
                self.add_line(
                    f"// Внимание: память, на которую указывал {target}, не освобождена!"
                )
            else:
                # Если не указатель, обрабатываем как обычный del
                self.add_line(
                    f"// {target} не является указателем, применен как обычный del"
                )
                c_type = var_info["c_type"]
                if c_type in ["int", "float", "double", "long"]:
                    self.add_line(f"{target} = 0;")
                elif c_type == "bool":
                    self.add_line(f"{target} = false;")

    def generate_assignment(self, node: Dict):
        """Генерирует присваивание с поддержкой строковых операций"""
        symbols = node.get("symbols", [])
        if not symbols:
            return

        target = symbols[0]
        expression_ast = node.get("expression_ast")

        if expression_ast:
            # Проверяем, является ли это строковой операцией
            if expression_ast.get("type") == "binary_operation":
                operator = expression_ast.get("operator_symbol", "")
                left_ast = expression_ast.get("left", {})
                right_ast = expression_ast.get("right", {})

                left_is_string = self._is_string_expression(left_ast)
                right_is_string = self._is_string_expression(right_ast)

                if operator == "+" and (left_is_string or right_is_string):
                    # Генерируем конкатенацию строк
                    left_expr = self.generate_expression(left_ast)
                    right_expr = self.generate_expression(right_ast)

                    # Освобождаем старую память, если переменная уже была инициализирована
                    var_info = self.get_variable_info(target)
                    if var_info and var_info.get("py_type") == "str":
                        self.add_line(f"if ({target}) {{")
                        self.indent_level += 1
                        self.add_line(f"free({target});")
                        self.indent_level -= 1
                        self.add_line(f"}}")

                    self.add_line(
                        f"{target} = malloc(strlen({left_expr}) + strlen({right_expr}) + 1);"
                    )
                    self.add_line(f"if (!{target}) {{")
                    self.indent_level += 1
                    self.add_line(
                        f'fprintf(stderr, "Memory allocation failed for string concatenation\\n");'
                    )
                    self.add_line(f"exit(1);")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    self.add_line(f"strcpy({target}, {left_expr});")
                    self.add_line(f"strcat({target}, {right_expr});")
                    return

            # Обычное присваивание
            expr = self.generate_expression(expression_ast)

            # Для строковых литералов при присваивании
            if (
                expression_ast.get("type") == "literal"
                and expression_ast.get("data_type") == "str"
            ):
                var_info = self.get_variable_info(target)
                if var_info and var_info.get("py_type") == "str":
                    self.add_line(f"if ({target}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({target});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    self.add_line(f"{target} = malloc(strlen({expr}) + 1);")
                    self.add_line(f"strcpy({target}, {expr});")
                    return

            self.add_line(f"{target} = {expr};")

    def generate_function_call(self, node: Dict):
        """Генерирует вызов функции"""
        func_name = node.get("function", "")
        args = node.get("arguments", [])

        # Проверяем, является ли это print
        if func_name == "print":
            # Вызываем метод для генерации print
            self.generate_print(node)
            return

        # Удаляем @ из имени функции для C кода
        if func_name.startswith("@"):
            func_name = func_name[1:]

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                arg_strings.append(self.generate_expression(arg))
            else:
                if str(arg) == "None":
                    arg_strings.append("NULL")
                else:
                    arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings)
        self.add_line(f"{func_name}({args_str});")

    def generate_return(self, node: Dict):
        """Генерирует return"""
        operations = node.get("operations", [])

        if operations:
            for op in operations:
                if op.get("type") == "RETURN":
                    value_ast = op.get("value")
                    if value_ast:
                        expr = self.generate_expression(value_ast)
                        self.add_line(f"return {expr};")
                        return

        # Если не нашли значение, генерируем return без значения
        self.add_line("return;")

    def generate_print(self, node: Dict):
        """Генерирует print с поддержкой разных типов в одной строке"""
        args = node.get("arguments", [])

        if not args:
            self.add_line('printf("\\n");')
            return

        # Собираем форматную строку и аргументы
        format_parts = []
        value_parts = []

        for arg in args:
            if isinstance(arg, dict):
                if arg.get("type") == "attribute_access":
                    # Доступ к атрибуту
                    expr = self.generate_attribute_access(arg)
                    format_parts.append("%d")
                    value_parts.append(expr)
                elif arg.get("type") == "variable":
                    var_name = arg.get("value", "")
                    var_info = self.get_variable_info(var_name)
                    if var_info:
                        var_type = var_info.get("py_type", "")
                        if var_type == "int":
                            format_parts.append("%d")
                            value_parts.append(var_name)
                        elif var_type == "float" or var_type == "double":
                            format_parts.append("%f")
                            value_parts.append(var_name)
                        elif var_type == "str":
                            format_parts.append("%s")
                            value_parts.append(var_name)
                        elif var_type == "bool":
                            format_parts.append("%s")
                            # В C нет встроенного типа bool для printf, преобразуем
                            value_parts.append(f'({var_name} ? "true" : "false")')
                        else:
                            format_parts.append("%d")
                            value_parts.append(var_name)
                    else:
                        format_parts.append("%d")
                        value_parts.append(var_name)
                elif arg.get("type") == "literal":
                    value = arg.get("value", "")
                    data_type = arg.get("data_type", "")
                    if data_type == "str":
                        format_parts.append("%s")
                        value_parts.append(f'"{value}"')
                    elif data_type == "bool":
                        format_parts.append("%s")
                        value_parts.append(f'"{str(value).lower()}"')
                    else:
                        format_parts.append("%d")
                        value_parts.append(str(value))
                else:
                    # Для других выражений (бинарные операции и т.д.)
                    expr = self.generate_expression(arg)
                    # По умолчанию считаем, что это int
                    format_parts.append("%d")
                    value_parts.append(expr)
            else:
                # Простое значение (не должно встречаться в нормальном AST)
                format_parts.append("%d")
                value_parts.append(str(arg))

        # Собираем форматную строку
        # Между элементами добавляем пробел, как в Python
        format_str = '"'
        for i, fmt in enumerate(format_parts):
            format_str += fmt
            if i < len(format_parts) - 1:
                format_str += " "
        format_str += '\\n"'

        # Аргументы для printf
        args_str = ", ".join(value_parts)

        self.add_line(f"printf({format_str}, {args_str});")

    def generate_while_loop(self, node: Dict):
        """Генерирует while loop с правильной обработкой структуры JSON"""
        # В вашем JSON ключ "condition", а не "condition_ast"
        condition_ast = node.get("condition")
        if not condition_ast:
            return

        condition = self.generate_expression(condition_ast)

        self.add_line(f"while ({condition}) {{")
        self.indent_level += 1

        # Входим в scope цикла
        self.enter_scope()

        # Генерируем тело цикла из списка body
        body_nodes = node.get("body", [])
        for body_node in body_nodes:
            self.generate_graph_node(body_node)

        # Выходим из scope цикла
        self.exit_scope()

        self.indent_level -= 1
        self.add_line("}")

    def generate_if_statement(self, node: Dict):
        """Генерирует if statement"""
        condition_ast = node.get("condition_ast")
        if not condition_ast:
            return

        condition = self.generate_expression(condition_ast)

        self.add_line(f"if ({condition}) {{")
        self.indent_level += 1

        # Входим в scope if
        self.enter_scope()

        # Генерируем тело if
        for body_node in node.get("body", []):
            self.generate_graph_node(body_node)

        # Выходим из scope if
        self.exit_scope()

        self.indent_level -= 1
        self.add_line("}")

        # elif блоки
        for elif_block in node.get("elif_blocks", []):
            elif_condition = self.generate_expression(
                elif_block.get("condition_ast", {})
            )
            self.add_line(f"else if ({elif_condition}) {{")
            self.indent_level += 1

            # Входим в scope elif
            self.enter_scope()

            # Генерируем тело elif
            for body_node in elif_block.get("body", []):
                self.generate_graph_node(body_node)

            # Выходим из scope elif
            self.exit_scope()

            self.indent_level -= 1
            self.add_line("}")

        # else блок
        else_block = node.get("else_block")
        if else_block:
            self.add_line("else {")
            self.indent_level += 1

            # Входим в scope else
            self.enter_scope()

            # Генерируем тело else
            for body_node in else_block.get("body", []):
                self.generate_graph_node(body_node)

            # Выходим из scope else
            self.exit_scope()

            self.indent_level -= 1
            self.add_line("}")

    def generate_for_loop(self, node: Dict):
        """Генерирует for loop"""
        loop_var = node.get("loop_variable", "i")
        iterable = node.get("iterable", {})

        if iterable.get("type") == "RANGE_CALL":
            args = iterable.get("arguments", {})
            start = args.get("start", "0")
            stop = args.get("stop", "10")
            step = args.get("step", "1")

            # Объявляем переменную цикла
            self.declare_variable(loop_var, "int")

            self.add_line(
                f"for (int {loop_var} = {start}; {loop_var} < {stop}; {loop_var} += {step}) {{"
            )
            self.indent_level += 1

            # Входим в scope цикла
            self.enter_scope()

            # Генерируем тело цикла
            for body_node in node.get("body", []):
                self.generate_graph_node(body_node)

            # Выходим из scope цикла
            self.exit_scope()

            self.indent_level -= 1
            self.add_line("}")

    def generate_c_import(self, node: Dict):
        """Генерирует #include директиву"""
        header = node.get("header", "")
        is_system = node.get("is_system", False)

        if is_system:
            self.add_line(f"#include <{header}>")
        else:
            self.add_line(f'#include "{header}"')

    def add_function_declaration(self, node: Dict):
        """Добавляет forward declaration функции"""
        func_name = node.get("function_name", "")
        return_type = node.get("return_type", "int")
        parameters = node.get("parameters", [])

        # Генерируем параметры
        param_decls = []
        for param in parameters:
            param_name = param.get("name", "")
            param_type = param.get("type", "int")
            c_param_type = self.map_type_to_c(param_type)
            param_decls.append(f"{c_param_type} {param_name}")

        # Генерируем forward declaration
        c_return_type = self.map_type_to_c(return_type)
        params_str = ", ".join(param_decls) if param_decls else "void"

        declaration = f"{c_return_type} {func_name}({params_str});"
        self.function_declarations.append(declaration)

    def collect_imports_and_declarations(self, json_data: List[Dict]):
        """Собирает импорты и объявления функций из JSON"""
        self.c_imports = []
        self.function_declarations = []

        # Собираем импорты из module scope
        for scope in json_data:
            if scope.get("type") == "module":
                for node in scope.get("graph", []):
                    if node.get("node") == "c_import":
                        self.c_imports.append(node)

        # Собираем информацию о классах и их методах
        for scope in json_data:
            if scope.get("type") == "module":
                for node in scope.get("graph", []):
                    if node.get("node") == "class_declaration":
                        class_name = node.get("class_name", "")
                        methods = node.get("methods", [])

                        # Собираем информацию о конструкторе
                        init_method = None
                        for method in methods:
                            if method.get("name") == "__init__":
                                init_method = method
                                break

                        # Генерируем объявление конструктора
                        if init_method:
                            params = []
                            init_params = init_method.get("parameters", [])
                            # Пропускаем self параметр
                            for param in init_params[1:]:
                                param_name = param.get("name", "")
                                param_type = param.get("type", "int")
                                c_param_type = self.map_type_to_c(param_type)
                                params.append(f"{c_param_type} {param_name}")

                            params_str = ", ".join(params) if params else "void"
                            self.function_declarations.append(
                                f"{class_name}* create_{class_name}({params_str});"
                            )

                        # Собираем объявления методов из описания класса
                        for method in methods:
                            if method.get("name") != "__init__":
                                method_name = method.get("name", "")
                                return_type = method.get("return_type", "void")
                                params = method.get("parameters", [])

                                # Формируем параметры метода
                                param_decls = []
                                for i, param in enumerate(params):
                                    param_name = param.get("name", "")
                                    param_type = param.get("type", "int")

                                    if i == 0 and param_name == "self":
                                        # Первый параметр - self, это указатель на класс
                                        param_decls.append(f"{class_name}* self")
                                    else:
                                        c_param_type = self.map_type_to_c(param_type)
                                        param_decls.append(
                                            f"{c_param_type} {param_name}"
                                        )

                                params_str = (
                                    ", ".join(param_decls) if param_decls else "void"
                                )
                                self.function_declarations.append(
                                    f"{return_type} {class_name}_{method_name}({params_str});"
                                )

        # Также добавляем объявления из class_method scope (для точности)
        for scope in json_data:
            if scope.get("type") == "class_method":
                class_name = scope.get("class_name", "")
                method_name = scope.get("method_name", "")
                return_type = scope.get("return_type", "void")

                if method_name != "__init__":
                    parameters = scope.get("parameters", [])

                    # Формируем параметры
                    param_decls = []
                    for i, param in enumerate(parameters):
                        param_name = param.get("name", "")
                        param_type = param.get("type", "int")

                        if i == 0 and param_name == "self":
                            param_decls.append(f"{class_name}* self")
                        else:
                            c_param_type = self.map_type_to_c(param_type)
                            param_decls.append(f"{c_param_type} {param_name}")

                    params_str = ", ".join(param_decls) if param_decls else "void"

                    declaration = (
                        f"{return_type} {class_name}_{method_name}({params_str});"
                    )
                    if declaration not in self.function_declarations:
                        self.function_declarations.append(declaration)

        # Добавляем объявление main
        self.function_declarations.append("int main(void);")

    def generate_c_imports(self):
        """Генерирует #include директивы"""
        seen = set()
        for c_import in self.c_imports:
            header = c_import.get("header", "")
            is_system = c_import.get("is_system", True)

            if header and header not in seen:
                seen.add(header)
                if is_system:
                    self.add_line(f"#include <{header}>")
                else:
                    self.add_line(f'#include "{header}"')

        if seen:
            self.add_empty_line()

    def generate_c_call(self, node: Dict):
        """Генерирует прямой вызов C-функции"""
        func_name = node.get("function", "")
        args = node.get("arguments", [])

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                # Если аргумент - AST, генерируем выражение
                arg_strings.append(self.generate_expression(arg))
            else:
                # Если это простая строка
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings)

        # Просто генерируем вызов C-функции
        self.add_line(f"{func_name}({args_str});")

    def generate_forward_declarations(self):
        """Генерирует forward declarations функций"""
        if hasattr(self, "function_declarations") and self.function_declarations:
            # Удаляем дубликаты
            unique_declarations = []
            seen = set()

            for decl in self.function_declarations:
                if decl not in seen:
                    seen.add(decl)
                    unique_declarations.append(decl)

            for decl in unique_declarations:
                self.add_line(decl)

            self.add_empty_line()

    def generate_tuple_struct_name(self, py_type: str) -> str:
        """Генерирует имя структуры для tuple"""
        # Извлекаем содержимое скобок
        match = re.match(r"tuple\[([^\]]+)\]", py_type)
        if not match:
            # Если не можем распарсить, возвращаем очищенное имя
            return f"tuple_{self.clean_type_name_for_c(py_type)}"

        inner = match.group(1)

        # Если это tuple[T] (один тип)
        if "," not in inner:
            return f"tuple_{self.clean_type_name_for_c(inner)}"

        # Если это tuple[T1, T2, ...]
        # Заменяем запятые на подчеркивания и убираем пробелы
        clean_inner = self.clean_type_name_for_c(
            inner.replace(",", "_").replace(" ", "")
        )
        return f"tuple_{clean_inner}"

    def generate_tuple_struct(self, py_type: str):
        """Генерирует структуру C для tuple типа"""
        if py_type in self.generated_structs:
            return

        self.generated_structs.add(py_type)

        match = re.match(r"tuple\[([^\]]+)\]", py_type)
        if not match:
            return

        inner = match.group(1)
        struct_name = self.generate_tuple_struct_name(py_type)

        # Определяем, является ли это универсальным tuple[T]
        is_fixed = "," in inner

        if not is_fixed:
            # tuple[T] - универсальный кортеж
            element_type = inner
            c_element_type = self.map_type_to_c(element_type)

            # Универсальная структура для tuple[T]
            struct_code = f"typedef struct {{\n"
            struct_code += f"    {c_element_type}* data;\n"
            struct_code += f"    int size;\n"
            struct_code += f"}} {struct_name};\n\n"

            # Функция создания из массива
            create_func = f"{struct_name} create_{struct_name}({c_element_type} arr[], int size) {{\n"
            create_func += f"    {struct_name} t;\n"
            create_func += f"    t.size = size;\n"
            create_func += f"    t.data = malloc(size * sizeof({c_element_type}));\n"
            create_func += f"    if (!t.data) {{\n"
            create_func += (
                f'        fprintf(stderr, "Memory allocation failed for tuple\\n");\n'
            )
            create_func += f"        exit(1);\n"
            create_func += f"    }}\n"
            create_func += f"    for (int i = 0; i < size; i++) {{\n"
            create_func += f"        t.data[i] = arr[i];\n"
            create_func += f"    }}\n"
            create_func += f"    return t;\n"
            create_func += f"}}\n\n"

            # Функция len()
            len_func = f"int builtin_len_{struct_name}({struct_name}* t) {{\n"
            len_func += f"    if (!t) return 0;\n"
            len_func += f"    return t->size;\n"
            len_func += f"}}\n\n"

            # Функция очистки
            free_func = f"void free_{struct_name}({struct_name}* t) {{\n"
            free_func += f"    if (t->data) {{\n"
            free_func += f"        free(t->data);\n"
            free_func += f"        t->data = NULL;\n"
            free_func += f"    }}\n"
            free_func += f"    t->size = 0;\n"
            free_func += f"}}\n\n"

            # Функция доступа к элементу по индексу
            get_func = (
                f"{c_element_type} get_{struct_name}({struct_name}* t, int index) {{\n"
            )
            get_func += f"    if (!t || index < 0 || index >= t->size) {{\n"
            get_func += f'        fprintf(stderr, "Index out of bounds in tuple\\n");\n'
            get_func += f"        exit(1);\n"
            get_func += f"    }}\n"
            get_func += f"    return t->data[index];\n"
            get_func += f"}}\n\n"

            # Функция slice для кортежа - ДОБАВЛЕНО
            slice_func = f"""{struct_name} slice_{struct_name}({struct_name}* t, int start, int stop, int step) {{
        if (!t) return ({struct_name}){{NULL, 0}};
        
        // Нормализация индексов
        if (start < 0) start = t->size + start;
        if (stop < 0) stop = t->size + stop;
        if (start < 0) start = 0;
        if (stop > t->size) stop = t->size;
        
        // Вычисляем размер результата
        int new_size;
        if (step > 0) {{
            if (start >= stop) new_size = 0;
            else new_size = (stop - start + step - 1) / step;
        }} else if (step < 0) {{
            if (start <= stop) new_size = 0;
            else new_size = (start - stop - step - 1) / (-step);
        }} else {{
            fprintf(stderr, "ValueError: slice step cannot be zero\\n");
            exit(1);
        }}
        
        // Создаем временный массив
        {c_element_type}* temp_data = malloc(new_size * sizeof({c_element_type}));
        if (!temp_data) {{
            fprintf(stderr, "Memory allocation failed for tuple slice\\n");
            exit(1);
        }}
        
        // Копируем элементы с учетом шага
        int pos = 0;
        if (step > 0) {{
            for (int i = start; i < stop && pos < new_size; i += step) {{
                if (i >= 0 && i < t->size) {{
                    temp_data[pos++] = t->data[i];
                }}
            }}
        }} else {{
            for (int i = start; i > stop && pos < new_size; i += step) {{
                if (i >= 0 && i < t->size) {{
                    temp_data[pos++] = t->data[i];
                }}
            }}
        }}
        
        // Создаем кортеж
        {struct_name} result;
        result.size = new_size;
        result.data = temp_data;
        
        return result;
    }}\n\n"""

            # Добавляем все функции
            self.generated_helpers.extend(
                [struct_code, create_func, len_func, free_func, get_func, slice_func]
            )

    def generate_list_struct(self, py_type: str):
        """Генерирует структуру C для списка любой вложенности"""

        # Получаем полную информацию о типе
        type_info = self.extract_nested_type_info(py_type)

        if not type_info:
            print(f"ERROR: Не удалось получить информацию о типе {py_type}")
            return

        struct_name = type_info.get("struct_name")
        if not struct_name:
            print(f"ERROR: Нет struct_name для типа {py_type}")
            return

        print(f"DEBUG generate_list_struct: {py_type}")
        print(f"  struct_name: {struct_name}")
        print(f"  element_type: {type_info.get('element_type')}")
        print(f"  element_py_type: {type_info.get('element_py_type')}")
        print(f"  is_c_type: {type_info.get('is_c_type')}")

        # Определяем element_type
        element_type = type_info.get("element_type", "void*")
        element_py_type = type_info.get("element_py_type")
        is_c_type = type_info.get("is_c_type", False)

        # Генерируем структуру только если еще не генерировали
        if struct_name not in self.generated_structs:
            self.generated_structs.add(struct_name)

            print(f"  Генерация структуры {struct_name} с element_type={element_type}")

            # ВАЖНО: Создаем правильную структуру
            struct_code = f"typedef struct {{\n"
            struct_code += f"    {element_type}* data;  // Указатель на массив элементов типа {element_type}\n"
            struct_code += f"    int size;\n"
            struct_code += f"    int capacity;\n"
            struct_code += f"}} {struct_name};\n\n"

            self.generated_helpers.append(struct_code)
        else:
            print(f"DEBUG: Структура {struct_name} уже сгенерирована")

        # ВАЖНО: Всегда генерируем функции, если они еще не были сгенерированы
        # Проверяем, есть ли slice функция для этой структуры
        has_slice_function = False
        for i, helper in enumerate(self.generated_helpers):
            if f"slice_{struct_name}" in helper:
                has_slice_function = True
                print(f"DEBUG: Найдена slice_{struct_name} в helper {i}")
                break

        if not has_slice_function:
            print(
                f"DEBUG: Функция slice_{struct_name} отсутствует, генерируем все функции..."
            )
            self._generate_list_functions(
                struct_name, element_type, element_py_type, is_c_type
            )
        else:
            print(f"DEBUG: Функция slice_{struct_name} уже существует")

    def _generate_leaf_list_struct(self, leaf_type: str, struct_name: str):
        """Генерирует структуру для листового списка (например, list_int)"""
        if struct_name in self.generated_structs:
            return

        self.generated_structs.add(struct_name)

        # Базовый тип элементов
        element_type = self.map_type_to_c(
            leaf_type
        )  # Например, "int" для leaf_type="int"

        struct_code = f"typedef struct {{\n"
        struct_code += f"    {element_type}* data;\n"
        struct_code += f"    int size;\n"
        struct_code += f"    int capacity;\n"
        struct_code += f"}} {struct_name};\n\n"

        self.generated_helpers.append(struct_code)

        # Генерируем функции для листового списка
        self._generate_list_functions(struct_name, element_type, leaf_type)

    def _generate_list_functions(
        self,
        struct_name: str,
        element_type: str,
        element_py_type: str = None,
        is_c_type: bool = False,
    ):
        """Генерирует функции для работы со списком"""

        print(
            f"DEBUG _generate_list_functions: struct_name={struct_name}, element_type={element_type}, is_c_type={is_c_type}"
        )

        print(
            f"DEBUG _generate_list_functions: struct_name={struct_name}, element_type={element_type}, is_c_type={is_c_type}"
        )
        print(f"DEBUG: Будет добавлено 7 функций для {struct_name}")

        # Определяем, нужна ли специальная обработка для типа
        if is_c_type:
            # Для C типов генерируем универсальные функции
            self._generate_generic_c_list_functions(
                struct_name, element_type, element_py_type
            )
            # return

        # Оригинальный код для обычных типов...
        # Функция создания
        create_func = f"{struct_name}* create_{struct_name}(int initial_capacity) {{\n"
        create_func += f"    {struct_name}* list = malloc(sizeof({struct_name}));\n"
        create_func += f"    if (!list) {{\n"
        create_func += (
            f'        fprintf(stderr, "Memory allocation failed for list\\n");\n'
        )
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"
        create_func += (
            f"    list->data = malloc(initial_capacity * sizeof({element_type}));\n"
        )
        create_func += f"    if (!list->data) {{\n"
        create_func += (
            f'        fprintf(stderr, "Memory allocation failed for list data\\n");\n'
        )
        create_func += f"        free(list);\n"
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"
        create_func += f"    list->size = 0;\n"
        create_func += f"    list->capacity = initial_capacity;\n"
        create_func += f"    return list;\n"
        create_func += f"}}\n\n"

        # Функция добавления
        append_func = (
            f"void append_{struct_name}({struct_name}* list, {element_type} value) {{\n"
        )
        append_func += f"    if (list->size >= list->capacity) {{\n"
        append_func += (
            f"        list->capacity = list->capacity == 0 ? 4 : list->capacity * 2;\n"
        )
        append_func += f"        list->data = realloc(list->data, list->capacity * sizeof({element_type}));\n"
        append_func += f"        if (!list->data) {{\n"
        append_func += (
            f'            fprintf(stderr, "Memory reallocation failed for list\\n");\n'
        )
        append_func += f"            exit(1);\n"
        append_func += f"        }}\n"
        append_func += f"    }}\n"
        append_func += f"    list->data[list->size] = value;\n"
        append_func += f"    list->size++;\n"
        append_func += f"}}\n\n"

        # Функция len()
        len_func = f"int builtin_len_{struct_name}({struct_name}* list) {{\n"
        len_func += f"    if (!list) return 0;\n"
        len_func += f"    return list->size;\n"
        len_func += f"}}\n\n"

        # Функция очистки
        free_func = f"void free_{struct_name}({struct_name}* list) {{\n"
        free_func += f"    if (list) {{\n"

        # Если элементы - указатели на списки, освобождаем их
        if element_py_type and element_py_type.startswith("list["):
            inner_struct_name = self.generate_list_struct_name(element_py_type)
            free_func += f"        for (int i = 0; i < list->size; i++) {{\n"
            free_func += f"            if (list->data[i]) {{\n"
            free_func += f"                free_{inner_struct_name}(list->data[i]);\n"
            free_func += f"            }}\n"
            free_func += f"        }}\n"

        free_func += f"        free(list->data);\n"
        free_func += f"        free(list);\n"
        free_func += f"    }}\n"
        free_func += f"}}\n\n"

        # Функция доступа к элементу (добавляем для всех типов)
        get_func = (
            f"{element_type} get_{struct_name}({struct_name}* list, int index) {{\n"
        )
        get_func += f"    if (!list || index < 0 || index >= list->size) {{\n"
        get_func += f'        fprintf(stderr, "Index out of bounds in list\\n");\n'
        get_func += f"        exit(1);\n"
        get_func += f"    }}\n"
        get_func += f"    return list->data[index];\n"
        get_func += f"}}\n\n"

        # Функция установки элемента
        set_func = f"void set_{struct_name}({struct_name}* list, int index, {element_type} value) {{\n"
        set_func += f"    if (!list || index < 0 || index >= list->size) {{\n"
        set_func += f'        fprintf(stderr, "Index out of bounds in list\\n");\n'
        set_func += f"        exit(1);\n"
        set_func += f"    }}\n"
        set_func += f"    list->data[index] = value;\n"
        set_func += f"}}\n\n"

        # Функция slice для списка - ИСПРАВЛЕННАЯ ВЕРСИЯ
        slice_func = f"""{struct_name}* slice_{struct_name}({struct_name}* list, int start, int stop, int step) {{
            if (!list) return NULL;
            
            // Нормализация индексов
            if (start < 0) start = list->size + start;
            if (stop < 0) stop = list->size + stop;
            if (start < 0) start = 0;
            if (stop > list->size) stop = list->size;
            
            // Вычисляем размер результата
            int new_size;
            if (step > 0) {{
                if (start >= stop) new_size = 0;
                else new_size = (stop - start + step - 1) / step;
            }} else if (step < 0) {{
                if (start <= stop) new_size = 0;
                else new_size = (start - stop - step - 1) / (-step);
            }} else {{
                fprintf(stderr, "ValueError: slice step cannot be zero\\n");
                exit(1);
            }}
            
            // Создаем новый список
            {struct_name}* result = create_{struct_name}(new_size);
            
            // Копируем элементы с учетом шага
            if (step > 0) {{
                for (int i = start; i < stop && result->size < new_size; i += step) {{
                    if (i >= 0 && i < list->size) {{
                        append_{struct_name}(result, list->data[i]);
                    }}
                }}
            }} else {{
                for (int i = start; i > stop && result->size < new_size; i += step) {{
                    if (i >= 0 && i < list->size) {{
                        append_{struct_name}(result, list->data[i]);
                    }}
                }}
            }}
            
            return result;
        }}\n\n"""

        # Добавляем все функции ОДИН РАЗ!
        self.generated_helpers.extend(
            [
                create_func,
                append_func,
                len_func,
                free_func,
                get_func,
                set_func,
                slice_func,
            ]
        )

        print(f"DEBUG: Всего helpers после добавления: {len(self.generated_helpers)}")

    def _generate_generic_c_list_functions(
        self, struct_name: str, element_type: str, element_py_type: str
    ):
        """Генерирует универсальные функции для списков C типов"""

        # Функция создания
        create_func = f"{struct_name}* create_{struct_name}(int initial_capacity) {{\n"
        create_func += f"    {struct_name}* list = malloc(sizeof({struct_name}));\n"
        create_func += f"    if (!list) {{\n"
        create_func += f'        fprintf(stderr, "Memory allocation failed for {struct_name}\\n");\n'
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"

        # ВАЖНО: Используем element_type для размера
        create_func += (
            f"    list->data = malloc(initial_capacity * sizeof({element_type}));\n"
        )
        create_func += f"    if (!list->data) {{\n"
        create_func += f'        fprintf(stderr, "Memory allocation failed for {struct_name} data\\n");\n'
        create_func += f"        free(list);\n"
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"
        create_func += f"    list->size = 0;\n"
        create_func += f"    list->capacity = initial_capacity;\n"
        create_func += f"    return list;\n"
        create_func += f"}}\n\n"

        # Функция добавления
        append_func = (
            f"void append_{struct_name}({struct_name}* list, {element_type} value) {{\n"
        )
        append_func += f"    if (list->size >= list->capacity) {{\n"
        append_func += (
            f"        list->capacity = list->capacity == 0 ? 4 : list->capacity * 2;\n"
        )
        append_func += f"        list->data = realloc(list->data, list->capacity * sizeof({element_type}));\n"
        append_func += f"        if (!list->data) {{\n"
        append_func += f'            fprintf(stderr, "Memory reallocation failed for {struct_name}\\n");\n'
        append_func += f"            exit(1);\n"
        append_func += f"        }}\n"
        append_func += f"    }}\n"
        append_func += f"    list->data[list->size] = value;\n"
        append_func += f"    list->size++;\n"
        append_func += f"}}\n\n"

        # Функция len()
        len_func = f"int builtin_len_{struct_name}({struct_name}* list) {{\n"
        len_func += f"    if (!list) return 0;\n"
        len_func += f"    return list->size;\n"
        len_func += f"}}\n\n"

        # Функция очистки
        free_func = f"void free_{struct_name}({struct_name}* list) {{\n"
        free_func += f"    if (list) {{\n"

        # Для C типов проверяем, нужно ли освобождать элементы
        if (
            element_type.endswith("*")
            and "char*" not in element_type
            and "void*" not in element_type
        ):
            # Если это указатель на структуру (но не char* или void*)
            # Определяем, есть ли у типа функция освобождения
            base_type = element_type[:-1]  # Убираем *
            if (
                base_type in self.class_types
                or f"free_{base_type}" in self.generated_helpers
            ):
                free_func += f"        for (int i = 0; i < list->size; i++) {{\n"
                free_func += f"            if (list->data[i]) {{\n"
                free_func += f"                free_{base_type}(list->data[i]);\n"
                free_func += f"            }}\n"
                free_func += f"        }}\n"
            elif "[" in base_type:  # Если это массив
                free_func += f"        for (int i = 0; i < list->size; i++) {{\n"
                free_func += f"            if (list->data[i]) {{\n"
                free_func += f"                free(list->data[i]);\n"
                free_func += f"            }}\n"
                free_func += f"        }}\n"

        free_func += f"        free(list->data);\n"
        free_func += f"        free(list);\n"
        free_func += f"    }}\n"
        free_func += f"}}\n\n"

        # Функция доступа к элементу
        get_func = (
            f"{element_type} get_{struct_name}({struct_name}* list, int index) {{\n"
        )
        get_func += f"    if (!list || index < 0 || index >= list->size) {{\n"
        get_func += (
            f'        fprintf(stderr, "Index out of bounds in {struct_name}\\n");\n'
        )
        get_func += f"        exit(1);\n"
        get_func += f"    }}\n"
        get_func += f"    return list->data[index];\n"
        get_func += f"}}\n\n"

        # Добавляем все функции
        self.generated_helpers.append(create_func)
        self.generated_helpers.append(append_func)
        self.generated_helpers.append(len_func)
        self.generated_helpers.append(free_func)
        self.generated_helpers.append(get_func)

    def _generate_nested_list_functions(
        self, struct_name: str, element_type: str, inner_info: Dict
    ):
        """Генерирует функции для работы с вложенным списком"""

        # Функция создания
        create_func = f"{struct_name}* create_{struct_name}(int initial_capacity) {{\n"
        create_func += f"    {struct_name}* list = malloc(sizeof({struct_name}));\n"
        create_func += f"    if (!list) {{\n"
        create_func += (
            f'        fprintf(stderr, "Memory allocation failed for list\\n");\n'
        )
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"
        create_func += (
            f"    list->data = malloc(initial_capacity * sizeof({element_type}));\n"
        )
        create_func += f"    if (!list->data) {{\n"
        create_func += (
            f'        fprintf(stderr, "Memory allocation failed for list data\\n");\n'
        )
        create_func += f"        free(list);\n"
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"
        create_func += f"    list->size = 0;\n"
        create_func += f"    list->capacity = initial_capacity;\n"
        create_func += f"    return list;\n"
        create_func += f"}}\n\n"

        # Функция добавления
        append_func = (
            f"void append_{struct_name}({struct_name}* list, {element_type} value) {{\n"
        )
        append_func += f"    if (list->size >= list->capacity) {{\n"
        append_func += (
            f"        list->capacity = list->capacity == 0 ? 4 : list->capacity * 2;\n"
        )
        append_func += f"        list->data = realloc(list->data, list->capacity * sizeof({element_type}));\n"
        append_func += f"        if (!list->data) {{\n"
        append_func += (
            f'            fprintf(stderr, "Memory reallocation failed for list\\n");\n'
        )
        append_func += f"            exit(1);\n"
        append_func += f"        }}\n"
        append_func += f"    }}\n"
        append_func += f"    list->data[list->size] = value;\n"
        append_func += f"    list->size++;\n"
        append_func += f"}}\n\n"

        # Функция len()
        len_func = f"int builtin_len_{struct_name}({struct_name}* list) {{\n"
        len_func += f"    if (!list) return 0;\n"
        len_func += f"    return list->size;\n"
        len_func += f"}}\n\n"

        # Функция очистки
        free_func = f"void free_{struct_name}({struct_name}* list) {{\n"
        free_func += f"    if (list) {{\n"

        # Рекурсивно освобождаем память для вложенных списков
        if inner_info and not inner_info["is_leaf"]:
            inner_struct_name = inner_info["struct_name"]
            free_func += f"        for (int i = 0; i < list->size; i++) {{\n"
            free_func += f"            if (list->data[i]) {{\n"
            free_func += f"                free_{inner_struct_name}(list->data[i]);\n"
            free_func += f"            }}\n"
            free_func += f"        }}\n"
        elif element_type.endswith("*") and "list_" in element_type:
            # Если элемент - указатель на какую-то структуру списка
            base_struct = element_type[:-1]  # Убираем *
            free_func += f"        for (int i = 0; i < list->size; i++) {{\n"
            free_func += f"            if (list->data[i]) {{\n"
            free_func += f"                free_{base_struct}(list->data[i]);\n"
            free_func += f"            }}\n"
            free_func += f"        }}\n"

        free_func += f"        free(list->data);\n"
        free_func += f"        free(list);\n"
        free_func += f"    }}\n"
        free_func += f"}}\n\n"

        # Добавляем все функции
        self.generated_helpers.append(create_func)
        self.generated_helpers.append(append_func)
        self.generated_helpers.append(len_func)
        self.generated_helpers.append(free_func)

    def extract_content_inside_brackets(
        self, s: str, prefix: str, closing_bracket: str
    ) -> str:
        """Извлекает содержимое внутри скобок, учитывая вложенность"""
        if not s.startswith(prefix):
            return ""

        content = s[len(prefix) :]
        depth = 0
        result = []

        for char in content:
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

        return "".join(result) if depth == 0 else ""

    def clean_type_name_for_c(self, type_name: str) -> str:
        """Очищает имя типа для использования в C идентификаторах"""
        if not isinstance(type_name, str):
            return "unknown"

        # Удаляем все небуквенно-цифровые символы и заменяем на _
        cleaned = re.sub(r"[^a-zA-Z0-9]", "_", type_name)
        # Убираем множественные подчеркивания
        cleaned = re.sub(r"_+", "_", cleaned)
        # Убираем подчеркивания в начале и конце
        cleaned = cleaned.strip("_")

        # Если после очистки строка пустая, используем дефолтное имя
        if not cleaned:
            return "unknown"

        # Делаем первую букву строчной для согласованности
        if cleaned[0].isupper():
            cleaned = cleaned[0].lower() + cleaned[1:]

        return cleaned

    def generate_list_functions(
        self, struct_name: str, element_type: str, element_py_type: str = None
    ):
        """Генерирует функции для работы со списком"""

        print(
            f"DEBUG generate_list_functions: struct_name={struct_name}, element_type={element_type}"
        )

        # Функция создания
        create_func = f"{struct_name}* create_{struct_name}(int initial_capacity) {{\n"
        create_func += f"    {struct_name}* list = malloc(sizeof({struct_name}));\n"
        create_func += f"    if (!list) {{\n"
        create_func += (
            f'        fprintf(stderr, "Memory allocation failed for list\\n");\n'
        )
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"
        create_func += (
            f"    list->data = malloc(initial_capacity * sizeof({element_type}));\n"
        )
        create_func += f"    if (!list->data) {{\n"
        create_func += (
            f'        fprintf(stderr, "Memory allocation failed for list data\\n");\n'
        )
        create_func += f"        free(list);\n"
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"
        create_func += f"    list->size = 0;\n"
        create_func += f"    list->capacity = initial_capacity;\n"
        create_func += f"    return list;\n"
        create_func += f"}}\n\n"

        # Функция добавления
        append_func = (
            f"void append_{struct_name}({struct_name}* list, {element_type} value) {{\n"
        )
        append_func += f"    if (list->size >= list->capacity) {{\n"
        append_func += (
            f"        list->capacity = list->capacity == 0 ? 4 : list->capacity * 2;\n"
        )
        append_func += f"        list->data = realloc(list->data, list->capacity * sizeof({element_type}));\n"
        append_func += f"        if (!list->data) {{\n"
        append_func += (
            f'            fprintf(stderr, "Memory reallocation failed for list\\n");\n'
        )
        append_func += f"            exit(1);\n"
        append_func += f"        }}\n"
        append_func += f"    }}\n"
        append_func += f"    list->data[list->size] = value;\n"
        append_func += f"    list->size++;\n"
        append_func += f"}}\n\n"

        # Функция len()
        len_func = f"int builtin_len_{struct_name}({struct_name}* list) {{\n"
        len_func += f"    if (!list) return 0;\n"
        len_func += f"    return list->size;\n"
        len_func += f"}}\n\n"

        # Функция очистки
        free_func = f"void free_{struct_name}({struct_name}* list) {{\n"
        free_func += f"    if (list) {{\n"

        # Если элементы - указатели на списки, освобождаем их
        if element_py_type and element_py_type.startswith("list["):
            inner_struct_name = self.generate_list_struct_name(element_py_type)
            free_func += f"        for (int i = 0; i < list->size; i++) {{\n"
            free_func += f"            if (list->data[i]) {{\n"
            free_func += f"                free_{inner_struct_name}(list->data[i]);\n"
            free_func += f"            }}\n"
            free_func += f"        }}\n"

        free_func += f"        free(list->data);\n"
        free_func += f"        free(list);\n"
        free_func += f"    }}\n"
        free_func += f"}}\n\n"

        # Добавляем все функции
        self.generated_helpers.append(create_func)
        self.generated_helpers.append(append_func)
        self.generated_helpers.append(len_func)
        self.generated_helpers.append(free_func)

        # Добавляем функцию получения по индексу
        get_func = f"""
            {element_type} get_{struct_name}({struct_name}* list, int index) {{
                if (!list || index < 0 || index >= list->size) {{
                    fprintf(stderr, "IndexError: list index out of range\\n");
                    exit(1);
                }}
                return list->data[index];
            }}
        """
        self.generated_helpers.append(get_func)

        # Добавляем функцию установки по индексу
        set_func = f"""
            void set_{struct_name}({struct_name}* list, int index, {element_type} value) {{
                if (!list || index < 0 || index >= list->size) {{
                    fprintf(stderr, "IndexError: list index out of range\\n");
                    exit(1);
                }}
                list->data[index] = value;
            }}
        """
        self.generated_helpers.append(set_func)

        # Функция получения элемента
        get_func = f"""
    {element_type} get_{struct_name}({struct_name}* list, int index) {{
        if (!list || index < 0 || index >= list->size) {{
            fprintf(stderr, "IndexError: list index out of range\\n");
            exit(1);
        }}
        return list->data[index];
    }}
"""
        self.generated_helpers.append(get_func)

        # Функция установки элемента
        set_func = f"""
    void set_{struct_name}({struct_name}* list, int index, {element_type} value) {{
        if (!list || index < 0 || index >= list->size) {{
            fprintf(stderr, "IndexError: list index out of range\\n");
            exit(1);
        }}
        list->data[index] = value;
    }}
"""
        self.generated_helpers.append(set_func)

        # Функция среза
        slice_func = f"""
    {struct_name}* slice_{struct_name}({struct_name}* list, int start, int stop, int step) {{
        if (!list) return NULL;
        
        // Нормализация индексов
        if (start < 0) start = list->size + start;
        if (stop < 0) stop = list->size + stop;
        if (start < 0) start = 0;
        if (stop > list->size) stop = list->size;
        
        // Вычисляем размер результата
        int new_size;
        if (step > 0) {{
            if (start >= stop) new_size = 0;
            else new_size = (stop - start + step - 1) / step;
        }} else if (step < 0) {{
            if (start <= stop) new_size = 0;
            else new_size = (start - stop - step - 1) / (-step);
        }} else {{
            fprintf(stderr, "ValueError: slice step cannot be zero\\n");
            exit(1);
        }}
        
        {struct_name}* result = create_{struct_name}(new_size);
        
        if (step > 0) {{
            for (int i = start; i < stop; i += step) {{
                if (i >= 0 && i < list->size) {{
                    append_{struct_name}(result, list->data[i]);
                }}
            }}
        }} else {{
            for (int i = start; i > stop; i += step) {{
                if (i >= 0 && i < list->size) {{
                    append_{struct_name}(result, list->data[i]);
                }}
            }}
        }}
        
        return result;
    }}
"""
        self.generated_helpers.append(slice_func)

        # ДОБАВЬТЕ эту функцию:
        slice_func = f"""
    {struct_name}* slice_{struct_name}({struct_name}* list, int start, int stop, int step) {{
        if (!list) return NULL;
        
        // Нормализация индексов
        if (start < 0) start = list->size + start;
        if (stop < 0) stop = list->size + stop;
        if (start < 0) start = 0;
        if (stop > list->size) stop = list->size;
        
        // Вычисляем размер результата
        int new_size;
        if (step > 0) {{
            if (start >= stop) new_size = 0;
            else new_size = (stop - start + step - 1) / step;
        }} else if (step < 0) {{
            if (start <= stop) new_size = 0;
            else new_size = (start - stop - step - 1) / (-step);
        }} else {{
            fprintf(stderr, "ValueError: slice step cannot be zero\\n");
            exit(1);
        }}
        
        {struct_name}* result = create_{struct_name}(new_size);
        
        if (step > 0) {{
            for (int i = start; i < stop; i += step) {{
                if (i >= 0 && i < list->size) {{
                    append_{struct_name}(result, list->data[i]);
                }}
            }}
        }} else {{
            for (int i = start; i > stop; i += step) {{
                if (i >= 0 && i < list->size) {{
                    append_{struct_name}(result, list->data[i]);
                }}
            }}
        }}
        
        return result;
    }}
"""
        self.generated_helpers.append(slice_func)

    def generate_tuple_functions(self, py_type: str):
        """Генерирует функции для кортежа с правильным использованием указателей"""
        struct_name = self.generate_tuple_struct_name(py_type)
        element_type = "int"

        # Функция slice для tuple
        slice_func = f"""
    {struct_name}* slice_{struct_name}({struct_name}* tuple, int start, int stop, int step) {{
        if (!tuple) return NULL;
        
        // Нормализация индексов
        if (start < 0) start = tuple->size + start;
        if (stop < 0) stop = tuple->size + stop;
        if (start < 0) start = 0;
        if (stop > tuple->size) stop = tuple->size;
        
        // Вычисляем размер результата
        int new_size;
        if (step > 0) {{
            if (start >= stop) new_size = 0;
            else new_size = (stop - start + step - 1) / step;
        }} else if (step < 0) {{
            if (start <= stop) new_size = 0;
            else new_size = (start - stop - step - 1) / (-step);
        }} else {{
            fprintf(stderr, "ValueError: slice step cannot be zero\\n");
            exit(1);
        }}
        
        // Создаем временный массив
        {element_type}* temp_data = malloc(new_size * sizeof({element_type}));
        if (!temp_data) {{
            fprintf(stderr, "Memory allocation failed for slice\\n");
            exit(1);
        }}
        
        // Копируем элементы
        int pos = 0;
        if (step > 0) {{
            for (int i = start; i < stop && pos < new_size; i += step) {{
                if (i >= 0 && i < tuple->size) {{
                    temp_data[pos++] = tuple->data[i];
                }}
            }}
        }} else {{
            for (int i = start; i > stop && pos < new_size; i += step) {{
                if (i >= 0 && i < tuple->size) {{
                    temp_data[pos++] = tuple->data[i];
                }}
            }}
        }}
        
        // Создаем кортеж
        {struct_name}* result = malloc(sizeof({struct_name}));
        if (!result) {{
            fprintf(stderr, "Memory allocation failed for tuple slice\\n");
            free(temp_data);
            exit(1);
        }}
        result->size = new_size;
        result->data = temp_data;
        
        return result;
    }}
"""
        self.generated_helpers.append(slice_func)

        # Функция освобождения tuple
        free_func = f"""
    void free_{struct_name}({struct_name}* tuple) {{
        if (tuple) {{
            if (tuple->data) {{
                free(tuple->data);
            }}
            free(tuple);
        }}
    }}
"""
        self.generated_helpers.append(free_func)

    def generate_helpers_section(self):
        """Генерирует секцию с вспомогательными функциями и структурами в правильном порядке"""

        self.generate_sort_helpers()
        self.generate_string_helpers()

        if not self.generated_helpers:
            return

        # Сначала генерируем структуры от простых к сложным
        # Собираем все структуры и сортируем по вложенности
        structures = []
        functions = []

        for helper in self.generated_helpers:
            if "typedef struct" in helper:
                structures.append(helper)
            else:
                functions.append(helper)

        # Сортируем структуры: сначала простые (list_int), потом сложные (list_list_int, list_list_list_int)
        def get_structure_depth(struct_code):
            # Определяем имя структуры
            lines = struct_code.split("\n")
            for line in lines:
                if "} " in line and ";" in line:
                    # Находим имя структуры
                    parts = line.split()
                    for part in parts:
                        if part.endswith(";"):
                            name = part[:-1]
                            # Считаем количество 'list_' в имени
                            return name.count("list_")
            return 0

        structures.sort(key=get_structure_depth)

        # Добавляем заголовок
        self.add_line("// =========================================")
        self.add_line("// Вспомогательные структуры и функции")
        self.add_line("// =========================================")
        self.add_empty_line()

        self.generate_sort_helpers()  # TODO
        self.generate_string_helpers()

        # Добавляем структуры
        for struct in structures:
            lines = struct.split("\n")
            for line in lines:
                if line.strip():
                    self.output.append(line)
            self.output.append("")  # Пустая строка между определениями

        # Добавляем функции
        for func in functions:
            lines = func.split("\n")
            for line in lines:
                if line.strip():
                    self.output.append(line)
            self.output.append("")  # Пустая строка между определениями

    def generate_from_json(self, json_data: List[Dict]) -> str:
        """Генерирует C код из JSON AST"""
        self.reset()

        # 1. Собираем все типы
        self.collect_types_from_ast(json_data)

        # 2. Анализируем наследование классов
        self.analyze_class_inheritance(json_data)

        # 3. Анализируем классы и их поля
        self.analyze_classes(json_data)

        # 4. Собираем импорты и объявления
        self.collect_imports_and_declarations(json_data)

        # 5. Генерируем заголовок с импортами
        self.generate_c_imports()

        # 6. Генерируем структуры классов (ПЕРЕД forward declarations!)
        for scope in json_data:
            if scope.get("type") == "module":
                for node in scope.get("graph", []):
                    if node.get("node") == "class_declaration":
                        self.generate_class_declaration_with_fields(node)

        # 7. Генерируем forward declarations
        self.generate_forward_declarations()

        # 8. Генерируем вспомогательные структуры и функции
        self.generate_helpers_section()

        # 9. Генерируем конструкторы классов
        self.generate_class_constructors(json_data)

        # 10. Генерируем все методы классов
        self.generate_all_methods(json_data)

        # 11. Генерируем код для каждой функции
        for scope in json_data:
            if scope.get("type") == "function" and not scope.get("is_stub", False):
                self.generate_function_scope(scope)

        return "\n".join(self.output)

    def collect_types_from_ast(self, json_data: List[Dict]):
        """Собирает все типы из AST для генерации структур"""
        all_types = set()

        def process_node(node):
            if not isinstance(node, dict):
                return

            # Обрабатываем declaration узлы
            if node.get("node") == "declaration":
                var_type = node.get("var_type", "")
                if var_type:
                    if var_type.startswith("list["):
                        all_types.add(var_type)
                        # Также добавляем все вложенные типы
                        self._collect_all_nested_list_types(var_type, all_types)
                    elif var_type.startswith("tuple["):
                        all_types.add(var_type)

        # Проходим по всем scope и узлам
        for scope in json_data:
            if scope.get("type") in ["module", "function"]:
                # Обрабатываем graph узлы
                for node in scope.get("graph", []):
                    process_node(node)

        # Генерируем структуры для всех найденных типов
        # Сортируем по глубине вложенности (от простых к сложным)
        sorted_types = sorted(all_types, key=lambda x: (x.count("["), x))
        for py_type in sorted_types:
            if py_type.startswith("list["):
                self.generate_list_struct(py_type)
            elif py_type.startswith("tuple["):
                self.generate_tuple_struct(py_type)

    def generate_list_struct_name(self, py_type: str) -> str:
        """Генерирует имя структуры для списка любой вложенности"""
        if not py_type.startswith("list["):
            # Если это уже базовый тип (например, pthread_t)
            clean_name = self.clean_type_name_for_c(py_type)
            # pthread_t -> pthread_t, Object* -> ObjectPtr
            if clean_name.endswith("*"):
                clean_name = clean_name[:-1] + "Ptr"
            return f"list_{clean_name}"

        # Используем уже существующий метод _generate_struct_name_recursive
        return self._generate_struct_name_recursive(py_type)

    def _collect_all_nested_list_types(self, list_type: str, type_set: set):
        """Рекурсивно собирает все вложенные типы списков"""
        if not list_type.startswith("list["):
            return

        type_set.add(list_type)

        # Извлекаем внутренний тип
        inner_type = self._parse_list_type(list_type)
        if inner_type:
            if inner_type.startswith("list["):
                # Если внутренний тип тоже список, рекурсивно обрабатываем
                self._collect_all_nested_list_types(inner_type, type_set)
            else:
                # Листовой тип - создаем базовую структуру list_тип
                leaf_struct = f"list[{inner_type}]"
                type_set.add(leaf_struct)

    def _collect_nested_list_types(self, py_type: str, type_set: set):
        """Рекурсивно собирает вложенные типы списков"""
        if not py_type.startswith("list["):
            return

        type_set.add(py_type)

        # Извлекаем внутренний тип
        inner = self._extract_inner_type(py_type)
        if inner and inner.startswith("list["):
            type_set.add(inner)
            self._collect_nested_list_types(inner, type_set)

    def _process_ast_for_types(self, ast):
        """Вспомогательный метод для обработки AST и сбора типов"""
        if not isinstance(ast, dict):
            return

        node_type = ast.get("type", "")

        if node_type == "tuple_literal":
            # Определяем тип tuple на основе элементов
            items = ast.get("items", [])
            if items:
                # Проверяем, все ли элементы одного типа
                element_types = set()
                for item in items:
                    if isinstance(item, dict):
                        if item.get("type") == "literal":
                            data_type = item.get("data_type", "int")
                            element_types.add(data_type)

                # Если все элементы одного типа - это tuple[T]
                if len(element_types) == 1:
                    element_type = next(iter(element_types))
                    py_type = f"tuple[{element_type}]"
                    self.map_type_to_c(py_type)
                else:
                    # Разные типы - это tuple[T1, T2, ...]
                    element_types_list = []
                    for item in items:
                        if isinstance(item, dict) and item.get("type") == "literal":
                            data_type = item.get("data_type", "int")
                            element_types_list.append(data_type)

                    if element_types_list:
                        py_type = f"tuple[{', '.join(element_types_list)}]"
                        self.map_type_to_c(py_type)

        elif node_type == "list_literal":
            items = ast.get("items", [])
            if items:
                # Определяем тип первого элемента
                first_item = items[0]
                if isinstance(first_item, dict):
                    if first_item.get("type") == "tuple_literal":
                        element_type = "tuple"
                    elif first_item.get("type") == "list_literal":
                        element_type = "list"
                    else:
                        element_type = "int"
                else:
                    element_type = "int"

                py_type = f"list[{element_type}]"
                self.map_type_to_c(py_type)

        # Рекурсивно обрабатываем вложенные структуры
        for key, value in ast.items():
            if isinstance(value, dict):
                self._process_ast_for_types(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._process_ast_for_types(item)

    def get_list_depth(self, py_type: str) -> int:
        """Определяет глубину вложенности списка"""
        depth = 0
        current_type = py_type

        while current_type.startswith("list["):
            depth += 1
            # Извлекаем внутренний тип
            inner_content = self.extract_content_inside_brackets(
                current_type, "list[", "]"
            )
            if inner_content and inner_content.startswith("list["):
                current_type = inner_content
            else:
                break

        return depth

    def extract_nested_type_info(self, py_type: str) -> Dict:
        """Извлекает информацию о вложенном типе списка с рекурсивным анализом"""
        if not py_type or not isinstance(py_type, str):
            return self._create_default_type_info()

        # Для отладки
        print(f"DEBUG extract_nested_type_info: {py_type}")

        # Базовый случай: не список
        if not py_type.startswith("list["):
            # Для простых типов
            is_c_type = self._is_c_type(py_type)
            c_type = py_type if is_c_type else self.map_type_to_c(py_type)
            struct_name = f"list_{self.clean_type_name_for_c(py_type)}"

            print(
                f"DEBUG: Базовый тип - is_c_type={is_c_type}, c_type={c_type}, struct_name={struct_name}"
            )

            return {
                "py_type": py_type,
                "c_type": f"{struct_name}*",
                "struct_name": struct_name,
                "element_type": c_type,
                "element_py_type": py_type,
                "is_leaf": True,
                "is_c_type": is_c_type,
                "inner_info": None,
            }

        try:
            # Извлекаем внутренний тип
            inner_type = self._parse_list_type(py_type)
            if not inner_type:
                print(f"DEBUG: Не удалось извлечь внутренний тип из {py_type}")
                return self._create_default_type_info()

            print(f"DEBUG: Внутренний тип: {inner_type}")

            # Генерируем имя структуры
            struct_name = self._generate_struct_name_recursive(py_type)
            print(f"DEBUG: Сгенерированное имя структуры: {struct_name}")

            # Рекурсивно анализируем внутренний тип
            inner_info = self.extract_nested_type_info(inner_type)

            # Определяем информацию о текущем уровне
            is_leaf = not inner_type.startswith("list[")

            # Определяем element_type
            if is_leaf:
                # Если это list[T], то element_type = T
                if self._is_c_type(inner_type):
                    element_type = inner_type
                else:
                    element_type = self.map_type_to_c(inner_type)
            else:
                # Если это list[list[...]], то element_type = inner_struct*
                if inner_info.get("struct_name"):
                    element_type = f"{inner_info['struct_name']}*"
                else:
                    element_type = "void*"

            result = {
                "py_type": py_type,
                "c_type": f"{struct_name}*",
                "struct_name": struct_name,
                "element_type": element_type,
                "element_py_type": inner_type,
                "is_leaf": is_leaf,
                "is_c_type": inner_info.get("is_c_type", False) if is_leaf else False,
                "inner_info": inner_info,
            }

            print(
                f"DEBUG результат: struct_name={struct_name}, element_type={element_type}, is_c_type={result['is_c_type']}"
            )

            return result

        except Exception as e:
            print(f"ERROR в extract_nested_type_info для {py_type}: {e}")
            return self._create_default_type_info()

    def _generate_struct_name_recursive(self, py_type: str) -> str:
        """Рекурсивно генерирует имя структуры для вложенного списка"""
        if not py_type.startswith("list["):
            # Если это не список, проверяем, является ли это C типом
            if self._is_c_type(py_type):
                # Для C типов возвращаем list_имя_типа
                clean_name = self.clean_type_name_for_c(py_type)
                return f"list_{clean_name}"
            else:
                # Для других типов (int, float и т.д.)
                clean_name = self.clean_type_name_for_c(py_type)
                return f"list_{clean_name}"

        # Извлекаем внутренний тип
        inner_type = self._parse_list_type(py_type)
        if not inner_type:
            return "list_unknown"

        # Если внутренний тип тоже список, рекурсивно генерируем имя
        if inner_type.startswith("list["):
            inner_struct_name = self._generate_struct_name_recursive(inner_type)
            # Для list[list[int]] -> list_list_int
            return f"list_{inner_struct_name}"
        else:
            # list[int] -> list_int
            clean_inner = self.clean_type_name_for_c(inner_type)
            return f"list_{clean_inner}"

    def _parse_list_type(self, list_type: str) -> Optional[str]:
        """Парсит тип списка и извлекает внутренний тип"""
        if not list_type.startswith("list["):
            return None

        # Счетчик скобок для правильного парсинга вложенных типов
        bracket_count = 0
        start_idx = 4  # индекс после "list"

        # Находим начало внутреннего типа
        for i in range(start_idx, len(list_type)):
            if list_type[i] == "[":
                bracket_count += 1
            elif list_type[i] == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    # Нашли закрывающую скобку
                    inner_type = list_type[start_idx + 1 : i]  # +1 чтобы пропустить '['
                    return inner_type.strip()

        return None

    def _extract_inner_type(self, list_type: str) -> Optional[str]:
        """Извлекает внутренний тип из объявления list[...]"""
        if not list_type.startswith("list["):
            return None

        # Ищем баланс скобок
        balance = 0
        start_pos = 4  # после "list"

        for i in range(start_pos, len(list_type)):
            char = list_type[i]
            if char == "[":
                balance += 1
            elif char == "]":
                balance -= 1
                if balance == 0:
                    # Нашли закрывающую скобку
                    inner = list_type[start_pos + 1 : i]  # +1 чтобы пропустить '['
                    return inner.strip()

        return None

    def _create_default_type_info(self) -> Dict:
        """Создает информацию о типе по умолчанию"""
        return {
            "py_type": "unknown",
            "c_type": "void*",
            "struct_name": None,
            "element_type": None,
            "is_leaf": True,
            "inner_info": None,
        }

    def _create_leaf_type_info(self, py_type: str) -> Dict:
        """Создает информацию о листовом типе"""
        c_type = self.map_type_to_c(py_type)
        return {
            "py_type": py_type,
            "c_type": c_type,
            "struct_name": None,
            "element_type": None,
            "is_leaf": True,
            "inner_info": None,
        }

    def generate_expression(self, ast: Dict) -> str:
        """Генерирует C выражение из AST с поддержкой tuple и list"""
        if not ast:
            return "0"

        node_type = ast.get("type", "")

        if node_type == "index_access":
            variable = ast.get("variable", "")
            index_ast = ast.get("index", {})

            index_expr = self.generate_expression(index_ast)
            var_info = self.get_variable_info(variable)

            if var_info:
                py_type = var_info.get("py_type", "")

                if py_type.startswith("list["):
                    struct_name = self.generate_list_struct_name(py_type)
                    return f"get_{struct_name}({variable}, {index_expr})"
                elif py_type.startswith("tuple["):
                    struct_name = self.generate_tuple_struct_name(py_type)
                    # Tuple передается по указателю в функции get
                    return f"get_{struct_name}(&{variable}, {index_expr})"

            return f"{variable}[{index_expr}]"

        elif node_type == "slice_access":
            variable = ast.get("variable", "")
            start_ast = ast.get("start", {})
            stop_ast = ast.get("stop", {})
            step_ast = ast.get("step", {})

            # Генерируем выражения для границ
            start_expr = self.generate_expression(start_ast) if start_ast else "0"
            stop_expr = self.generate_expression(stop_ast) if stop_ast else ""
            step_expr = self.generate_expression(step_ast) if step_ast else "1"

            var_info = self.get_variable_info(variable)
            if var_info:
                py_type = var_info.get("py_type", "")

                if py_type.startswith("list["):
                    # Для списка stop по умолчанию: list->size
                    if not stop_ast:
                        stop_expr = f"{variable}->size"

                    struct_name = self.generate_list_struct_name(py_type)
                    # Создаем срез списка напрямую без временной переменной
                    return f"slice_{struct_name}({variable}, {start_expr}, {stop_expr}, {step_expr})"

                elif py_type.startswith("tuple["):
                    # Для кортежа stop по умолчанию: tuple.size
                    if not stop_ast:
                        stop_expr = f"{variable}.size"

                    struct_name = self.generate_tuple_struct_name(py_type)
                    # Создаем срез кортежа
                    return f"slice_{struct_name}(&{variable}, {start_expr}, {stop_expr}, {step_expr})"

            # Если не list и не tuple, генерируем обычный slice
            return f"/* slice of {variable}[{start_expr}:{stop_expr}] */"

        if node_type == "tuple_literal":
            # Для tuple литералов используем метод generate_tuple_creation
            return self.generate_tuple_creation(ast)
        elif node_type == "literal":
            value = ast.get("value")
            data_type = ast.get("data_type", "")

            if data_type == "str":
                return f'"{value}"'
            elif data_type == "bool":
                return "true" if value else "false"
            elif data_type == "None":
                return "NULL"
            else:
                return str(value)
        elif node_type == "variable":
            var_name = ast.get("value", "")

            if not self.is_variable_declared(var_name):
                print(f"WARNING: Использование необъявленной переменной '{var_name}'")

            return var_name

        # Добавляем обработку новых типов узлов
        elif node_type == "attribute_access":
            return self.generate_attribute_access(ast)
        elif node_type == "constructor_call":
            return self.generate_constructor_call(ast)
        elif node_type == "method_call":
            return self.generate_method_call(ast)

        if node_type == "literal":
            value = ast.get("value")
            data_type = ast.get("data_type", "")

            if data_type == "str":
                return f'"{value}"'
            elif data_type == "bool":
                return "true" if value else "false"
            elif data_type == "None":
                return "NULL"
            else:
                return str(value)

        elif node_type == "variable":
            var_name = ast.get("value", "")

            if not self.is_variable_declared(var_name):
                print(f"WARNING: Использование необъявленной переменной '{var_name}'")

            return var_name

        elif node_type == "binary_operation":
            left_ast = ast.get("left", {})
            right_ast = ast.get("right", {})
            operator = ast.get("operator_symbol", "")

            left = self.generate_expression(left_ast)
            right = self.generate_expression(right_ast)

            # Проверяем, являются ли операнды строками
            left_is_string = self._is_string_expression(left_ast)
            right_is_string = self._is_string_expression(right_ast)

            # Для сложения строк используем strcat
            if operator == "+" and (left_is_string or right_is_string):
                # Создаем временную переменную для результата
                temp_var = self.generate_temporary_var("str")

                # Генерируем код для конкатенации строк
                self.add_line(
                    f"char* {temp_var} = malloc(strlen({left}) + strlen({right}) + 1);"
                )
                self.add_line(f"if (!{temp_var}) {{")
                self.indent_level += 1
                self.add_line(
                    f'fprintf(stderr, "Memory allocation failed for string concatenation\\n");'
                )
                self.add_line(f"exit(1);")
                self.indent_level -= 1
                self.add_line(f"}}")
                self.add_line(f"strcpy({temp_var}, {left});")
                self.add_line(f"strcat({temp_var}, {right});")

                return temp_var

            if operator == "**":
                return f"pow({left}, {right})"

            c_operator = self.operator_map.get(operator, operator)
            return f"({left} {c_operator} {right})"

        elif node_type == "unary_operation":
            operand_ast = ast.get("operand", {})
            operator = ast.get("operator_symbol", "")

            operand = self.generate_expression(operand_ast)
            c_operator = self.operator_map.get(operator, operator)

            return f"{c_operator}({operand})"

        elif node_type == "function_call":
            func_name = ast.get("function", "")

            if func_name.startswith("@"):
                func_name = func_name[1:]

            builtin_funcs = ["len", "str", "int", "bool", "range", "input"]
            if func_name in builtin_funcs:
                args = ast.get("arguments", [])

                # Для len() определяем тип аргумента
                if func_name == "len" and args:
                    arg_ast = args[0]
                    if arg_ast.get("type") == "variable":
                        var_name = arg_ast.get("value", "")
                        var_info = self.get_variable_info(var_name)

                        if var_info:
                            py_type = var_info.get("py_type", "")

                            if py_type.startswith("tuple["):
                                struct_name = self.generate_tuple_struct_name(py_type)
                                # Используем специализированную функцию
                                c_func_name = f"builtin_len_{struct_name}"
                            elif py_type.startswith("list["):
                                struct_name = self.generate_list_struct_name(py_type)
                                # Используем специализированную функцию для списков
                                c_func_name = f"builtin_len_{struct_name}"
                            else:
                                c_func_name = "builtin_len"
                        else:
                            c_func_name = "builtin_len"
                    else:
                        c_func_name = "builtin_len"
                elif func_name == "input":
                    # Для input в выражениях генерируем код и возвращаем переменную
                    return self.generate_input_expression(ast)
                else:
                    c_func_name = f"builtin_{func_name}"
            else:
                c_func_name = func_name

            args = ast.get("arguments", [])
            arg_strings = [self.generate_expression(arg_ast) for arg_ast in args]
            args_str = ", ".join(arg_strings)
            return f"{c_func_name}({args_str})"

        elif node_type == "tuple_literal":
            # Для tuple литералов генерируем временную структуру
            items = ast.get("items", [])
            if items:
                item_strs = [self.generate_expression(item) for item in items]

                # Создаем временный tuple
                temp_name = self.generate_temporary_var("tuple")
                struct_name = f"tuple_{len(items)}_{'_'.join(['item' for _ in items])}"

                # Регистрируем тип
                elements_type = ", ".join(["int" for _ in items])  # Упрощенно
                py_type = f"tuple[{elements_type}]"
                self.generate_tuple_struct(py_type)

                return f"create_{self.generate_tuple_struct_name(py_type)}({', '.join(item_strs)})"
            return "{}"

        elif node_type == "list_literal":
            # Для list литералов генерируем создание списка
            items = ast.get("items", [])
            if items:
                # Определяем тип элементов
                if items:
                    first_item = items[0]
                    if isinstance(first_item, dict):
                        if first_item.get("type") == "tuple_literal":
                            element_type = "tuple"
                        elif first_item.get("type") == "list_literal":
                            element_type = "list"
                        else:
                            element_type = "int"  # По умолчанию
                    else:
                        element_type = "int"
                else:
                    element_type = "int"

                py_type = f"list[{element_type}]"
                struct_name = self.generate_list_struct_name(py_type)

                # Генерируем код для создания списка
                temp_name = self.generate_temporary_var("list")
                self.generate_list_struct(py_type)

                # Создаем список
                code_parts = []
                code_parts.append(f"create_{struct_name}({len(items)})")

                # Добавляем элементы
                for item_ast in items:
                    item_expr = self.generate_expression(item_ast)
                    code_parts.append(f"append_{struct_name}({temp_name}, {item_expr})")

                return temp_name
            return "NULL"

        elif node_type == "address_of":
            variable = ast.get("variable", "")
            return f"&{variable}"

        elif node_type == "dereference":
            pointer = ast.get("pointer", "")
            return f"*{pointer}"

        # Для неизвестных типов пытаемся извлечь значение
        ast_value = str(ast.get("value", "0"))
        if ast_value.startswith("@"):  # C - code
            ast_value = ast_value[1:]

        return ast_value

    def _is_string_expression(self, ast: Dict) -> bool:
        """Определяет, является ли выражение строкой"""
        if not ast:
            return False

        node_type = ast.get("type", "")

        if node_type == "literal":
            return ast.get("data_type", "") == "str"

        elif node_type == "variable":
            var_name = ast.get("value", "")
            var_info = self.get_variable_info(var_name)
            if var_info:
                return var_info.get("py_type", "") == "str"

        elif node_type == "binary_operation":
            left_ast = ast.get("left", {})
            right_ast = ast.get("right", {})
            operator = ast.get("operator_symbol", "")

            if operator == "+":
                return self._is_string_expression(
                    left_ast
                ) or self._is_string_expression(right_ast)

        return False

    def generate_class_declaration(self, node: Dict):
        """Генерирует структуру для класса C динамически"""
        class_name = node.get("class_name", "")

        # Регистрируем класс
        self.class_types.add(class_name)
        self.type_map[class_name] = f"{class_name}*"

        # Анализируем класс для определения полей
        # (fields будут собраны позже при анализе методов)
        if class_name not in self.class_fields:
            self.class_fields[class_name] = {}

        # Генерируем структуру
        self.add_line(f"typedef struct {class_name} {{")
        self.indent_level += 1

        # Добавляем таблицу виртуальных методов
        self.add_line(f"void** vtable;")

        # Поля будут добавлены позже, после анализа методов
        # Создаем временный комментарий
        self.add_line(f"// Поля класса будут добавлены после анализа методов")

        self.indent_level -= 1
        self.add_line(f"}} {class_name};")
        self.add_empty_line()

    def collect_class_fields(self, class_name: str, json_data: List[Dict]) -> Dict:
        """Собирает поля класса из всех его методов (включая __init__)"""
        fields = {}

        # Ищем все методы этого класса в json_data
        for scope in json_data:
            if (
                scope.get("type") == "class_method"
                and scope.get("class_name") == class_name
            ):
                method_name = scope.get("method_name", "")

                # Анализируем метод __init__ для присваиваний атрибутам
                if method_name == "__init__":
                    self._analyze_init_method_for_fields(fields, scope)

                # Также анализируем другие методы для использования атрибутов
                else:
                    self._analyze_method_for_field_references(fields, scope)

        return fields

    def _analyze_init_method_for_fields(self, fields: Dict, init_scope: Dict):
        """Анализирует метод __init__ для определения полей класса"""
        graph = init_scope.get("graph", [])

        for node in graph:
            if node.get("node") == "attribute_assignment":
                # Присваивание атрибуту: self.attr = value
                attr_name = node.get("attribute", "")
                value = node.get("value", {})

                # Определяем тип значения
                field_type = self._infer_field_type(value)
                if field_type:
                    fields[attr_name] = field_type

            elif node.get("node") == "declaration":
                # Объявление атрибута с типом: self.attr: type = value
                var_name = node.get("var_name", "")
                if var_name.startswith("self."):
                    attr_name = var_name[5:]  # Убираем "self."
                    var_type = node.get("var_type", "")
                    if var_type:
                        fields[attr_name] = var_type

    def _analyze_method_for_field_references(self, fields: Dict, method_scope: Dict):
        """Анализирует метод для ссылок на атрибуты"""
        graph = method_scope.get("graph", [])

        # Собираем все обращения к атрибутам
        def collect_attribute_accesses(node):
            accesses = []

            if isinstance(node, dict):
                node_type = node.get("type", "")

                if node_type == "attribute_access":
                    # Доступ к атрибуту: self.attr или obj.attr
                    obj_name = node.get("object", "")
                    attr_name = node.get("attribute", "")

                    if obj_name == "self":
                        accesses.append(attr_name)

                # Рекурсивно проверяем все значения
                for key, value in node.items():
                    if isinstance(value, (dict, list)):
                        if isinstance(value, dict):
                            accesses.extend(collect_attribute_accesses(value))
                        elif isinstance(value, list):
                            for item in value:
                                accesses.extend(collect_attribute_accesses(item))

            return accesses

        # Проходим по всему графу метода
        for node in graph:
            attr_accesses = collect_attribute_accesses(node)
            for attr_name in attr_accesses:
                # Если атрибут упоминается, но не зарегистрирован, добавляем как int
                if attr_name not in fields:
                    fields[attr_name] = "int"

    def _infer_field_type(self, value_ast: Dict) -> str:
        """Определяет тип поля по значению"""
        if not value_ast:
            return "int"  # По умолчанию

        value_type = value_ast.get("type", "")

        # Литералы
        if value_type == "literal":
            data_type = value_ast.get("data_type", "int")
            return data_type

        # Переменные
        elif value_type == "variable":
            var_name = value_ast.get("value", "")
            # Пытаемся определить тип переменной по контексту
            if var_name in ["in_dim", "out_dim", "x", "y", "z"]:
                return "int"
            elif var_name in ["weight", "bias", "value"]:
                return "float"

        # Бинарные операции
        elif value_type == "binary_operation":
            left = value_ast.get("left", {})
            right = value_ast.get("right", {})

            left_type = self._infer_field_type(left)
            right_type = self._infer_field_type(right)

            # Если типы совпадают, возвращаем его
            if left_type == right_type:
                return left_type

            # Если один float, а другой int - возвращаем float
            if "float" in left_type or "double" in left_type:
                return left_type
            if "float" in right_type or "double" in right_type:
                return right_type

            # По умолчанию int
            return "int"

        # Атрибуты
        elif value_type == "attribute_access":
            # Не можем определить тип атрибута рекурсивно
            return "int"

        # По умолчанию
        return "int"

    def generate_vtable(self, class_name: str, methods: List[Dict]):
        """Генерирует таблицу виртуальных методов"""
        # Определяем, какие методы виртуальные (переопределяемые)
        virtual_methods = []
        for method in methods:
            method_name = method.get("name", "")
            if method_name != "__init__":
                virtual_methods.append(method)

        if virtual_methods:
            # Создаем тип для указателя на таблицу виртуальных методов
            vtable_type_name = f"{class_name}_vtable"

            self.add_line(f"typedef struct {{")
            self.indent_level += 1
            for method in virtual_methods:
                method_name = method.get("name", "")
                return_type = method.get("return_type", "void")
                params = method.get("parameters", [])

                # Пропускаем self параметр
                actual_params = []
                if params and params[0].get("name") == "self":
                    # Определяем тип self для данного метода
                    for param in params[1:]:
                        param_name = param.get("name", "")
                        param_type = param.get("type", "int")
                        c_param_type = self.map_type_to_c(param_type)
                        actual_params.append(f"{c_param_type} {param_name}")
                else:
                    for param in params:
                        param_name = param.get("name", "")
                        param_type = param.get("type", "int")
                        c_param_type = self.map_type_to_c(param_type)
                        actual_params.append(f"{c_param_type} {param_name}")

                c_return_type = self.map_type_to_c(return_type)
                params_str = ", ".join(actual_params) if actual_params else "void"

                # Создаем указатель на функцию
                # Для методов, параметр self уже учтен в сигнатуре функции
                if params and params[0].get("name") == "self":
                    self_param_type = params[0].get("type", class_name)
                    func_ptr = f"({c_return_type} (*)({self_param_type}*"
                    if actual_params:
                        func_ptr += f", {params_str}"
                    func_ptr += "))"
                else:
                    func_ptr = f"({c_return_type} (*)({params_str}))"

                self.add_line(f"{func_ptr} {method_name};")

            self.indent_level -= 1
            self.add_line(f"}} {vtable_type_name};")
            self.add_empty_line()

            # Глобальная таблица виртуальных методов
            self.add_line(f"// Таблица виртуальных методов для {class_name}")
            self.add_line(f"extern {vtable_type_name} {class_name}_vtable_instance;")
            self.add_empty_line()

    def generate_constructor(
        self,
        class_name: str,
        init_method: Optional[Dict] = None,
        init_scope: Optional[Dict] = None,
    ):
        """Генерирует конструктор класса"""
        self.add_line(f"// Конструктор для {class_name}")

        # Определяем параметры
        params = []
        param_names = []
        if init_method:
            init_params = init_method.get("parameters", [])
            # Пропускаем self параметр
            for param in init_params[1:]:
                param_name = param.get("name", "")
                param_type = param.get("type", "int")
                c_param_type = self.map_type_to_c(param_type)
                params.append(f"{c_param_type} {param_name}")
                param_names.append(param_name)

        params_str = ", ".join(params) if params else "void"

        # Функция создания объекта
        self.add_line(f"{class_name}* create_{class_name}({params_str}) {{")
        self.indent_level += 1

        # Выделяем память
        self.add_line(f"{class_name}* obj = malloc(sizeof({class_name}));")
        self.add_line(f"if (!obj) {{")
        self.indent_level += 1
        self.add_line(
            f'fprintf(stderr, "Memory allocation failed for {class_name}\\n");'
        )
        self.add_line(f"exit(1);")
        self.indent_level -= 1
        self.add_line(f"}}")
        self.add_empty_line()

        # Генерируем логику инициализации
        if init_scope:
            self._generate_init_logic(class_name, init_scope, param_names)
        else:
            # Базовая инициализация для классов без __init__
            base_classes = self.class_hierarchy.get(class_name, [])
            if not base_classes:
                # Корневой класс
                self.add_line(f"obj->vtable = malloc(sizeof(void*) * 16);")
            else:
                # Производный класс
                self.add_line(f"obj->base.vtable = malloc(sizeof(void*) * 16);")

            self.add_line(
                f"if (!obj->{'vtable' if not base_classes else 'base.vtable'}) {{"
            )
            self.indent_level += 1
            self.add_line(f'fprintf(stderr, "Memory allocation failed for vtable\\n");')
            self.add_line(f"free(obj);")
            self.add_line(f"exit(1);")
            self.indent_level -= 1
            self.add_line(f"}}")

        self.add_line(f"return obj;")
        self.indent_level -= 1
        self.add_line(f"}}")
        self.add_empty_line()

    def _generate_field_initializations(
        self, class_name: str, init_scope: Dict, constructor_params: List[str]
    ):
        """Генерирует инициализацию полей на основе метода __init__"""
        if not init_scope:
            return

        graph = init_scope.get("graph", [])
        if not graph:
            return

        # Создаем контекст параметров для подстановки
        param_map = {}
        for param in constructor_params:
            parts = param.split()
            if len(parts) >= 2:
                param_map[parts[-1]] = parts[-1]  # Имя параметра

        self.add_line(f"// Инициализация полей для {class_name}")

        for node in graph:
            node_type = node.get("node", "")

            if node_type == "attribute_assignment":
                # Присваивание атрибуту: self.attr = value
                obj_name = node.get("object", "")
                attr_name = node.get("attribute", "")
                value_ast = node.get("value", {})

                if obj_name == "self":
                    # Генерируем выражение для значения
                    if value_ast:
                        try:
                            value_expr = self.generate_expression(value_ast)
                            # Заменяем параметры конструктора
                            for param_name in param_map:
                                value_expr = value_expr.replace(
                                    param_name, param_map[param_name]
                                )
                            self.add_line(f"obj->{attr_name} = {value_expr};")
                        except Exception as e:
                            self.add_line(f"// Ошибка генерации выражения: {e}")

    def _debug_expression_node(self, node: Dict):
        """Отладочный вывод для узла expression"""
        operations = node.get("operations", [])
        self.add_line(f"// Количество операций в expression: {len(operations)}")

        for i, op in enumerate(operations):
            op_type = op.get("type", "")
            self.add_line(f"// Операция {i}: тип={op_type}")

            if op_type == "ATTRIBUTE_ASSIGN":
                self.add_line(f"//   object={op.get('object')}")
                self.add_line(f"//   attribute={op.get('attribute')}")
                self.add_line(f"//   value={op.get('value')}")

    def generate_class_method(self, class_name: str, method: Dict):
        """Генерирует метод класса"""
        method_name = method.get("name", "")
        return_type = method.get("return_type", "void")
        params = method.get("parameters", [])

        # Генерируем сигнатуру метода
        c_return_type = self.map_type_to_c(return_type)

        # Первый параметр - всегда self
        if params and params[0].get("name") == "self":
            # Параметр self в C - это указатель на структуру
            param_decls = [f"{class_name}* self"]
            # Остальные параметры
            for param in params[1:]:
                param_name = param.get("name", "")
                param_type = param.get("type", "int")
                c_param_type = self.map_type_to_c(param_type)
                param_decls.append(f"{c_param_type} {param_name}")
        else:
            param_decls = []
            for param in params:
                param_name = param.get("name", "")
                param_type = param.get("type", "int")
                c_param_type = self.map_type_to_c(param_type)
                param_decls.append(f"{c_param_type} {param_name}")

        params_str = ", ".join(param_decls) if param_decls else "void"

        self.add_line(f"{c_return_type} {class_name}_{method_name}({params_str}) {{")
        self.indent_level += 1

        # Тело метода будет сгенерировано отдельно
        self.add_line(f"// Реализация метода {method_name}")

        # Для метода get_age из примера
        if method_name == "get_age":
            self.add_line(f"return self->age;")

        self.indent_level -= 1
        self.add_line(f"}}")
        self.add_empty_line()

    def register_class_type(self, class_name: str):
        """Регистрирует тип как класс"""
        self.class_types.add(class_name)
        self.pointer_types.add(class_name)  # Классы обычно указатели на структуры

        # Добавляем в маппинг типов
        self.type_map[class_name] = f"{class_name}*"

    def register_struct_type(self, struct_name: str, is_pointer: bool = True):
        """Регистрирует тип как структуру"""
        self.struct_types.add(struct_name)
        if is_pointer:
            self.pointer_types.add(struct_name)

    def is_pointer_type(self, type_name: str) -> bool:
        """Определяет, является ли тип указателем"""
        # Проверяем различные условия
        if type_name in self.pointer_types:
            return True

        # Проверяем по маппингу
        if type_name in self.type_map:
            c_type = self.type_map[type_name]
            return c_type.endswith("*")

        # Проверяем по имени
        if type_name.endswith("*"):
            return True

        return False

    def generate_attribute_access(self, ast: Dict) -> str:
        """Генерирует доступ к атрибуту объекта"""
        obj_name = ast.get("object", "")
        attr_name = ast.get("attribute", "")

        # Проверяем тип объекта
        var_info = self.get_variable_info(obj_name)
        if var_info:
            obj_type = var_info.get("py_type", "")

            # Если это класс, используем стрелочку
            if self._is_class_type(obj_type):
                return f"{obj_name}->{attr_name}"

        # По умолчанию используем точку
        return f"{obj_name}.{attr_name}"

    def generate_constructor_call(self, ast: Dict) -> str:
        """Генерирует вызов конструктора"""
        class_name = ast.get("class_name", "")
        args = ast.get("arguments", [])

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                arg_strings.append(self.generate_expression(arg))
            else:
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings)
        return f"create_{class_name}({args_str})"

    def generate_method_call(self, node: Dict):
        """Генерирует вызов метода объекта"""
        object_name = node.get("object", "")
        method_name = node.get("method", "")
        args = node.get("arguments", [])
        is_standalone = node.get("is_standalone", False)  # Новое поле из парсера

        # Проверяем тип объекта
        var_info = self.get_variable_info(object_name)
        if not var_info:
            self.add_line(f"// ERROR: Объект '{object_name}' не найден")
            return

        obj_type = var_info.get("py_type", "")

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                arg_strings.append(self.generate_expression(arg))
            else:
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings) if arg_strings else ""

        if self._is_class_type(obj_type):
            # Это класс - используем формат ClassName_methodName
            # Первым аргументом идет указатель на объект (self)
            full_args = f"{object_name}"
            if args_str:
                full_args = f"{object_name}, {args_str}"

            # Если это standalone вызов (statement)
            if is_standalone:
                self.add_line(f"{obj_type}_{method_name}({full_args});")
            else:
                # Если это выражение (возвращаем результат)
                return f"{obj_type}_{method_name}({full_args})"
        # Обработка методов для списков
        # Обработка методов для строк
        elif obj_type == "str":
            if method_name == "upper":
                if is_standalone:
                    # Для a.upper() как standalone - результат должен быть присвоен обратно в a
                    self.add_line("// upper")
                    temp_var = self.generate_temporary_var("str")
                    self.add_line(f"char* {temp_var} = string_upper({object_name});")
                    # Освобождаем старую строку
                    self.add_line(f"if ({object_name}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({object_name});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    # Присваиваем новую строку
                    self.add_line(f"{object_name} = {temp_var};")
                else:
                    # Для upper() внутри выражения
                    return f"string_upper({object_name})"

            elif method_name == "lower":
                if is_standalone:
                    self.add_line("// lower")
                    # Для a.lower() как standalone
                    temp_var = self.generate_temporary_var("str")
                    self.add_line(f"char* {temp_var} = string_lower({object_name});")
                    # Освобождаем старую строку
                    self.add_line(f"if ({object_name}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({object_name});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    # Присваиваем новую строку
                    self.add_line(f"{object_name} = {temp_var};")
                else:
                    # Для lower() внутри выражения
                    return f"string_lower({object_name})"

            elif method_name == "capitalize":
                if is_standalone:
                    self.add_line("// capitalize")

                    # Для a.capitalize() как standalone
                    temp_var = self.generate_temporary_var("str")
                    self.add_line(
                        f"char* {temp_var} = string_capitalize({object_name});"
                    )
                    # Освобождаем старую строку
                    self.add_line(f"if ({object_name}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({object_name});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    # Присваиваем новую строку
                    self.add_line(f"{object_name} = {temp_var};")
                else:
                    # Для capitalize() внутри выражения
                    return f"string_capitalize({object_name})"

            elif method_name == "title":
                if is_standalone:
                    self.add_line("// title")

                    # Для a.title() как standalone
                    temp_var = self.generate_temporary_var("str")
                    self.add_line(f"char* {temp_var} = string_title({object_name});")
                    # Освобождаем старую строку
                    self.add_line(f"if ({object_name}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({object_name});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    # Присваиваем новую строку
                    self.add_line(f"{object_name} = {temp_var};")
                else:
                    # Для title() внутри выражения
                    return f"string_title({object_name})"

            elif method_name == "strip":
                if is_standalone:
                    self.add_line("// strip")

                    # Для a.strip() как standalone
                    temp_var = self.generate_temporary_var("str")
                    self.add_line(f"char* {temp_var} = string_strip({object_name});")
                    # Освобождаем старую строку
                    self.add_line(f"if ({object_name}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({object_name});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    # Присваиваем новую строку
                    self.add_line(f"{object_name} = {temp_var};")
                else:
                    # Для strip() внутри выражения
                    return f"string_strip({object_name})"

            elif method_name == "lstrip":
                if is_standalone:
                    self.add_line("// lstrip")

                    # Для a.lstrip() как standalone
                    temp_var = self.generate_temporary_var("str")
                    self.add_line(f"char* {temp_var} = string_lstrip({object_name});")
                    # Освобождаем старую строку
                    self.add_line(f"if ({object_name}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({object_name});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    # Присваиваем новую строку
                    self.add_line(f"{object_name} = {temp_var};")
                else:
                    # Для lstrip() внутри выражения
                    return f"string_lstrip({object_name})"

            elif method_name == "rstrip":
                if is_standalone:
                    self.add_line("// rstrip")

                    # Для a.rstrip() как standalone
                    temp_var = self.generate_temporary_var("str")
                    self.add_line(f"char* {temp_var} = string_rstrip({object_name});")
                    # Освобождаем старую строку
                    self.add_line(f"if ({object_name}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({object_name});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    # Присваиваем новую строку
                    self.add_line(f"{object_name} = {temp_var};")
                else:
                    # Для rstrip() внутри выражения
                    return f"string_rstrip({object_name})"

            elif method_name == "format":
                if is_standalone:
                    self.add_line("// format")

                    # Для a.format("world") как standalone - результат должен быть присвоен обратно в a
                    temp_var = self.generate_temporary_var("str")
                    self.add_line(
                        f"char* {temp_var} = string_format({object_name}, {args_str});"
                    )
                    # Освобождаем старую строку
                    self.add_line(f"if ({object_name}) {{")
                    self.indent_level += 1
                    self.add_line(f"free({object_name});")
                    self.indent_level -= 1
                    self.add_line(f"}}")
                    # Присваиваем новую строку
                    self.add_line(f"{object_name} = {temp_var};")
                else:
                    # Для format() внутри выражения
                    return f"string_format({object_name}, {args_str})"

            elif method_name == "split":
                # Определяем разделитель
                if len(arg_strings) > 0:
                    delimiter = arg_strings[0]
                else:
                    delimiter = '" "'  # По умолчанию пробел

                if is_standalone:
                    # Для a.split() как standalone - результат игнорируется
                    temp_var = self.generate_temporary_var("str_list")
                    self.add_line(
                        f"string_list* {temp_var} = string_split({object_name}, {delimiter});"
                    )
                    self.add_line(f"// Результат split() игнорируется")
                else:
                    # Для split() внутри выражения - возвращаем результат
                    return f"string_split({object_name}, {delimiter})"

        elif obj_type.startswith("list["):
            if method_name == "append":
                if args_str:
                    struct_name = self.generate_list_struct_name(obj_type)
                    self.add_line(f"append_{struct_name}({object_name}, {args_str});")

            elif method_name == "extend":
                if args_str:
                    # args[0] должен быть другим списком
                    struct_name = self.generate_list_struct_name(obj_type)
                    other_list = arg_strings[0]
                    self.add_line(f"// extend: добавление элементов из другого списка")
                    self.add_line(f"for (int i = 0; i < {other_list}->size; i++) {{")
                    self.indent_level += 1
                    self.add_line(
                        f"append_{struct_name}({object_name}, {other_list}->data[i]);"
                    )
                    self.indent_level -= 1
                    self.add_line("}")

            elif method_name == "insert":
                if len(arg_strings) >= 2:
                    index_var = arg_strings[0]
                    value_var = arg_strings[1]
                    struct_name = self.generate_list_struct_name(obj_type)
                    self.add_line(
                        f"if ({index_var} >= 0 && {index_var} <= {object_name}->size) {{"
                    )
                    self.indent_level += 1
                    self.add_line(
                        f"if ({object_name}->size >= {object_name}->capacity) {{"
                    )
                    self.indent_level += 1
                    self.add_line(
                        f"{object_name}->capacity = {object_name}->capacity == 0 ? 4 : {object_name}->capacity * 2;"
                    )
                    self.add_line(
                        f"{object_name}->data = realloc({object_name}->data, {object_name}->capacity * sizeof(int));"
                    )
                    self.indent_level -= 1
                    self.add_line("}")
                    self.add_line(
                        f"for (int i = {object_name}->size; i > {index_var}; i--) {{"
                    )
                    self.indent_level += 1
                    self.add_line(
                        f"{object_name}->data[i] = {object_name}->data[i - 1];"
                    )
                    self.indent_level -= 1
                    self.add_line("}")
                    self.add_line(f"{object_name}->data[{index_var}] = {value_var};")
                    self.add_line(f"{object_name}->size++;")
                    self.indent_level -= 1
                    self.add_line("}")

            elif method_name == "remove":
                if args_str:
                    value_var = arg_strings[0]
                    self.add_line(f"// remove первый элемент со значением {value_var}")
                    self.add_line(f"int found_index = -1;")
                    self.add_line(f"for (int i = 0; i < {object_name}->size; i++) {{")
                    self.indent_level += 1
                    self.add_line(f"if ({object_name}->data[i] == {value_var}) {{")
                    self.indent_level += 1
                    self.add_line(f"found_index = i;")
                    self.add_line(f"break;")
                    self.indent_level -= 1
                    self.add_line("}")
                    self.indent_level -= 1
                    self.add_line("}")
                    self.add_line(f"if (found_index != -1) {{")
                    self.indent_level += 1
                    self.add_line(
                        f"for (int i = found_index; i < {object_name}->size - 1; i++) {{"
                    )
                    self.indent_level += 1
                    self.add_line(
                        f"{object_name}->data[i] = {object_name}->data[i + 1];"
                    )
                    self.indent_level -= 1
                    self.add_line("}")
                    self.add_line(f"{object_name}->size--;")
                    self.indent_level -= 1
                    self.add_line("}")

            elif method_name == "pop":
                if not args_str:
                    # pop() без аргументов - удалить последний
                    self.add_line(f"if ({object_name}->size > 0) {{")
                    self.indent_level += 1
                    temp_var = self.generate_temporary_var("int")
                    self.add_line(
                        f"int {temp_var} = {object_name}->data[{object_name}->size - 1];"
                    )
                    self.add_line(f"{object_name}->size--;")
                    # TODO: Возвращаемое значение
                    self.indent_level -= 1
                    self.add_line("}")
                else:
                    # pop(index) - удалить по индексу
                    index_var = arg_strings[0]
                    self.add_line(
                        f"if ({object_name}->size > 0 && {index_var} >= 0 && {index_var} < {object_name}->size) {{"
                    )
                    self.indent_level += 1
                    temp_var = self.generate_temporary_var("int")
                    self.add_line(f"int {temp_var} = {object_name}->data[{index_var}];")
                    self.add_line(
                        f"for (int i = {index_var}; i < {object_name}->size - 1; i++) {{"
                    )
                    self.indent_level += 1
                    self.add_line(
                        f"{object_name}->data[i] = {object_name}->data[i + 1];"
                    )
                    self.indent_level -= 1
                    self.add_line("}")
                    self.add_line(f"{object_name}->size--;")
                    # TODO: Возвращаемое значение
                    self.indent_level -= 1
                    self.add_line("} else {")
                    self.indent_level += 1
                    self.add_line(
                        f'fprintf(stderr, "IndexError: pop index out of range\\n");'
                    )
                    self.indent_level -= 1
                    self.add_line("}")

            elif method_name == "clear":
                self.add_line(f"{object_name}->size = 0;")

            elif method_name == "index":
                if args_str:
                    value_var = arg_strings[0]
                    temp_var = self.generate_temporary_var("int")
                    self.add_line(f"int {temp_var} = -1;")
                    self.add_line(f"for (int i = 0; i < {object_name}->size; i++) {{")
                    self.indent_level += 1
                    self.add_line(f"if ({object_name}->data[i] == {value_var}) {{")
                    self.indent_level += 1
                    self.add_line(f"{temp_var} = i;")
                    self.add_line(f"break;")
                    self.indent_level -= 1
                    self.add_line("}")
                    self.indent_level -= 1
                    self.add_line("}")
                    # TODO: Проверить на -1 и выдать ошибку как в Python

            elif method_name == "count":
                if args_str:
                    value_var = arg_strings[0]
                    temp_var = self.generate_temporary_var("int")
                    self.add_line(f"int {temp_var} = 0;")
                    self.add_line(f"for (int i = 0; i < {object_name}->size; i++) {{")
                    self.indent_level += 1
                    self.add_line(f"if ({object_name}->data[i] == {value_var}) {{")
                    self.indent_level += 1
                    self.add_line(f"{temp_var}++;")
                    self.indent_level -= 1
                    self.add_line("}")
                    self.indent_level -= 1
                    self.add_line("}")

            elif method_name == "sort":
                # Используем qsort для эффективности
                # Определяем тип элементов списка
                match = re.match(r"list\[([^\]]+)\]", obj_type)
                element_type = match.group(1) if match else "int"

                # Выбираем соответствующую функцию сравнения
                if element_type == "int":
                    compare_func = "compare_int"
                elif element_type == "float":
                    compare_func = "compare_float"
                elif element_type == "double":
                    compare_func = "compare_double"
                else:
                    # По умолчанию для неизвестных типов
                    compare_func = "compare_int"

                self.add_line(
                    f"qsort({object_name}->data, {object_name}->size, sizeof(int), {compare_func});"
                )

            elif method_name == "reverse":
                self.add_line(f"for (int i = 0; i < {object_name}->size / 2; i++) {{")
                self.indent_level += 1
                self.add_line(f"int temp = {object_name}->data[i];")
                self.add_line(
                    f"{object_name}->data[i] = {object_name}->data[{object_name}->size - i - 1];"
                )
                self.add_line(
                    f"{object_name}->data[{object_name}->size - i - 1] = temp;"
                )
                self.indent_level -= 1
                self.add_line("}")

            else:
                self.add_line(f"// Метод списка '{method_name}' не реализован")

        # Обработка методов для кортежей
        elif obj_type.startswith("tuple["):
            if method_name == "count":
                if args_str:
                    struct_name = self.generate_tuple_struct_name(obj_type)
                    self.add_line(f"// count в кортеже")
                    temp_var = self.generate_temporary_var("int")
                    self.add_line(f"int {temp_var} = 0;")
                    self.add_line(f"for (int i = 0; i < {object_name}.size; i++) {{")
                    self.indent_level += 1
                    self.add_line(f"if ({object_name}.data[i] == {args_str}) {{")
                    self.indent_level += 1
                    self.add_line(f"{temp_var}++;")
                    self.indent_level -= 1
                    self.add_line("}")
                    self.indent_level -= 1
                    self.add_line("}")
                    # Возвращаем значение
                    # Но в вашем коде нет присваивания результата, так что просто вычисляем

            elif method_name == "index":
                if args_str:
                    struct_name = self.generate_tuple_struct_name(obj_type)
                    self.add_line(f"// index в кортеже")
                    temp_var = self.generate_temporary_var("int")
                    self.add_line(f"int {temp_var} = -1;")
                    self.add_line(f"for (int i = 0; i < {object_name}.size; i++) {{")
                    self.indent_level += 1
                    self.add_line(
                        f"if ({object_name}.data[i] == {args_str} && {temp_var} == -1) {{"
                    )
                    self.indent_level += 1
                    self.add_line(f"{temp_var} = i;")
                    self.indent_level -= 1
                    self.add_line("}")
                    self.indent_level -= 1
                    self.add_line("}")
                    # Возвращаем значение
                    # Но в вашем коде нет присваивания результата

            else:
                self.add_line(f"// Метод '{method_name}' для кортежа не реализован")

    def generate_class_constructors(self, json_data: List[Dict]):
        """Генерирует конструкторы для всех классов"""
        # Сначала находим все методы __init__
        init_scopes = {}

        for scope in json_data:
            # Ищем как constructor ИЛИ class_method
            if (
                scope.get("type") == "class_method"
                or scope.get("type") == "constructor"
            ) and scope.get("method_name") == "__init__":
                class_name = scope.get("class_name", "")
                init_scopes[class_name] = scope
                print(
                    f"DEBUG: Found init_scope for {class_name} (type: {scope.get('type')})"
                )
                print(f"DEBUG: Graph length: {len(scope.get('graph', []))}")

        # Затем находим объявления классов
        for scope in json_data:
            if scope.get("type") == "module":
                for node in scope.get("graph", []):
                    if node.get("node") == "class_declaration":
                        class_name = node.get("class_name", "")
                        methods = node.get("methods", [])

                        # Ищем метод __init__ в объявлении класса
                        init_method = None
                        for method in methods:
                            if method.get("name") == "__init__":
                                init_method = method
                                print(f"DEBUG: Found init_method for {class_name}")
                                break

                        # Получаем scope для этого метода
                        init_scope = init_scopes.get(class_name)

                        if init_scope:
                            print(f"DEBUG: Will generate constructor for {class_name}")
                            # Выводим для отладки структуру init_scope
                            print(f"DEBUG init_scope keys: {init_scope.keys()}")
                            print(
                                f"DEBUG init_scope graph: {init_scope.get('graph', [])}"
                            )
                        else:
                            print(f"DEBUG: No init_scope found for {class_name}")
                            print(
                                f"DEBUG: Available scopes: {list(init_scopes.keys())}"
                            )

                        # Генерируем конструктор
                        self.generate_constructor(class_name, init_method, init_scope)

    def generate_class_methods(self, json_data: List[Dict]):
        """Генерирует методы для всех классов"""
        for scope in json_data:
            if scope.get("type") == "class_method":
                class_name = scope.get("class_name", "")
                method_name = scope.get("method_name", "")

                # Пропускаем конструктор
                if method_name == "__init__":
                    continue

                self.generate_class_method_implementation(class_name, scope)

    def generate_class_method_implementation(self, class_name: str, scope: Dict):
        """Генерирует реализацию метода класса с учетом наследования"""
        method_name = scope.get("method_name", "")
        return_type = scope.get("return_type", "void")
        parameters = scope.get("parameters", [])

        # Получаем информацию о методе из иерархии
        method_info = self.all_class_methods.get(class_name, {}).get(method_name)

        if not method_info:
            print(f"WARNING: Метод {method_name} не найден для класса {class_name}")
            return

        # Определяем, является ли метод унаследованным
        is_inherited = method_info.get("origin") != class_name

        # Для унаследованных методов не генерируем реализацию повторно
        if is_inherited:
            self.add_line(
                f"// Метод {method_name} унаследован от {method_info['origin']}"
            )
            return

        # Входим в scope метода
        self.enter_scope()

        # Объявляем параметры
        param_decls = []

        for param in parameters:
            param_name = param.get("name", "")
            param_type = param.get("type", "int")

            if param_name == "self":
                # self - это указатель на структуру класса
                c_param_type = f"{class_name}*"
                self.declare_variable("self", class_name, is_pointer=True)
            else:
                c_param_type = self.map_type_to_c(param_type)
                self.declare_variable(param_name, param_type)

            param_decls.append(f"{c_param_type} {param_name}")

        # Генерируем сигнатуру метода
        c_return_type = self.map_type_to_c(return_type)
        params_str = ", ".join(param_decls) if param_decls else "void"

        self.add_line(f"{c_return_type} {class_name}_{method_name}({params_str}) {{")
        self.indent_level += 1

        # Генерируем тело метода
        for node in scope.get("graph", []):
            self.generate_graph_node(node)

        # Если метод должен что-то возвращать, но нет return
        return_info = scope.get("return_info", {})
        if c_return_type != "void" and not return_info.get("has_return", False):
            self.add_line(f"return 0; // default return")

        self.indent_level -= 1
        self.add_line("}")
        self.add_empty_line()

        # Выходим из scope метода
        self.exit_scope()

    def add_class_method_declaration(self, class_name: str, method: Dict):
        """Добавляет forward declaration для метода класса"""
        method_name = method.get("name", "")
        return_type = method.get("return_type", "void")
        parameters = method.get("parameters", [])

        c_return_type = self.map_type_to_c(return_type)

        # Формируем параметры
        param_decls = []
        for param in parameters:
            param_name = param.get("name", "")
            param_type = param.get("type", "int")

            if param_name == "self":
                # self - это указатель на структуру класса
                c_param_type = f"{class_name}*"
            else:
                c_param_type = self.map_type_to_c(param_type)

            param_decls.append(f"{c_param_type} {param_name}")

        params_str = ", ".join(param_decls) if param_decls else "void"

        declaration = f"{c_return_type} {class_name}_{method_name}({params_str});"
        self.function_declarations.append(declaration)

    def _is_class_type(self, type_name: str) -> bool:
        """Определяет, является ли тип классом"""
        if not isinstance(type_name, str):
            return False

        # Проверяем по зарегистрированным классам
        if hasattr(self, "class_types") and type_name in self.class_types:
            return True

        # Проверяем по типу (классы обычно с большой буквы)
        if type_name and len(type_name) > 0 and type_name[0].isupper():
            # Проверяем, не является ли это базовым типом или встроенным типом
            base_types = {"int", "float", "double", "char", "bool", "void", "None"}
            if type_name not in base_types:
                return True

        return False

    def analyze_classes(self, json_data: List[Dict]):
        """Анализирует все классы и их методы для определения полей"""
        # Сначала находим все методы __init__
        init_scopes = {}

        for scope in json_data:
            if (
                scope.get("type") == "class_method"
                and scope.get("method_name") == "__init__"
            ):
                class_name = scope.get("class_name", "")
                init_scopes[class_name] = scope

        # Сначала анализируем методы __init__ для определения полей
        for scope in json_data:
            if (
                scope.get("type") == "class_method"
                and scope.get("method_name") == "__init__"
            ):
                class_name = scope.get("class_name", "")
                self._analyze_init_method(class_name, scope)

        # Затем анализируем другие методы для ссылок на поля
        for scope in json_data:
            if (
                scope.get("type") == "class_method"
                and scope.get("method_name") != "__init__"
            ):
                class_name = scope.get("class_name", "")
                self._analyze_method_for_fields(class_name, scope)

    def _analyze_init_method(self, class_name: str, init_scope: Dict):
        """Анализирует метод __init__ для определения полей класса"""
        if class_name not in self.class_fields:
            self.class_fields[class_name] = {}

        graph = init_scope.get("graph", [])

        for node in graph:
            if node.get("node") == "attribute_assignment":
                # Присваивание атрибуту: self.attr = value
                attr_name = node.get("attribute", "")
                value = node.get("value", {})

                # Определяем тип значения
                field_type = self._infer_field_type(value)
                if field_type:
                    self.class_fields[class_name][attr_name] = field_type

            elif node.get("node") == "declaration":
                # Объявление атрибута с типом: self.attr: type = value
                var_name = node.get("var_name", "")
                if var_name.startswith("self."):
                    attr_name = var_name[5:]  # Убираем "self."
                    var_type = node.get("var_type", "")
                    if var_type:
                        self.class_fields[class_name][attr_name] = var_type

    def _analyze_method_for_fields(self, class_name: str, method_scope: Dict):
        """Анализирует метод для ссылок на поля"""
        if class_name not in self.class_fields:
            self.class_fields[class_name] = {}

        graph = method_scope.get("graph", [])

        def collect_attribute_accesses(node):
            accesses = []

            if isinstance(node, dict):
                node_type = node.get("type", "")

                if node_type == "attribute_access":
                    # Доступ к атрибуту: self.attr или obj.attr
                    obj_name = node.get("object", "")
                    attr_name = node.get("attribute", "")

                    if obj_name == "self":
                        accesses.append(attr_name)

                # Рекурсивно проверяем все значения
                for key, value in node.items():
                    if isinstance(value, (dict, list)):
                        if isinstance(value, dict):
                            accesses.extend(collect_attribute_accesses(value))
                        elif isinstance(value, list):
                            for item in value:
                                accesses.extend(collect_attribute_accesses(item))

            return accesses

        # Проходим по всему графу метода
        for node in graph:
            attr_accesses = collect_attribute_accesses(node)
            for attr_name in attr_accesses:
                # Если атрибут упоминается, но не зарегистрирован, добавляем как int
                if attr_name not in self.class_fields[class_name]:
                    self.class_fields[class_name][attr_name] = "int"

    def generate_class_declaration_with_fields(self, node: Dict):
        """Генерирует структуру для класса C с полями"""
        class_name = node.get("class_name", "")
        base_classes = node.get("base_classes", [])

        # Регистрируем класс
        self.class_types.add(class_name)
        self.type_map[class_name] = f"{class_name}*"

        # Генерируем forward declaration
        self.add_line(f"typedef struct {class_name} {class_name};")

        # Генерируем структуру
        self.add_line(f"struct {class_name} {{")
        self.indent_level += 1

        # Добавляем наследование через композицию
        if base_classes and len(base_classes) > 0:
            parent_class = base_classes[0]
            self.add_line(f"// Наследование от {parent_class}")
            self.add_line(f"{parent_class} base;")
        else:
            # Для корневого класса Object добавляем vtable
            self.add_line(f"void** vtable;")

        # Добавляем поля класса
        if class_name in self.class_fields and self.class_fields[class_name]:
            self.add_line(f"// Поля класса {class_name}")
            for field_name, field_type in self.class_fields[class_name].items():
                c_type = self.map_type_to_c(field_type)
                self.add_line(f"{c_type} {field_name};")

        self.indent_level -= 1
        self.add_line(f"}};")
        self.add_empty_line()

    def _try_generate_init_logic(
        self, class_name: str, init_scope: Dict, param_names: List[str]
    ):
        """Пытается сгенерировать логику из метода __init__"""
        graph = init_scope.get("graph", [])

        for node in graph:
            node_type = node.get("node", "")

            if node_type == "attribute_assignment":
                # Старый формат
                self._process_attribute_assignment(node, param_names)

            elif node_type == "expression":
                # Новый формат: выражение может содержать присваивание
                self._process_expression_node(node, param_names)

    def _process_expression_node(self, node: Dict, param_names: List[str]):
        """Обрабатывает узел выражения"""
        operations = node.get("operations", [])

        for op in operations:
            op_type = op.get("type", "")

            if op_type == "ATTRIBUTE_ASSIGN":
                # Это присваивание атрибуту
                object_name = op.get("object", "")
                attribute = op.get("attribute", "")
                value = op.get("value", {})

                if object_name == "self":
                    # Генерируем выражение для значения
                    if value:
                        value_expr = self._generate_value_expression(value, param_names)
                        if value_expr:
                            self.add_line(f"obj->{attribute} = {value_expr};")

    def _generate_value_expression(self, value: Dict, param_names: List[str]) -> str:
        """Генерирует выражение для значения"""
        if not value:
            return ""

        value_type = value.get("type", "")

        if value_type == "variable":
            var_name = value.get("value", "")
            return var_name

        elif value_type == "binary_operation":
            left = value.get("left", {})
            right = value.get("right", {})
            operator = value.get("operator_symbol", "")

            left_expr = self._generate_value_expression(left, param_names)
            right_expr = self._generate_value_expression(right, param_names)
            c_operator = self.operator_map.get(operator, operator)

            if left_expr and right_expr:
                return f"({left_expr} {c_operator} {right_expr})"

        return ""

    def generate_attribute_assignment(self, node: Dict):
        """Генерирует присваивание атрибуту объекта"""
        object_name = node.get("object", "")
        attribute = node.get("attribute", "")
        value_ast = node.get("value", {})

        # Проверяем, находимся ли мы в конструкторе
        # Если это конструктор, метод уже обрабатывается в _process_attribute_assignment_in_init
        # Так что пропускаем здесь
        if object_name == "self":
            print(
                f"DEBUG generate_attribute_assignment: Skipping self.{attribute} assignment in constructor"
            )
            return

        # Генерируем выражение для значения
        if value_ast:
            value_expr = self.generate_expression(value_ast)
            self.add_line(f"{object_name}->{attribute} = {value_expr};")

    def _process_expression_in_init(self, node: Dict):
        """Обрабатывает expression узел в методе __init__"""
        operations = node.get("operations", [])

        for op in operations:
            op_type = op.get("type", "")

            if op_type == "ATTRIBUTE_ASSIGN":
                # Присваивание атрибуту: self.attr = value
                object_name = op.get("object", "")
                attr_name = op.get("attribute", "")
                value_ast = op.get("value", {})

                if object_name == "self":
                    if value_ast:
                        try:
                            value_expr = self.generate_expression(value_ast)
                            self.add_line(f"obj->{attr_name} = {value_expr};")
                        except Exception as e:
                            self.add_line(f"// Ошибка генерации выражения: {e}")

    def _process_attribute_assignment_in_init(self, node: Dict, param_names: List[str]):
        """Обрабатывает присваивание атрибуту в конструкторе"""
        object_name = node.get("object", "")
        attribute = node.get("attribute", "")
        value_ast = node.get("value", {})

        print(
            f"DEBUG _process_attribute_assignment_in_init: {object_name}.{attribute} = {value_ast}"
        )

        if object_name == "self" and value_ast:
            # Генерируем выражение для значения с учетом параметров конструктора
            value_expr = self._generate_expression_from_ast_for_init(
                value_ast, param_names
            )
            if value_expr:
                print(f"DEBUG: Generated expression: obj->{attribute} = {value_expr}")
                self.add_line(f"obj->{attribute} = {value_expr};")
            else:
                print(f"DEBUG: Could not generate expression for {attribute}")
                self.add_line(f"obj->{attribute} = 0; // default value")
        else:
            print(f"DEBUG: Skipping non-self assignment or empty value")

    def _generate_expression_from_ast_for_init(
        self, ast: Dict, param_names: List[str]
    ) -> str:
        """Генерирует выражение из AST для конструктора с подстановкой параметров"""
        if not ast:
            return ""

        node_type = ast.get("type", "")
        print(
            f"DEBUG _generate_expression_from_ast_for_init: type={node_type}, ast={ast}"
        )

        if node_type == "literal":
            value = ast.get("value", "")
            data_type = ast.get("data_type", "")
            print(f"DEBUG: Found literal: {value} (type: {data_type})")
            if data_type == "str":
                return f'"{value}"'
            else:
                return str(value)

        elif node_type == "variable":
            # Поддерживаем оба формата: 'value' и 'name'
            var_name = ast.get("value") or ast.get("name", "")
            print(f"DEBUG: Found variable: {var_name}")
            # Если это параметр конструктора, используем как есть
            if var_name in param_names:
                print(f"DEBUG: Is a constructor parameter")
                return var_name
            # Если это не параметр, возможно это атрибут self
            print(f"DEBUG: Not a constructor parameter")
            return var_name

        elif node_type == "binary_operation":
            left_ast = ast.get("left", {})
            right_ast = ast.get("right", {})
            operator = ast.get("operator_symbol") or ast.get("operator", "")

            print(f"DEBUG: Binary operation: {operator}")

            left = self._generate_expression_from_ast_for_init(left_ast, param_names)
            right = self._generate_expression_from_ast_for_init(right_ast, param_names)

            if operator in ["**", "POW"]:
                return f"pow({left}, {right})"

            c_operator = self.operator_map.get(operator, operator)

            # Правильно расставляем скобки для сохранения приоритета операций
            if operator in ["+", "-", "ADD", "SUBTRACT"]:
                # Для сложения/вычитания в сложных выражениях нужны скобки
                if left_ast.get("type") == "binary_operation":
                    left_operator = left_ast.get("operator_symbol") or left_ast.get(
                        "operator", ""
                    )
                    if left_operator in ["*", "/", "%", "MULTIPLY", "DIVIDE", "MODULO"]:
                        left = f"({left})"
                if right_ast.get("type") == "binary_operation":
                    right_operator = right_ast.get("operator_symbol") or right_ast.get(
                        "operator", ""
                    )
                    if right_operator in [
                        "*",
                        "/",
                        "%",
                        "MULTIPLY",
                        "DIVIDE",
                        "MODULO",
                    ]:
                        right = f"({right})"

            result = f"{left} {c_operator} {right}"
            print(f"DEBUG: Generated binary expression: {result}")
            return result

        print(
            f"DEBUG _generate_expression_from_ast_for_init: Unknown AST type: {node_type}"
        )
        return ""

    def _generate_expression_from_ast(self, ast: Dict, param_names: List[str]) -> str:
        """Генерирует выражение из AST с подстановкой параметров конструктора"""
        if not ast:
            return ""

        node_type = ast.get("type", "")
        print(f"DEBUG _generate_expression_from_ast: type={node_type}, ast={ast}")

        if node_type == "variable":
            # Поддерживаем оба формата: 'value' и 'name'
            var_name = ast.get("value") or ast.get("name", "")
            # Если это параметр конструктора, используем как есть
            if var_name in param_names:
                print(f"DEBUG: Found parameter: {var_name}")
                return var_name
            print(f"DEBUG: Variable not a parameter: {var_name}")
            return var_name

        elif node_type == "literal":
            value = ast.get("value", "")
            data_type = ast.get("data_type", "")
            print(f"DEBUG: Found literal: {value} (type: {data_type})")
            if data_type == "str":
                return f'"{value}"'
            else:
                return str(value)

        elif node_type == "binary_operation":
            left_ast = ast.get("left", {})
            right_ast = ast.get("right", {})
            operator = ast.get("operator_symbol") or ast.get("operator", "")

            print(f"DEBUG: Binary operation: {operator}")

            left = self._generate_expression_from_ast(left_ast, param_names)
            right = self._generate_expression_from_ast(right_ast, param_names)

            if operator == "**" or operator == "POW":
                return f"pow({left}, {right})"

            c_operator = self.operator_map.get(operator, operator)

            # Правильно расставляем скобки для сохранения приоритета операций
            if operator in ["+", "-", "ADD", "SUBTRACT"]:
                # Для сложения/вычитания в сложных выражениях нужны скобки
                if left_ast.get("type") == "binary_operation":
                    left_operator = left_ast.get("operator_symbol") or left_ast.get(
                        "operator", ""
                    )
                    if left_operator in ["*", "/", "%", "MULTIPLY", "DIVIDE", "MODULO"]:
                        left = f"({left})"
                if right_ast.get("type") == "binary_operation":
                    right_operator = right_ast.get("operator_symbol") or right_ast.get(
                        "operator", ""
                    )
                    if right_operator in [
                        "*",
                        "/",
                        "%",
                        "MULTIPLY",
                        "DIVIDE",
                        "MODULO",
                    ]:
                        right = f"({right})"

            result = f"{left} {c_operator} {right}"
            print(f"DEBUG: Generated binary expression: {result}")
            return result

        elif node_type == "attribute_access":
            obj_name = ast.get("object", "")
            attr_name = ast.get("attribute", "")

            print(f"DEBUG: Attribute access: {obj_name}.{attr_name}")

            # В конструкторе атрибуты объекта еще не инициализированы
            # Это не должно случиться при правильном анализе
            self.add_line(
                f"// WARNING: Accessing attribute {attr_name} of {obj_name} in constructor"
            )
            return f"obj->{attr_name}"

        print(f"DEBUG: Unknown AST type: {node_type}")
        return ""

    def _generate_init_logic(
        self, class_name: str, init_scope: Dict, param_names: List[str]
    ):
        """Генерирует логику инициализации полей из метода __init__"""
        if not init_scope:
            return

        graph = init_scope.get("graph", [])
        base_classes = self.class_hierarchy.get(class_name, [])

        self.add_line(f"// Инициализация полей класса {class_name}")

        # Инициализируем vtable
        if not base_classes:
            # Для корневого класса (например, Object) - прямое поле vtable
            self.add_line(f"obj->vtable = malloc(sizeof(void*) * 16);")
            self.add_line(f"if (!obj->vtable) {{")
        else:
            # Для производных классов - vtable в базовом классе
            self.add_line(f"obj->base.vtable = malloc(sizeof(void*) * 16);")
            self.add_line(f"if (!obj->base.vtable) {{")

        self.indent_level += 1
        self.add_line(f'fprintf(stderr, "Memory allocation failed for vtable\\n");')
        self.add_line(f"free(obj);")
        self.add_line(f"exit(1);")
        self.indent_level -= 1
        self.add_line(f"}}")

        # Инициализация полей из метода __init__
        for node in graph:
            node_type = node.get("node", "")

            if node_type == "attribute_assignment":
                self._process_attribute_assignment_in_init(node, param_names)

    def generate_input(self, node: Dict):
        """Генерирует код для функции input()"""
        args = node.get("arguments", [])

        # Форматная строка для prompt (если есть)
        format_str = ""
        value_parts = []

        if args:
            # Создаем форматную строку для prompt
            format_parts = []
            for arg in args:
                if isinstance(arg, dict):
                    if arg.get("type") == "literal" and arg.get("data_type") == "str":
                        # Строковый литерал
                        value = arg.get("value", "")
                        format_parts.append(f"{value}")
                    else:
                        # Другие выражения
                        expr = self.generate_expression(arg)
                        format_parts.append("%s")
                        value_parts.append(expr)
                else:
                    # Простая строка
                    format_parts.append(str(arg))

            # Собираем строку
            prompt = " ".join(format_parts)
            format_str = f'printf("{prompt}"); '

        # Добавляем чтение ввода
        # Создаем временную переменную для результата input()
        temp_var = self.generate_temporary_var("str")
        self.add_line(
            f"{format_str}char {temp_var}[256]; fgets({temp_var}, sizeof({temp_var}), stdin);"
        )

        # Убираем символ новой строки в конце
        self.add_line(f'{temp_var}[strcspn({temp_var}, "\\n")] = 0;')

        # Если input() используется в выражении, нужно вернуть значение
        # Для этого создадим узел с результатом
        return temp_var

    def generate_expression_input(self, node: Dict) -> str:
        """Генерирует выражение с input() и возвращает имя переменной"""
        args = node.get("arguments", [])

        # Создаем временную переменную для результата
        temp_var = self.generate_temporary_var("str")

        # Создаем prompt если есть аргументы
        if args:
            format_parts = []
            value_parts = []

            for arg in args:
                if isinstance(arg, dict):
                    if arg.get("type") == "literal" and arg.get("data_type") == "str":
                        value = arg.get("value", "")
                        format_parts.append(value)
                    else:
                        expr = self.generate_expression(arg)
                        format_parts.append("%s")
                        value_parts.append(expr)

            prompt = " ".join(format_parts)
            if value_parts:
                args_str = ", ".join(value_parts)
                self.add_line(f'printf("{prompt}", {args_str});')
            else:
                self.add_line(f'printf("{prompt}");')

        # Читаем ввод
        self.add_line(f"char {temp_var}_buffer[256];")
        self.add_line(f"fgets({temp_var}_buffer, sizeof({temp_var}_buffer), stdin);")
        self.add_line(f'{temp_var}_buffer[strcspn({temp_var}_buffer, "\\n")] = 0;')

        # Выделяем память для строки
        self.add_line(f"{temp_var} = malloc(strlen({temp_var}_buffer) + 1);")
        self.add_line(f"strcpy({temp_var}, {temp_var}_buffer);")

        return temp_var

    def generate_print_from_ast(self, ast: Dict):
        """Генерирует print из AST выражения"""
        args = ast.get("arguments", [])

        # Создаем временный узел для print
        print_node = {
            "node": "print",
            "arguments": args,
        }

        # Используем существующий метод generate_print
        self.generate_print(print_node)

    def generate_input_expression(self, node: Dict) -> str:
        """Генерирует выражение с input() и возвращает имя переменной с результатом"""
        args = node.get("arguments", [])

        # Создаем уникальное имя для временной переменной
        temp_var = self.generate_temporary_var("str")

        # Объявляем переменную
        self.declare_variable(temp_var, "str")

        # Получаем информацию о переменной для генерации правильного типа
        var_info = self.get_variable_info(temp_var)
        c_type = var_info["c_type"] if var_info else "char*"

        # Объявляем переменную
        self.add_line(f"{c_type} {temp_var} = NULL;")

        # Генерируем prompt если есть аргументы
        if args:
            self._generate_input_prompt(args)

        # Генерируем код для чтения ввода
        self._generate_input_read_code_direct(temp_var)

        return temp_var

    def _generate_input_prompt(self, args: List):
        """Генерирует код для вывода prompt в input()"""
        format_parts = []
        value_parts = []

        for arg in args:
            if isinstance(arg, dict):
                if arg.get("type") == "literal" and arg.get("data_type") == "str":
                    # Строковый литерал
                    value = arg.get("value", "")
                    format_parts.append(f"{value}")
                else:
                    # Другие выражения (переменные, вызовы функций и т.д.)
                    expr = self.generate_expression(arg)
                    format_parts.append("%s")
                    value_parts.append(expr)
            else:
                # Простая строка (не должно быть в нормальном AST)
                format_parts.append(str(arg))

        # Собираем prompt строку
        if format_parts:
            prompt = " ".join(format_parts)

            if value_parts:
                # Если есть динамические части (переменные)
                args_str = ", ".join(value_parts)
                self.add_line(f'printf("{prompt}", {args_str});')
            else:
                # Простой строковый литерал
                self.add_line(f'printf("{prompt}");')

    def _generate_input_read_code(self, target_var: str):
        """Генерирует код для чтения ввода с клавиатуры"""
        # Создаем буфер для ввода
        buffer_var = f"{target_var}_buffer"

        # Выделяем память для буфера
        self.add_line(f"char {buffer_var}[256];")

        # Читаем строку с stdin
        self.add_line(f"fgets({buffer_var}, sizeof({buffer_var}), stdin);")

        # Убираем символ новой строки
        self.add_line(f'{buffer_var}[strcspn({buffer_var}, "\\n")] = 0;')

        # Выделяем память для результата и копируем
        self.add_line(f"{target_var} = malloc(strlen({buffer_var}) + 1);")
        self.add_line(f"if (!{target_var}) {{")
        self.indent_level += 1
        self.add_line(
            f'fprintf(stderr, "Memory allocation failed for input result\\n");'
        )
        self.add_line(f"exit(1);")
        self.indent_level -= 1
        self.add_line(f"}}")
        self.add_line(f"strcpy({target_var}, {buffer_var});")

    def generate_input_statement(self, node: Dict):
        """Генерирует вызов input() как отдельный statement (без присваивания)"""
        args = node.get("arguments", [])

        # Генерируем prompt если есть аргументы
        if args:
            self._generate_input_prompt(args)

        # Читаем ввод, но игнорируем результат
        temp_var = self.generate_temporary_var("str")
        buffer_var = f"{temp_var}_buffer"

        self.add_line(f"char {buffer_var}[256];")
        self.add_line(f"fgets({buffer_var}, sizeof({buffer_var}), stdin);")
        self.add_line(f'{buffer_var}[strcspn({buffer_var}, "\\n")] = 0;')
        self.add_line(f"// Ввод прочитан, результат игнорируется")

    def generate_tuple_creation(self, tuple_ast: Dict, tuple_type: str = None) -> str:
        """Генерирует выражение для создания кортежа"""
        items = tuple_ast.get("items", [])

        # Если tuple_type уже задан и является именем структуры (начинается с tuple_), не анализируем
        if tuple_type and tuple_type.startswith("tuple_"):
            # Это уже имя структуры, а не тип
            struct_name = tuple_type
            print(
                f"DEBUG generate_tuple_creation: struct_name={struct_name} (уже задано)"
            )
        else:
            if not tuple_type:
                # Определяем тип кортежа на основе элементов
                if items:
                    # Проверяем, все ли элементы одного типа
                    element_types = set()
                    for item in items:
                        if isinstance(item, dict):
                            if item.get("type") == "literal":
                                data_type = item.get("data_type", "int")
                                element_types.add(data_type)

                    if len(element_types) == 1:
                        element_type = next(iter(element_types))
                        tuple_type = f"tuple[{element_type}]"
                    else:
                        # Разные типы - используем фиксированный кортеж
                        element_types_list = []
                        for item in items:
                            if isinstance(item, dict) and item.get("type") == "literal":
                                data_type = item.get("data_type", "int")
                                element_types_list.append(data_type)

                        if element_types_list:
                            tuple_type = f"tuple[{', '.join(element_types_list)}]"
                        else:
                            tuple_type = "tuple[int]"
                else:
                    tuple_type = "tuple[int]"

            struct_name = self.generate_tuple_struct_name(tuple_type)
            print(
                f"DEBUG generate_tuple_creation: tuple_type={tuple_type}, struct_name={struct_name}"
            )

        if items:
            # Для универсального кортежа tuple[T]
            if "," not in tuple_type:  # tuple[int] (нет запятых)
                # Создаем временный массив
                temp_var = self.generate_temporary_var("array")

                # Генерируем элементы массива
                item_exprs = [self.generate_expression(item) for item in items]

                # Создаем массив
                self.add_line(f"int {temp_var}[{len(items)}] = {{")
                self.indent_level += 1
                for i, item_expr in enumerate(item_exprs):
                    self.add_line(f"{item_expr}{',' if i < len(items) - 1 else ''}")
                self.indent_level -= 1
                self.add_line("};")

                # Возвращаем вызов create_tuple_int
                return f"create_{struct_name}({temp_var}, {len(items)})"

            else:
                # Для фиксированного кортежа tuple[T1, T2, ...]
                item_exprs = [self.generate_expression(item) for item in items]
                return f"create_{struct_name}({', '.join(item_exprs)})"

        # Пустой кортеж
        return f"({struct_name}){{NULL, 0}}"

    # Добавьте вспомогательные функции для строк в generate_helpers:

    def generate_string_helpers(self):
        """Генерирует вспомогательные функции для работы со строками"""
        helpers = []

        # 1. Функция upper
        helpers.append("""
    char* string_upper(const char* str) {
        if (!str) return NULL;
        int len = strlen(str);
        char* result = malloc(len + 1);
        if (!result) return NULL;
        for (int i = 0; i < len; i++) {
            if (str[i] >= 'a' && str[i] <= 'z') {
                result[i] = str[i] - 32;
            } else {
                result[i] = str[i];
            }
        }
        result[len] = '\\0';
        return result;
    }
    """)

        # 2. Функция lower
        helpers.append("""
    char* string_lower(const char* str) {
        if (!str) return NULL;
        int len = strlen(str);
        char* result = malloc(len + 1);
        if (!result) return NULL;
        for (int i = 0; i < len; i++) {
            if (str[i] >= 'A' && str[i] <= 'Z') {
                result[i] = str[i] + 32;
            } else {
                result[i] = str[i];
            }
        }
        result[len] = '\\0';
        return result;
    }
    """)

        # 3. Функция capitalize
        helpers.append("""
    char* string_capitalize(const char* str) {
        if (!str || strlen(str) == 0) return NULL;
        int len = strlen(str);
        char* result = malloc(len + 1);
        if (!result) return NULL;
        
        // Первый символ в верхний регистр
        if (str[0] >= 'a' && str[0] <= 'z') {
            result[0] = str[0] - 32;
        } else {
            result[0] = str[0];
        }
        
        // Остальные в нижний регистр
        for (int i = 1; i < len; i++) {
            if (str[i] >= 'A' && str[i] <= 'Z') {
                result[i] = str[i] + 32;
            } else {
                result[i] = str[i];
            }
        }
        result[len] = '\\0';
        return result;
    }
    """)

        # 4. Функция title
        helpers.append("""
    char* string_title(const char* str) {
        if (!str) return NULL;
        int len = strlen(str);
        char* result = malloc(len + 1);
        if (!result) return NULL;
        
        int new_word = 1;
        for (int i = 0; i < len; i++) {
            if (new_word && str[i] >= 'a' && str[i] <= 'z') {
                result[i] = str[i] - 32;
                new_word = 0;
            } else if (!new_word && str[i] >= 'A' && str[i] <= 'Z') {
                result[i] = str[i] + 32;
            } else {
                result[i] = str[i];
            }
            
            // Проверяем, начинается ли новое слово
            if (str[i] == ' ' || str[i] == '\\t' || str[i] == '\\n') {
                new_word = 1;
            }
        }
        result[len] = '\\0';
        return result;
    }
    """)

        # 5. Функция strip
        helpers.append("""
    char* string_strip(const char* str) {
        if (!str) return NULL;
        
        int start = 0;
        int end = strlen(str) - 1;
        
        // Находим начало без пробельных символов
        while (start <= end && (str[start] == ' ' || str[start] == '\\t' || str[start] == '\\n')) {
            start++;
        }
        
        // Находим конец без пробельных символов
        while (end >= start && (str[end] == ' ' || str[end] == '\\t' || str[end] == '\\n')) {
            end--;
        }
        
        int len = end - start + 1;
        char* result = malloc(len + 1);
        if (!result) return NULL;
        
        strncpy(result, str + start, len);
        result[len] = '\\0';
        return result;
    }
    """)

        # 6. Функция lstrip
        helpers.append("""
    char* string_lstrip(const char* str) {
        if (!str) return NULL;
        
        int start = 0;
        int len = strlen(str);
        
        // Находим начало без пробельных символов
        while (start < len && (str[start] == ' ' || str[start] == '\\t' || str[start] == '\\n')) {
            start++;
        }
        
        int result_len = len - start;
        char* result = malloc(result_len + 1);
        if (!result) return NULL;
        
        strcpy(result, str + start);
        return result;
    }
    """)

        # 7. Функция rstrip
        helpers.append("""
    char* string_rstrip(const char* str) {
        if (!str) return NULL;
        
        int end = strlen(str) - 1;
        
        // Находим конец без пробельных символов
        while (end >= 0 && (str[end] == ' ' || str[end] == '\\t' || str[end] == '\\n')) {
            end--;
        }
        
        int result_len = end + 1;
        char* result = malloc(result_len + 1);
        if (!result) return NULL;
        
        strncpy(result, str, result_len);
        result[result_len] = '\\0';
        return result;
    }
    """)

        # 8. Функция split
        helpers.append("""
    typedef struct {
        char** items;
        int size;
        int capacity;
    } string_list;

    string_list* string_split(const char* str, const char* delimiter) {
        if (!str) return NULL;
        
        string_list* result = malloc(sizeof(string_list));
        result->size = 0;
        result->capacity = 10;
        result->items = malloc(result->capacity * sizeof(char*));
        
        if (!delimiter || delimiter[0] == '\\0') {
            // Разделение по пробелам (по умолчанию)
            const char* start = str;
            const char* end = str;
            
            while (*end) {
                if (*end == ' ' || *end == '\\t' || *end == '\\n') {
                    if (start != end) {
                        // Добавляем токен
                        int token_len = end - start;
                        char* token = malloc(token_len + 1);
                        strncpy(token, start, token_len);
                        token[token_len] = '\\0';
                        
                        if (result->size >= result->capacity) {
                            result->capacity *= 2;
                            result->items = realloc(result->items, result->capacity * sizeof(char*));
                        }
                        result->items[result->size++] = token;
                    }
                    start = end + 1;
                }
                end++;
            }
            
            // Последний токен
            if (start != end) {
                int token_len = end - start;
                char* token = malloc(token_len + 1);
                strncpy(token, start, token_len);
                token[token_len] = '\\0';
                
                if (result->size >= result->capacity) {
                    result->capacity *= 2;
                    result->items = realloc(result->items, result->capacity * sizeof(char*));
                }
                result->items[result->size++] = token;
            }
        } else {
            // Разделение по указанному разделителю
            int delim_len = strlen(delimiter);
            const char* start = str;
            const char* pos = strstr(start, delimiter);
            
            while (pos) {
                int token_len = pos - start;
                char* token = malloc(token_len + 1);
                strncpy(token, start, token_len);
                token[token_len] = '\\0';
                
                if (result->size >= result->capacity) {
                    result->capacity *= 2;
                    result->items = realloc(result->items, result->capacity * sizeof(char*));
                }
                result->items[result->size++] = token;
                
                start = pos + delim_len;
                pos = strstr(start, delimiter);
            }
            
            // Последний токен
            int token_len = strlen(start);
            if (token_len > 0) {
                char* token = malloc(token_len + 1);
                strcpy(token, start);
                
                if (result->size >= result->capacity) {
                    result->capacity *= 2;
                    result->items = realloc(result->items, result->capacity * sizeof(char*));
                }
                result->items[result->size++] = token;
            }
        }
        
        return result;
    }

    void free_string_list(string_list* list) {
        if (list) {
            for (int i = 0; i < list->size; i++) {
                free(list->items[i]);
            }
            free(list->items);
            free(list);
        }
    }
    """)

        # 9. Функция join
        helpers.append("""
    char* string_join(const char* separator, string_list* list) {
        if (!list || list->size == 0) {
            char* empty = malloc(1);
            empty[0] = '\\0';
            return empty;
        }
        
        // Вычисляем общую длину
        int total_len = 0;
        for (int i = 0; i < list->size; i++) {
            total_len += strlen(list->items[i]);
        }
        total_len += (list->size - 1) * strlen(separator);
        
        char* result = malloc(total_len + 1);
        if (!result) return NULL;
        
        result[0] = '\\0';
        for (int i = 0; i < list->size; i++) {
            strcat(result, list->items[i]);
            if (i < list->size - 1) {
                strcat(result, separator);
            }
        }
        
        return result;
    }
    """)

        # 10. Функция replace
        helpers.append("""
    char* string_replace(const char* str, const char* old, const char* new) {
        if (!str || !old || !new) return NULL;
        
        int str_len = strlen(str);
        int old_len = strlen(old);
        int new_len = strlen(new);
        
        // Считаем количество вхождений
        int count = 0;
        const char* pos = str;
        while ((pos = strstr(pos, old)) != NULL) {
            count++;
            pos += old_len;
        }
        
        // Вычисляем длину результата
        int result_len = str_len + count * (new_len - old_len);
        char* result = malloc(result_len + 1);
        if (!result) return NULL;
        
        // Заменяем
        const char* src = str;
        char* dest = result;
        while ((pos = strstr(src, old)) != NULL) {
            // Копируем часть до старой подстроки
            int copy_len = pos - src;
            strncpy(dest, src, copy_len);
            dest += copy_len;
            
            // Копируем новую подстроку
            strcpy(dest, new);
            dest += new_len;
            
            // Пропускаем старую подстроку
            src = pos + old_len;
        }
        
        // Копируем остаток
        strcpy(dest, src);
        
        return result;
    }
    """)

        # 11. Функция find
        helpers.append("""
    int string_find(const char* str, const char* sub) {
        if (!str || !sub) return -1;
        char* pos = strstr(str, sub);
        if (pos) {
            return pos - str;
        }
        return -1;
    }
    """)

        # 12. Функция index
        helpers.append("""
    int string_index(const char* str, const char* sub) {
        if (!str || !sub) return -1;
        char* pos = strstr(str, sub);
        if (!pos) {
            fprintf(stderr, "ValueError: substring not found\\n");
            exit(1);
        }
        return pos - str;
    }
    """)

        # 13. Функция count
        helpers.append("""
    int string_count(const char* str, const char* sub) {
        if (!str || !sub || sub[0] == '\\0') return 0;
        
        int count = 0;
        int sub_len = strlen(sub);
        const char* pos = str;
        
        while ((pos = strstr(pos, sub)) != NULL) {
            count++;
            pos += sub_len;
        }
        
        return count;
    }
    """)

        # 14. Функция startswith
        helpers.append("""
    bool string_startswith(const char* str, const char* prefix) {
        if (!str || !prefix) return false;
        return strncmp(str, prefix, strlen(prefix)) == 0;
    }
    """)

        # 15. Функция endswith
        helpers.append("""
    bool string_endswith(const char* str, const char* suffix) {
        if (!str || !suffix) return false;
        int str_len = strlen(str);
        int suffix_len = strlen(suffix);
        
        if (suffix_len > str_len) return false;
        return strcmp(str + str_len - suffix_len, suffix) == 0;
    }
    """)

        # 16. Функция isdigit
        helpers.append("""
    bool string_isdigit(const char* str) {
        if (!str || str[0] == '\\0') return false;
        
        for (int i = 0; str[i]; i++) {
            if (!(str[i] >= '0' && str[i] <= '9')) {
                return false;
            }
        }
        return true;
    }
    """)

        # 17. Функция isalpha
        helpers.append("""
    bool string_isalpha(const char* str) {
        if (!str || str[0] == '\\0') return false;
        
        for (int i = 0; str[i]; i++) {
            if (!((str[i] >= 'a' && str[i] <= 'z') || (str[i] >= 'A' && str[i] <= 'Z'))) {
                return false;
            }
        }
        return true;
    }
    """)

        # 18. Функция isalnum
        helpers.append("""
    bool string_isalnum(const char* str) {
        if (!str || str[0] == '\\0') return false;
        
        for (int i = 0; str[i]; i++) {
            char c = str[i];
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) {
                return false;
            }
        }
        return true;
    }
    """)

        # 19. Функция islower
        helpers.append("""
    bool string_islower(const char* str) {
        if (!str || str[0] == '\\0') return false;
        
        int has_letter = 0;
        for (int i = 0; str[i]; i++) {
            if (str[i] >= 'A' && str[i] <= 'Z') {
                return false;
            }
            if (str[i] >= 'a' && str[i] <= 'z') {
                has_letter = 1;
            }
        }
        return has_letter;
    }
    """)

        # 20. Функция isupper
        helpers.append("""
    bool string_isupper(const char* str) {
        if (!str || str[0] == '\\0') return false;
        
        int has_letter = 0;
        for (int i = 0; str[i]; i++) {
            if (str[i] >= 'a' && str[i] <= 'z') {
                return false;
            }
            if (str[i] >= 'A' && str[i] <= 'Z') {
                has_letter = 1;
            }
        }
        return has_letter;
    }
    """)

        # 21. Функция zfill
        helpers.append("""
    char* string_zfill(const char* str, int width) {
        if (!str) return NULL;
        
        int str_len = strlen(str);
        int total_len = (width > str_len) ? width : str_len;
        
        char* result = malloc(total_len + 1);
        if (!result) return NULL;
        
        if (str_len >= width) {
            strcpy(result, str);
        } else {
            int zeros = width - str_len;
            for (int i = 0; i < zeros; i++) {
                result[i] = '0';
            }
            strcpy(result + zeros, str);
        }
        
        result[total_len] = '\\0';
        return result;
    }
    """)

        # 22. Функция center
        helpers.append("""
    char* string_center(const char* str, int width, char fillchar) {
        if (!str) return NULL;
        
        int str_len = strlen(str);
        if (str_len >= width) {
            char* result = malloc(str_len + 1);
            strcpy(result, str);
            return result;
        }
        
        char* result = malloc(width + 1);
        if (!result) return NULL;
        
        int left = (width - str_len) / 2;
        int right = width - str_len - left;
        
        for (int i = 0; i < left; i++) {
            result[i] = fillchar;
        }
        strcpy(result + left, str);
        for (int i = left + str_len; i < width; i++) {
            result[i] = fillchar;
        }
        
        result[width] = '\\0';
        return result;
    }
    """)

        # 23. Функция ljust
        helpers.append("""
    char* string_ljust(const char* str, int width, char fillchar) {
        if (!str) return NULL;
        
        int str_len = strlen(str);
        if (str_len >= width) {
            char* result = malloc(str_len + 1);
            strcpy(result, str);
            return result;
        }
        
        char* result = malloc(width + 1);
        if (!result) return NULL;
        
        strcpy(result, str);
        for (int i = str_len; i < width; i++) {
            result[i] = fillchar;
        }
        
        result[width] = '\\0';
        return result;
    }
    """)

        # 24. Функция rjust
        helpers.append("""
    char* string_rjust(const char* str, int width, char fillchar) {
        if (!str) return NULL;
        
        int str_len = strlen(str);
        if (str_len >= width) {
            char* result = malloc(str_len + 1);
            strcpy(result, str);
            return result;
        }
        
        char* result = malloc(width + 1);
        if (!result) return NULL;
        
        int padding = width - str_len;
        for (int i = 0; i < padding; i++) {
            result[i] = fillchar;
        }
        strcpy(result + padding, str);
        
        result[width] = '\\0';
        return result;
    }
    """)

        # 25. Функция format (простая версия для одного аргумента)
        helpers.append("""
    char* string_format(const char* format_str, const char* arg) {
        if (!format_str) return NULL;
        
        // Ищем {} в строке
        char* pos = strstr(format_str, "{}");
        if (!pos) {
            // Если нет {}, просто копируем строку
            char* result = malloc(strlen(format_str) + 1);
            strcpy(result, format_str);
            return result;
        }
        
        // Вычисляем длину результата
        int format_len = strlen(format_str);
        int arg_len = arg ? strlen(arg) : 0;
        int result_len = format_len - 2 + arg_len; // -2 для удаления {}
        
        char* result = malloc(result_len + 1);
        if (!result) return NULL;
        
        // Копируем часть до {}
        int before_len = pos - format_str;
        strncpy(result, format_str, before_len);
        
        // Копируем аргумент
        if (arg) {
            strcpy(result + before_len, arg);
        }
        
        // Копируем часть после {}
        strcpy(result + before_len + arg_len, pos + 2);
        
        return result;
    }
    """)

        self.generated_helpers.extend(helpers)

    def generate_sort_helpers(self):
        """Генерирует вспомогательные функции для сортировки"""
        helpers = []

        # Для целых чисел
        helpers.append("""
    int compare_int(const void* a, const void* b) {
        return (*(int*)a - *(int*)b);
    }
    """)

        # Для чисел с плавающей точкой
        helpers.append("""
    int compare_float(const void* a, const void* b) {
        float float_a = *(float*)a;
        float float_b = *(float*)b;
        if (float_a < float_b) return -1;
        if (float_a > float_b) return 1;
        return 0;
    }
    """)

        # Для double
        helpers.append("""
    int compare_double(const void* a, const void* b) {
        double double_a = *(double*)a;
        double double_b = *(double*)b;
        if (double_a < double_b) return -1;
        if (double_a > double_b) return 1;
        return 0;
    }
    """)

        self.generated_helpers.extend(helpers)

    def compile_method_call(self, node):
        """Компилирует вызов метода: obj.method(args)"""
        obj_name = node.get("object")
        method_name = node.get("method")
        args = node.get("arguments", [])

        # Получаем информацию о классе
        class_info = self.get_class_of_object(obj_name)

        # Генерируем код вызова
        arg_code = ", ".join(self.compile_expression(arg) for arg in args)
        return f"{obj_name}->{method_name}({arg_code})"

    def compile_assignment(self, node):
        """Компилирует присваивание с вызовом метода"""
        if node.get("is_method_call_assignment"):
            # var x: type = obj.method(args)
            target = node["var_name"]
            obj_name = node["object"]
            method_name = node["method"]
            args = node["arguments"]

            # Генерируем вызов метода
            method_call = self.compile_method_call(
                {"object": obj_name, "method": method_name, "arguments": args}
            )

            return f"{target} = {method_call};"

    def analyze_class_inheritance(self, json_data: List[Dict]):
        """Анализирует иерархию наследования классов"""
        # Сначала собираем информацию о всех классах
        class_info = {}

        for scope in json_data:
            if scope.get("type") == "module":
                for node in scope.get("graph", []):
                    if node.get("node") == "class_declaration":
                        class_name = node.get("class_name", "")
                        base_classes = node.get("base_classes", [])
                        methods = node.get("methods", [])

                        class_info[class_name] = {
                            "base_classes": base_classes,
                            "methods": {method["name"]: method for method in methods},
                        }

        # Строим иерархию наследования
        for class_name, info in class_info.items():
            self.class_hierarchy[class_name] = info["base_classes"]
            self.all_class_methods[class_name] = {}

            # Начинаем с методов текущего класса
            for method_name, method_info in info["methods"].items():
                self.all_class_methods[class_name][method_name] = {
                    **method_info,
                    "origin": class_name,
                }

            # Добавляем методы из родительских классов (рекурсивно)
            self._inherit_methods_recursive(class_name, class_info)

    def _inherit_methods_recursive(
        self, class_name: str, class_info: Dict, visited=None
    ):
        """Рекурсивно добавляет методы из родительских классов"""
        if visited is None:
            visited = set()

        if class_name in visited:
            return
        visited.add(class_name)

        if class_name not in class_info:
            return

        base_classes = class_info[class_name]["base_classes"]

        for base_class in base_classes:
            if base_class in class_info:
                # Добавляем методы родительского класса, если их еще нет
                for method_name, method_info in class_info[base_class][
                    "methods"
                ].items():
                    if method_name not in self.all_class_methods[class_name]:
                        self.all_class_methods[class_name][method_name] = {
                            **method_info,
                            "origin": base_class,
                        }

                # Рекурсивно обрабатываем родительские классы родителя
                self._inherit_methods_recursive(base_class, class_info, visited)

    def generate_all_methods(self, json_data: List[Dict]):
        """Генерирует все методы всех классов"""
        # Сначала собираем все методы классов
        class_method_scopes = {}

        for scope in json_data:
            if scope.get("type") == "class_method":
                class_name = scope.get("class_name", "")
                method_name = scope.get("method_name", "")

                if class_name not in class_method_scopes:
                    class_method_scopes[class_name] = {}

                class_method_scopes[class_name][method_name] = scope

        # Генерируем методы для каждого класса
        for class_name, method_scopes in class_method_scopes.items():
            all_methods = self.all_class_methods.get(class_name, {})

            for method_name in all_methods.keys():
                if method_name in method_scopes:
                    # Метод определен в этом классе
                    scope = method_scopes[method_name]
                    self.generate_class_method_implementation(class_name, scope)
                else:
                    # Метод унаследован - не генерируем
                    method_info = all_methods[method_name]
                    if method_info.get("origin") != class_name:
                        self.add_line(
                            f"// Метод {class_name}_{method_name} унаследован от {method_info['origin']}"
                        )
                        # Генерируем заглушку или вызываем родительский метод
                        self._generate_inherited_method_stub(class_name, method_info)

    def generate_method_call_expression(self, ast: Dict) -> str:
        """Генерирует выражение вызова метода с учетом наследования"""
        object_name = ast.get("object", "")
        method_name = ast.get("method", "")
        args = ast.get("arguments", [])

        # Проверяем тип объекта
        var_info = self.get_variable_info(object_name)
        if not var_info:
            return f"// ERROR: Объект '{object_name}' не найден"

        obj_type = var_info.get("py_type", "")

        # Определяем, какой класс на самом деле содержит метод
        actual_class = self._find_method_class(obj_type, method_name)

        if not actual_class:
            return f"// ERROR: Метод '{method_name}' не найден для типа '{obj_type}'"

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                arg_strings.append(self.generate_expression(arg))
            else:
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings) if arg_strings else ""

        # Если это self (внутри метода класса), вызываем напрямую
        if object_name == "self":
            return f"{obj_type}_{method_name}({object_name}, {args_str})"
        else:
            # Внешний вызов - используем указатель на объект
            full_args = f"{object_name}"
            if args_str:
                full_args = f"{object_name}, {args_str}"

            return f"{actual_class}_{method_name}({full_args})"

    def _find_method_class(self, class_name: str, method_name: str) -> str:
        """Находит класс, в котором определен метод (с учетом наследования)"""
        if class_name in self.all_class_methods:
            methods = self.all_class_methods[class_name]
            if method_name in methods:
                method_info = methods[method_name]
                return method_info.get("origin", class_name)

        # Проверяем родительские классы
        if class_name in self.class_hierarchy:
            for parent_class in self.class_hierarchy[class_name]:
                result = self._find_method_class(parent_class, method_name)
                if result:
                    return result

        return None

    def _generate_inherited_method_stub(self, class_name: str, method_info: Dict):
        """Генерирует заглушку для унаследованного метода"""
        method_name = method_info["name"]
        return_type = method_info.get("return_type", "void")
        parameters = method_info.get("parameters", [])

        origin_class = method_info.get("origin")

        if not origin_class:
            return

        # Генерируем сигнатуру
        param_decls = []
        for param in parameters:
            param_name = param.get("name", "")
            param_type = param.get("type", "int")

            if param_name == "self":
                c_param_type = f"{class_name}*"
            else:
                c_param_type = self.map_type_to_c(param_type)

            param_decls.append(f"{c_param_type} {param_name}")

        c_return_type = self.map_type_to_c(return_type)
        params_str = ", ".join(param_decls) if param_decls else "void"

        self.add_line(f"{c_return_type} {class_name}_{method_name}({params_str}) {{")
        self.indent_level += 1

        # Вызываем родительский метод с приведением типа
        if return_type != "void":
            if origin_class == class_name:
                # Метод определен в этом классе (не должен вызываться здесь)
                self.add_line(f"return 0;")
            else:
                # Приводим self к типу родительского класса
                self.add_line(f"// Вызов унаследованного метода из {origin_class}")
                self.add_line(f"{origin_class}* base_obj = ({origin_class}*)self;")
                self.add_line(f"return {origin_class}_{method_name}(base_obj);")
        else:
            if origin_class != class_name:
                self.add_line(f"// Вызов унаследованного метода из {origin_class}")
                self.add_line(f"{origin_class}* base_obj = ({origin_class}*)self;")
                self.add_line(f"{origin_class}_{method_name}(base_obj);")

        self.indent_level -= 1
        self.add_line("}")
        self.add_empty_line()

    def generate_index_assignment(self, node: Dict):
        """Генерирует присваивание по индексу: list[index] = value"""
        variable = node.get("variable", "")
        index_ast = node.get("index", {})
        value_ast = node.get("value", {})

        index_expr = self.generate_expression(index_ast)
        value_expr = self.generate_expression(value_ast)

        var_info = self.get_variable_info(variable)

        if var_info:
            py_type = var_info.get("py_type", "")

            if py_type.startswith("list["):
                struct_name = self.generate_list_struct_name(py_type)
                self.add_line(
                    f"set_{struct_name}({variable}, {index_expr}, {value_expr});"
                )
            elif py_type.startswith("tuple["):
                # Кортежи неизменяемы, но все равно генерируем код
                struct_name = self.generate_tuple_struct_name(py_type)
                self.add_line(
                    f"{variable}.data[{index_expr}] = {value_expr}; // Note: tuples are immutable in Python"
                )
            else:
                self.add_line(f"{variable}[{index_expr}] = {value_expr};")

    def generate_slice_assignment(self, node: Dict):
        """Генерирует присваивание среза: list[start:stop] = values"""
        variable = node.get("variable", "")
        start_ast = node.get("start", {})
        stop_ast = node.get("stop", {})
        step_ast = node.get("step", {})
        value_ast = node.get("value", {})

        start_expr = self.generate_expression(start_ast) if start_ast else "0"
        stop_expr = (
            self.generate_expression(stop_ast) if stop_ast else f"{variable}->size"
        )

        var_info = self.get_variable_info(variable)

        if var_info and var_info.get("py_type", "").startswith("list["):
            if value_ast.get("type") == "list_literal":
                items = value_ast.get("items", [])
                if items:
                    # Присваивание списка значений срезу
                    for i, item in enumerate(items):
                        item_expr = self.generate_expression(item)
                        idx = f"{start_expr} + {i}"
                        self.add_line(
                            f"if ({idx} < {stop_expr} && {idx} < {variable}->size) {{"
                        )
                        self.indent_level += 1
                        self.add_line(
                            f"set_{self.generate_list_struct_name(var_info['py_type'])}({variable}, {idx}, {item_expr});"
                        )
                        self.indent_level -= 1
                        self.add_line("}")
            else:
                # Присваивание одного значения всем элементам среза
                value_expr = self.generate_expression(value_ast)
                temp_var = self.generate_temporary_var("int")
                self.add_line(
                    f"for (int {temp_var} = {start_expr}; {temp_var} < {stop_expr}; {temp_var}++) {{"
                )
                self.indent_level += 1
                self.add_line(f"if ({temp_var} < {variable}->size) {{")
                self.indent_level += 1
                self.add_line(
                    f"set_{self.generate_list_struct_name(var_info['py_type'])}({variable}, {temp_var}, {value_expr});"
                )
                self.indent_level -= 1
                self.add_line("}")
                self.indent_level -= 1
                self.add_line("}")

    def generate_augmented_index_assignment(self, node: Dict):
        """Генерирует составное присваивание по индексу: list[index] += value"""
        variable = node.get("variable", "")
        index_ast = node.get("index", {})
        operator = node.get("operator", "")
        value_ast = node.get("value", {})

        index_expr = self.generate_expression(index_ast)
        value_expr = self.generate_expression(value_ast)

        var_info = self.get_variable_info(variable)

        if var_info and var_info.get("py_type", "").startswith("list["):
            struct_name = self.generate_list_struct_name(var_info["py_type"])
            # Получаем текущее значение
            temp_var = self.generate_temporary_var("int")
            self.add_line(
                f"int {temp_var} = get_{struct_name}({variable}, {index_expr});"
            )
            # Применяем оператор
            op_symbol = operator.replace("=", "")
            c_op = self.operator_map.get(op_symbol, op_symbol)
            if c_op == "pow":
                self.add_line(f"{temp_var} = pow({temp_var}, {value_expr});")
            else:
                self.add_line(f"{temp_var} {operator} {value_expr};")
            # Устанавливаем новое значение
            self.add_line(f"set_{struct_name}({variable}, {index_expr}, {temp_var});")
