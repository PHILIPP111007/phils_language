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

            match = re.match(r"tuple\[([^\]]+)\]", py_type)
            if match:
                inner = match.group(1)
                if "," not in inner:
                    # tuple[T] - универсальный
                    c_type = struct_name
                else:
                    # tuple[T1, T2, ...] - фиксированный
                    c_type = struct_name

                if is_pointer:
                    return f"{c_type}*"
                return c_type
            return "void*"
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
            # Если нет целевой переменной, генерируем просто вызов
            self.generate_builtin_function_call(node)
            return

        # Получаем информацию о целевой переменной
        var_info = self.get_variable_info(target)
        if not var_info:
            # Если переменная не объявлена, объявляем ее
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

        # Генерируем присваивание
        c_type = var_info["c_type"] if var_info else self.map_type_to_c(return_type)
        self.add_line(f"{c_type} {target} = {c_func_name}({args_str});")

    def generate_declaration(self, node: Dict):
        """Генерирует объявление переменной с поддержкой tuple и list"""
        var_name = node.get("var_name", "")
        var_type = node.get("var_type", "")
        operations = node.get("operations", [])

        if var_type.startswith("tuple["):
            struct_name = self.generate_tuple_struct_name(var_type)

            # Проверяем тип кортежа
            match = re.match(r"tuple\[([^\]]+)\]", var_type)
            if match:
                elements_str = match.group(1)

                if "," not in elements_str:
                    # tuple[T] - универсальный
                    element_type = elements_str.strip()
                    c_element_type = self.map_type_to_c(element_type)

                    # Ищем операцию CREATE_TUPLE_UNIFORM
                    for op in operations:
                        if op.get("type") == "CREATE_TUPLE_UNIFORM":
                            items = op.get("items", [])
                            size = op.get("size", 0)

                            if items and size > 0:
                                # Вариант 1: Создаем временный массив
                                temp_array_name = f"temp_{var_name}"
                                self.add_line(
                                    f"{c_element_type} {temp_array_name}[{size}] = {{"
                                )
                                self.indent_level += 1
                                for i, item_ast in enumerate(items):
                                    item_expr = self.generate_expression(item_ast)
                                    self.add_line(
                                        f"{item_expr}{',' if i < size - 1 else ''}"
                                    )
                                self.indent_level -= 1
                                self.add_line(f"}};")

                                # Создаем кортеж из массива
                                self.add_line(
                                    f"{struct_name} {var_name} = create_{struct_name}({temp_array_name}, {size});"
                                )

                                # Добавляем автоматическую очистку в конце функции (опционально)
                                # self.add_line(f"atexit((void(*)())free_{struct_name}, &{var_name});")

                            elif size == 0:
                                # Пустой кортеж
                                self.add_line(f"{struct_name} {var_name};")
                                self.add_line(f"{var_name}.data = NULL;")
                                self.add_line(f"{var_name}.size = 0;")

                            break

                    # Объявляем переменную
                    self.declare_variable(var_name, var_type)

                else:
                    # Получаем C тип
                    c_type = self.map_type_to_c(var_type)

                    # Объявляем переменную
                    self.declare_variable(var_name, var_type)

                    # Генерируем объявление
                    if var_type.startswith("list["):
                        # Для list создаем указатель на структуру
                        struct_name = self.generate_list_struct_name(var_type)

                        # Проверяем инициализацию
                        has_initialization = False
                        for op in operations:
                            if op.get("type") == "CREATE_LIST":
                                has_initialization = True
                                size = op.get("size", 0)

                                # Создаем список
                                self.add_line(
                                    f"{c_type} {var_name} = create_{struct_name}({max(size, 4)});"
                                )

                                # Добавляем элементы
                                items = op.get("items", [])
                                for item_ast in items:
                                    item_expr = self.generate_expression(item_ast)
                                    self.add_line(
                                        f"append_{struct_name}({var_name}, {item_expr});"
                                    )
                                break

                        if not has_initialization:
                            self.add_line(f"{c_type} {var_name} = NULL;")

                    elif var_type.startswith("tuple["):
                        # Для tuple
                        struct_name = self.generate_tuple_struct_name(var_type)

                        # Проверяем инициализацию
                        has_initialization = False
                        for op in operations:
                            if op.get("type") == "CREATE_TUPLE":
                                has_initialization = True
                                items = op.get("items", [])
                                if items:
                                    # Создаем вызов функции создания
                                    args = [
                                        self.generate_expression(item) for item in items
                                    ]
                                    self.add_line(
                                        f"{c_type} {var_name} = create_{struct_name}({', '.join(args)});"
                                    )
                                else:
                                    self.add_line(f"{c_type} {var_name};")
                                break

                        if not has_initialization:
                            self.add_line(f"{c_type} {var_name};")

                    else:
                        # Обычные переменные
                        self.add_line(f"{c_type} {var_name};")

                        # Инициализация если есть
                        expression_ast = node.get("expression_ast")
                        if expression_ast:
                            expr = self.generate_expression(expression_ast)
                            self.add_line(f"{var_name} = {expr};")

        elif var_type.startswith("list["):
            # Генерируем структуру для list
            self.map_type_to_c(var_type)
            struct_name = self.generate_list_struct_name(var_type)

            # Проверяем, есть ли инициализация
            list_initialized = False

            # Ищем операцию CREATE_LIST
            for op in operations:
                if op.get("type") == "CREATE_LIST":
                    items = op.get("items", [])
                    initial_capacity = op.get("size", 4)

                    # Создаем list
                    self.add_line(
                        f"{struct_name}* {var_name} = create_{struct_name}({initial_capacity});"
                    )

                    # Добавляем элементы
                    for item_ast in items:
                        item_expr = self.generate_expression(item_ast)
                        self.add_line(f"append_{struct_name}({var_name}, {item_expr});")

                    list_initialized = True
                    break

            # Если нет инициализации, создаем пустой list
            if not list_initialized:
                self.add_line(f"{struct_name}* {var_name} = create_{struct_name}(4);")

            # Объявляем переменную в scope
            self.declare_variable(var_name, var_type)

        else:
            # Обычные переменные
            c_type = self.map_type_to_c(var_type)
            self.add_line(f"{c_type} {var_name};")

            # Инициализация если есть
            expression_ast = node.get("expression_ast")
            if expression_ast:
                expr = self.generate_expression(expression_ast)
                self.add_line(f"{var_name} = {expr};")

            # Объявляем переменную в scope
            self.declare_variable(var_name, var_type)

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
            return "tuple_unknown"

        inner = match.group(1)

        # Если это tuple[T] (один тип)
        if "," not in inner:
            # Просто tuple_int, tuple_str и т.д.
            return f"tuple_{inner}"

        # Если это tuple[T1, T2, ...]
        # Заменяем запятые на подчеркивания и убираем пробелы
        clean_inner = inner.replace(", ", "_").replace(",", "_")
        return f"tuple_{clean_inner}"

    def generate_list_struct_name(self, py_type: str) -> str:
        """Генерирует имя структуры для list типа"""
        # Для list[int] должно быть list_int
        # Для list[tuple[int]] должно быть list_tuple_int

        match = re.match(r"list\[([^\]]+)\]", py_type)
        if not match:
            return f"list_{py_type}"

        element_type = match.group(1)
        # Очищаем имя типа
        clean_element = (
            element_type.replace("[", "_").replace("]", "").replace(",", "_")
        )
        return f"list_{clean_element}"

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

        # Если это tuple[T] (один тип) - например, tuple[int]
        if "," not in inner:
            element_type = inner
            c_element_type = self.map_type_to_c(element_type)

            # Универсальная структура для tuple[T]
            struct_code = []
            struct_code.append(f"typedef struct {{")
            struct_code.append(f"    {c_element_type}* data;")
            struct_code.append(f"    int size;")
            struct_code.append(f"}} {struct_name};")
            struct_code.append("")

            # Добавляем структуру
            self.generated_helpers.append("\n".join(struct_code))

            # Функция создания
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
            create_func += f"}}\n"

            self.generated_helpers.append(create_func)

            # Функция очистки
            free_func = f"void free_{struct_name}({struct_name}* t) {{\n"
            free_func += f"    if (t && t->data) {{\n"
            free_func += f"        free(t->data);\n"
            free_func += f"        t->data = NULL;\n"
            free_func += f"    }}\n"
            free_func += f"}}\n"

            self.generated_helpers.append(free_func)

            # Forward declarations
            self.helper_declarations.append(
                f"typedef struct {struct_name} {struct_name};"
            )
            self.helper_declarations.append(
                f"{struct_name} create_{struct_name}({c_element_type} arr[], int size);"
            )
            self.helper_declarations.append(
                f"void free_{struct_name}({struct_name}* t);"
            )

        else:
            # tuple[T1, T2, ...] - фиксированный
            element_types = [t.strip() for t in inner.split(",")]
            c_element_types = [self.map_type_to_c(t) for t in element_types]

            # Фиксированная структура
            struct_code = []
            struct_code.append(f"typedef struct {{")
            struct_code.append(f"    int size;")
            for i, c_type in enumerate(c_element_types):
                struct_code.append(f"    {c_type} item_{i};")
            struct_code.append(f"}} {struct_name};")
            struct_code.append("")

            self.generated_helpers.append("\n".join(struct_code))

            # Функция создания
            create_func = f"{struct_name} create_{struct_name}("
            params = [f"{c_type} arg_{i}" for i, c_type in enumerate(c_element_types)]
            create_func += ", ".join(params)
            create_func += f") {{\n"
            create_func += f"    {struct_name} t;\n"
            create_func += f"    t.size = {len(element_types)};\n"
            for i in range(len(element_types)):
                create_func += f"    t.item_{i} = arg_{i};\n"
            create_func += f"    return t;\n"
            create_func += f"}}\n"

            self.generated_helpers.append(create_func)

            # Forward declarations
            self.helper_declarations.append(
                f"typedef struct {struct_name} {struct_name};"
            )
            self.helper_declarations.append(
                f"{struct_name} create_{struct_name}({', '.join(params)});"
            )

    def generate_list_struct(self, py_type: str):
        """Генерирует структуру C для list типа"""
        if py_type in self.generated_structs:
            return

        self.generated_structs.add(py_type)

        # Извлекаем тип элементов
        match = re.match(r"list\[([^\]]+)\]", py_type)
        if not match:
            return

        element_type = match.group(1)

        # Определяем тип элементов для C
        if element_type.startswith("tuple["):
            # list[tuple[...]]
            c_element_type = self.generate_tuple_struct_name(element_type)
        else:
            # list[int] или другие простые типы
            c_element_type = self.map_type_to_c(element_type)

        struct_name = self.generate_list_struct_name(py_type)

        # Генерируем структуру
        struct_code = []
        struct_code.append(f"typedef struct {{")
        struct_code.append(f"    {c_element_type}* data;")
        struct_code.append(f"    int size;")
        struct_code.append(f"    int capacity;")
        struct_code.append(f"}} {struct_name};")
        struct_code.append("")

        self.generated_helpers.append("\n".join(struct_code))

        # Генерируем функцию создания
        create_func = f"{struct_name}* create_{struct_name}(int initial_capacity) {{\n"
        create_func += f"    {struct_name}* list = malloc(sizeof({struct_name}));\n"
        create_func += f"    if (!list) {{\n"
        create_func += (
            f'        fprintf(stderr, "Memory allocation failed for list\\n");\n'
        )
        create_func += f"        exit(1);\n"
        create_func += f"    }}\n"
        create_func += (
            f"    list->data = malloc(initial_capacity * sizeof({c_element_type}));\n"
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
        create_func += f"}}\n"

        # Генерируем функцию добавления
        append_func = f"void append_{struct_name}({struct_name}* list, {c_element_type} value) {{\n"
        append_func += f"    if (list->size >= list->capacity) {{\n"
        append_func += (
            f"        list->capacity = list->capacity == 0 ? 4 : list->capacity * 2;\n"
        )
        append_func += f"        list->data = realloc(list->data, list->capacity * sizeof({c_element_type}));\n"
        append_func += f"        if (!list->data) {{\n"
        append_func += (
            f'            fprintf(stderr, "Memory reallocation failed for list\\n");\n'
        )
        append_func += f"            exit(1);\n"
        append_func += f"        }}\n"
        append_func += f"    }}\n"
        append_func += f"    list->data[list->size] = value;\n"
        append_func += f"    list->size++;\n"
        append_func += f"}}\n"

        # Генерируем функцию очистки
        free_func = f"void free_{struct_name}({struct_name}* list) {{\n"
        free_func += f"    if (list) {{\n"

        # Если элементы - tuple, нужно освободить их память
        if element_type.startswith("tuple["):
            tuple_struct_name = self.generate_tuple_struct_name(element_type)
            free_func += f"        for (int i = 0; i < list->size; i++) {{\n"
            free_func += f"            free_{tuple_struct_name}(&list->data[i]);\n"
            free_func += f"        }}\n"

        free_func += f"        free(list->data);\n"
        free_func += f"        free(list);\n"
        free_func += f"    }}\n"
        free_func += f"}}\n"

        # Добавляем в helpers
        self.generated_helpers.append(create_func)
        self.generated_helpers.append(append_func)
        self.generated_helpers.append(free_func)

        # Добавляем forward declarations
        self.helper_declarations.append(f"typedef struct {struct_name} {struct_name};")
        self.helper_declarations.append(
            f"{struct_name}* create_{struct_name}(int initial_capacity);"
        )
        self.helper_declarations.append(
            f"void append_{struct_name}({struct_name}* list, {c_element_type} value);"
        )
        self.helper_declarations.append(
            f"void free_{struct_name}({struct_name}* list);"
        )

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
        self.generate_helpers_section()

        # 4. Генерируем код для каждой функции
        for scope in json_data:
            if scope.get("type") == "function" and not scope.get("is_stub", False):
                self.generate_function_scope(scope)

        return "\n".join(self.output)

    def collect_types_from_ast(self, json_data: List[Dict]):
        """Собирает все типы из AST для генерации структур"""

        def process_node(node):
            if not isinstance(node, dict):
                return

            # Обрабатываем declaration узлы
            if node.get("node") == "declaration":
                var_type = node.get("var_type", "")
                if var_type:
                    # Для tuple[int] генерируем только универсальную структуру
                    if var_type.startswith("tuple["):
                        # Проверяем, есть ли tuple_info
                        tuple_info = node.get("tuple_info", {})
                        if tuple_info.get("is_uniform", False):
                            # Это tuple[T] - генерируем универсальную структуру
                            print(f"DEBUG: Найден tuple[int]: {var_type}")
                            self.map_type_to_c(
                                var_type
                            )  # Это вызовет generate_tuple_struct()
                        elif tuple_info.get("is_fixed", False):
                            # Это tuple[T1, T2, ...] - генерируем фиксированную структуру
                            self.map_type_to_c(var_type)

                    elif var_type.startswith("list["):
                        print(f"DEBUG: Найден list: {var_type}")
                        self.map_type_to_c(var_type)

            # Обрабатываем expression_ast
            expression_ast = node.get("expression_ast")
            if expression_ast:
                self._process_ast_for_types(expression_ast)

            # Обрабатываем операции
            operations = node.get("operations", [])
            for op in operations:
                if isinstance(op, dict):
                    if op.get("type") in [
                        "CREATE_TUPLE_UNIFORM",
                        "CREATE_TUPLE_FIXED",
                        "CREATE_LIST",
                    ]:
                        items = op.get("items", [])
                        for item in items:
                            if isinstance(item, dict):
                                self._process_ast_for_types(item)

        # Проходим по всем scope и узлам
        for scope in json_data:
            if scope.get("type") in ["module", "function"]:
                # Обрабатываем graph узлы
                for node in scope.get("graph", []):
                    process_node(node)

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
