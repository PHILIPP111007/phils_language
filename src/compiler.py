import json
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

        # Маппинг типов Python -> C
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
        }

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

    def indent(self) -> str:
        """Возвращает отступ для текущего уровня"""
        return "    " * self.indent_level

    def add_line(self, line: str):
        """Добавляет строку с правильным отступом"""
        self.output.append(self.indent() + line)

    def add_empty_line(self):
        """Добавляет пустую строку"""
        self.output.append("")

    def map_type_to_c(self, py_type: str, is_pointer: bool = False) -> str:
        """Преобразует тип Python в тип C"""
        if py_type.startswith("*"):
            # Уже указатель
            base_type = py_type[1:]
            c_base_type = self.type_map.get(base_type, "void")
            return f"{c_base_type}*"
        elif py_type == "pointer":
            return "void*"
        else:
            c_type = self.type_map.get(py_type, "int")
            if is_pointer:
                return f"{c_type}*"
            return c_type

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
        self.reset()

        # Обрабатываем каждый scope
        for scope in json_data:
            scope_type = scope.get("type", "")

            if scope_type == "module":
                self.generate_module_scope(scope)
            elif scope_type == "function":
                self.generate_function_scope(scope)

        return "\n".join(self.output)

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
        """Генерирует объявление переменной"""
        var_name = node.get("var_name", "")
        var_type = node.get("var_type", "")
        is_pointer = node.get("is_pointer", False)
        operations = node.get("operations", [])

        # Проверяем, была ли переменная ранее удалена
        was_deleted = False
        for op in operations:
            if op.get("type") == "NEW_VAR":
                was_deleted = op.get("was_deleted", False)
                break

        # Объявляем переменную
        self.declare_variable(var_name, var_type, is_pointer)

        # Генерируем C тип
        c_type = self.map_type_to_c(var_type, is_pointer)

        # Если переменная была удалена, это переобъявление
        if was_deleted:
            self.add_line(f"// Переобъявление {var_name} после удаления")

        # Добавляем объявление
        self.add_line(f"{c_type} {var_name};")

        # Обрабатываем инициализацию
        expression_ast = node.get("expression_ast")
        if expression_ast:
            expr = self.generate_expression(expression_ast)
            self.add_line(f"{var_name} = {expr};")

    def generate_delete(self, node: Dict):
        """Генерирует код для del (полное удаление)"""
        symbols = node.get("symbols", [])

        for target in symbols:
            # Помечаем переменную как удаленную
            self.mark_variable_deleted(target, "full")

            # Получаем информацию о переменной
            var_info = self.get_variable_info(target)

            if not var_info:
                self.add_line(f"// ERROR: Переменная '{target}' не найдена для del")
                continue

            self.add_line(f"// del {target} (полное удаление)")

            # Обрабатываем в зависимости от типа переменной
            if var_info["is_pointer"]:
                # Для указателей - освобождаем память если не NULL
                self.add_line(f"if ({target} != NULL) {{")
                self.indent_level += 1
                self.add_line(f"free({target});")
                self.indent_level -= 1
                self.add_line("}")

            # Обнуляем переменную
            c_type = var_info["c_type"]
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

    def generate_from_json(self, json_data: List[Dict]) -> str:
        """Генерирует C код из JSON AST (альтернативный интерфейс)"""
        self.output = []
        self.indent_level = 0
        self.variable_scopes = [{}]
        self.current_scope_level = 0

        # Собираем импорты и объявления
        self.collect_imports_and_declarations(json_data)

        # Генерируем заголовок
        self.generate_c_imports()

        # Генерируем forward declarations
        self.generate_forward_declarations()

        # Генерируем код для каждой функции
        for scope in json_data:
            if scope.get("type") == "function" and not scope.get("is_stub", False):
                self.generate_function_scope(scope)

        return "\n".join(self.output)

    def generate_expression(self, ast: Dict) -> str:
        """Генерирует C выражение из AST"""
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

            # Проверяем, объявлена ли переменная
            if not self.is_variable_declared(var_name):
                print(f"WARNING: Использование необъявленной переменной '{var_name}'")

            return var_name

        elif node_type == "binary_operation":
            left_ast = ast.get("left", {})
            right_ast = ast.get("right", {})
            operator = ast.get("operator_symbol", "")

            left = self.generate_expression(left_ast)
            right = self.generate_expression(right_ast)

            # Обработка специальных операторов
            if operator == "**":
                return f"pow({left}, {right})"

            # Маппинг операторов
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

            # Удаляем @ из имени функции для C кода
            if func_name.startswith("@"):
                func_name = func_name[1:]

            # Проверяем, является ли встроенной функцией
            builtin_funcs = ["len", "str", "int", "bool", "range"]
            if func_name in builtin_funcs:
                c_func_name = f"builtin_{func_name}"
            else:
                c_func_name = func_name

            # Генерируем аргументы
            args = ast.get("arguments", [])
            arg_strings = []
            for arg_ast in args:
                arg_strings.append(self.generate_expression(arg_ast))

            args_str = ", ".join(arg_strings)
            return f"{c_func_name}({args_str})"

        # Добавляем обработку других типов AST

        elif node_type == "list_literal":
            # Для списков генерируем массив
            items = ast.get("items", [])
            if items:
                item_strs = [self.generate_expression(item) for item in items]
                return f"{{{', '.join(item_strs)}}}"
            else:
                return "{}"

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
