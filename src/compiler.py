import json
import re
from typing import Dict, List, Any, Optional


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
        }

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

    def reset(self):
        """Сброс состояния генератора"""
        self.output = []
        self.indent_level = 0
        self.temp_var_counter = 0
        self.variable_scopes = [{}]  # Глобальный scope
        self.current_scope_level = 0
        self.generated_structs.clear()
        self.generated_helpers.clear()
        self.generic_type_map.clear()

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
        """Преобразует тип Python в тип C"""
        if py_type.startswith("*"):
            base_type = py_type[1:]
            c_base_type = self.map_type_to_c(base_type)
            return f"{c_base_type}*"
        elif py_type == "pointer":
            return "void*"
        elif py_type.startswith("tuple["):
            # Генерируем структуру для кортежа
            self.generate_tuple_struct(py_type)
            struct_name = self.generate_tuple_struct_name(py_type)

            # Убедимся, что имя структуры корректное
            if struct_name == "tuple_unknown":
                # Попробуем определить тип по содержимому
                match = re.match(r"tuple\[([^\]]+)\]", py_type)
                if match:
                    inner = match.group(1)
                    if "," not in inner:
                        struct_name = f"tuple_{inner}"
                    else:
                        clean_inner = self.clean_type_name_for_c(inner)
                        struct_name = f"tuple_{clean_inner}"

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
        """Генерирует код для scope функции"""
        func_name = scope.get("function_name", "")
        return_type = scope.get("return_type", "int")
        parameters = scope.get("parameters", [])

        # Создаем новый scope для функции
        self.enter_scope()

        # Объявляем параметры
        param_decls = []
        for param in parameters:
            param_name = param.get("name", "")
            param_type = param.get("type", "int")
            c_param_type = self.map_type_to_c(param_type)
            param_decls.append(f"{c_param_type} {param_name}")
            self.declare_variable(param_name, param_type)

        # Генерируем сигнатуру функции
        c_return_type = self.map_type_to_c(return_type)
        params_str = ", ".join(param_decls) if param_decls else "void"

        self.add_line(f"{c_return_type} {func_name}({params_str}) {{")
        self.indent_level += 1

        # Генерируем тело функции
        for node in scope.get("graph", []):
            self.generate_graph_node(node)

        self.indent_level -= 1
        self.add_line("}")
        self.add_empty_line()

        # Выходим из scope функции
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
        elif node_type == "method_call":
            self.generate_method_call(node)
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
        return_type = node.get("return_type", "")

        # Маппинг встроенных функций Python -> C
        builtin_map = {
            "print": "printf",
            "len": "builtin_len",
            "str": "builtin_str",
            "int": "builtin_int",
            "bool": "builtin_bool",
            "range": "builtin_range",
        }

        # Получаем C имя функции
        c_func_name = builtin_map.get(func_name, func_name)

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                arg_strings.append(self.generate_expression(arg))
            else:
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings)

        # Обработка специальных случаев
        if func_name == "print":
            # Для print генерируем полную строку
            if not args:
                self.add_line('printf("\\n");')
            else:
                # Создаем форматную строку
                format_parts = []
                for arg in args:
                    if (
                        isinstance(arg, str)
                        and arg.startswith('"')
                        and arg.endswith('"')
                    ):
                        format_parts.append(arg[1:-1])
                    else:
                        format_parts.append("%d")  # По умолчанию int
                format_str = '"' + " ".join(format_parts) + '\\n"'
                self.add_line(f"printf({format_str}, {args_str});")
        else:
            # Для других встроенных функций
            self.add_line(f"{c_func_name}({args_str});")

    def generate_builtin_function_call_assignment(self, node: Dict):
        """Генерирует присваивание результата встроенной функции"""
        target = node.get("symbols", [])[0] if node.get("symbols") else ""
        func_name = node.get("function", "")
        args = node.get("arguments", [])
        return_type = node.get("return_type", "")

        if not target:
            self.generate_builtin_function_call(node)
            return

        var_info = self.get_variable_info(target)
        if not var_info:
            node_type = node.get("var_type", "int")
            self.declare_variable(target, node_type)
            var_info = self.get_variable_info(target)

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

    def generate_break(self, node: Dict):
        """Генерирует оператор break"""
        self.add_line("break;")
        self.add_line("// break statement")

    def generate_continue(self, node: Dict):
        """Генерирует оператор continue"""
        self.add_line("continue;")
        self.add_line("// continue statement")

    def generate_method_call(self, node: Dict):
        """Генерирует вызов метода"""
        obj_name = node.get("object", "")
        method_name = node.get("method", "")
        args = node.get("arguments", [])

        # Получаем информацию об объекте
        var_info = self.get_variable_info(obj_name)
        if not var_info:
            self.add_line(f"// ERROR: Объект '{obj_name}' не найден")
            return

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                arg_strings.append(self.generate_expression(arg))
            else:
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings)

        # Определяем тип объекта и маппим метод
        py_type = var_info.get("py_type", "")

        if py_type.startswith("list["):
            struct_name = self.generate_list_struct_name(py_type)

            if method_name == "append":
                self.add_line(f"append_{struct_name}({obj_name}, {args_str});")
            else:
                self.add_line(f"// Неизвестный метод '{method_name}' для списка")
        else:
            self.add_line(f"// Вызов метода '{method_name}' для типа '{py_type}'")

    def generate_declaration(self, node: Dict):
        """Генерирует объявление переменной с поддержкой всех типов"""
        var_name = node.get("var_name", "")
        var_type = node.get("var_type", "")
        operations = node.get("operations", [])
        expression_ast = node.get("expression_ast", {})
        tuple_info = node.get("tuple_info", {})

        # Пропускаем удаленные переменные
        var_info = self.get_variable_info(var_name)
        if var_info and var_info.get("is_deleted"):
            delete_type = var_info.get("delete_type", "full")
            self.add_line(f"// Переменная '{var_name}' была удалена ({delete_type})")
            return

        # 1. Проверяем, является ли это восстановлением удаленной переменной
        was_deleted = False
        for op in operations:
            if op.get("type") == "RESTORE_VAR" and op.get("was_deleted", False):
                was_deleted = True
                break

        if was_deleted:
            self.add_line(f"// Восстановление удаленной переменной '{var_name}'")

        # 2. Определяем тип и генерируем соответствующее объявление

        # 2.1 Указатели
        if var_type.startswith("*"):
            self.generate_pointer_declaration(
                var_name, var_type, expression_ast, operations
            )

        # 2.2 Кортежи
        elif var_type.startswith("tuple["):
            self.generate_tuple_declaration(
                var_name, var_type, expression_ast, operations, tuple_info
            )

        # 2.3 Списки
        elif var_type.startswith("list["):
            self.generate_list_declaration(
                var_name, var_type, expression_ast, operations
            )

        # 2.4 Словари
        elif var_type.startswith("dict["):
            self.generate_dict_declaration(
                var_name, var_type, expression_ast, operations
            )

        # 2.5 Множества
        elif var_type.startswith("set["):
            self.generate_set_declaration(
                var_name, var_type, expression_ast, operations
            )

        # 2.6 Простые типы (int, float, str, bool, None)
        else:
            self.generate_simple_declaration(
                var_name, var_type, expression_ast, operations
            )

        # 3. Объявляем переменную в scope
        self.declare_variable(var_name, var_type)

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
        c_type = self.map_type_to_c(var_type)

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
        """Генерирует присваивание"""
        symbols = node.get("symbols", [])
        if not symbols:
            return

        target = symbols[0]

        # Проверяем, не удалена ли переменная
        var_info = self.get_variable_info(target)
        if var_info and var_info.get("is_deleted"):
            delete_type = var_info.get("delete_type", "full")
            self.add_line(
                f"// Внимание: присваивание удаленной переменной '{target}' (удаление: {delete_type})"
            )

        # Генерируем выражение
        expression_ast = node.get("expression_ast")
        if expression_ast:
            expr = self.generate_expression(expression_ast)
            self.add_line(f"{target} = {expr};")

    def generate_function_call(self, node: Dict):
        """Генерирует вызов функции"""
        func_name = node.get("function", "")
        args = node.get("arguments", [])

        # Удаляем @ из имени функции для C кода
        if func_name.startswith("@"):
            func_name = func_name[1:]
            print(f"DEBUG: Вызов C-функции '{func_name}'")

        # Генерируем аргументы
        arg_strings = []
        for arg in args:
            if isinstance(arg, dict):
                # Если аргумент - это AST
                arg_strings.append(self.generate_expression(arg))
            else:
                # Если аргумент - простая строка
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
        """Генерирует print"""
        args = node.get("arguments", [])

        if not args:
            self.add_line('printf("\\n");')
            return

        for arg in args:
            # Определяем формат в зависимости от типа
            if isinstance(arg, str):
                if arg.startswith('"') and arg.endswith('"'):
                    # Строковый литерал
                    self.add_line(f"printf({arg});")
                else:
                    # Предполагаем, что это переменная типа int
                    self.add_line(f'printf("%d\\n", {arg});')
            else:
                # Для сложных выражений
                self.add_line(f'printf("%d\\n", {arg});')

    def generate_while_loop(self, node: Dict):
        """Генерирует while loop"""
        condition_ast = node.get("condition_ast")
        if not condition_ast:
            return

        condition = self.generate_expression(condition_ast)

        self.add_line(f"while ({condition}) {{")
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

        for scope in json_data:
            if scope.get("type") == "module":
                for node in scope.get("graph", []):
                    if node.get("node") == "c_import":
                        self.c_imports.append(node)
                    elif node.get("node") == "function_declaration":
                        self.add_function_declaration(node)

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
        if self.function_declarations:
            for decl in self.function_declarations:
                self.add_line(decl)
            self.add_empty_line()

    def generate_tuple_struct_name(self, py_type: str) -> str:
        """Генерирует корректное имя структуры для tuple"""
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
        clean_inner = self.clean_type_name_for_c(inner)
        return f"tuple_{clean_inner}"

    def generate_list_struct_name(self, py_type: str) -> str:
        """Генерирует корректное имя структуры для списка любой вложенности"""
        if not py_type.startswith("list["):
            return f"list_{self.clean_type_name_for_c(py_type)}"

        # Упрощенный алгоритм без рекурсии
        depth = 0
        current = py_type
        inner_type = "int"  # по умолчанию

        # Считаем уровни вложенности
        while current.startswith("list["):
            depth += 1
            # Находим закрывающую скобку
            balance = 0
            end_pos = -1

            for i in range(5, len(current)):  # Пропускаем "list["
                char = current[i]
                if char == "[":
                    balance += 1
                elif char == "]":
                    if balance == 0:
                        end_pos = i
                        break
                    balance -= 1

            if end_pos == -1:
                break

            inner = current[5:end_pos]  # Пропускаем "list[" и до "]"

            if not inner.startswith("list["):
                inner_type = inner
                break

            current = inner

        # Генерируем имя
        prefix = "list_" * depth
        return f"{prefix}{self.clean_type_name_for_c(inner_type)}"

    def generate_tuple_struct(self, py_type: str):
        """Генерирует структуру C для tuple типа"""
        if py_type in self.generated_structs:
            return

        self.generated_structs.add(py_type)

        match = re.match(r"tuple\[([^\]]+)\]", py_type)
        if not match:
            return

        inner = match.group(1)
        struct_name = self.generate_tuple_struct_name(
            py_type
        )  # tuple_int для tuple[int]

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

            # Функция очистки
            free_func = f"void free_{struct_name}({struct_name}* t) {{\n"
            free_func += f"    if (t->data) {{\n"
            free_func += f"        free(t->data);\n"
            free_func += f"        t->data = NULL;\n"
            free_func += f"    }}\n"
            free_func += f"    t->size = 0;\n"
            free_func += f"}}\n\n"

            # Добавляем все функции
            self.generated_helpers.extend([struct_code, create_func, free_func])
        else:
            # tuple[T1, T2, ...] - фиксированный кортеж
            # TODO: Реализовать генерацию фиксированных кортежей
            element_types = [t.strip() for t in inner.split(",")]
            c_element_types = [self.map_type_to_c(t) for t in element_types]

            # Создаем структуру с полями для каждого элемента
            struct_code = f"typedef struct {{\n"
            for i, (elem_type, c_elem_type) in enumerate(
                zip(element_types, c_element_types)
            ):
                field_name = f"elem_{i}"
                struct_code += f"    {c_elem_type} {field_name};\n"
            struct_code += f"}} {struct_name};\n\n"

            self.generated_helpers.append(struct_code)

            # Функция создания для фиксированного кортежа
            param_list = ", ".join(
                [f"{c_elem_type} a{i}" for i, c_elem_type in enumerate(c_element_types)]
            )
            create_func = f"{struct_name} create_{struct_name}({param_list}) {{\n"
            create_func += f"    {struct_name} t;\n"
            for i, (elem_type, c_elem_type) in enumerate(
                zip(element_types, c_element_types)
            ):
                field_name = f"elem_{i}"
                create_func += f"    t.{field_name} = a{i};\n"
            create_func += f"    return t;\n"
            create_func += f"}}\n\n"

            # Функция очистки (для типов с указателями)
            free_func = f"void free_{struct_name}({struct_name}* t) {{\n"
            # TODO: Добавить освобождение памяти для указателей если нужно
            free_func += f"    // Освобождение памяти для указателей (если есть)\n"
            free_func += f"}}\n\n"

            self.generated_helpers.extend([create_func, free_func])

    def generate_list_struct(self, py_type: str):
        """Генерирует структуру C для списка любой вложенности"""

        # Получаем информацию о типе
        type_info = self.extract_nested_type_info(py_type)

        if not type_info:
            print(f"ERROR: Не удалось получить информацию о типе {py_type}")
            return

        struct_name = type_info.get("struct_name")
        if not struct_name:
            return

        element_type = type_info.get("element_type", "void*")

        print(f"DEBUG generate_list_struct: {py_type}")
        print(f"  struct_name: {struct_name}")
        print(f"  element_type: {element_type}")

        # Рекурсивно генерируем структуры для внутренних типов
        inner_info = type_info.get("inner_info")
        if inner_info and not inner_info.get("is_leaf", True):
            inner_py_type = inner_info.get("py_type", "")
            if inner_py_type:
                self.generate_list_struct(inner_py_type)

        # Генерируем структуру только если еще не генерировали
        struct_exists = False
        for helper in self.generated_helpers:
            if f"typedef struct {{" in helper and f"}} {struct_name};" in helper:
                struct_exists = True
                break

        if not struct_exists:
            struct_code = f"typedef struct {{\n"
            struct_code += f"    {element_type}* data;\n"
            struct_code += f"    int size;\n"
            struct_code += f"    int capacity;\n"
            struct_code += f"}} {struct_name};\n\n"

            self.generated_helpers.append(struct_code)

            # Генерируем функции
            self._generate_list_functions(
                struct_name,
                element_type,
                inner_info.get("py_type") if inner_info else None,
            )

    def _generate_list_functions(
        self, struct_name: str, element_type: str, element_py_type: str = None
    ):
        """Генерирует функции для работы со списком"""

        print(
            f"DEBUG _generate_list_functions: struct_name={struct_name}, element_type={element_type}"
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

    def generate_helpers(self):
        """Генерирует вспомогательные функции и структуры"""
        if self.generated_helpers:
            self.add_line("// Вспомогательные структуры и функции")
            for helper in self.generated_helpers:
                self.output.append(helper)
            self.add_empty_line()

    def generate_helpers_section(self):
        """Генерирует секцию с вспомогательными функциями и структурами"""
        if not self.generated_helpers:
            return

        # Добавляем заголовок
        self.add_line("// =========================================")
        self.add_line("// Вспомогательные структуры и функции")
        self.add_line("// =========================================")
        self.add_empty_line()

        # Просто добавляем все сгенерированные helpers в output
        for helper in self.generated_helpers:
            lines = helper.split("\n")
            for line in lines:
                if line.strip():
                    self.output.append(line)
            self.output.append("")  # Пустая строка между определениями

    def generate_helpers_section_sorted(self):
        """Генерирует секцию с вспомогательными функциями и структурами в правильном порядке"""
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

        # Сначала собираем все типы, которые нужны
        self.collect_types_from_ast(json_data)

        # Собираем импорты и объявления
        self.collect_imports_and_declarations(json_data)

        # 1. Генерируем заголовок
        self.generate_c_imports()

        # 2. Генерируем forward declarations функций (если есть)
        self.generate_forward_declarations()

        # 3. Генерируем вспомогательные структуры и функции
        # ВАЖНО: Это ДОЛЖНО быть здесь, перед main!
        # Но сначала отсортируем структуры по вложенности
        self.generate_helpers_section_sorted()

        # 4. Генерируем код для каждой функции
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
                    elif var_type.startswith("tuple["):
                        all_types.add(var_type)

            # Обрабатываем операции
            operations = node.get("operations", [])
            for op in operations:
                if isinstance(op, dict):
                    if op.get("type") in ["CREATE_TUPLE_UNIFORM", "CREATE_TUPLE_FIXED"]:
                        element_type = op.get("element_type", "")
                        if element_type:
                            all_types.add(f"tuple[{element_type}]")

        # Проходим по всем scope и узлам
        for scope in json_data:
            if scope.get("type") in ["module", "function"]:
                # Обрабатываем graph узлы
                for node in scope.get("graph", []):
                    process_node(node)

        # Генерируем структуры для всех найденных типов
        for py_type in sorted(all_types, key=lambda x: x.count("[")):
            if py_type.startswith("list["):
                self.generate_list_struct(py_type)
            elif py_type.startswith("tuple["):
                self.generate_tuple_struct(py_type)

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
        """Извлекает информацию о вложенном типе списка (универсальная версия)"""
        # Кэшируем результаты для производительности
        if not hasattr(self, "_type_info_cache"):
            self._type_info_cache = {}

        if py_type in self._type_info_cache:
            return self._type_info_cache[py_type]

        if not py_type or not isinstance(py_type, str):
            result = self._create_default_type_info()
            self._type_info_cache[py_type] = result
            return result

        # Для отладки
        print(f"DEBUG extract_nested_type_info: {py_type}")

        # Базовый случай: не список
        if not py_type.startswith("list["):
            result = self._create_leaf_type_info(py_type)
            self._type_info_cache[py_type] = result
            return result

        try:
            # Используем универсальный парсер скобок
            inner_type = self._parse_list_type(py_type)
            if not inner_type:
                result = self._create_default_type_info()
                self._type_info_cache[py_type] = result
                return result

            # Генерируем имя структуры
            struct_name = self._generate_struct_name_recursive(py_type)

            # Рекурсивно анализируем внутренний тип
            inner_info = self.extract_nested_type_info(inner_type)

            # Определяем информацию о текущем уровне
            # is_leaf = True только если внутренний тип НЕ является списком
            is_leaf = not inner_type.startswith("list[")

            # Определяем element_type
            if is_leaf:
                # Если это list[int], то element_type = int
                element_type = inner_info.get("c_type", "void*")
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
                "is_leaf": is_leaf,
                "inner_info": inner_info,
            }

            # Кэшируем результат
            self._type_info_cache[py_type] = result
            return result

        except Exception as e:
            print(f"ERROR в extract_nested_type_info для {py_type}: {e}")
            result = self._create_default_type_info()
            self._type_info_cache[py_type] = result
            return result

    def _generate_struct_name_recursive(self, py_type: str) -> str:
        """Рекурсивно генерирует имя структуры для вложенного списка"""
        if not py_type.startswith("list["):
            # Листовой тип
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

            builtin_funcs = ["len", "str", "int", "bool", "range"]
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
