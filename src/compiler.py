import json
from typing import Dict, List, Any


class CCodeGenerator:
    def __init__(self):
        self.output = []
        self.indent_level = 0
        self.temp_var_counter = 0
        self.function_declarations = []
        self.c_imports = []
        self.declared_vars = set()

        # Маппинг типов
        self.type_map = {
            "int": "int",
            "float": "double",  # В C float обычно double
            "str": "char*",
            "bool": "bool",
            "None": "void",
            "null": "void*",
            "list": "void*",
            "dict": "void*",
            "set": "void*",
        }

    def indent(self):
        return "    " * self.indent_level

    def add_line(self, line: str):
        self.output.append(self.indent() + line)

    def reset_declared_vars(self):
        """Сброс для новой функции"""
        self.declared_vars = set()

    def map_type(self, type_str: str) -> str:
        if type_str.startswith("*"):
            base_type = type_str[1:]
            c_base_type = self.type_map.get(base_type, "void")
            return f"{c_base_type}*"
        return self.type_map.get(type_str, type_str)

    def collect_imports_and_declarations(self, json_data: List[Dict]):
        """Собирает импорты и объявления функций"""
        for scope in json_data:
            if scope["type"] == "module":
                for node in scope.get("graph", []):
                    if node["node"] == "c_import":
                        self.c_imports.append(node)
                    elif node["node"] == "function_declaration":
                        self.add_function_declaration(node)

    def add_function_declaration(self, node: Dict):
        """Добавляет forward declaration функции"""
        func_name = node["function_name"]
        return_type = self.map_type(node.get("return_type", "None"))

        # Параметры
        params = []
        for param in node.get("parameters", []):
            param_type = self.map_type(param["type"])
            param_name = param["name"]
            params.append(f"{param_type} {param_name}")

        # Пустые параметры -> void
        if not params:
            params_str = "void"
        else:
            params_str = ", ".join(params)

        declaration = f"{return_type} {func_name}({params_str});"
        self.function_declarations.append(declaration)

    def generate_c_imports(self):
        """Генерирует #include директивы"""
        seen = set()
        for c_import in self.c_imports:
            header = c_import["header"]
            is_system = c_import["is_system"]

            if header not in seen:
                seen.add(header)
                if is_system:
                    self.add_line(f"#include <{header}>")
                else:
                    self.add_line(f'#include "{header}"')

        if seen:
            self.add_line("")

    def generate_forward_declarations(self):
        """Генерирует forward declarations функций"""
        if self.function_declarations:
            for decl in self.function_declarations:
                self.add_line(decl)
            self.add_line("")

    def generate_from_json(self, json_data: List[Dict]) -> str:
        """Генерирует C код из JSON AST"""
        self.output = []
        self.c_imports = []
        self.function_declarations = []

        # Собираем импорты и объявления
        self.collect_imports_and_declarations(json_data)

        # Генерируем заголовок
        self.generate_c_imports()

        # Генерируем forward declarations
        self.generate_forward_declarations()

        # Генерируем код для каждой функции
        for scope in json_data:
            if scope["type"] == "function" and not scope.get("is_stub", False):
                self.generate_function(scope)

        return "\n".join(self.output)

    def generate_function(self, func_scope: Dict):
        """Генерирует код функции"""
        self.reset_declared_vars()
        func_name = func_scope["function_name"]
        return_type = self.map_type(func_scope.get("return_type", "None"))

        # Параметры
        params = []
        for param in func_scope.get("parameters", []):
            param_type = self.map_type(param["type"])
            param_name = param["name"]
            params.append(f"{param_type} {param_name}")
            self.declared_vars.add(param_name)

        if not params:
            params_str = "void"
        else:
            params_str = ", ".join(params)

        # Сигнатура функции
        self.add_line(f"{return_type} {func_name}({params_str}) {{")
        self.indent_level += 1

        # Генерируем ВСЕ узлы из графа
        for node in func_scope.get("graph", []):
            self.generate_node(node)

        self.indent_level -= 1
        self.add_line("}")
        self.add_line("")

    def generate_node(self, node: Dict):
        """Генерирует код для узла AST"""
        node_type = node.get("node")

        if node_type == "declaration":
            self.generate_declaration(node)
        elif node_type == "assignment":
            self.generate_assignment(node)
        elif node_type == "function_call":
            self.generate_function_call(node)
        elif node_type == "builtin_function_call":
            self.generate_builtin_function_call(node)
        elif node_type == "return":
            self.generate_return(node)
        elif node_type == "if_statement":
            self.generate_if_statement(node)
        elif node_type == "while_loop":
            self.generate_while_loop(node)
        elif node_type == "for_loop":
            self.generate_for_loop(node)
        elif node_type == "print":
            self.generate_print(node)
        else:
            # Для отладки: выводим информацию о неподдерживаемом узле
            print(f"Warning: Unsupported node type: {node_type}")

    def generate_declaration(self, node: Dict):
        """Генерирует объявление переменной"""
        var_name = node["var_name"]
        var_type = self.map_type(node["var_type"])

        # Проверяем, не объявлена ли уже переменная
        if var_name in self.declared_vars:
            # Если уже объявлена (как параметр), НЕ объявляем заново
            # Просто присваиваем значение
            if "expression_ast" in node:
                value = self.generate_expression(node["expression_ast"])
                self.add_line(f"{var_name} = {value};")
        else:
            # Новая переменная
            self.declared_vars.add(var_name)

            if "expression_ast" in node:
                value = self.generate_expression(node["expression_ast"])
                self.add_line(f"{var_type} {var_name} = {value};")
            else:
                self.add_line(f"{var_type} {var_name};")

    def generate_assignment(self, node: Dict):
        """Генерирует присваивание"""
        if "symbols" in node and node["symbols"]:
            var_name = node["symbols"][0]
            if "expression_ast" in node:
                value = self.generate_expression(node["expression_ast"])
                self.add_line(f"{var_name} = {value};")

    def generate_builtin_function_call(self, node: Dict):
        """Генерирует вызов встроенной функции"""
        func_name = node["function"]
        args = node.get("arguments", [])

        # Преобразуем аргументы в строки
        arg_strings = []
        for arg in args:
            if isinstance(arg, str):
                arg_strings.append(arg)
            else:
                # Если аргумент сложный, генерируем выражение
                # (в вашем JSON аргументы представлены как строки)
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings)

        if func_name == "print":
            # Для print используем printf
            # Нужно определить формат в зависимости от типа
            if args_str:
                self.add_line(f'printf("%d\\n", {args_str});')
            else:
                self.add_line('printf("\\n");')
        else:
            # Другие встроенные функции
            self.add_line(f"{func_name}({args_str});")

    def generate_function_call(self, node: Dict):
        """Генерирует вызов функции"""
        func_name = node["function"]

        if func_name.startswith("@"):
            func_name = func_name[1:]

        args = node.get("arguments", [])

        # Преобразуем аргументы в строки
        arg_strings = []
        for arg in args:
            if isinstance(arg, str):
                arg_strings.append(arg)
            else:
                arg_strings.append(str(arg))

        args_str = ", ".join(arg_strings)
        self.add_line(f"{func_name}({args_str});")

    def generate_return(self, node: Dict):
        """Генерирует return"""
        if "operations" in node and node["operations"]:
            operation = node["operations"][0]
            if "value" in operation:
                value = self.generate_expression(operation["value"])
                self.add_line(f"return {value};")
            else:
                self.add_line("return;")
        else:
            self.add_line("return;")

    def generate_if_statement(self, node: Dict):
        """Генерирует if statement"""
        condition = self.generate_expression(node.get("condition_ast", {}))
        self.add_line(f"if ({condition}) {{")
        self.indent_level += 1

        for body_node in node.get("body", []):
            self.generate_node(body_node)

        self.indent_level -= 1
        self.add_line("}")

        # elif блоки
        for elif_block in node.get("elif_blocks", []):
            elif_condition = self.generate_expression(
                elif_block.get("condition_ast", {})
            )
            self.add_line(f"else if ({elif_condition}) {{")
            self.indent_level += 1

            for body_node in elif_block.get("body", []):
                self.generate_node(body_node)

            self.indent_level -= 1
            self.add_line("}")

        # else блок
        if node.get("else_block"):
            self.add_line("else {")
            self.indent_level += 1

            for body_node in node["else_block"].get("body", []):
                self.generate_node(body_node)

            self.indent_level -= 1
            self.add_line("}")

    def generate_while_loop(self, node: Dict):
        """Генерирует while loop"""
        condition = self.generate_expression(node.get("condition", {}))
        self.add_line(f"while ({condition}) {{")
        self.indent_level += 1

        for body_node in node.get("body", []):
            self.generate_node(body_node)

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

            self.add_line(
                f"for (int {loop_var} = {start}; {loop_var} < {stop}; {loop_var} += {step}) {{"
            )
            self.indent_level += 1

            for body_node in node.get("body", []):
                self.generate_node(body_node)

            self.indent_level -= 1
            self.add_line("}")

    def generate_print(self, node: Dict):
        """Генерирует print"""
        args = node.get("arguments", [])
        if args:
            for arg in args:
                self.add_line(f'printf("%d\\n", {arg});')
        else:
            self.add_line('printf("\\n");')

    def generate_expression(self, ast: Dict) -> str:
        """Генерирует C выражение из AST"""
        if not ast:
            return ""

        node_type = ast.get("type")

        if node_type == "literal":
            value = ast.get("value")
            data_type = ast.get("data_type")

            if data_type == "str":
                return f'"{value}"'
            elif data_type == "bool":
                return "true" if value else "false"
            elif data_type == "None":
                return "NULL"
            else:
                return str(value)

        elif node_type == "variable":
            return ast.get("value", "")

        elif node_type == "binary_operation":
            left = self.generate_expression(ast.get("left", {}))
            right = self.generate_expression(ast.get("right", {}))
            operator = ast.get("operator_symbol", "")

            # Специальная обработка для pow()
            if operator == "**":
                return f"pow({left}, {right})"

            return f"({left} {operator} {right})"

        elif node_type == "function_call":
            func_name = ast.get("function", "")
            args = ast.get("arguments", [])

            print(f"DEBUG generate_expression: вызов функции '{func_name}'")
            print(
                f"  Начинается с @: {func_name.startswith('@') if func_name else False}"
            )

            # УДАЛЯЕМ @ из имени функции для C кода
            if func_name.startswith("@"):  # C - code
                original_name = func_name
                func_name = func_name[1:]  # Удаляем @
                print(f"  Преобразовано '{original_name}' -> '{func_name}'")

            # Генерируем аргументы
            arg_strings = []
            for arg in args:
                arg_strings.append(self.generate_expression(arg))

            args_str = ", ".join(arg_strings)

            return f"{func_name}({args_str})"

        elif node_type == "unary_operation":
            operand = self.generate_expression(ast.get("operand", {}))
            operator = ast.get("operator_symbol", "")
            return f"{operator}({operand})"

        ast_value = str(ast.get("value", ""))
        if ast_value.startswith("@"):  # C - code
            ast_value = ast_value[1:]

        # Для неизвестных типов
        return ast_value
