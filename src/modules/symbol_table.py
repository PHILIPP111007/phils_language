class SymbolTable:
    def __init__(self):
        self.symbols = {}
        self.deleted_symbols = set()  # Множество удаленных символов
        self.class_hierarchy = {}  # Для хранения иерархии наследования

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

    def add_class(self, name, base_classes=None, **kwargs):
        """Добавляет класс в таблицу символов"""
        symbol_id = name

        symbol_data = {
            "name": name,
            "key": "class",
            "type": "class",
            "value": None,
            "id": symbol_id,
            "is_deleted": False,
            "methods": [],  # Список методов
            "attributes": [],  # Список атрибутов
            "static_methods": [],  # Статические методы
            "class_methods": [],  # Методы класса
            "base_classes": base_classes or [],  # Родительские классы
            "access_modifiers": {},  # Модификаторы доступа
        }

        # Добавляем дополнительные атрибуты
        for key, val in kwargs.items():
            if val is not None:
                symbol_data[key] = val

        self.symbols[symbol_id] = symbol_data

        # Добавляем в иерархию наследования
        if base_classes:
            self.class_hierarchy[name] = base_classes

        return symbol_id

    def add_class_method(
        self, class_name, method_name, is_static=False, is_classmethod=False, **kwargs
    ):
        """Добавляет метод в класс"""
        class_symbol = self.get_symbol(class_name)
        if not class_symbol:
            return False

        method_data = {
            "name": method_name,
            "is_static": is_static,
            "is_classmethod": is_classmethod,
            "parameters": kwargs.get("parameters", []),
            "return_type": kwargs.get("return_type", "None"),
            "access": kwargs.get("access", "public"),
        }

        # Добавляем в соответствующий список
        if is_static:
            class_symbol["static_methods"].append(method_data)
        elif is_classmethod:
            class_symbol["class_methods"].append(method_data)
        else:
            class_symbol["methods"].append(method_data)

        return True

    def add_class_attribute(
        self, class_name, attribute_name, attribute_type, access="public"
    ):
        """Добавляет атрибут в класс"""
        class_symbol = self.get_symbol(class_name)
        if not class_symbol:
            return False

        attribute_data = {
            "name": attribute_name,
            "type": attribute_type,
            "access": access,
        }

        class_symbol["attributes"].append(attribute_data)
        return True

    def get_class_method(self, class_name, method_name):
        """Получает метод класса (ищет в родительских классах)"""
        class_symbol = self.get_symbol(class_name)
        if not class_symbol:
            return None

        # Ищем в методах текущего класса
        for method in class_symbol["methods"]:
            if method["name"] == method_name:
                return method

        # Ищем в статических методах
        for method in class_symbol["static_methods"]:
            if method["name"] == method_name:
                return method

        # Ищем в методах класса
        for method in class_symbol["class_methods"]:
            if method["name"] == method_name:
                return method

        # Ищем в родительских классах
        for base_class in class_symbol["base_classes"]:
            method = self.get_class_method(base_class, method_name)
            if method:
                return method

        return None

    def is_subclass(self, subclass, superclass):
        """Проверяет, является ли subclass наследником superclass"""
        if subclass == superclass:
            return True

        class_symbol = self.get_symbol(subclass)
        if not class_symbol:
            return False

        # Проверяем прямые родительские классы
        if superclass in class_symbol["base_classes"]:
            return True

        # Рекурсивно проверяем родительские классы
        for base in class_symbol["base_classes"]:
            if self.is_subclass(base, superclass):
                return True

        return False
