import json
import os
from typing import Dict, List, Any


class CCodeGenerator:
    def __init__(self):
        self.output = []
        self.indent_level = 0
        self.temp_var_counter = 0
        self.function_declarations = []
        self.c_imports = []
        self.user_imports = {}

        # Маппинг типов
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
        }

        self.operator_map = {
            "+": "+",
            "-": "-",
            "*": "*",
            "/": "/",
            "//": "/",
            "%": "%",
            "**": "pow",
            "==": "==",
            "!=": "!=",
            "<": "<",
            ">": ">",
            "<=": "<=",
            ">=": ">=",
            "and": "&&",
            "or": "||",
            "not": "!",
            "&": "&",
            "|": "|",
            "^": "^",
            "<<": "<<",
            ">>": ">>",
            "~": "~",
        }

    def indent(self):
        return "    " * self.indent_level

    def add_line(self, line: str):
        self.output.append(self.indent() + line)

    def generate_temp_var(self):
        self.temp_var_counter += 1
        return f"temp_{self.temp_var_counter}"

    def map_type(self, type_str: str) -> str:
        if type_str.startswith("*"):
            base_type = type_str[1:]
            c_base_type = self.type_map.get(base_type, "void")
            return f"{c_base_type}*"
        return self.type_map.get(type_str, type_str)

    def collect_imports(self, json_data: List[Dict]):
        """Собирает все импорты из глобального scope"""
        for scope in json_data:
            if scope["type"] == "module":
                for node in scope.get("graph", []):
                    if node["node"] == "c_import":
                        self.c_imports.append(node)
                    # user imports пока не обрабатываем, но можем сохранить
                    elif node["node"] == "function_declaration":
                        # Сохраняем пользовательские функции для forward declarations
                        func_name = node["function_name"]
                        return_type = self.map_type(node.get("return_type", "None"))
                        params = []
                        for param in node.get("parameters", []):
                            param_type = self.map_type(param["type"])
                            params.append(f"{param_type} {param['name']}")

                        if not params:
                            params_str = "void"
                        else:
                            params_str = ", ".join(params)

                        declaration = f"{return_type} {func_name}({params_str});"
                        self.function_declarations.append(declaration)

    def generate_c_imports(self):
        """Генерирует #include директивы из cimport"""

        # Пользовательские cimport
        for c_import in self.c_imports:
            header = c_import["header"]
            is_system = c_import["is_system"]

            if is_system:
                self.add_line(f"#include <{header}>")
            else:
                self.add_line(f'#include "{header}"')

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

        # Собираем импорты и объявления функций
        self.collect_imports(json_data)

        # Генерируем заголовок с импортами
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
        func_name = func_scope["function_name"]
        return_type = self.map_type(func_scope.get("return_type", "None"))

        # Параметры
        params = []
        for param in func_scope.get("parameters", []):
            param_type = self.map_type(param["type"])
            param_name = param["name"]
            params.append(f"{param_type} {param_name}")

        if not params:
            params_str = "void"
        else:
            params_str = ", ".join(params)

        # Сигнатура функции
        self.add_line(f"{return_type} {func_name}({params_str}) {{")
        self.indent_level += 1

        # Локальные переменные (декларируем их в начале функции)
        local_vars = func_scope.get("local_variables", [])
        symbol_table = func_scope.get("symbol_table", {})

        for var_name in local_vars:
            var_info = symbol_table.get(var_name)
            if var_info and var_info.get("key") == "var":
                var_type = self.map_type(var_info.get("type", "int"))

                # Если есть начальное значение
                if "value" in var_info and var_info["value"]:
                    value = self.generate_expression(var_info["value"])
                    self.add_line(f"{var_type} {var_name} = {value};")
                else:
                    self.add_line(f"{var_type} {var_name};")

        # Генерируем тело функции
        for node in func_scope.get("graph", []):
            self.generate_node(node)

        # Если функция не имеет явного return, добавляем по умолчанию
        has_return = func_scope.get("return_info", {}).get("has_return", False)
        if return_type != "void" and not has_return:
            self.add_line(f"return 0;")

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
        elif node_type == "dereference_write":
            self.generate_dereference_write(node)
        elif node_type == "dereference_read":
            self.generate_dereference_read(node)

    def generate_declaration(self, node: Dict):
        var_name = node["var_name"]
        var_type = self.map_type(node["var_type"])
        is_pointer = node.get("is_pointer", False)

        if "expression_ast" in node:
            value = self.generate_expression(node["expression_ast"])
            self.add_line(f"{var_type} {var_name} = {value};")
        else:
            self.add_line(f"{var_type} {var_name};")

    def generate_assignment(self, node: Dict):
        var_name = node["symbols"][0]
        if "expression_ast" in node:
            value = self.generate_expression(node["expression_ast"])
            self.add_line(f"{var_name} = {value};")

    def generate_function_call(self, node: Dict):
        func_name = node["function"]
        args = node.get("arguments", [])

        # Для простоты считаем, что аргументы - это строки с именами переменных
        # В реальности нужно парсить AST аргументов
        args_str = ", ".join(args)
        self.add_line(f"{func_name}({args_str});")

    def generate_builtin_function_call(self, node: Dict):
        func_name = node["function"]
        args = node.get("arguments", [])

        # Специальная обработка встроенных функций
        if func_name == "print":
            # В C используем printf
            if args:
                # Простая реализация: предполагаем, что аргумент - переменная
                arg = args[0]
                # Определяем тип для форматирования
                # В реальности нужно анализировать тип переменной
                self.add_line(f'printf("%d\\n", {arg});')
            else:
                self.add_line('printf("\\n");')
        elif func_name == "len":
            # Для длины массива/строки - нужно знать тип
            pass  # Пока пропускаем
        else:
            args_str = ", ".join(args)
            self.add_line(f"{func_name}({args_str});")

    def generate_return(self, node: Dict):
        if "operations" in node and node["operations"]:
            operation = node["operations"][0]
            if "value" in operation:
                value = self.generate_expression(operation["value"])
                self.add_line(f"return {value};")
            else:
                self.add_line("return;")

    def generate_if_statement(self, node: Dict):
        condition = self.generate_expression(node["condition_ast"])
        self.add_line(f"if ({condition}) {{")
        self.indent_level += 1

        for body_node in node.get("body", []):
            self.generate_node(body_node)

        self.indent_level -= 1
        self.add_line("}")

        # elif блоки
        for elif_block in node.get("elif_blocks", []):
            elif_condition = self.generate_expression(elif_block["condition_ast"])
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
        condition = self.generate_expression(node.get("condition", {}))
        self.add_line(f"while ({condition}) {{")
        self.indent_level += 1

        for body_node in node.get("body", []):
            self.generate_node(body_node)

        self.indent_level -= 1
        self.add_line("}")

    def generate_for_loop(self, node: Dict):
        loop_var = node.get("loop_variable", "i")
        iterable = node.get("iterable", {})

        # Простая реализация для range()
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
        args = node.get("arguments", [])
        if args:
            # Простая реализация для одного аргумента
            arg = args[0]
            self.add_line(f'printf("%d\\n", {arg});')
        else:
            self.add_line('printf("\\n");')

    def generate_dereference_write(self, node: Dict):
        # *p = value
        pointer = node.get("symbols", [""])[0]
        operations = node.get("operations", [])
        if operations:
            for op in operations:
                if op["type"] == "WRITE_POINTER":
                    value = self.generate_expression(op["value"])
                    self.add_line(f"*{pointer} = {value};")

    def generate_dereference_read(self, node: Dict):
        # var = *p
        operations = node.get("operations", [])
        if operations:
            for op in operations:
                if op["type"] == "READ_POINTER":
                    target = op.get("target", "")
                    pointer = op.get("from", "")
                    self.add_line(f"{target} = *{pointer};")

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
            operator = self.operator_map.get(
                ast.get("operator_symbol", ""), ast.get("operator_symbol", "")
            )

            # Специальная обработка для pow()
            if operator == "pow":
                return f"pow({left}, {right})"

            return f"({left} {operator} {right})"

        elif node_type == "function_call":
            func_name = ast.get("function", "")
            args = [self.generate_expression(arg) for arg in ast.get("arguments", [])]
            args_str = ", ".join(args)
            return f"{func_name}({args_str})"

        elif node_type == "address_of":
            variable = ast.get("variable", "")
            return f"&{variable}"

        elif node_type == "dereference":
            pointer = ast.get("pointer", "")
            return f"*{pointer}"

        elif node_type == "unary_operation":
            operand = self.generate_expression(ast.get("operand", {}))
            operator = self.operator_map.get(
                ast.get("operator_symbol", ""), ast.get("operator_symbol", "")
            )
            return f"{operator}({operand})"

        # Для других типов
        return str(ast.get("value", ""))
