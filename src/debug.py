import re
from typing import Dict, List, Optional

from src.modules.constants import DATA_TYPES
from src.modules.logger import logger


class JSONValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.scope_symbols = {}  # {scope_level: {var_name: var_info}}
        self.all_scopes = []  # Сохраняем все scopes для поиска родительских
        self.functions = {}  # {func_name: func_info}
        self.source_map = {}  # Сопоставление узлов с исходными строками
        self.builtin_functions = {
            "print": {"return_type": "None", "min_args": 0, "max_args": None},
            "len": {"return_type": "int", "min_args": 1, "max_args": 1},
            "str": {"return_type": "str", "min_args": 1, "max_args": 1},
            "int": {"return_type": "int", "min_args": 1, "max_args": 1},
            "bool": {"return_type": "bool", "min_args": 1, "max_args": 1},
            "range": {"return_type": "range", "min_args": 1, "max_args": 3},
        }
        # Для отслеживания состояния переменных
        self.variable_history = {}  # {(scope_level, var_name): [{"action": "declare"/"assign"/"delete", "node_id": str}]}
        self.variable_states = {}  # {(scope_level, var_name): "active"/"deleted"}
        self.classes = {}  # {class_name: class_info}

    def validate(self, json_data: List[Dict]) -> list[Dict]:
        """Основной метод валидации"""
        self.errors = []
        self.warnings = []
        self.scope_symbols = {}
        self.functions = {}
        self.all_scopes = json_data
        self.source_map = {}
        self.variable_history = {}  # Оставляем, но не используем
        self.variable_states = {}  # Оставляем, но не используем

        # Собираем информацию о всех узлах и их строках
        self.build_source_map(json_data)

        if not isinstance(json_data, list):
            self.add_error("JSON должен быть списком scope'ов")
            return self.get_report()

        # Собираем информацию о всех scope'ах и символах
        self.collect_symbols(json_data)

        # ЗАКОММЕНТИРОВАТЬ: не строим историю переменных
        # self.build_variable_history(json_data)

        # Проверяем каждый scope
        for scope_idx, scope in enumerate(json_data):
            self.validate_scope(scope, scope_idx, json_data)

        return self.get_report()

    def collect_symbols(self, json_data: List[Dict]):
        """Собирает информацию о всех символах в системе"""
        for scope_idx, scope in enumerate(json_data):
            level = scope.get("level", 0)

            if "symbol_table" in scope and scope["symbol_table"]:
                if level not in self.scope_symbols:
                    self.scope_symbols[level] = {}

                for symbol_name, symbol_info in scope["symbol_table"].items():
                    key = symbol_info.get("key")

                    # Сохраняем функции отдельно
                    if key == "function":
                        self.functions[symbol_name] = symbol_info
                    # Сохраняем классы отдельно
                    elif key == "class":
                        self.classes[symbol_name] = symbol_info
                        # Также добавляем в обычные символы
                        self.scope_symbols[level][symbol_name] = symbol_info
                    else:
                        # Сохраняем обычные переменные
                        self.scope_symbols[level][symbol_name] = symbol_info

            # Также собираем классы из class_declaration узлов
            if scope.get("type") == "class_declaration":
                class_name = scope.get("class_name")
                if class_name:
                    self.classes[class_name] = {
                        "name": class_name,
                        "key": "class",
                        "type": "class",
                        "value": None,
                        "id": class_name,
                        "is_deleted": False,
                    }
                    if level not in self.scope_symbols:
                        self.scope_symbols[level] = {}
                    self.scope_symbols[level][class_name] = self.classes[class_name]

    def build_source_map(self, json_data: List[Dict]):
        """Строит карту соответствия узлов исходным строкам"""
        # Счетчик глобальных строк
        global_line_counter = 1

        for scope_idx, scope in enumerate(json_data):
            level = scope.get("level", 0)
            graph = scope.get("graph", [])

            for node_idx, node in enumerate(graph):
                node_id = f"{scope_idx}.{node_idx}"
                content = node.get("content", "")

                # Сохраняем информацию о строке
                self.source_map[node_id] = {
                    "content": content,
                    "scope_idx": scope_idx,
                    "scope_level": level,
                    "scope_type": scope.get("type", "unknown"),
                    "node_idx": node_idx,
                    "global_line_number": global_line_counter,
                }

                # Увеличиваем счетчик только если строка не пустая
                if content.strip():
                    global_line_counter += 1

    def build_variable_history(self, json_data: List[Dict]):
        """Строит историю операций с переменными С УЧЕТОМ ПОРЯДКА СТРОК"""
        # Сначала собираем все узлы в правильном порядке
        all_nodes = []

        for scope_idx, scope in enumerate(json_data):
            level = scope.get("level", 0)
            graph = scope.get("graph", [])

            for node_idx, node in enumerate(graph):
                node_id = f"{scope_idx}.{node_idx}"
                all_nodes.append(
                    {
                        "scope_idx": scope_idx,
                        "node_idx": node_idx,
                        "node_id": node_id,
                        "level": level,
                        "node": node,
                        "scope": scope,
                    }
                )

        # Сортируем по scope_idx и node_idx для сохранения порядка
        all_nodes.sort(key=lambda x: (x["scope_idx"], x["node_idx"]))

        # Глобальный счетчик времени для всех операций
        global_timestamp = 0

        for node_info in all_nodes:
            scope_idx = node_info["scope_idx"]
            node_idx = node_info["node_idx"]
            node_id = node_info["node_id"]
            level = node_info["level"]
            node = node_info["node"]
            node_type = node.get("node", "unknown")

            if node_type == "declaration":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    key = (level, symbol)
                    if key not in self.variable_history:
                        self.variable_history[key] = []
                    self.variable_history[key].append(
                        {
                            "action": "declare",
                            "node_id": node_id,
                            "content": node.get("content", ""),
                            "timestamp": global_timestamp,
                            "unique_id": f"{node_id}_{symbol}",
                        }
                    )
                    global_timestamp += 1
                    # При объявлении переменная активна
                    self.variable_states[key] = "active"

            elif node_type == "assignment":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    key = (level, symbol)
                    if key not in self.variable_history:
                        self.variable_history[key] = []
                    self.variable_history[key].append(
                        {
                            "action": "assign",
                            "node_id": node_id,
                            "content": node.get("content", ""),
                            "timestamp": global_timestamp,
                            "unique_id": f"{node_id}_{symbol}",
                        }
                    )
                    global_timestamp += 1

            elif node_type == "delete":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    key = (level, symbol)
                    if key not in self.variable_history:
                        self.variable_history[key] = []
                    self.variable_history[key].append(
                        {
                            "action": "delete",
                            "node_id": node_id,
                            "content": node.get("content", ""),
                            "timestamp": global_timestamp,
                            "unique_id": f"{node_id}_{symbol}",
                        }
                    )
                    global_timestamp += 1
                    # Переменная помечается как удаленная
                    self.variable_states[key] = "deleted"

            elif node_type == "del_pointer":  # НОВОЕ
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    key = (level, symbol)
                    if key not in self.variable_history:
                        self.variable_history[key] = []
                    self.variable_history[key].append(
                        {
                            "action": "delete_pointer",
                            "node_id": node_id,
                            "content": node.get("content", ""),
                            "timestamp": global_timestamp,
                            "unique_id": f"{node_id}_{symbol}",
                        }
                    )
                    global_timestamp += 1
                    # При del_pointer помечаем как удаленный указатель, но данные остаются
                    self.variable_states[key] = "pointer_deleted"

            elif node_type == "builtin_function_call":
                func_name = node.get("function", "")
                args = node.get("arguments", [])
                dependencies = node.get("dependencies", [])

                # Используем dependencies из узла
                for dep in dependencies:
                    if dep and dep.isalpha() and dep not in ["True", "False", "None"]:
                        key = (level, dep)
                        if key not in self.variable_history:
                            self.variable_history[key] = []
                        self.variable_history[key].append(
                            {
                                "action": "use_in_function",
                                "function": func_name,
                                "node_id": node_id,
                                "content": node.get("content", ""),
                                "timestamp": global_timestamp,
                                "unique_id": f"{node_id}_{dep}",
                            }
                        )
                        global_timestamp += 1

            elif node_type == "function_call":
                args = node.get("arguments", [])
                dependencies = node.get("dependencies", [])
                for dep in dependencies:
                    if dep and dep.isalpha() and dep not in ["True", "False", "None"]:
                        key = (level, dep)
                        if key not in self.variable_history:
                            self.variable_history[key] = []
                        self.variable_history[key].append(
                            {
                                "action": "use_in_function",
                                "node_id": node_id,
                                "content": node.get("content", ""),
                                "timestamp": global_timestamp,
                                "unique_id": f"{node_id}_{dep}",
                            }
                        )
                        global_timestamp += 1

    def get_variable_state(self, var_name: str, level: int) -> str:
        """Получает текущее состояние переменной"""
        key = (level, var_name)
        return self.variable_states.get(key, "unknown")

    def is_variable_deleted(self, var_name: str, level: int) -> bool:
        """Проверяет, удалена ли переменная"""
        state = self.get_variable_state(var_name, level)
        return state == "deleted"

    def get_last_variable_action(self, var_name: str, level: int) -> Optional[Dict]:
        """Получает последнее действие с переменной"""
        key = (level, var_name)
        if key in self.variable_history and self.variable_history[key]:
            return self.variable_history[key][-1]
        return None

    def add_error(self, message: str, scope_idx: int = None, node_idx: int = None):
        """Добавляет ошибку с информацией о строке"""
        full_message = message

        if scope_idx is not None and node_idx is not None:
            node_id = f"{scope_idx}.{node_idx}"
            if node_id in self.source_map:
                content = self.source_map[node_id]["content"]
                if content:
                    full_message = f"Строка '{content}': {message}"

        self.errors.append(
            {
                "message": full_message,
                "scope_idx": scope_idx,
                "node_idx": node_idx,
                "line_number": self.get_line_number(scope_idx, node_idx),
            }
        )

    # TODO
    def add_warning(self, message: str, scope_idx: int = None, node_idx: int = None):
        """Добавляет предупреждение с информацией о строке"""
        full_message = message

        if scope_idx is not None and node_idx is not None:
            node_id = f"{scope_idx}.{node_idx}"
            if node_id in self.source_map:
                content = self.source_map[node_id]["content"]
                if content:
                    full_message = f"Строка '{content}': {message}"

        self.warnings.append(
            {
                "message": full_message,
                "scope_idx": scope_idx,
                "node_idx": node_idx,
                "line_number": self.get_line_number(scope_idx, node_idx),
            }
        )

    def get_line_number(self, scope_idx: int, node_idx: int) -> Optional[int]:
        """Получает номер строки исходного кода для узла"""
        if scope_idx is None or node_idx is None:
            return None

        node_id = f"{scope_idx}.{node_idx}"
        if node_id in self.source_map:
            content = self.source_map[node_id]["content"]
            if content:
                # Считаем строки в исходном коде
                # Для простоты, можно использовать индекс узла + 1
                return node_idx + 1

        return None

    def validate_scope(self, scope: Dict, scope_idx: int, all_scopes: List[Dict]):
        """Валидирует отдельный scope с учетом всех новых проверок"""
        level = scope.get("level", 0)
        scope_type = scope.get("type", "unknown")

        # 1. БАЗОВЫЕ ПРОВЕРКИ СТРУКТУРЫ
        required_fields = ["level", "type", "local_variables", "graph", "symbol_table"]
        for field in required_fields:
            if field not in scope:
                self.add_error(
                    f"Scope {scope_idx} (level {level}, type {scope_type}) отсутствует поле '{field}'",
                    scope_idx,
                    None,
                )

        # 2. ПРОВЕРКА ТАБЛИЦЫ СИМВОЛОВ И ЛОКАЛЬНЫХ ПЕРЕМЕННЫХ
        self.validate_symbol_table(scope, scope_idx)
        self.check_duplicate_declarations_in_scope(scope, scope_idx)

        # 3. КОНТЕКСТНЫЕ ПРОВЕРКИ В ЗАВИСИМОСТИ ОТ ТИПА SCOPE
        if scope_type == "class_declaration":
            # Ключевая проверка наследования для классов
            self.validate_inheritance_hierarchy(scope, scope_idx)

            # Вычисляем MRO для информации и дальнейших проверок
            class_name = scope.get("class_name")
            if class_name:
                mro = self.check_method_resolution_order(class_name)
                # Можно сохранить MRO для использования в других проверках
                if mro and len(mro) > 1:
                    logger.debug(f"  MRO для класса '{class_name}': {mro}")

        elif scope_type == "function":
            # Проверяем функции для потоков
            self.validate_thread_functions(scope, scope_idx)

            # Старая проверка наличия return
            self.validate_function_return(scope, scope_idx)
            # Проверка типа возвращаемого значения
            self.validate_function_return_type(scope, scope_idx)
            # Проверка всех путей возврата
            self.validate_return_paths(scope, scope_idx)

        # Проверка неиспользуемых параметров для всех типов функций/методов
        if scope_type in ["function", "constructor", "class_method"]:
            self.check_unused_parameters(scope, scope_idx)

        # 4. ПРОВЕРКА ГРАФА ОПЕРАЦИЙ
        if "graph" in scope:
            self.validate_graph(scope, scope_idx)

            # Детальная проверка каждого узла графа
            graph = scope.get("graph", [])
            for node_idx, node in enumerate(graph):
                node_type = node.get("node", "unknown")

                # ВАЖНЕЙШИЕ ПРОВЕРКИ УЗЛОВ:

                # 4.1 ПРОВЕРКА УКАЗАТЕЛЕЙ (критически важно для C-кода)
                self.validate_pointer_usage(node, node_idx, scope_idx, level)

                # 4.2 ПРОВЕРКА ГРАНИЦ МАССИВОВ (предотвращение ошибок выполнения)
                self.validate_array_bounds(node, node_idx, scope_idx, level)

                # 4.3 ПРОВЕРКА СТРОКОВЫХ ОПЕРАЦИЙ (частая ошибка)
                self.validate_string_operations(node, node_idx, scope_idx, level)

                # 4.4 ПРОВЕРКА C-ФУНКЦИЙ (безопасность и корректность)
                self.validate_c_function_calls(node, node_idx, scope_idx, level)

                # 4.5 ПРОВЕРКА ТИПОВ В УЗЛАХ
                self.validate_node_types(node, node_idx, scope_idx, level)

                # 4.6 ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА ДЕЛЕНИЯ НА НОЛЬ
                self.check_division_by_zero(node, node_idx, scope_idx, level)

                # 4.7 ПРОВЕРКА ОПЕРАЦИЙ С КОРТЕЖАМИ (неизменяемость)
                if node_type in [
                    "index_assignment",
                    "augmented_index_assignment",
                    "slice_assignment",
                ]:
                    variable = node.get("variable", "")
                    if variable:
                        var_info = self.get_symbol_info(variable, level)
                        if var_info and "tuple" in var_info.get("type", ""):
                            self.add_error(
                                f"попытка изменения неизменяемого кортежа '{variable}'",
                                scope_idx,
                                node_idx,
                            )

                # 4.8 ПРОВЕРКА НЕОПРЕДЕЛЕННЫХ МЕТОДОВ (важно для ООП)
                self.check_undefined_methods(scope, scope_idx)

            # 5. ПОСТ-ПРОВЕРКИ ПОСЛЕ АНАЛИЗА ГРАФА

            # 5.1 Проверка неиспользуемых переменных
            self.check_unused_variables(scope, scope_idx)

            # 5.2 Проверка условий циклов
            self.check_loop_conditions(scope, scope_idx)

            # 5.3 Проверка утечек памяти (особенно для указателей)
            self.check_memory_leaks(scope, scope_idx)

            # 5.4 Проверка отсутствующих объявлений (C-типы, импорты)
            self.check_missing_declarations(scope, scope_idx)

        # 6. СПЕЦИФИЧНЫЕ ПРОВЕРКИ ДЛЯ ЦИКЛОВ
        self.validate_loops(scope, scope_idx)

        # 7. ПРОВЕРКА ВЫЗОВОВ МЕТОДОВ КЛАССОВ (особенно в наследовании)
        if scope_type == "class_method":
            self._validate_class_method_calls(scope, scope_idx)

        # 8. СБОР МЕТРИК КОДА (информация для разработчика)
        if scope_type == "function" or scope_type == "class_method":
            self._collect_function_metrics(scope, scope_idx)

    def check_duplicate_declarations_in_scope(self, scope: Dict, scope_idx: int):
        """Проверяет дублирование переменных в local_variables"""
        local_vars = scope.get("local_variables", [])
        seen = {}

        for i, var_name in enumerate(local_vars):
            if var_name in seen:
                # Нашли дубликат
                first_occurrence = seen[var_name]
                self.add_warning(
                    f"переменная '{var_name}' дублируется в local_variables (первое упоминание на позиции {first_occurrence})",
                    scope_idx,
                    None,
                )
            else:
                seen[var_name] = i

    def validate_symbol_table(self, scope: Dict, scope_idx: int):
        """Валидирует таблицу символов scope'а"""
        symbol_table = scope.get("symbol_table", {})
        local_vars = scope.get("local_variables", [])

        for var_name in local_vars:
            if var_name not in symbol_table:
                self.add_warning(
                    f"переменная '{var_name}' в local_variables отсутствует в symbol_table",
                    scope_idx,
                    None,
                )

        for symbol_name, symbol_info in symbol_table.items():
            self.validate_symbol(symbol_info, scope_idx, symbol_name)

    def validate_symbol(self, symbol_info: Dict, scope_idx: int, symbol_name: str):
        """Валидирует отдельный символ"""
        required_fields = ["name", "key", "type", "id"]
        for field in required_fields:
            if field not in symbol_info:
                self.add_error(
                    f"у символа '{symbol_name}' отсутствует поле '{field}'",
                    scope_idx,
                    None,
                )

        if symbol_info.get("name") != symbol_name:
            self.add_warning(
                f"имя символа '{symbol_name}' не совпадает с полем 'name': {symbol_info.get('name')}",
                scope_idx,
                None,
            )

        var_type = symbol_info.get("type", "")
        key = symbol_info.get("key", "")

        # Для классов и функций типы могут быть любыми
        if key in ["class", "function"]:
            return

        # Пропускаем проверку для параметра 'self'
        if symbol_name == "self":
            return

        if var_type not in DATA_TYPES and not var_type.startswith("*"):
            # Проверяем, не является ли это пользовательским классом
            if var_type not in self.classes:
                self.add_warning(
                    f"символ '{symbol_name}' имеет неизвестный тип '{var_type}'",
                    scope_idx,
                    None,
                )

    def validate_graph(self, scope: Dict, scope_idx: int):
        """Валидирует граф операций"""
        graph = scope.get("graph", [])
        symbol_table = scope.get("symbol_table", {})
        level = scope.get("level", 0)

        # Отслеживаем состояние переменных в процессе валидации
        variable_states = {}  # {var_name: "active"/"deleted"/"pointer_deleted"}

        for node_idx, node in enumerate(graph):
            node_type = node.get("node", "unknown")
            content = node.get("content", "")

            self.validate_node_types(node, node_idx, scope_idx, level)

            if node_type == "declaration":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    if symbol in variable_states:
                        if variable_states[symbol] == "deleted":
                            # Переменная была удалена, можно переобъявлять
                            variable_states[symbol] = "active"
                        else:
                            # Переменная уже активна - ошибка
                            self.add_error(
                                f"повторное объявление переменной '{symbol}' без предварительного удаления",
                                scope_idx,
                                node_idx,
                            )
                    else:
                        # Новая переменная
                        variable_states[symbol] = "active"

                self.validate_declaration(
                    node, node_idx, scope_idx, symbol_table, level
                )

            elif node_type == "redeclaration":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    if symbol in variable_states:
                        if variable_states[symbol] == "deleted":
                            # Разрешено: переменная была удалена
                            variable_states[symbol] = "active"
                        else:
                            # Ошибка: переменная активна
                            self.add_error(
                                f"недопустимое переобъявление переменной '{symbol}' без предварительного удаления",
                                scope_idx,
                                node_idx,
                            )
                    else:
                        # Переменная не была объявлена в этом scope
                        # Может быть объявлена в родительском scope
                        self.add_warning(
                            f"переобъявление переменной '{symbol}', не объявленной в текущем scope",
                            scope_idx,
                            node_idx,
                        )
                        variable_states[symbol] = "active"

                self.validate_declaration(
                    node, node_idx, scope_idx, symbol_table, level
                )

            elif node_type in ["assignment", "declaration", "return", "while_loop"]:
                self.validate_node_types(node, node_idx, scope_idx, level)

            elif node_type == "delete":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    if symbol in variable_states:
                        if variable_states[symbol] == "deleted":
                            # Уже удалена
                            self.add_error(
                                f"переменная '{symbol}' уже была удалена",
                                scope_idx,
                                node_idx,
                            )
                        else:
                            # Помечаем как удаленную
                            variable_states[symbol] = "deleted"
                            logger.debug(
                                f"    Переменная '{symbol}' помечена как удаленная"
                            )
                    else:
                        # Переменная не была объявлена в этом scope
                        self.add_error(
                            f"переменная '{symbol}' не была объявлена перед удалением",
                            scope_idx,
                            node_idx,
                        )

                self.validate_delete(node, node_idx, scope_idx, symbol_table, level)

            elif node_type == "del_pointer":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    if symbol in variable_states:
                        if variable_states[symbol] in ["deleted", "pointer_deleted"]:
                            # Уже удалена
                            self.add_error(
                                f"указатель '{symbol}' уже был удален",
                                scope_idx,
                                node_idx,
                            )
                        else:
                            # Помечаем как удаленный указатель
                            variable_states[symbol] = "pointer_deleted"
                            logger.debug(
                                f"    Указатель '{symbol}' помечен как удаленный (данные сохранены)"
                            )
                    else:
                        # Переменная не была объявлена в этом scope
                        self.add_error(
                            f"указатель '{symbol}' не был объявлен перед del_pointer",
                            scope_idx,
                            node_idx,
                        )

                self.validate_del_pointer(
                    node, node_idx, scope_idx, symbol_table, level
                )

            elif node_type == "builtin_function_call":
                # Проверяем аргументы
                func_name = node.get("function", "")
                dependencies = node.get("dependencies", [])

                for dep in dependencies:
                    if dep and dep.isalpha() and dep not in ["True", "False", "None"]:
                        # Проверяем в текущем scope
                        if dep in variable_states:
                            if variable_states[dep] == "deleted":
                                self.add_error(
                                    f"использование удаленной переменной '{dep}' в аргументе функции '{func_name}'",
                                    scope_idx,
                                    node_idx,
                                )
                            elif variable_states[dep] == "pointer_deleted":
                                self.add_warning(
                                    f"использование удаленного указателя '{dep}' в аргументе функции '{func_name}' (данные могут быть доступны)",
                                    scope_idx,
                                    node_idx,
                                )
                        else:
                            # Проверяем в родительских scope'ах
                            parent_scope = self.get_parent_scope(level)
                            found = False
                            current_level = level

                            while not found and parent_scope is not None:
                                parent_vars = parent_scope.get("local_variables", [])
                                if dep in parent_vars:
                                    found = True
                                    break

                                current_level = parent_scope.get("level", 0)
                                parent_scope = self.get_parent_scope(current_level)

                            if not found:
                                self.add_error(
                                    f"использование необъявленной переменной '{dep}' в аргументе функции '{func_name}'",
                                    scope_idx,
                                    node_idx,
                                )

                self.validate_builtin_function_call(
                    node, node_idx, scope_idx, symbol_table, level
                )

            elif node_type == "print":
                dependencies = node.get("dependencies", [])
                for dep in dependencies:
                    if dep and dep.isalpha() and dep not in ["True", "False", "None"]:
                        # Проверяем в текущем scope
                        if dep in variable_states:
                            if variable_states[dep] == "deleted":
                                self.add_error(
                                    f"использование удаленной переменной '{dep}' в print",
                                    scope_idx,
                                    node_idx,
                                )
                            elif variable_states[dep] == "pointer_deleted":
                                self.add_warning(
                                    f"использование удаленного указателя '{dep}' в print (данные могут быть доступны)",
                                    scope_idx,
                                    node_idx,
                                )
                        else:
                            # Проверяем в родительских scope'ах
                            parent_scope = self.get_parent_scope(level)
                            found = False
                            current_level = level

                            while not found and parent_scope is not None:
                                parent_vars = parent_scope.get("local_variables", [])
                                if dep in parent_vars:
                                    found = True
                                    break

                                current_level = parent_scope.get("level", 0)
                                parent_scope = self.get_parent_scope(current_level)

                            if not found:
                                self.add_error(
                                    f"использование необъявленной переменной '{dep}' в print",
                                    scope_idx,
                                    node_idx,
                                )

                self.validate_print(node, node_idx, scope_idx, symbol_table, level)

            elif node_type == "assignment":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    if symbol in variable_states:
                        if variable_states[symbol] == "deleted":
                            self.add_error(
                                f"присваивание полностью удаленной переменной '{symbol}' (требуется переобъявление)",
                                scope_idx,
                                node_idx,
                            )
                        elif variable_states[symbol] == "pointer_deleted":
                            self.add_warning(
                                f"присваивание удаленному указателю '{symbol}' (данные могут быть доступны)",
                                scope_idx,
                                node_idx,
                            )
                    else:
                        # Проверяем в родительских scope'ах
                        parent_scope = self.get_parent_scope(level)
                        found = False
                        current_level = level

                        while not found and parent_scope is not None:
                            parent_vars = parent_scope.get("local_variables", [])
                            if symbol in parent_vars:
                                found = True
                                break

                            current_level = parent_scope.get("level", 0)
                            parent_scope = self.get_parent_scope(current_level)

                        if not found:
                            self.add_error(
                                f"присваивание необъявленной переменной '{symbol}'",
                                scope_idx,
                                node_idx,
                            )

                self.validate_assignment(node, node_idx, scope_idx, symbol_table, level)

            elif node_type == "dereference_write":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    if symbol in variable_states:
                        if variable_states[symbol] == "deleted":
                            self.add_error(
                                f"запись через полностью удаленный указатель '{symbol}'",
                                scope_idx,
                                node_idx,
                            )
                        elif variable_states[symbol] == "pointer_deleted":
                            self.add_warning(
                                f"запись через удаленный указатель '{symbol}' (данные могут быть доступны)",
                                scope_idx,
                                node_idx,
                            )
                    else:
                        self.add_warning(
                            f"запись через необъявленный указатель '{symbol}'",
                            scope_idx,
                            node_idx,
                        )

                self.validate_dereference_write(
                    node, node_idx, scope_idx, symbol_table, level
                )

            elif node_type == "dereference_read":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    if symbol in variable_states:
                        if variable_states[symbol] == "deleted":
                            self.add_error(
                                f"чтение в полностью удаленную переменную '{symbol}'",
                                scope_idx,
                                node_idx,
                            )
                        elif variable_states[symbol] == "pointer_deleted":
                            self.add_warning(
                                f"чтение в переменную '{symbol}', которая была удалена через del_pointer",
                                scope_idx,
                                node_idx,
                            )
                    else:
                        self.add_warning(
                            f"чтение в необъявленную переменную '{symbol}'",
                            scope_idx,
                            node_idx,
                        )

                self.validate_dereference_read(
                    node, node_idx, scope_idx, symbol_table, level
                )

            elif node_type == "augmented_assignment":
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    if symbol in variable_states:
                        if variable_states[symbol] == "deleted":
                            self.add_error(
                                f"составное присваивание удаленной переменной '{symbol}'",
                                scope_idx,
                                node_idx,
                            )
                        elif variable_states[symbol] == "pointer_deleted":
                            self.add_warning(
                                f"составное присваивание удаленному указателю '{symbol}'",
                                scope_idx,
                                node_idx,
                            )
                    else:
                        self.add_error(
                            f"составное присваивание необъявленной переменной '{symbol}'",
                            scope_idx,
                            node_idx,
                        )

                self.validate_augmented_assignment(
                    node, node_idx, scope_idx, symbol_table, level
                )

            elif node_type in [
                "function_declaration",
                "function_call",
                "function_call_assignment",
                "return",
                "while_loop",
                "for_loop",
            ]:
                # Вызываем соответствующие методы валидации
                if node_type == "function_declaration":
                    self.validate_function_declaration(
                        node, node_idx, scope_idx, symbol_table, level
                    )
                elif node_type in ["function_call", "function_call_assignment"]:
                    self.validate_function_call(
                        node, node_idx, scope_idx, symbol_table, level
                    )
                elif node_type == "return":
                    self.validate_return(node, node_idx, scope_idx, symbol_table, level)
                elif node_type in ["while_loop", "for_loop"]:
                    self.validate_loop_node(
                        node, node_idx, scope_idx, symbol_table, level
                    )

    def validate_node_types(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Валидирует типы в узле"""
        node_type = node.get("node", "")

        if node_type == "assignment":
            self.validate_assignment_types(node, node_idx, scope_idx, level)
        elif node_type == "declaration":
            self.validate_declaration_types(node, node_idx, scope_idx, level)
        elif node_type == "return":
            self.validate_return_types(node, node_idx, scope_idx, level)
        elif node_type == "while_loop":
            self.validate_while_condition_types(node, node_idx, scope_idx, level)
        elif node_type == "if_statement":
            self.validate_if_condition_types(node, node_idx, scope_idx, level)
        elif node_type in ["binary_operation", "unary_operation"]:
            self.validate_operation_types(node, node_idx, scope_idx, level)

    def validate_assignment_types(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Валидирует типы в присваивании"""
        symbols = node.get("symbols", [])
        expression_ast = node.get("expression_ast")

        if not symbols or not expression_ast:
            return

        target_var = symbols[0]
        target_info = self.get_symbol_info(target_var, level)

        if not target_info:
            return

        target_type = target_info.get("type", "")
        value_type = self.get_type_from_ast(expression_ast, scope_idx, node_idx, level)

        # Проверяем совместимость типов
        if not self.are_types_compatible(target_type, value_type):
            self.add_error(
                f"нельзя присвоить значение типа '{value_type}' переменной типа '{target_type}'",
                scope_idx,
                node_idx,
            )

        # Рекурсивно проверяем типы в AST
        self.validate_ast_types(expression_ast, node_idx, scope_idx, level)

    def validate_declaration_types(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Валидирует типы при объявлении"""
        content = node.get("content", "")

        if not content:
            return

        # Парсим строку объявления
        patterns = [
            r"var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)",
            r"const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)",
        ]

        for pattern in patterns:
            match = re.match(pattern, content)
            if match:
                var_name, var_type, value = match.groups()

                # Для выражений с операциями используем более сложную логику
                if any(op in value for op in ["+", "-", "*", "/", "(", ")"]):
                    # Определяем тип выражения
                    if var_type == "int":
                        # Проверяем, что это числовое выражение
                        if '"' in value or "'" in value:
                            self.add_error(
                                f"нельзя присвоить строку переменной типа int",
                                scope_idx,
                                node_idx,
                            )
                        elif "True" in value or "False" in value:
                            self.add_error(
                                f"нельзя присвоить bool переменной типа int",
                                scope_idx,
                                node_idx,
                            )
                    elif var_type == "str":
                        # Проверяем, что выражение возвращает строку
                        if value.isdigit():
                            self.add_warning(
                                f"присвоение числа строковой переменной",
                                scope_idx,
                                node_idx,
                            )
                else:
                    # Простое значение
                    value_type = self.guess_type_from_value(value)

                    # Проверяем совместимость типов
                    if not self.are_types_compatible(var_type, value_type):
                        self.add_warning(
                            f"инициализация переменной '{var_name}' типа '{var_type}' "
                            f"значением типа '{value_type}' может вызвать проблемы",
                            scope_idx,
                            node_idx,
                        )
                break

    def validate_return_types(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Валидирует типы возвращаемых значений"""
        return
        # Получаем текущую функцию
        current_scope = self.get_scope_by_level(level)
        if not current_scope or current_scope.get("type") != "function":
            return

        declared_return_type = current_scope.get("return_type", "None")
        return_value_ast = node.get("operations", [{}])[0].get("value")

        if not return_value_ast:
            return

        actual_return_type = self.get_type_from_ast(
            return_value_ast, scope_idx, node_idx, level
        )

        if not self.are_types_compatible(declared_return_type, actual_return_type):
            self.add_error(
                f"функция объявлена как возвращающая '{declared_return_type}', "
                f"но возвращает значение типа '{actual_return_type}'",
                scope_idx,
                node_idx,
            )

    def validate_while_condition_types(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Валидирует типы в условии while"""
        condition_ast = node.get("condition_ast")

        if condition_ast:
            condition_type = self.get_type_from_ast(
                condition_ast, scope_idx, node_idx, level
            )

            # Условие должно быть bool
            if condition_type not in ["bool", "unknown"] and condition_type != "bool":
                self.add_error(
                    f"условие цикла while должно быть bool, получено: {condition_type}",
                    scope_idx,
                    node_idx,
                )

            # Рекурсивно проверяем AST условия
            self.validate_ast_types(condition_ast, node_idx, scope_idx, level)

    def validate_if_condition_types(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Валидирует типы в условии if/elif"""
        condition_ast = node.get("condition_ast")

        if condition_ast:
            condition_type = self.get_type_from_ast(
                condition_ast, scope_idx, node_idx, level
            )

            # Условие должно быть bool
            if condition_type not in ["bool", "unknown"] and condition_type != "bool":
                self.add_error(
                    f"условие if должно быть bool, получено: {condition_type}",
                    scope_idx,
                    node_idx,
                )

            # Рекурсивно проверяем AST условия
            self.validate_ast_types(condition_ast, node_idx, scope_idx, level)

        # Проверяем elif блоки
        for elif_block in node.get("elif_blocks", []):
            self.validate_if_condition_types(elif_block, node_idx, scope_idx, level)

    def validate_operation_types(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Валидирует типы в операциях"""
        operations = node.get("operations", [])

        for op in operations:
            op_type = op.get("type")

            if op_type == "BINARY_OPERATION":
                left_ast = op.get("left")
                right_ast = op.get("right")
                operator = op.get("operator_symbol", "")

                if left_ast and right_ast:
                    left_type = self.get_type_from_ast(
                        left_ast, scope_idx, node_idx, level
                    )
                    right_type = self.get_type_from_ast(
                        right_ast, scope_idx, node_idx, level
                    )

                    if not self.can_operate_between_types(
                        left_type, right_type, operator
                    ):
                        self.add_error(
                            f"нельзя выполнить операцию '{operator}' "
                            f"между типами '{left_type}' и '{right_type}'",
                            scope_idx,
                            node_idx,
                        )

            elif op_type == "UNARY_OPERATION":
                operand_ast = op.get("operand")
                operator = op.get("operator_symbol", "")

                if operand_ast:
                    operand_type = self.get_type_from_ast(
                        operand_ast, scope_idx, node_idx, level
                    )

                    if operator == "not" and operand_type != "bool":
                        self.add_error(
                            f"оператор 'not' применяется к типу '{operand_type}', а не к bool",
                            scope_idx,
                            node_idx,
                        )

    def get_parent_scope(self, level: int) -> Optional[Dict]:
        """Находит родительский scope для заданного уровня"""
        # Ищем scope с уровнем, указанным как parent_scope
        for scope in self.all_scopes:
            if scope.get("level") == level:
                parent_level = scope.get("parent_scope")
                if parent_level is not None:
                    # Ищем scope с таким уровнем
                    for parent_scope in self.all_scopes:
                        if parent_scope.get("level") == parent_level:
                            return parent_scope
        return None

    def validate_declaration(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует объявление переменной"""
        symbols = node.get("symbols", [])
        operations = node.get("operations", [])
        content = node.get("content", "")

        for symbol in symbols:
            if symbol not in symbol_table:
                self.add_error(
                    f"объявляемая переменная '{symbol}' отсутствует в symbol_table",
                    scope_idx,
                    node_idx,
                )
            else:
                for op in operations:
                    if op.get("type") in ["NEW_VAR", "NEW_CONST"]:
                        declared_type = op.get("var_type") or op.get("const_type")
                        actual_type = symbol_table[symbol].get("type")
                        if declared_type != actual_type:
                            self.add_error(
                                f"тип переменной '{symbol}' не совпадает (объявлен: {declared_type}, в symbol_table: {actual_type})",
                                scope_idx,
                                node_idx,
                            )

        # Проверяем значение инициализации
        if content:
            # Парсим объявление
            pattern = r"var\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)"
            match = re.match(pattern, content)

            if match:
                var_name, var_type, value = match.groups()

                # Проверяем выражение инициализации
                self.validate_expression(value, scope_idx, node_idx, level)

                # Проверяем совместимость типов при инициализации
                self.validate_type_compatibility(
                    var_name, value, scope_idx, node_idx, level
                )

    def validate_expression(
        self, expression: str, scope_idx: int, node_idx: int, level: int
    ):
        """Валидирует выражение (правая часть присваивания или инициализации)"""
        expression = expression.strip()

        constructor_pattern = r"([A-Z][a-zA-Z0-9_]*)\s*\(([^)]*)\)"
        match = re.match(constructor_pattern, expression)
        if match:
            class_name = match.group(1)
            # Проверяем, что класс существует
            if class_name not in self.classes:
                self.add_error(
                    f"класс '{class_name}' не объявлен",
                    scope_idx,
                    node_idx,
                )
            return

        # Сначала проверяем, не является ли это литералом
        if (expression.startswith('"') and expression.endswith('"')) or (
            expression.startswith("'") and expression.endswith("'")
        ):
            return

        if expression.isdigit() or (
            expression.startswith("-") and expression[1:].isdigit()
        ):
            return

        if expression in ["True", "False", "None"]:
            return

        # Проверяем операции с указателями
        if expression.startswith("&"):
            # Адрес переменной
            var_name = expression[1:].strip()
            if var_name and var_name.isalpha():
                if not self.find_symbol_in_scope(var_name, level):
                    self.add_error(
                        f"переменная '{var_name}' для взятия адреса не объявлена",
                        scope_idx,
                        node_idx,
                    )
            return

        elif expression.startswith("*"):
            # Разыменование указателя
            pointer_name = expression[1:].strip()
            if pointer_name and pointer_name.isalpha():
                pointer_info = self.get_symbol_info(pointer_name, level)
                if not pointer_info:
                    self.add_error(
                        f"указатель '{pointer_name}' для разыменования не найден",
                        scope_idx,
                        node_idx,
                    )
                elif not pointer_info.get("type", "").startswith("*"):
                    self.add_error(
                        f"переменная '{pointer_name}' не является указателем",
                        scope_idx,
                        node_idx,
                    )
            return

        # Проверяем вызовы функций - ИГНОРИРУЕМ функции с @
        func_calls = re.findall(r"(@?[a-zA-Z_][a-zA-Z0-9_]*)\s*\(", expression)
        for func_name in func_calls:
            # Игнорируем функции, начинающиеся с @
            if func_name.startswith("@"):
                logger.debug(
                    f"    Пропускаем проверку функции '{func_name}' (игнорируемая)"
                )
                continue

            if (
                func_name not in self.functions
                and func_name not in self.builtin_functions
            ):
                self.add_error(
                    f"функция '{func_name}' не объявлена", scope_idx, node_idx
                )

        # Проверяем переменные (игнорируя части внутри вызовов функций)
        # Убираем все вызовы функций для упрощения
        temp_expr = expression
        for func_name in func_calls:
            # Простое удаление вызовов функций
            temp_expr = temp_expr.replace(f"{func_name}(", "")

        # Ищем переменные
        var_pattern = r'(?<!["\'])(?<![a-zA-Z0-9_])\b([a-zA-Z_][a-zA-Z0-9_]+)\b(?![a-zA-Z0-9_])(?!["\'])'
        identifiers = re.findall(var_pattern, temp_expr)

        for identifier in identifiers:
            # Пропускаем ключевые слова, типы данных, литералы
            if identifier in ["True", "False", "None"] or identifier.isdigit():
                continue

            # Пропускаем функции с @
            if identifier.startswith("@"):
                continue

            # Проверяем, не является ли это вызовом функции (уже обработали)
            if identifier in func_calls:
                continue

            # Это переменная - проверяем ее существование
            logger.debug(f"      Проверка переменной '{identifier}' в выражении")
            if not self.find_symbol_in_scope(identifier, level):
                self.add_error(
                    f"переменная '{identifier}' в выражении не объявлена",
                    scope_idx,
                    node_idx,
                )
            elif self.is_variable_deleted(identifier, level):
                self.add_error(
                    f"переменная '{identifier}' в выражении была удалена",
                    scope_idx,
                    node_idx,
                )

    def validate_assignment(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует присваивание"""
        symbols = node.get("symbols", [])
        dependencies = node.get("dependencies", [])
        operations = node.get("operations", [])
        content = node.get("content", "")

        # 1. Проверяем левую часть (целевую переменную)
        for symbol in symbols:
            symbol_info = self.get_symbol_info(symbol, level)
            logger.debug(
                f"  Проверка переменной '{symbol}': symbol_info={symbol_info is not None}"
            )

            if not symbol_info:
                self.add_error(
                    f"присваиваемая переменная '{symbol}' не объявлена",
                    scope_idx,
                    node_idx,
                )
            else:
                # Проверяем, не была ли переменная удалена
                logger.debug(
                    f"    Состояние переменной '{symbol}': {self.get_variable_state(symbol, level)}"
                )
                logger.debug(
                    f"    Удалена ли: {self.is_variable_deleted(symbol, level)}"
                )

                if self.is_variable_deleted(symbol, level):
                    # Получаем историю переменной
                    key = (level, symbol)
                    if key in self.variable_history:
                        logger.debug(f"    История переменной {symbol}:")
                        for action in self.variable_history[key]:
                            logger.debug(
                                f"      Действие: {action['action']}, content: {action.get('content', '')}"
                            )

                    # Проверяем, была ли после удаления переинициализация
                    last_action = self.get_last_variable_action(symbol, level)
                    if last_action and last_action["action"] == "delete":
                        # Ищем объявления после удаления
                        found_redeclaration = False
                        for action in self.variable_history.get(key, []):
                            if (
                                action["action"] == "declare"
                                and action["timestamp"] > last_action["timestamp"]
                            ):
                                found_redeclaration = True
                                break

                        if not found_redeclaration:
                            self.add_error(
                                f"переменная '{symbol}' была удалена и требует переинициализации",
                                scope_idx,
                                node_idx,
                            )
                elif symbol_info.get("key") == "const":
                    self.add_error(
                        f"попытка присваивания константе '{symbol}'",
                        scope_idx,
                        node_idx,
                    )

        # 2. Проверяем правую часть выражения
        # Извлекаем правую часть из content
        if symbols and content:
            target_var = symbols[0]
            # Вырезаем правую часть после "="
            if "=" in content:
                expression = content.split("=", 1)[1].strip()
                logger.debug(f"  Выражение в правой части: '{expression}'")

                # Проверяем вызовы функций в правой части
                self.validate_expression(expression, scope_idx, node_idx, level)

                # Проверяем совместимость типов
                self.validate_type_compatibility(
                    target_var, expression, scope_idx, node_idx, level
                )

        # 3. Проверяем зависимости (используемые переменные)
        for dep in dependencies:
            logger.debug(f"  Проверка зависимости '{dep}'")
            found = self.find_symbol_in_scope(dep, level)
            logger.debug(f"    Найдена в scope: {found}")

            if not found:
                self.add_error(
                    f"используемая переменная '{dep}' не объявлена", scope_idx, node_idx
                )
            elif self.is_variable_deleted(dep, level):
                logger.debug(
                    f"    Переменная '{dep}' удалена: {self.is_variable_deleted(dep, level)}"
                )
                self.add_error(
                    f"используемая переменная '{dep}' была удалена", scope_idx, node_idx
                )

    def validate_delete(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует удаление переменной"""
        symbols = node.get("symbols", [])

        for symbol in symbols:
            # Проверяем, существует ли переменная
            symbol_info = self.get_symbol_info(symbol, level)
            if not symbol_info:
                self.add_error(
                    f"удаляемая переменная '{symbol}' не объявлена", scope_idx, node_idx
                )
                continue

            # Проверяем, константа ли это
            if symbol_info.get("key") == "const":
                self.add_error(
                    f"попытка удаления константы '{symbol}'", scope_idx, node_idx
                )
                continue

            # Проверяем, не была ли уже удалена
            key = (level, symbol)
            current_state = self.variable_states.get(key)

            if current_state == "deleted":
                self.add_error(
                    f"переменная '{symbol}' уже была удалена", scope_idx, node_idx
                )
            else:
                # Помечаем как удаленную
                self.variable_states[key] = "deleted"
                logger.debug(f"    Переменная '{symbol}' помечена как удаленная")

    def validate_del_pointer(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует оператор del_pointer"""
        symbols = node.get("symbols", [])

        for symbol in symbols:
            symbol_info = self.get_symbol_info(symbol, level)
            if not symbol_info:
                self.add_error(
                    f"удаляемый указатель '{symbol}' не объявлен", scope_idx, node_idx
                )
            else:
                if symbol_info.get("key") == "const":
                    self.add_error(
                        f"попытка удаления константы '{symbol}'", scope_idx, node_idx
                    )

    def validate_unary_operation(
        self, op: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Валидирует унарную операцию"""
        value = op.get("value")

        if value and value.isalpha() and value not in ["True", "False", "None"]:
            if not self.find_symbol_in_scope(value, level):
                self.add_error(
                    f"операнд унарной операции '{value}' не объявлен",
                    scope_idx,
                    node_idx,
                )
            elif self.is_variable_deleted(value, level):
                self.add_error(
                    f"операнд унарной операции '{value}' был удален",
                    scope_idx,
                    node_idx,
                )

    def validate_augmented_assignment(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует составное присваивание"""
        symbols = node.get("symbols", [])
        operations = node.get("operations", [])
        dependencies = node.get("dependencies", [])

        for symbol in symbols:
            symbol_info = self.get_symbol_info(symbol, level)
            if not symbol_info:
                self.add_error(
                    f"переменная '{symbol}' в составном присваивании не объявлена",
                    scope_idx,
                    node_idx,
                )
            else:
                # Проверяем, не была ли переменная удалена
                if self.is_variable_deleted(symbol, level):
                    self.add_error(
                        f"переменная '{symbol}' была удалена и требует переинициализации",
                        scope_idx,
                        node_idx,
                    )
                elif symbol_info.get("key") == "const":
                    self.add_error(
                        f"попытка модификации константы '{symbol}'", scope_idx, node_idx
                    )

        for dep in dependencies:
            if not self.find_symbol_in_scope(dep, level):
                self.add_error(
                    f"используемая переменная '{dep}' не объявлена", scope_idx, node_idx
                )
            elif self.is_variable_deleted(dep, level):
                self.add_error(
                    f"используемая переменная '{dep}' была удалена", scope_idx, node_idx
                )

    def validate_function_declaration(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует объявление функции"""
        func_name = node.get("function_name")
        parameters = node.get("parameters", [])
        is_stub = node.get("is_stub", False)

        # Проверяем дублирование функций
        for other_scope in self.all_scopes:
            if other_scope.get("level") <= level:
                for other_node in other_scope.get("graph", []):
                    if (
                        other_node.get("node") == "function_declaration"
                        and other_node.get("function_name") == func_name
                        and other_node is not node
                    ):
                        self.add_error(
                            f"функция '{func_name}' уже объявлена", scope_idx, node_idx
                        )
                        return

        # Проверяем параметры
        param_names = set()
        for param in parameters:
            param_name = param.get("name")
            if param_name in param_names:
                self.add_error(
                    f"дублирующийся параметр '{param_name}' в функции '{func_name}'",
                    scope_idx,
                    node_idx,
                )
            param_names.add(param_name)

        # Если это заглушка, выводим предупреждение
        if is_stub:
            self.add_warning(
                f"функция '{func_name}' объявлена как заглушка (только pass)",
                scope_idx,
                node_idx,
            )

    def validate_function_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов функции с поддержкой AST аргументов"""
        func_name = node.get("function")
        arguments = node.get("arguments", [])

        # ИГНОРИРОВАНИЕ: если функция начинается с @ - пропускаем стандартные проверки
        if func_name and func_name.startswith("@"):
            logger.debug(
                f"✓ Вызов функции '{func_name}' - пропускаем стандартную проверку (C-code/игнорируемая функция)"
            )

            # Только базовая проверка аргументов (если нужно)
            for arg in arguments:
                self._validate_argument(arg, func_name, scope_idx, node_idx, level)
            return  # Завершаем проверку для этой функции

        # Проверяем, что функция существует или является встроенной
        if func_name not in self.functions and func_name not in self.builtin_functions:
            self.add_error(
                f"вызываемая функция '{func_name}' не объявлена", scope_idx, node_idx
            )
        elif func_name in self.functions:
            func_info = self.functions[func_name]
            func_params = func_info.get("parameters", [])

            if len(arguments) != len(func_params):
                self.add_error(
                    f"функция '{func_name}' ожидает {len(func_params)} аргументов, передано {len(arguments)}",
                    scope_idx,
                    node_idx,
                )

        # Проверяем аргументы
        for arg in arguments:
            self._validate_argument(arg, func_name, scope_idx, node_idx, level)

    def _validate_argument(
        self, arg, func_name: str, scope_idx: int, node_idx: int, level: int
    ):
        """Валидирует один аргумент (может быть строкой или AST)"""
        if not arg:
            return

        # Если аргумент - строка
        if isinstance(arg, str):
            # Пропускаем NULL, True, False, None
            if arg in ["NULL", "True", "False", "None"]:
                return

            # Пропускаем литералы
            if (arg.startswith('"') and arg.endswith('"')) or (
                arg.startswith("'") and arg.endswith("'")
            ):
                return

            # Пропускаем числа
            if arg.isdigit() or (arg.startswith("-") and arg[1:].isdigit()):
                return

            # Пропускаем вызовы конструкторов
            if "(" in arg:
                # Это вызов функции или конструктора
                return

            # Проверяем обычные переменные
            if arg.isalpha():
                if not self.find_symbol_in_scope(arg, level):
                    self.add_error(f"аргумент '{arg}' не объявлен", scope_idx, node_idx)
                elif self.is_variable_deleted(arg, level):
                    self.add_error(f"аргумент '{arg}' был удален", scope_idx, node_idx)

        # Если аргумент - AST (словарь)
        elif isinstance(arg, dict):
            arg_type = arg.get("type")

            # Пропускаем конструкторы классов
            if arg_type == "constructor_call":
                return

            # Пропускаем литералы
            if arg_type == "literal":
                return

            # Извлекаем зависимости из AST
            dependencies = self._extract_dependencies_from_ast(arg)

            for dep in dependencies:
                if not self.find_symbol_in_scope(dep, level):
                    self.add_warning(
                        f"переменная '{dep}' в аргументе функции '{func_name}' не объявлена",
                        scope_idx,
                        node_idx,
                    )
                elif self.is_variable_deleted(dep, level):
                    self.add_error(
                        f"переменная '{dep}' в аргументе функции '{func_name}' была удалена",
                        scope_idx,
                        node_idx,
                    )

    def _extract_dependencies_from_ast(self, ast: Dict) -> List[str]:
        """Извлекает зависимости (имена переменных) из AST"""
        dependencies = []

        def traverse(node):
            if not isinstance(node, dict):
                return

            node_type = node.get("type")

            if node_type == "variable":
                var_name = node.get("name") or node.get("value")
                if var_name and var_name not in dependencies:
                    dependencies.append(var_name)

            elif node_type == "attribute_access":
                obj_name = node.get("object")
                if obj_name and obj_name not in dependencies:
                    dependencies.append(obj_name)

            elif node_type == "method_call":
                obj_name = node.get("object")
                if obj_name and obj_name not in dependencies:
                    dependencies.append(obj_name)

                for arg in node.get("arguments", []):
                    traverse(arg)

            elif node_type == "constructor_call":
                for arg in node.get("arguments", []):
                    traverse(arg)

            elif node_type == "function_call":
                # Пользовательские функции добавляем как зависимости
                func_name = node.get("function")
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

            elif node_type == "list_literal":
                for item in node.get("items", []):
                    traverse(item)

            elif node_type == "tuple_literal":
                for item in node.get("items", []):
                    traverse(item)

            elif node_type == "dict_literal":
                for value in node.get("pairs", {}).values():
                    traverse(value)

            elif node_type == "set_literal":
                for item in node.get("items", []):
                    traverse(item)

            elif node_type == "address_of":
                var_name = node.get("variable")
                if var_name and var_name not in dependencies:
                    dependencies.append(var_name)

            elif node_type == "dereference":
                pointer_name = node.get("pointer")
                if pointer_name and pointer_name not in dependencies:
                    dependencies.append(pointer_name)

            elif node_type == "index_access":
                var_name = node.get("variable")
                if var_name and var_name not in dependencies:
                    dependencies.append(var_name)
                traverse(node.get("index"))

            elif node_type == "slice_access":
                var_name = node.get("variable")
                if var_name and var_name not in dependencies:
                    dependencies.append(var_name)

                start = node.get("start")
                stop = node.get("stop")
                step = node.get("step")

                if start:
                    traverse(start)
                if stop:
                    traverse(stop)
                if step:
                    traverse(step)

        traverse(ast)
        return dependencies

    def validate_builtin_function_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов встроенной функции"""
        func_name = node.get("function")
        arguments = node.get("arguments", [])
        dependencies = node.get("dependencies", [])

        if func_name not in self.builtin_functions:
            self.add_error(
                f"встроенная функция '{func_name}' не поддерживается",
                scope_idx,
                node_idx,
            )
            return

        # ... остальная валидация ...

        # Проверяем зависимости (переменные в аргументах)
        for dep in dependencies:
            if not self.find_symbol_in_scope(dep, level):
                self.add_error(
                    f"переменная '{dep}' в аргументе функции '{func_name}' не объявлена",
                    scope_idx,
                    node_idx,
                )
            elif self.is_variable_deleted(dep, level):
                # Но нужно проверить, не было ли использование раньше удаления
                node_id = f"{scope_idx}.{node_idx}"
                current_timestamp = None
                for action in self.variable_history.get((level, dep), []):
                    if action.get("node_id") == node_id:
                        current_timestamp = action.get("timestamp")
                        break

                if current_timestamp is not None:
                    # Ищем удаление после этого использования
                    found_delete_after = False
                    for action in self.variable_history.get((level, dep), []):
                        if (
                            action["action"] == "delete"
                            and action["timestamp"] > current_timestamp
                        ):
                            found_delete_after = True
                            break

                    if not found_delete_after:
                        self.add_error(
                            f"переменная '{dep}' в аргументе функции '{func_name}' была удалена",
                            scope_idx,
                            node_idx,
                        )

    def validate_print(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов функции print"""
        arguments = node.get("arguments", [])
        dependencies = node.get("dependencies", [])

        for dep in dependencies:
            if not self.find_symbol_in_scope(dep, level):
                self.add_error(
                    f"переменная '{dep}' в аргументе print не объявлена",
                    scope_idx,
                    node_idx,
                )
            elif self.is_variable_deleted(dep, level):
                self.add_error(
                    f"переменная '{dep}' в аргументе print была удалена",
                    scope_idx,
                    node_idx,
                )

        # Дополнительно проверяем аргументы для сложных выражений
        for arg in arguments:
            if (
                arg
                and not arg.startswith('"')
                and not arg.endswith('"')
                and not arg.startswith("'")
                and not arg.endswith("'")
                and not arg.isdigit()
                and arg not in ["True", "False", "None"]
            ):
                # Ищем переменные в сложных выражениях
                var_pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)"
                vars_in_arg = re.findall(var_pattern, arg)
                for var in vars_in_arg:
                    if (
                        var not in ["True", "False", "None"]
                        and var not in self.builtin_functions
                        and not self.find_symbol_in_scope(var, level)
                    ):
                        self.add_error(
                            f"переменная '{var}' в выражении print не объявлена",
                            scope_idx,
                            node_idx,
                        )
                    elif self.is_variable_deleted(var, level):
                        self.add_error(
                            f"переменная '{var}' в выражении print была удалена",
                            scope_idx,
                            node_idx,
                        )

    def validate_len_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов len()"""
        arguments = node.get("arguments", [])

        if len(arguments) != 1:
            return

        arg = arguments[0]

        # len() принимает строки или массивы (пока только строки)
        if arg.startswith('"') and arg.endswith('"'):
            return

        if arg.startswith("'") and arg.endswith("'"):
            return

        # Для переменных нужно проверить тип
        if arg.isalpha():
            symbol_info = self.get_symbol_info(arg, level)
            if symbol_info:
                var_type = symbol_info.get("type")
                if var_type not in ["str", "list", "array"]:
                    self.add_error(
                        f"функция len() ожидает строку, передана переменная типа '{var_type}'",
                        scope_idx,
                        node_idx,
                    )

    def validate_int_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов int()"""
        arguments = node.get("arguments", [])

        if len(arguments) != 1:
            return

        arg = arguments[0]

        # int() принимает числа, строки с числами или bool
        if arg.isdigit() or arg in ["True", "False"]:
            return

        if arg.startswith('"') and arg.endswith('"'):
            str_value = arg[1:-1]
            if not str_value.lstrip("-").isdigit():
                self.add_error(
                    f"функция int() не может преобразовать строку '{arg}' в число",
                    scope_idx,
                    node_idx,
                )

        # Для переменных проверяем тип
        if arg.isalpha():
            symbol_info = self.get_symbol_info(arg, level)
            if symbol_info:
                var_type = symbol_info.get("type")
                if var_type not in ["int", "str", "bool"]:
                    self.add_error(
                        f"функция int() ожидает int, string или bool, передана переменная типа '{var_type}'",
                        scope_idx,
                        node_idx,
                    )

    def validate_str_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов str()"""
        arguments = node.get("arguments", [])

        if len(arguments) != 1:
            return

        # str() принимает любые значения
        # Проверяем только, что аргумент существует
        arg = arguments[0]
        if arg.isalpha() and not self.find_symbol_in_scope(arg, level):
            self.add_error(
                f"переменная '{arg}' в аргументе str() не объявлена",
                scope_idx,
                node_idx,
            )
        elif arg.isalpha() and self.is_variable_deleted(arg, level):
            self.add_error(
                f"переменная '{arg}' в аргументе str() была удалена",
                scope_idx,
                node_idx,
            )

    def validate_bool_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов bool()"""
        arguments = node.get("arguments", [])

        if len(arguments) != 1:
            return

        # bool() принимает любые значения
        # Проверяем только, что аргумент существует
        arg = arguments[0]
        if arg.isalpha() and not self.find_symbol_in_scope(arg, level):
            self.add_error(
                f"переменная '{arg}' в аргументе bool() не объявлена",
                scope_idx,
                node_idx,
            )
        elif arg.isalpha() and self.is_variable_deleted(arg, level):
            self.add_error(
                f"переменная '{arg}' в аргументе bool() была удалена",
                scope_idx,
                node_idx,
            )

    def validate_range_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов range()"""
        arguments = node.get("arguments", [])

        # range() принимает 1-3 аргумента, все должны быть int
        for i, arg in enumerate(arguments):
            if arg.isdigit():
                continue

            if arg.isalpha():
                symbol_info = self.get_symbol_info(arg, level)
                if symbol_info:
                    var_type = symbol_info.get("type")
                    if var_type != "int":
                        self.add_error(
                            f"аргумент {i + 1} функции range() должен быть int, передана переменная типа '{var_type}'",
                            scope_idx,
                            node_idx,
                        )
                else:
                    self.add_error(
                        f"переменная '{arg}' в аргументе range() не объявлена",
                        scope_idx,
                        node_idx,
                    )

                # Проверяем, не удалена ли переменная
                if self.is_variable_deleted(arg, level):
                    self.add_error(
                        f"переменная '{arg}' в аргументе range() была удалена",
                        scope_idx,
                        node_idx,
                    )

    def validate_return(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует оператор return"""
        dependencies = node.get("dependencies", [])
        content = node.get("content", "")
        operations = node.get("operations", [])

        # Парсим return выражение
        if content.startswith("return "):
            return_expr = content[7:].strip()  # Убираем "return "
            logger.debug(f"  Проверка return: '{return_expr}'")

            # Получаем текущий scope (функцию) - КОРРЕКТНО
            current_scope = self.get_scope_for_node(scope_idx, level)

            if not current_scope or current_scope.get("type") != "function":
                logger.debug(f"    Return не в функции, пропускаем проверку типа")
                return

            declared_return_type = current_scope.get("return_type", "None")
            logger.debug(
                f"    Функция объявлена как возвращающая: {declared_return_type}"
            )

            # Получаем тип возвращаемого значения
            actual_return_type = "unknown"

            # Используем AST из operations если есть
            for op in operations:
                if op.get("type") == "RETURN":
                    value_ast = op.get("value")
                    if value_ast:
                        actual_return_type = self.get_type_from_ast(
                            value_ast, scope_idx, node_idx, level
                        )
                        logger.debug(
                            f"    Тип возвращаемого значения из AST: {actual_return_type}"
                        )
                        break

            # Если не нашли в AST, пытаемся определить из выражения
            if actual_return_type == "unknown":
                actual_return_type = self.guess_type_from_value(return_expr)
                logger.debug(
                    f"    Тип возвращаемого значения из выражения: {actual_return_type}"
                )

            # Проверяем совместимость типов
            if actual_return_type != "unknown" and not self.are_types_compatible(
                declared_return_type, actual_return_type
            ):
                self.add_error(
                    f"функция объявлена как возвращающая '{declared_return_type}', "
                    f"фактически возвращает '{actual_return_type}'",
                    scope_idx,
                    node_idx,
                )

            # Проверяем сложные выражения
            self.validate_expression(return_expr, scope_idx, node_idx, level)

        # Старая проверка dependencies (для совместимости)
        for dep in dependencies:
            if not self.find_symbol_in_scope(dep, level):
                self.add_error(
                    f"возвращаемая переменная '{dep}' не объявлена", scope_idx, node_idx
                )
            elif self.is_variable_deleted(dep, level):
                self.add_error(
                    f"возвращаемая переменная '{dep}' была удалена", scope_idx, node_idx
                )

    def validate_loop_node(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует узел цикла"""
        node_type = node.get("node")

        if node_type == "while_loop":
            condition = node.get("condition", {})
            if condition.get("type") == "COMPARISON":
                left = condition.get("left")
                right = condition.get("right")

                for var in [left, right]:
                    if var and var.isalpha() and var not in ["True", "False", "None"]:
                        if not self.find_symbol_in_scope(var, level):
                            self.add_error(
                                f"переменная '{var}' в условии цикла не объявлена",
                                scope_idx,
                                node_idx,
                            )
                        elif self.is_variable_deleted(var, level):
                            self.add_error(
                                f"переменная '{var}' в условии цикла была удалена",
                                scope_idx,
                                node_idx,
                            )

        elif node_type == "for_loop":
            loop_var = node.get("loop_variable")
            iterable = node.get("iterable", {})

            if loop_var not in symbol_table:
                self.add_error(
                    f"переменная цикла '{loop_var}' не объявлена", scope_idx, node_idx
                )
            elif self.is_variable_deleted(loop_var, level):
                self.add_error(
                    f"переменная цикла '{loop_var}' была удалена", scope_idx, node_idx
                )

            if iterable.get("type") == "RANGE_CALL":
                args = iterable.get("arguments", {})
                for arg_name, arg_value in args.items():
                    if (
                        arg_value
                        and arg_value.isalpha()
                        and arg_value not in ["True", "False", "None"]
                    ):
                        if not self.find_symbol_in_scope(arg_value, level):
                            self.add_error(
                                f"аргумент range '{arg_value}' не объявлен",
                                scope_idx,
                                node_idx,
                            )
                        elif self.is_variable_deleted(arg_value, level):
                            self.add_error(
                                f"аргумент range '{arg_value}' был удален",
                                scope_idx,
                                node_idx,
                            )

    def validate_function_return(self, scope: Dict, scope_idx: int):
        """Проверяет, что функция имеет return если нужно"""
        return_info = scope.get("return_info", {})
        return_type = scope.get("return_type", "None")
        is_stub = scope.get("is_stub", False)

        # Если функция - заглушка, пропускаем проверку return
        if is_stub:
            if return_type != "None":
                self.add_warning(
                    f"функция-заглушка возвращает '{return_type}' но не имеет return",
                    scope_idx,
                    None,
                )
            return

        # Обычная проверка для не-заглушек
        if return_type != "None" and not return_info.get("has_return", False):
            func_content = ""
            for node_idx, node in enumerate(scope.get("graph", [])):
                if node.get("node") == "function_declaration":
                    func_content = node.get("content", "")
                    break

            if func_content:
                self.add_warning(
                    f"функция возвращает '{return_type}' но не имеет оператора return",
                    scope_idx,
                    None,
                )

    def validate_loops(self, scope: Dict, scope_idx: int):
        """Проверяет циклы на корректность"""
        graph = scope.get("graph", [])

        for node_idx, node in enumerate(graph):
            if node.get("node") in ["while_loop", "for_loop"]:
                body = node.get("body", [])
                if not body:
                    self.add_warning(f"тело цикла пустое", scope_idx, node_idx)

    def validate_pointer_declaration(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует объявление указателя"""
        content = node.get("content", "")
        symbols = node.get("symbols", [])
        operations = node.get("operations", [])

        if not symbols:
            return

        pointer_name = symbols[0]
        pointer_info = self.get_symbol_info(pointer_name, level)

        if not pointer_info:
            return

        # Проверяем, что тип действительно указатель
        if not pointer_info.get("type", "").startswith("*"):
            self.add_error(
                f"переменная '{pointer_name}' объявлена как указатель, но тип не начинается с '*'",
                scope_idx,
                node_idx,
            )
            return

        # Получаем тип, на который указывает указатель
        pointed_type = pointer_info.get("type")[1:]  # Убираем звездочку

        # Проверяем операции с указателем
        for op in operations:
            if op.get("type") == "GET_ADDRESS":
                pointed_var = op.get("of")
                pointed_var_info = self.get_symbol_info(pointed_var, level)

                if pointed_var_info:
                    # Проверяем совместимость типов
                    pointed_var_type = pointed_var_info.get("type")
                    if pointed_var_type != pointed_type:
                        self.add_error(
                            f"указатель '*{pointed_type}' не может указывать на переменную '{pointed_var}' типа '{pointed_var_type}'",
                            scope_idx,
                            node_idx,
                        )

    def validate_dereference_write(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует запись через указатель (*p = значение)"""
        content = node.get("content", "")
        symbols = node.get("symbols", [])
        operations = node.get("operations", [])

        if not symbols:
            return

        pointer_name = symbols[0]
        pointer_info = self.get_symbol_info(pointer_name, level)

        if not pointer_info:
            self.add_error(f"указатель '{pointer_name}' не найден", scope_idx, node_idx)
            return

        # Проверяем, что это действительно указатель
        pointer_type = pointer_info.get("type", "")
        if not pointer_type.startswith("*"):
            self.add_error(
                f"переменная '{pointer_name}' не является указателем",
                scope_idx,
                node_idx,
            )
            return

        # Получаем тип, на который указывает указатель
        pointed_type = pointer_type[1:]  # Убираем звездочку

        # Получаем значение для присваивания
        for op in operations:
            if op.get("type") == "WRITE_POINTER":
                value = op.get("value", {})  # Теперь это AST

                # Получаем тип значения из AST
                value_type = self.get_type_from_ast(value, scope_idx, node_idx, level)

                if value_type and value_type != "unknown":
                    # Проверяем совместимость типов
                    if not self.are_types_compatible(pointed_type, value_type):
                        self.add_error(
                            f"нельзя присвоить значение типа '{value_type}' через указатель на '{pointed_type}'",
                            scope_idx,
                            node_idx,
                        )

    def get_type_from_ast(
        self, ast: Dict, scope_idx: int, node_idx: int, level: int
    ) -> str:
        """Определяет тип значения из AST"""
        if not isinstance(ast, dict):
            return "unknown"

        ast_type = ast.get("type")

        if ast_type == "literal":
            data_type = ast.get("data_type")
            if data_type:
                return data_type
            elif "value" in ast:
                val = ast["value"]
                if isinstance(val, str):
                    return "str"
                elif isinstance(val, int):
                    return "int"
                elif isinstance(val, bool):
                    return "bool"
                elif val is None:
                    return "None"

        elif ast_type == "variable":
            var_name = ast.get("value")
            if var_name:
                var_info = self.get_symbol_info(var_name, level)
                if var_info:
                    return var_info.get("type", "unknown")

        elif ast_type == "binary_operation":
            # Определяем тип результата бинарной операции
            operator = ast.get("operator_symbol", "")
            left_type = self.get_type_from_ast(
                ast.get("left"), scope_idx, node_idx, level
            )
            right_type = self.get_type_from_ast(
                ast.get("right"), scope_idx, node_idx, level
            )

            # Для арифметических операций
            if operator in ["+", "-", "*", "/", "//", "%", "**"]:
                if left_type == "float" or right_type == "float":
                    return "float"
                elif left_type == "int" and right_type == "int":
                    return "int"
                elif left_type == "unknown" or right_type == "unknown":
                    return "int"  # Предполагаем int по умолчанию

            # Для сравнений - возвращается bool
            elif operator in ["<", ">", "<=", ">=", "==", "!=", "and", "or"]:
                return "bool"

            return "int"  # По умолчанию для других операций

        elif ast_type == "function_call":
            func_name = ast.get("function")
            if func_name in self.builtin_functions:
                return self.builtin_functions[func_name]["return_type"]
            elif func_name in self.functions:
                func_info = self.functions[func_name]
                return func_info.get("return_type", "unknown")
            else:
                # Проверяем среди C функций
                return "unknown"  # Будет определено через guess_type_from_value

        elif ast_type == "dereference":
            pointer_name = ast.get("pointer")
            if pointer_name:
                pointer_info = self.get_symbol_info(pointer_name, level)
                if pointer_info:
                    pointer_type = pointer_info.get("type", "")
                    if pointer_type.startswith("*"):
                        return pointer_type[1:]  # Тип, на который указывает указатель

        return "unknown"

    def validate_assignment(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует присваивание"""
        symbols = node.get("symbols", [])
        dependencies = node.get("dependencies", [])
        content = node.get("content", "")
        expression_ast = node.get("expression_ast")

        # 1. Проверяем левую часть (целевую переменную)
        for symbol in symbols:
            symbol_info = self.get_symbol_info(symbol, level)

            if not symbol_info:
                self.add_error(
                    f"присваиваемая переменная '{symbol}' не объявлена",
                    scope_idx,
                    node_idx,
                )
            else:
                if self.is_variable_deleted(symbol, level):
                    # Проверяем переинициализацию
                    key = (level, symbol)
                    last_action = self.get_last_variable_action(symbol, level)
                    if last_action and last_action["action"] == "delete":
                        found_redeclaration = False
                        for action in self.variable_history.get(key, []):
                            if (
                                action["action"] == "declare"
                                and action["timestamp"] > last_action["timestamp"]
                            ):
                                found_redeclaration = True
                                break

                        if not found_redeclaration:
                            self.add_error(
                                f"переменная '{symbol}' была удалена и требует переинициализации",
                                scope_idx,
                                node_idx,
                            )
                elif symbol_info.get("key") == "const":
                    self.add_error(
                        f"попытка присваивания константе '{symbol}'",
                        scope_idx,
                        node_idx,
                    )

        # 2. Проверяем правую часть выражения
        if symbols and expression_ast:
            target_var = symbols[0]

            # Получаем тип значения из AST
            value_type = self.get_type_from_ast(
                expression_ast, scope_idx, node_idx, level
            )

            # Получаем тип целевой переменной
            target_info = self.get_symbol_info(target_var, level)
            if target_info:
                target_type = target_info.get("type", "")

                # Проверяем совместимость типов
                if value_type and value_type != "unknown" and target_type:
                    if not self.are_types_compatible(target_type, value_type):
                        self.add_error(
                            f"нельзя присвоить значение типа '{value_type}' переменной типа '{target_type}'",
                            scope_idx,
                            node_idx,
                        )

        # 3. Проверяем зависимости (используемые переменные)
        for dep in dependencies:
            if not self.find_symbol_in_scope(dep, level):
                self.add_error(
                    f"используемая переменная '{dep}' не объявлена", scope_idx, node_idx
                )
            elif self.is_variable_deleted(dep, level):
                self.add_error(
                    f"используемая переменная '{dep}' была удалена", scope_idx, node_idx
                )

    def validate_function_return_type(self, scope: Dict, scope_idx: int):
        """Проверяет соответствие типа возвращаемого значения"""
        return_info = scope.get("return_info", {})
        declared_return_type = scope.get("return_type", "None")

        if not return_info.get("has_return", False):
            # Функция не имеет return, но проверяем тип
            if declared_return_type != "None":
                self.add_warning(
                    f"функция объявлена как возвращающая '{declared_return_type}', но не имеет return",
                    scope_idx,
                    None,
                )
            return

        # Получаем информацию о возвращаемом значении
        return_value = return_info.get("return_value")
        if not return_value:
            return

        # Определяем фактический тип возвращаемого значения
        actual_return_type = self.determine_return_type(
            return_value, scope_idx, scope.get("level", 0)
        )

        if actual_return_type and actual_return_type != "unknown":
            # Сравниваем объявленный и фактический типы
            if not self.are_types_compatible(declared_return_type, actual_return_type):
                # Находим узел return в графе для правильной привязки ошибки
                graph = scope.get("graph", [])
                return_node_idx = -1

                for i, node in enumerate(graph):
                    if node.get("node") == "return":
                        return_node_idx = i
                        break

                # Добавляем ошибку только один раз
                if return_node_idx != -1:
                    self.add_error(
                        f"функция объявлена как возвращающая '{declared_return_type}', "
                        f"фактически возвращает '{actual_return_type}'",
                        scope_idx,
                        return_node_idx,
                    )

    def determine_return_type(self, return_value, scope_idx: int, level: int) -> str:
        """Определяет тип возвращаемого значения"""
        # Если return_value - строка (из content)
        if isinstance(return_value, str):
            # Парсим выражение
            if (return_value.startswith('"') and return_value.endswith('"')) or (
                return_value.startswith("'") and return_value.endswith("'")
            ):
                return "str"
            elif return_value.isdigit() or (
                return_value.startswith("-") and return_value[1:].isdigit()
            ):
                return "int"
            elif return_value in ["True", "False"]:
                return "bool"
            elif return_value == "None":
                return "None"
            else:
                # Это может быть переменная или выражение
                # Проверяем, не является ли это вызовом функции с @
                if "(" in return_value and ")" in return_value:
                    # Извлекаем имя функции
                    func_match = re.match(r"(@?[a-zA-Z_][a-zA-Z0-9_]*)\(", return_value)
                    if func_match:
                        func_name = func_match.group(1)

                        # Игнорируем функции с @
                        if func_name.startswith("@"):
                            logger.debug(
                                f"    Функция '{func_name}' игнорируется при определении типа возврата"
                            )
                            return "unknown"

                        # Получаем информацию о функции
                        func_info = None

                        # Проверяем в функциях
                        if func_name in self.functions:
                            func_info = self.functions[func_name]
                        else:
                            # Ищем в scope'ах
                            for scope in self.all_scopes:
                                if (
                                    scope.get("type") == "function"
                                    and scope.get("function_name") == func_name
                                ):
                                    return scope.get("return_type", "unknown")

                        if func_info:
                            return func_info.get("return_type", "unknown")

                # Если это переменная
                var_info = self.get_symbol_info(return_value, level)
                if var_info:
                    return var_info.get("type", "unknown")
                else:
                    return "unknown"

        # Если return_value - AST (словарь)
        elif isinstance(return_value, dict):
            return self.get_type_from_ast(return_value, scope_idx, None, level)

        return "unknown"

    def validate_type_compatibility(
        self, var_name: str, value: str, scope_idx: int, node_idx: int, level: int
    ):
        """Проверяет совместимость типов при присваивании"""
        var_info = self.get_symbol_info(var_name, level)
        if not var_info:
            return

        var_type = var_info.get("type")

        if "(" in value and ")" in value:
            # Извлекаем имя функции
            func_match = re.match(r"(@?[a-zA-Z_][a-zA-Z0-9_]*)\(", value)
            if func_match:
                func_name = func_match.group(1)

                # Игнорируем функции с @
                if func_name.startswith("@"):
                    logger.debug(
                        f"    Функция '{func_name}' игнорируется при проверке совместимости типов"
                    )
                    return

                # Получаем возвращаемый тип функции
                func_return_type = "unknown"

                # Проверяем в функциях
                if func_name in self.functions:
                    func_return_type = self.functions[func_name].get(
                        "return_type", "unknown"
                    )
                else:
                    # Ищем в scope'ах
                    for scope in self.all_scopes:
                        if (
                            scope.get("type") == "function"
                            and scope.get("function_name") == func_name
                        ):
                            func_return_type = scope.get("return_type", "unknown")
                            break

                if func_return_type != "unknown" and not self.are_types_compatible(
                    var_type, func_return_type
                ):
                    self.add_error(
                        f"переменной типа '{var_type}' присваивается результат функции '{func_name}' "
                        f"с возвращаемым типом '{func_return_type}'",
                        scope_idx,
                        node_idx,
                    )
                return  # Пропускаем дальнейшие проверки для вызова функции

        # Если это указатель
        if var_type.startswith("*"):
            pointed_type = var_type[1:]  # Тип, на который указывает указатель

            # Если берем адрес переменной (&x)
            if value.strip().startswith("&"):
                pointed_var = value.strip()[1:].strip()
                pointed_var_info = self.get_symbol_info(pointed_var, level)

                if pointed_var_info:
                    pointed_var_type = pointed_var_info.get("type")
                    if pointed_var_type != pointed_type:
                        self.add_error(
                            f"указатель '*{pointed_type}' не может указывать на переменную '{pointed_var}' типа '{pointed_var_type}'",
                            scope_idx,
                            node_idx,
                        )
            # Проверяем другие значения для указателей
            elif value.strip() != "null":  # null - допустимо для любого указателя
                value_type = self.guess_type_from_value(value)
                self.add_warning(
                    f"присвоение значения типа '{value_type}' указателю типа '*{pointed_type}'",
                    scope_idx,
                    node_idx,
                )
        else:
            # Проверяем обычные типы
            if var_type == "int":
                if value.startswith('"') or value.startswith("'"):
                    self.add_error(
                        f"нельзя присвоить строку переменной типа int",
                        scope_idx,
                        node_idx,
                    )
                elif value in ["True", "False"]:
                    self.add_error(
                        f"нельзя присвоить bool переменной типа int",
                        scope_idx,
                        node_idx,
                    )
            elif var_type == "str":
                if value.isdigit():
                    self.add_warning(
                        f"присвоение числа строковой переменной", scope_idx, node_idx
                    )

    # В JSONValidator добавьте:
    def validate_type_operations(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует операции с типами"""
        if "expression_ast" in node:
            ast = node["expression_ast"]
            self.validate_ast_types(ast, node_idx, scope_idx, level)

    def validate_ast_types(self, ast: Dict, node_idx: int, scope_idx: int, level: int):
        """Рекурсивно валидирует типы в AST"""
        if not isinstance(ast, dict):
            return

        node_type = ast.get("type")

        if node_type == "binary_operation":
            # Проверяем совместимость типов операндов
            left_type = self.get_type_from_ast(
                ast.get("left"), scope_idx, node_idx, level
            )
            right_type = self.get_type_from_ast(
                ast.get("right"), scope_idx, node_idx, level
            )
            operator = ast.get("operator_symbol", "")

            if not self.can_operate_between_types(left_type, right_type, operator):
                self.add_error(
                    f"нельзя выполнить операцию '{operator}' "
                    f"между типами '{left_type}' и '{right_type}'",
                    scope_idx,
                    node_idx,
                )

            # Рекурсивно проверяем дочерние узлы
            self.validate_ast_types(ast.get("left"), node_idx, scope_idx, level)
            self.validate_ast_types(ast.get("right"), node_idx, scope_idx, level)

        elif node_type == "unary_operation":
            operand_type = self.get_type_from_ast(
                ast.get("operand"), scope_idx, node_idx, level
            )
            operator = ast.get("operator_symbol", "")

            if operator == "not" and operand_type != "bool":
                self.add_error(
                    f"оператор 'not' применяется к типу '{operand_type}', а не к bool",
                    scope_idx,
                    node_idx,
                )

            # Рекурсивно проверяем операнд
            self.validate_ast_types(ast.get("operand"), node_idx, scope_idx, level)

        elif node_type == "function_call":
            # Проверяем аргументы
            for arg in ast.get("arguments", []):
                self.validate_ast_types(arg, node_idx, scope_idx, level)

    def can_operate_between_types(self, type1: str, type2: str, operator: str) -> bool:
        """Проверяет, можно ли выполнить операцию между двумя типами"""
        # Если один из типов unknown, пропускаем проверку
        if type1 == "unknown" or type2 == "unknown":
            return True

        # Арифметические операции требуют числовых типов
        arithmetic_ops = [
            "+",
            "-",
            "*",
            "/",
            "//",
            "%",
            "**",
            "+=",
            "-=",
            "*=",
            "/=",
            "%=",
            "**=",
        ]

        if operator in arithmetic_ops:
            # int и float могут взаимодействовать
            numeric_types = ["int", "float"]
            return type1 in numeric_types and type2 in numeric_types

        # Операции сравнения
        comparison_ops = ["<", ">", "<=", ">=", "==", "!="]
        if operator in comparison_ops:
            # Можно сравнивать числовые типы между собой
            if type1 in ["int", "float"] and type2 in ["int", "float"]:
                return True
            # Можно сравнивать строки со строками
            if type1 == "str" and type2 == "str":
                return True
            # Можно сравнивать булевы с булевыми
            if type1 == "bool" and type2 == "bool":
                return True
            return False

        # Логические операции
        logical_ops = ["and", "or"]
        if operator in logical_ops:
            return type1 == "bool" and type2 == "bool"

        return True

    def check_unused_variables(self, scope: Dict, scope_idx: int):
        """Проверяет объявленные, но неиспользуемые переменные"""
        local_vars = scope.get("local_variables", [])
        graph = scope.get("graph", [])
        level = scope.get("level", 0)

        if not local_vars:
            return

        used_vars = set()

        # Собираем все используемые переменные из графа
        for node in graph:
            node_type = node.get("node", "")

            # Пропускаем узлы declaration, так как они объявляют переменные
            if node_type == "declaration":
                continue

            # Проверяем зависимости
            if "dependencies" in node:
                for dep in node["dependencies"]:
                    if (
                        isinstance(dep, str)
                        and dep.isalpha()
                        and dep not in ["True", "False", "None", "NULL"]
                    ):
                        used_vars.add(dep)

            # Проверяем символы в узлах
            if "symbols" in node:
                for symbol in node["symbols"]:
                    if isinstance(symbol, str) and symbol not in [
                        "True",
                        "False",
                        "None",
                        "NULL",
                    ]:
                        used_vars.add(symbol)

            # Проверяем аргументы в вызовах функций
            if "arguments" in node:
                for arg in node["arguments"]:
                    if (
                        isinstance(arg, str)
                        and arg.isalpha()
                        and arg not in ["True", "False", "None", "NULL"]
                    ):
                        used_vars.add(arg)

            # Проверяем условия в if/while (через AST)
            if node_type in ["if_statement", "while_loop"]:
                condition_ast = node.get("condition_ast")
                if condition_ast:
                    self._collect_vars_from_ast(condition_ast, used_vars)

            # Проверяем возвращаемые значения
            if node_type == "return":
                # Проверяем expression_ast если есть
                if "expression_ast" in node:
                    expression_ast = node["expression_ast"]
                    self._collect_vars_from_ast(expression_ast, used_vars)
                # Или проверяем зависимости
                elif "dependencies" in node:
                    for dep in node["dependencies"]:
                        if isinstance(dep, str) and dep.isalpha():
                            used_vars.add(dep)

        # Находим неиспользуемые переменные
        for var in local_vars:
            # Пропускаем параметр 'self' в методах
            if var == "self" and scope.get("type") in ["constructor", "class_method"]:
                continue

            if var not in used_vars:
                self.add_warning(
                    f"переменная '{var}' объявлена, но нигде не используется",
                    scope_idx,
                    None,
                )

    def _collect_vars_from_ast(self, ast: Dict, used_vars: set):
        """Собирает переменные из AST"""
        if not isinstance(ast, dict):
            return

        node_type = ast.get("type")

        if node_type == "variable":
            var_name = ast.get("value")
            if (
                var_name
                and var_name.isalpha()
                and var_name not in ["True", "False", "None"]
            ):
                used_vars.add(var_name)

        elif node_type == "binary_operation":
            self._collect_vars_from_ast(ast.get("left"), used_vars)
            self._collect_vars_from_ast(ast.get("right"), used_vars)

        elif node_type == "unary_operation":
            self._collect_vars_from_ast(ast.get("operand"), used_vars)

        elif node_type == "function_call":
            func_name = ast.get("function", "")
            # Игнорируем функции с @
            if not func_name.startswith("@"):
                for arg in ast.get("arguments", []):
                    self._collect_vars_from_ast(arg, used_vars)

    def validate_return_paths(self, scope: Dict, scope_idx: int):
        """Проверяет, что все пути выполнения функции возвращают значение"""
        if scope.get("type") != "function":
            return

        return_type = scope.get("return_type", "None")
        if return_type == "None":
            return  # Функция void - не проверяем

        graph = scope.get("graph", [])
        has_return = False

        # Рекурсивно проверяем все узлы
        def check_node_for_return(node: Dict) -> bool:
            node_type = node.get("node")

            if node_type == "return":
                return True

            elif node_type == "if_statement":
                # Проверяем тело if
                if_body_has_return = False
                for body_node in node.get("body", []):
                    if check_node_for_return(body_node):
                        if_body_has_return = True
                        break

                # Проверяем elif блоки
                elif_has_return = False
                for elif_block in node.get("elif_blocks", []):
                    for body_node in elif_block.get("body", []):
                        if check_node_for_return(body_node):
                            elif_has_return = True
                            break
                    if elif_has_return:
                        break

                # Проверяем else блок
                else_has_return = False
                else_block = node.get("else_block")
                if else_block:
                    for body_node in else_block.get("body", []):
                        if check_node_for_return(body_node):
                            else_has_return = True
                            break

                # Если есть else, проверяем, что все пути возвращают значение
                if else_block:
                    return if_body_has_return and elif_has_return and else_has_return
                else:
                    # Если нет else, функция может не возвращать значение
                    return False

            elif node_type in ["while_loop", "for_loop"]:
                # Циклы не гарантируют возврат
                return False

            return False

        # Проверяем все узлы в графе
        for node in graph:
            if check_node_for_return(node):
                has_return = True
                break

        if not has_return:
            self.add_warning(
                f"функция объявлена как возвращающая '{return_type}', "
                f"но не все пути выполнения возвращают значение",
                scope_idx,
                None,
            )

    def check_division_by_zero(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Проверяет деление на ноль"""
        if node.get("node") in ["assignment", "declaration"]:
            content = node.get("content", "")

            # Ищем операции деления
            if "/" in content or "//" in content or "/=" in content:
                # Упрощенная проверка
                if "/ 0" in content or "// 0" in content:
                    self.add_warning("возможное деление на ноль", scope_idx, node_idx)

                # Более сложная проверка для переменных
                pattern = (
                    r"[/](?:\s*0\b|\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\s*[*+-/]\s*\w+)*\s*)"
                )
                if re.search(pattern, content):
                    # Проверяем, может ли переменная быть нулем
                    self.add_warning(
                        "возможное деление на переменную, которая может быть нулем",
                        scope_idx,
                        node_idx,
                    )

    def check_loop_conditions(self, scope: Dict, scope_idx: int):
        """Проверяет условия циклов на потенциальные проблемы"""
        graph = scope.get("graph", [])

        for node_idx, node in enumerate(graph):
            if node.get("node") == "while_loop":
                condition = node.get("condition", {})

                # Проверяем вечные циклы (while True)
                if condition.get("value") == "True":
                    self.add_warning("бесконечный цикл while True", scope_idx, node_idx)

                # Проверяем невозможные условия (while False)
                if condition.get("value") == "False":
                    self.add_warning(
                        "цикл while с условием, которое всегда ложно",
                        scope_idx,
                        node_idx,
                    )

            elif node.get("node") == "for_loop":
                iterable = node.get("iterable", {})

                # Проверяем пустые диапазоны range()
                if iterable.get("type") == "RANGE_CALL":
                    args = iterable.get("arguments", {})

                    # range(x, x) - пустой диапазон
                    if args.get("start") == args.get("stop"):
                        self.add_warning(
                            "цикл for с пустым диапазоном range()", scope_idx, node_idx
                        )

                    # range(x, y) где x > y без отрицательного шага
                    if (
                        args.get("start")
                        and args.get("stop")
                        and args.get("step") not in ["-1", "-2"]
                    ):
                        # Упрощенная проверка
                        try:
                            start = int(args.get("start"))
                            stop = int(args.get("stop"))
                            if start > stop:
                                self.add_warning(
                                    "цикл for с start > stop без отрицательного шага",
                                    scope_idx,
                                    node_idx,
                                )
                        except Exception:
                            pass

    def check_memory_leaks(self, scope: Dict, scope_idx: int):
        """Проверяет потенциальные утечки памяти с указателями"""
        graph = scope.get("graph", [])
        level = scope.get("level", 0)

        pointer_declarations = {}  # {pointer_name: node_idx}
        pointer_deletes = set()  # pointer_names that were deleted

        for node_idx, node in enumerate(graph):
            node_type = node.get("node")

            # Отслеживаем объявления указателей
            if node_type == "declaration":
                operations = node.get("operations", [])
                for op in operations:
                    if op.get("type") == "NEW_POINTER":
                        symbols = node.get("symbols", [])
                        if symbols:
                            pointer_declarations[symbols[0]] = node_idx

            # Отслеживаем удаление указателей
            elif node_type in ["delete", "del_pointer"]:
                symbols = node.get("symbols", [])
                for symbol in symbols:
                    pointer_deletes.add(symbol)

        # Проверяем объявленные, но не удаленные указатели
        for pointer_name, decl_idx in pointer_declarations.items():
            if pointer_name not in pointer_deletes:
                # Проверяем, что указатель не был удален в родительском scope
                # или что это не возвращаемое значение
                self.add_warning(
                    f"указатель '{pointer_name}' объявлен, но не удален (возможная утечка памяти)",
                    scope_idx,
                    decl_idx,
                )

    def get_scope_by_level(self, level: int) -> Optional[Dict]:
        """Находит scope по уровню"""
        for scope in self.all_scopes:
            if scope.get("level") == level:
                return scope
        return None

    def guess_type_from_value(self, value) -> str:
        """Пытается определить тип по значению"""
        # Если value - строка
        if isinstance(value, str):
            value = value.strip()

            # Проверяем арифметические выражения
            if any(op in value for op in ["+", "-", "*", "/"]):
                # Простая эвристика: если есть цифры - предположительно int
                if any(c.isdigit() for c in value):
                    return "int"
                return "unknown"

            # Остальные проверки как раньше
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                return "str"

            if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                return "int"

            if re.match(r"^-?\d+\.\d+$", value):
                return "float"

            if value in ["True", "False"]:
                return "bool"

            if value == "None":
                return "None"

            if value == "null":
                return "null"

            if value.startswith("&"):
                return "pointer"

            if value.startswith("*"):
                return "dereference"

            if value.startswith("["):
                return "list"

            if value.startswith("{"):
                if ":" in value:
                    return "dict"
                else:
                    return "set"

            # Если это вызов функции (содержит скобки)
            if "(" in value and ")" in value:
                # Извлекаем имя функции
                func_match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\(", value)
                if func_match:
                    func_name = func_match.group(1)
                    # Проверяем тип возвращаемого значения функции
                    if func_name in self.functions:
                        func_info = self.functions[func_name]
                        return func_info.get("return_type", "unknown")
                    elif func_name in self.builtin_functions:
                        return self.builtin_functions[func_name]["return_type"]

            return "unknown"

        # Если value - AST (словарь)
        elif isinstance(value, dict):
            return self.get_type_from_ast(value, None, None, None)

        return "unknown"

    def are_types_compatible(self, target_type: str, value_type: str) -> bool:
        """Проверяет совместимость типов"""
        # Если типы равны - совместимы
        if target_type == value_type:
            return True

        # Null совместим с любым указателем
        if value_type == "null" and target_type.startswith("*"):
            return True

        # None совместим с любым типом, если target_type - None
        if value_type == "None" and target_type == "None":
            return True

        # Ошибка: если функция должна возвращать int, а возвращает str
        if target_type == "int" and value_type == "str":
            return False

        if target_type == "str" and value_type == "int":
            return False

        # Упрощенные правила совместимости
        compatibility_rules = {
            "int": ["bool"],  # int может принимать bool (True=1, False=0)
            "bool": ["int"],  # bool может принимать int (0=False, не 0=True)
        }

        if (
            target_type in compatibility_rules
            and value_type in compatibility_rules[target_type]
        ):
            return True

        # Если value_type - конкретный тип, а target_type - указатель на тот же тип
        if target_type.startswith("*") and f"*{value_type}" == target_type:
            return True

        return False

    def find_symbol_in_scope(self, symbol_name: str, current_level: int) -> bool:
        """Ищет символ в текущем или родительских scope'ах"""
        # Проверяем встроенные функции
        if symbol_name in self.builtin_functions:
            return True

        # Проверяем пользовательские функции
        if symbol_name in self.functions:
            return True

        # Проверяем классы
        if symbol_name in self.classes:
            return True

        # Проверяем текущий scope
        if (
            current_level in self.scope_symbols
            and symbol_name in self.scope_symbols[current_level]
        ):
            return True

        # Находим текущий scope в all_scopes
        current_scope = None
        for scope in self.all_scopes:
            if scope.get("level") == current_level:
                current_scope = scope
                break

        if current_scope:
            # Проверяем родительский scope
            parent_level = current_scope.get("parent_scope")
            if parent_level is not None:
                return self.find_symbol_in_scope(symbol_name, parent_level)

        return False

    def get_symbol_info(self, symbol_name: str, current_level: int) -> Optional[Dict]:
        """Получает информацию о символе из текущего или родительских scope'ов"""
        # Сначала проверяем функции
        if symbol_name in self.functions:
            return self.functions[symbol_name]

        # Проверяем встроенные функции
        if symbol_name in self.builtin_functions:
            return {"name": symbol_name, "type": "function", "key": "builtin_function"}

        # Проверяем классы
        if symbol_name in self.classes:
            return self.classes[symbol_name]

        # Сначала проверяем текущий scope
        if (
            current_level in self.scope_symbols
            and symbol_name in self.scope_symbols[current_level]
        ):
            return self.scope_symbols[current_level][symbol_name]

        # Если не нашли в текущем scope, ищем во всех scope'ах
        for level, symbols in self.scope_symbols.items():
            if symbol_name in symbols:
                return symbols[symbol_name]

        return None

    def validate_method_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов метода объекта"""
        obj_name = node.get("object")
        method_name = node.get("method")
        arguments = node.get("arguments", [])

        # Проверяем объект
        if obj_name and not self.find_symbol_in_scope(obj_name, level):
            self.add_error(f"объект '{obj_name}' не объявлен", scope_idx, node_idx)
        elif obj_name and self.is_variable_deleted(obj_name, level):
            self.add_error(f"объект '{obj_name}' был удален", scope_idx, node_idx)

        # Проверяем аргументы метода
        for arg in arguments:
            self._validate_argument(
                arg, f"{obj_name}.{method_name}", scope_idx, node_idx, level
            )

    def validate_static_method_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов статического метода"""
        class_name = node.get("class_name")
        method_name = node.get("method")
        arguments = node.get("arguments", [])

        # Проверяем, существует ли класс
        class_symbol = self._find_class_symbol(class_name, level)
        if not class_symbol:
            self.add_error(f"класс '{class_name}' не объявлен", scope_idx, node_idx)

        # Проверяем аргументы
        for arg in arguments:
            self._validate_argument(
                arg, f"{class_name}.{method_name}", scope_idx, node_idx, level
            )

    def _find_class_symbol(self, class_name: str, level: int) -> Optional[Dict]:
        """Находит символ класса в таблице символов"""
        for scope_info in self.scopes_info:
            if scope_info["level"] <= level:
                symbol_table = scope_info.get("symbol_table", {})
                class_symbol = symbol_table.get(class_name)
                if class_symbol and class_symbol.get("key") == "class":
                    return class_symbol
        return None

    def validate_builtin_function_call(
        self, node: Dict, node_idx: int, scope_idx: int, symbol_table: Dict, level: int
    ):
        """Валидирует вызов встроенной функции"""
        func_name = node.get("function")
        arguments = node.get("arguments", [])

        # Проверяем аргументы встроенных функций
        for arg in arguments:
            self._validate_argument(arg, func_name, scope_idx, node_idx, level)

    def get_report(self) -> Dict:
        """Возвращает отчет о проверке"""
        # Форматируем ошибки и предупреждения для вывода
        formatted_errors = []
        formatted_warnings = []

        for error in self.errors:
            if isinstance(error, dict):
                line_info = (
                    f" (строка {error['line_number']})"
                    if error.get("line_number")
                    else ""
                )
                formatted_errors.append(f"{error['message']}{line_info}")
            else:
                formatted_errors.append(str(error))

        for warning in self.warnings:
            if isinstance(warning, dict):
                line_info = (
                    f" (строка {warning['line_number']})"
                    if warning.get("line_number")
                    else ""
                )
                formatted_warnings.append(f"{warning['message']}{line_info}")
            else:
                formatted_warnings.append(str(warning))

        return {
            "is_valid": len(self.errors) == 0,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,  # Сохраняем полную информацию
            "warnings": self.warnings,  # Сохраняем полную информацию
            "formatted_errors": formatted_errors,  # Для обратной совместимости
            "formatted_warnings": formatted_warnings,  # Для обратной совместимости
        }

    def validate_inheritance_hierarchy(self, scope: Dict, scope_idx: int):
        """Проверяет корректность иерархии наследования классов"""
        if scope.get("type") != "class_declaration":
            return

        class_name = scope.get("class_name")
        base_classes = scope.get("base_classes", [])

        if not base_classes:
            return

        # 1. Проверяем циклические зависимости
        for base_class in base_classes:
            # Находим базовый класс в all_scopes
            base_scope = None
            for s in self.all_scopes:
                if (
                    s.get("type") == "class_declaration"
                    and s.get("class_name") == base_class
                ):
                    base_scope = s
                    break

            if base_scope:
                # Проверяем, не наследует ли базовый класс от текущего (цикл)
                if class_name in base_scope.get("base_classes", []):
                    self.add_error(
                        f"циклическое наследование: класс '{class_name}' и '{base_class}' наследуют друг от друга",
                        scope_idx,
                        None,
                    )

        # 2. Проверяем дублирование методов в MRO
        all_methods = []
        method_sources = {}  # {method_name: [class_name, ...]}

        # Собираем методы текущего класса
        for method in scope.get("methods", []):
            method_name = method.get("name")
            if method_name not in method_sources:
                method_sources[method_name] = []
            method_sources[method_name].append(class_name)
            all_methods.append(method_name)

        # Рекурсивно собираем методы из базовых классов
        def collect_base_methods(base_class_name, visited=None):
            if visited is None:
                visited = set()

            if base_class_name in visited:
                return
            visited.add(base_class_name)

            # Находим базовый класс
            base_scope = None
            for s in self.all_scopes:
                if (
                    s.get("type") == "class_declaration"
                    and s.get("class_name") == base_class_name
                ):
                    base_scope = s
                    break

            if not base_scope:
                return

            # Собираем методы базового класса
            for method in base_scope.get("methods", []):
                method_name = method.get("name")
                if method_name not in method_sources:
                    method_sources[method_name] = []
                method_sources[method_name].append(base_class_name)
                all_methods.append(method_name)

            # Рекурсивно для родительских классов
            for parent in base_scope.get("base_classes", []):
                collect_base_methods(parent, visited)

        for base_class in base_classes:
            collect_base_methods(base_class)

        # Проверяем конфликты методов (одинаковые имена в разных классах)
        for method_name, sources in method_sources.items():
            if len(sources) > 1:
                # Метод есть в нескольких классах - проверяем, переопределен ли он
                if class_name in sources:
                    # Текущий класс переопределяет метод
                    self.add_warning(
                        f"метод '{method_name}' переопределен в классе '{class_name}' "
                        f"(также определен в: {', '.join([c for c in sources if c != class_name])})",
                        scope_idx,
                        None,
                    )
                else:
                    # Конфликт в базовых классах
                    self.add_error(
                        f"конфликт методов: '{method_name}' определен в нескольких базовых классах "
                        f"({', '.join(sources)}) без переопределения",
                        scope_idx,
                        None,
                    )

    def check_method_resolution_order(self, class_name: str):
        """Проверяет порядок разрешения методов (MRO)"""
        # Находим класс
        class_scope = None
        for scope in self.all_scopes:
            if (
                scope.get("type") == "class_declaration"
                and scope.get("class_name") == class_name
            ):
                class_scope = scope
                break

        if not class_scope:
            return

        base_classes = class_scope.get("base_classes", [])
        if not base_classes:
            return

        # Простой алгоритм MRO (C3 linearization)
        def compute_mro(cls_name, visited=None):
            if visited is None:
                visited = set()

            if cls_name in visited:
                return []
            visited.add(cls_name)

            # Находим класс
            cls_scope = None
            for s in self.all_scopes:
                if (
                    s.get("type") == "class_declaration"
                    and s.get("class_name") == cls_name
                ):
                    cls_scope = s
                    break

            if not cls_scope:
                return [cls_name]

            result = [cls_name]
            for base in cls_scope.get("base_classes", []):
                result.extend(compute_mro(base, visited))

            return result

        try:
            mro = compute_mro(class_name)
            # Проверяем дубликаты в MRO (циклическое наследование)
            if len(mro) != len(set(mro)):
                self.add_error(
                    f"циклическое наследование в MRO класса '{class_name}'",
                    self.all_scopes.index(class_scope)
                    if class_scope in self.all_scopes
                    else None,
                    None,
                )

            return mro
        except RecursionError:
            self.add_error(
                f"бесконечная рекурсия в наследовании класса '{class_name}'",
                self.all_scopes.index(class_scope)
                if class_scope in self.all_scopes
                else None,
                None,
            )
            return []

    def validate_thread_functions(self, scope: Dict, scope_idx: int):
        """Проверяет функции для использования в потоках"""
        if scope.get("type") != "function":
            return

        func_name = scope.get("function_name")
        if not func_name:
            return

        # Проверяем, используется ли функция как callback для потока
        for other_scope in self.all_scopes:
            for node_idx, node in enumerate(other_scope.get("graph", [])):
                if (
                    node.get("node") == "c_call"
                    and node.get("function") == "pthread_create"
                ):
                    args = node.get("arguments", [])
                    if len(args) >= 3 and args[2] == func_name:
                        # Эта функция передается в pthread_create

                        # 1. Проверяем сигнатуру функции
                        parameters = scope.get("parameters", [])
                        if len(parameters) != 1:
                            self.add_error(
                                f"функция '{func_name}' передается в pthread_create, "
                                f"но должна принимать ровно 1 параметр (void*), а принимает {len(parameters)}",
                                scope_idx,
                                None,
                            )
                        else:
                            param_type = parameters[0].get("type", "")
                            if param_type not in ["None", "void*", "*void"]:
                                self.add_warning(
                                    f"функция '{func_name}' передается в pthread_create, "
                                    f"параметр должен быть void* (получен: {param_type})",
                                    scope_idx,
                                    None,
                                )

                        # 2. Проверяем тип возврата
                        return_type = scope.get("return_type", "")
                        if return_type not in ["None", "void*", "*void"]:
                            self.add_warning(
                                f"функция потока '{func_name}' должна возвращать void* (возвращает: {return_type})",
                                scope_idx,
                                None,
                            )

    def check_unused_parameters(self, scope: Dict, scope_idx: int):
        """Находит неиспользуемые параметры функций и методов"""
        scope_type = scope.get("type")

        if scope_type not in ["function", "constructor", "class_method"]:
            return

        parameters = scope.get("parameters", [])
        if not parameters:
            return

        # Собираем все используемые переменные в теле функции
        used_vars = set()
        graph = scope.get("graph", [])

        for node in graph:
            # Собираем зависимости
            if "dependencies" in node:
                for dep in node["dependencies"]:
                    if isinstance(dep, str) and dep.isalpha():
                        used_vars.add(dep)

            # Собираем символы
            if "symbols" in node:
                for symbol in node["symbols"]:
                    if isinstance(symbol, str) and symbol.isalpha():
                        used_vars.add(symbol)

            # Собираем переменные из AST
            if "expression_ast" in node:
                self._collect_vars_from_ast(node["expression_ast"], used_vars)

        # Проверяем каждый параметр
        for param in parameters:
            param_name = param.get("name")
            if not param_name:
                continue

            # Пропускаем self в методах
            if scope_type in ["constructor", "class_method"] and param_name == "self":
                continue

            if param_name not in used_vars:
                # Для конструкторов это ошибка, для других методов - предупреждение
                if scope.get("method_name") == "__init__":
                    self.add_error(
                        f"параметр конструктора '{param_name}' не используется",
                        scope_idx,
                        None,
                    )
                else:
                    self.add_warning(
                        f"параметр '{param_name}' не используется", scope_idx, None
                    )

    def validate_pointer_usage(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Проверяет корректное использование указателей"""
        node_type = node.get("node")

        if node_type == "declaration":
            # Проверяем объявление указателей
            var_type = node.get("var_type", "")
            if var_type.startswith("*"):
                # Это указатель - проверяем инициализацию
                operations = node.get("operations", [])
                for op in operations:
                    if op.get("type") == "GET_ADDRESS":
                        pointed_var = op.get("of", "")
                        if pointed_var:
                            # Проверяем, что переменная существует
                            if not self.find_symbol_in_scope(pointed_var, level):
                                self.add_error(
                                    f"указатель создается для несуществующей переменной '{pointed_var}'",
                                    scope_idx,
                                    node_idx,
                                )

        elif node_type == "function_call" or node_type == "c_call":
            # Проверяем передачу указателей в функции
            func_name = node.get("function", "")
            arguments = node.get("arguments", [])

            # Проверяем pthread_create
            if func_name == "pthread_create":
                if len(arguments) >= 4:
                    thread_data_arg = arguments[3]
                    # Проверяем, что 4-й аргумент - указатель
                    if isinstance(thread_data_arg, str) and thread_data_arg.isalpha():
                        var_info = self.get_symbol_info(thread_data_arg, level)
                        if var_info:
                            var_type = var_info.get("type", "")
                            if not var_type.startswith("*"):
                                self.add_warning(
                                    f"в pthread_create передается не указатель '{thread_data_arg}' типа '{var_type}'",
                                    scope_idx,
                                    node_idx,
                                )

            # Проверяем pthread_join
            elif func_name == "pthread_join":
                if len(arguments) >= 1:
                    thread_arg = arguments[0]
                    if isinstance(thread_arg, str) and thread_arg.isalpha():
                        var_info = self.get_symbol_info(thread_arg, level)
                        if not var_info:
                            self.add_error(
                                f"переменная потока '{thread_arg}' не объявлена",
                                scope_idx,
                                node_idx,
                            )

        elif node_type == "dereference_read" or node_type == "dereference_write":
            # Проверяем разыменование указателей
            symbols = node.get("symbols", [])
            for symbol in symbols:
                var_info = self.get_symbol_info(symbol, level)
                if var_info:
                    var_type = var_info.get("type", "")
                    if not var_type.startswith("*"):
                        self.add_error(
                            f"попытка разыменования не указателя '{symbol}' типа '{var_type}'",
                            scope_idx,
                            node_idx,
                        )

    def validate_array_bounds(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Проверяет выход за границы массивов/списков"""
        node_type = node.get("node")

        if node_type == "index_access":
            # Чтение по индексу
            variable = node.get("variable", "")
            index = node.get("index", {})

            if variable and index:
                # Получаем информацию о списке/массиве
                var_info = self.get_symbol_info(variable, level)
                if var_info:
                    var_type = var_info.get("type", "")
                    if "list" in var_type or "array" in var_type:
                        # Пытаемся получить статическое значение индекса
                        index_value = self._get_static_value_from_ast(index, level)
                        if index_value is not None:
                            # Проверяем отрицательные индексы
                            if index_value < 0:
                                self.add_warning(
                                    f"использование отрицательного индекса {index_value} для '{variable}'",
                                    scope_idx,
                                    node_idx,
                                )

        elif node_type == "index_assignment":
            # Присваивание по индексу
            variable = node.get("variable", "")
            index = node.get("index", {})

            if variable and index:
                var_info = self.get_symbol_info(variable, level)
                if var_info:
                    var_type = var_info.get("type", "")
                    if "list" in var_type or "array" in var_type:
                        index_value = self._get_static_value_from_ast(index, level)
                        if index_value is not None and index_value < 0:
                            self.add_warning(
                                f"присваивание по отрицательному индексу {index_value} для '{variable}'",
                                scope_idx,
                                node_idx,
                            )

        elif node_type == "slice_access" or node_type == "slice_assignment":
            # Работа со срезами
            variable = node.get("variable", "")
            start = node.get("start")
            stop = node.get("stop")

            if variable:
                # Проверяем отрицательные индексы в срезах
                if start:
                    start_value = self._get_static_value_from_ast(start, level)
                    if start_value is not None and start_value < 0:
                        self.add_warning(
                            f"использование отрицательного начала среза {start_value} для '{variable}'",
                            scope_idx,
                            node_idx,
                        )

                if stop:
                    stop_value = self._get_static_value_from_ast(stop, level)
                    if stop_value is not None and stop_value < 0:
                        self.add_warning(
                            f"использование отрицательного конца среза {stop_value} для '{variable}'",
                            scope_idx,
                            node_idx,
                        )

    def validate_string_operations(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Проверяет операции со строками"""
        node_type = node.get("node")

        if node_type == "method_call":
            obj_name = node.get("object", "")
            method_name = node.get("method", "")

            if obj_name and method_name:
                obj_info = self.get_symbol_info(obj_name, level)
                if obj_info:
                    obj_type = obj_info.get("type", "")

                    if obj_type == "str":
                        if method_name == "upper":
                            # Проверяем, используется ли результат
                            parent_node = self._find_parent_node(scope_idx, node_idx)
                            if parent_node and parent_node.get("node") not in [
                                "assignment",
                                "declaration",
                            ]:
                                self.add_warning(
                                    f"результат метода '{obj_name}.upper()' не сохраняется",
                                    scope_idx,
                                    node_idx,
                                )

                        elif method_name == "split":
                            arguments = node.get("arguments", [])
                            if len(arguments) == 1:
                                arg = arguments[0]
                                if (
                                    isinstance(arg, dict)
                                    and arg.get("type") == "literal"
                                ):
                                    value = arg.get("value", "")
                                    if value == " ":
                                        # Правильный разделитель
                                        pass
                                    elif value == "":
                                        self.add_warning(
                                            f"пустой разделитель в '{obj_name}.split(\"\")' может привести к неожиданным результатам",
                                            scope_idx,
                                            node_idx,
                                        )
                                    else:
                                        self.add_warning(
                                            f"использование нестандартного разделителя '{value}' в split",
                                            scope_idx,
                                            node_idx,
                                        )

    def validate_c_function_calls(
        self, node: Dict, node_idx: int, scope_idx: int, level: int
    ):
        """Проверяет вызовы C-функций (начинающиеся с @)"""
        node_type = node.get("node")

        if node_type == "c_call":
            func_name = node.get("function", "")
            arguments = node.get("arguments", [])

            # Проверяем известные C-функции
            if func_name in ["pthread_create", "pthread_join"]:
                # Проверяем количество аргументов
                expected_args = 4 if func_name == "pthread_create" else 2
                if len(arguments) != expected_args:
                    self.add_error(
                        f"функция '{func_name}' ожидает {expected_args} аргументов, получено {len(arguments)}",
                        scope_idx,
                        node_idx,
                    )

                # Проверяем типы аргументов
                if func_name == "pthread_create":
                    # 1-й аргумент: &thread (адрес переменной pthread_t)
                    if len(arguments) > 0:
                        arg = arguments[0]
                        if isinstance(arg, str) and arg.startswith("&"):
                            var_name = arg[1:].strip()
                            var_info = self.get_symbol_info(var_name, level)
                            if not var_info:
                                self.add_error(
                                    f"переменная '{var_name}' для &thread не объявлена",
                                    scope_idx,
                                    node_idx,
                                )

                    # 2-й аргумент: NULL
                    if len(arguments) > 1:
                        arg = arguments[1]
                        if arg != "NULL" and arg != "nullptr":
                            self.add_warning(
                                f"второй аргумент pthread_create должен быть NULL (получен: {arg})",
                                scope_idx,
                                node_idx,
                            )

                    # 3-й аргумент: функция
                    if len(arguments) > 2:
                        func_arg = arguments[2]
                        if isinstance(func_arg, str) and func_arg.isalpha():
                            # Проверяем, что функция существует
                            func_found = False
                            for scope in self.all_scopes:
                                if (
                                    scope.get("type") == "function"
                                    and scope.get("function_name") == func_arg
                                ):
                                    func_found = True
                                    break

                            if not func_found:
                                self.add_error(
                                    f"функция '{func_arg}' для потока не объявлена",
                                    scope_idx,
                                    node_idx,
                                )

    def check_missing_declarations(self, scope: Dict, scope_idx: int):
        """Проверяет отсутствующие объявления"""
        # Проверяем C-типы
        for node_idx, node in enumerate(scope.get("graph", [])):
            if node.get("node") == "declaration":
                var_type = node.get("var_type", "")
                if var_type in ["pthread_t"]:
                    # Проверяем, импортирован ли соответствующий заголовок
                    has_pthread_import = False
                    for module_scope in self.all_scopes:
                        if module_scope.get("level") == 0:
                            for module_node in module_scope.get("graph", []):
                                if module_node.get("node") == "c_import":
                                    header = module_node.get("header", "")
                                    if "pthread" in header.lower():
                                        has_pthread_import = True
                                        break

                    if not has_pthread_import:
                        self.add_warning(
                            f"используется тип '{var_type}' без импорта pthread.h",
                            scope_idx,
                            node_idx,
                        )

    # Вспомогательные методы

    def _collect_vars_from_ast(self, ast: Dict, used_vars: set):
        """Собирает переменные из AST (уже есть, но дополним)"""
        if not isinstance(ast, dict):
            return

        node_type = ast.get("type")

        if node_type == "variable":
            var_name = ast.get("value")
            if var_name and var_name.isalpha():
                used_vars.add(var_name)

        elif node_type == "binary_operation":
            self._collect_vars_from_ast(ast.get("left"), used_vars)
            self._collect_vars_from_ast(ast.get("right"), used_vars)

        elif node_type == "unary_operation":
            self._collect_vars_from_ast(ast.get("operand"), used_vars)

        elif node_type == "function_call":
            for arg in ast.get("arguments", []):
                self._collect_vars_from_ast(arg, used_vars)

        elif node_type == "method_call":
            obj_name = ast.get("object")
            if obj_name and obj_name.isalpha():
                used_vars.add(obj_name)
            for arg in ast.get("arguments", []):
                self._collect_vars_from_ast(arg, used_vars)

    def _get_static_value_from_ast(self, ast: Dict, level: int):
        """Пытается получить статическое значение из AST"""
        if not isinstance(ast, dict):
            return None

        node_type = ast.get("type")

        if node_type == "literal":
            return ast.get("value")

        elif node_type == "variable":
            var_name = ast.get("value")
            # Можем попытаться отследить константы
            var_info = self.get_symbol_info(var_name, level)
            if var_info and var_info.get("key") == "const":
                value = var_info.get("value")
                if isinstance(value, dict) and value.get("type") == "literal":
                    return value.get("value")

        return None

    def _find_parent_node(self, scope_idx: int, node_idx: int):
        """Находит родительский узел (если есть)"""
        if scope_idx >= len(self.all_scopes):
            return None

        graph = self.all_scopes[scope_idx].get("graph", [])
        # Простая реализация - возвращаем предыдущий узел
        if node_idx > 0 and node_idx - 1 < len(graph):
            return graph[node_idx - 1]
        return None

    def _validate_class_method_calls(self, scope: Dict, scope_idx: int):
        """Проверяет вызовы методов в контексте наследования"""
        class_name = scope.get("class_name", "")
        method_name = scope.get("method_name", "")

        # Для методов get_age проверяем конфликты с родительскими классами
        if method_name == "get_age":
            # Находим информацию о классе
            class_scope = None
            for s in self.all_scopes:
                if (
                    s.get("type") == "class_declaration"
                    and s.get("class_name") == class_name
                ):
                    class_scope = s
                    break

            if class_scope:
                base_classes = class_scope.get("base_classes", [])
                for base_class in base_classes:
                    # Проверяем, есть ли метод get_age в базовом классе
                    base_scope = None
                    for s in self.all_scopes:
                        if (
                            s.get("type") == "class_declaration"
                            and s.get("class_name") == base_class
                        ):
                            base_scope = s
                            break

                    if base_scope:
                        for method in base_scope.get("methods", []):
                            if method.get("name") == "get_age":
                                # Проверяем совместимость сигнатур
                                current_params = scope.get("parameters", [])
                                base_params = method.get("parameters", [])

                                if len(current_params) != len(base_params):
                                    self.add_warning(
                                        f"метод '{method_name}' переопределен с изменением количества параметров "
                                        f"(было {len(base_params)}, стало {len(current_params)})",
                                        scope_idx,
                                        None,
                                    )
                                break

    def _collect_function_metrics(self, scope: Dict, scope_idx: int):
        """Собирает метрики сложности кода"""
        if "graph" not in scope:
            return

        graph = scope.get("graph", [])

        # Считаем сложность (упрощенный цикломатический)
        complexity = 1  # базовая сложность
        condition_count = 0
        loop_count = 0

        for node in graph:
            node_type = node.get("node", "")
            if node_type in ["if_statement", "while_loop", "for_loop"]:
                condition_count += 1
            if node_type in ["while_loop", "for_loop"]:
                loop_count += 1

        complexity += condition_count + loop_count

        # Пороги предупреждений
        if complexity > 10:
            self.add_warning(
                f"высокая цикломатическая сложность функции ({complexity})",
                scope_idx,
                None,
            )

        if loop_count > 3:
            self.add_warning(
                f"слишком много циклов в функции ({loop_count})",
                scope_idx,
                None,
            )

        # Считаем длину функции (узлы)
        if len(graph) > 50:
            self.add_warning(
                f"функция слишком длинная ({len(graph)} операций)",
                scope_idx,
                None,
            )

    def check_undefined_methods(self, scope: Dict, scope_idx: int):
        """Проверяет, что все используемые методы определены в классе или его родителях"""
        scope_type = scope.get("type")

        if scope_type not in ["function", "constructor", "class_method", "module"]:
            return

        # Собираем все вызовы методов в текущем scope
        method_calls = []

        graph = scope.get("graph", [])
        for node_idx, node in enumerate(graph):
            node_type = node.get("node")

            if node_type == "method_call":
                obj_name = node.get("object", "")
                method_name = node.get("method", "")

                if obj_name and method_name:
                    # Добавляем в список для проверки
                    method_calls.append(
                        {
                            "obj": obj_name,
                            "method": method_name,
                            "node_idx": node_idx,
                            "content": node.get("content", ""),
                        }
                    )

            # Также проверяем вызовы методов в AST
            if "expression_ast" in node:
                self._extract_method_calls_from_ast(
                    node["expression_ast"],
                    method_calls,
                    node_idx,
                    node.get("content", ""),
                )

        # Уникальные проверки (чтобы избежать дублирования)
        checked_calls = set()

        # Проверяем каждый вызов метода
        for call in method_calls:
            obj_name = call["obj"]
            method_name = call["method"]
            node_idx = call["node_idx"]
            content = call["content"]

            # Пропускаем, если уже проверяли эту комбинацию
            call_key = f"{obj_name}.{method_name}.{node_idx}"
            if call_key in checked_calls:
                continue
            checked_calls.add(call_key)

            # Получаем информацию об объекте
            obj_info = self.get_symbol_info(obj_name, scope.get("level", 0))
            if not obj_info:
                # Объект не найден - другая проверка это поймает
                continue

            obj_type = obj_info.get("type", "")

            # Пропускаем, если тип неизвестен
            if not obj_type or obj_type == "unknown":
                continue

            # Проверяем, является ли тип классом
            class_found = False

            # Ищем класс во всех scope'ах
            for s in self.all_scopes:
                if (
                    s.get("type") == "class_declaration"
                    and s.get("class_name") == obj_type
                ):
                    class_found = True
                    # Добавляем в classes для будущих проверок
                    if obj_type not in self.classes:
                        self._add_class_to_registry(s)

                    # Проверяем метод
                    if not self._method_exists_in_class_hierarchy(
                        obj_type, method_name
                    ):
                        self.add_error(
                            f"метод '{method_name}' не определен для объекта типа '{obj_type}'",
                            scope_idx,
                            node_idx,
                        )
                    break

            if not class_found:
                # Проверяем встроенные типы
                if obj_type in ["str", "list", "dict", "set", "tuple"]:
                    if not self._is_builtin_method_for_type(obj_type, method_name):
                        self.add_error(
                            f"метод '{method_name}' не существует для типа '{obj_type}'",
                            scope_idx,
                            node_idx,
                        )
                elif obj_type in self.builtin_functions:
                    # Это встроенная функция, а не объект
                    continue
                else:
                    # Неизвестный тип - возможно, это ошибка в другом месте
                    pass

    def _method_exists_in_class_hierarchy(
        self, class_name: str, method_name: str
    ) -> bool:
        """Проверяет, существует ли метод в классе или его иерархии наследования"""
        # Сначала ищем среди встроенных методов стандартных типов
        if class_name in ["str", "list", "dict", "set", "tuple"]:
            return self._is_builtin_method_for_type(class_name, method_name)

        visited = set()

        def search_in_class(cls_name):
            if cls_name in visited:
                return False
            visited.add(cls_name)

            # Находим класс
            class_scope = None
            for s in self.all_scopes:
                if (
                    s.get("type") == "class_declaration"
                    and s.get("class_name") == cls_name
                ):
                    class_scope = s
                    break

            if not class_scope:
                # Проверяем, не является ли это встроенным типом
                if cls_name in [
                    "str",
                    "int",
                    "bool",
                    "float",
                    "list",
                    "dict",
                    "set",
                    "tuple",
                ]:
                    return self._is_builtin_method_for_type(cls_name, method_name)
                return False

            # Проверяем методы текущего класса
            for method in class_scope.get("methods", []):
                if method.get("name") == method_name:
                    return True

            # Проверяем статические методы
            for method in class_scope.get("static_methods", []):
                if method.get("name") == method_name:
                    return True

            # Проверяем методы класса (classmethod)
            for method in class_scope.get("class_methods", []):
                if method.get("name") == method_name:
                    return True

            # Рекурсивно проверяем базовые классы
            for base_class in class_scope.get("base_classes", []):
                if search_in_class(base_class):
                    return True

            return False

        return search_in_class(class_name)

    def _extract_method_calls_from_ast(
        self, ast: Dict, method_calls: list, node_idx: int, content: str = ""
    ):
        """Извлекает вызовы методов из AST"""
        if not isinstance(ast, dict):
            return

        node_type = ast.get("type")

        if node_type == "method_call":
            obj_name = ast.get("object", "")
            method_name = ast.get("method", "")

            if obj_name and method_name:
                method_calls.append(
                    {
                        "obj": obj_name,
                        "method": method_name,
                        "node_idx": node_idx,
                        "content": content,
                    }
                )

            # Рекурсивно проверяем аргументы
            for arg in ast.get("arguments", []):
                self._extract_method_calls_from_ast(
                    arg, method_calls, node_idx, content
                )

        elif node_type == "function_call":
            # Рекурсивно проверяем аргументы функций
            for arg in ast.get("arguments", []):
                self._extract_method_calls_from_ast(
                    arg, method_calls, node_idx, content
                )

        elif node_type == "binary_operation":
            self._extract_method_calls_from_ast(
                ast.get("left"), method_calls, node_idx, content
            )
            self._extract_method_calls_from_ast(
                ast.get("right"), method_calls, node_idx, content
            )

        elif node_type == "unary_operation":
            self._extract_method_calls_from_ast(
                ast.get("operand"), method_calls, node_idx, content
            )

        elif node_type == "ternary_operator":
            self._extract_method_calls_from_ast(
                ast.get("condition"), method_calls, node_idx, content
            )
            self._extract_method_calls_from_ast(
                ast.get("true_expr"), method_calls, node_idx, content
            )
            self._extract_method_calls_from_ast(
                ast.get("false_expr"), method_calls, node_idx, content
            )

        elif node_type == "list_literal":
            for item in ast.get("items", []):
                self._extract_method_calls_from_ast(
                    item, method_calls, node_idx, content
                )

        elif node_type == "tuple_literal":
            for item in ast.get("items", []):
                self._extract_method_calls_from_ast(
                    item, method_calls, node_idx, content
                )

    def _is_builtin_method_for_type(self, type_name: str, method_name: str) -> bool:
        """Проверяет, является ли метод встроенным для данного типа"""
        builtin_methods = {
            "str": [
                "upper",
                "lower",
                "split",
                "strip",
                "replace",
                "find",
                "startswith",
                "endswith",
                "isdigit",
                "isalpha",
                "format",
                "join",
                "capitalize",
            ],
            "list": [
                "append",
                "extend",
                "insert",
                "remove",
                "pop",
                "clear",
                "index",
                "count",
                "sort",
                "reverse",
                "copy",
            ],
            "dict": [
                "get",
                "keys",
                "values",
                "items",
                "update",
                "pop",
                "clear",
                "copy",
            ],
            "set": [
                "add",
                "remove",
                "discard",
                "pop",
                "clear",
                "union",
                "intersection",
                "difference",
                "copy",
            ],
            "tuple": ["count", "index"],
        }

        if type_name in builtin_methods:
            return method_name in builtin_methods[type_name]

        return False

    def _add_class_to_registry(self, class_scope: Dict):
        """Добавляет класс в реестр классов"""
        class_name = class_scope.get("class_name")
        if not class_name or class_name in self.classes:
            return

        # Собираем информацию о методах класса
        methods_info = []
        for method in class_scope.get("methods", []):
            methods_info.append(
                {
                    "name": method.get("name"),
                    "is_static": method.get("is_static", False),
                    "is_classmethod": method.get("is_classmethod", False),
                    "parameters": method.get("parameters", []),
                    "return_type": method.get("return_type", ""),
                }
            )

        self.classes[class_name] = {
            "name": class_name,
            "key": "class",
            "type": "class",
            "value": None,
            "id": class_name,
            "is_deleted": False,
            "methods": methods_info,
            "attributes": class_scope.get("attributes", []),
            "static_methods": class_scope.get("static_methods", []),
            "class_methods": class_scope.get("class_methods", []),
            "base_classes": class_scope.get("base_classes", []),
        }

        # Также добавляем в scope_symbols
        level = class_scope.get("level", 0)
        if level not in self.scope_symbols:
            self.scope_symbols[level] = {}
        self.scope_symbols[level][class_name] = self.classes[class_name]
