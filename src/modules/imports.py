import os
import re


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
