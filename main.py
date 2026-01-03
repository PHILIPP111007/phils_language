import json
from src.parser import Parser
from src.debug import JSONValidator
from src.compiler import CCodeGenerator


def main(base_path: str, json_path: str, output_path: str) -> int:
    with open("/Users/phil/GitHub/phils_language/data/main.p", "r") as file:
        code = file.read()

    # PARSER
    parser = Parser(base_path=base_path)
    result = parser.parse_code(code)

    json_output = json.dumps(result, indent=2, default=str)
    with open(json_path, "w") as f:
        f.write(json_output)

    # DEBUGGER

    with open(json_path, "r") as file:
        data = json.load(file)

    validator = JSONValidator()
    result = validator.validate(data)

    print("\nРезультат валидации:")
    print(f"Валидный: {result['is_valid']}")
    print(f"Ошибок: {result['error_count']}")
    print(f"Предупреждений: {result['warning_count']}")

    if result["errors"]:
        print("\nОшибки:")
        for error in result["errors"]:
            print("Строка", error["line_number"], ": ", error["message"])

    if result["warnings"]:
        print("\nПредупреждения:")
        for warning in result["warnings"]:
            print("Строка", warning["line_number"], ": ", warning["message"])

    if not result["errors"]:
        print("\nOK")

    if result["errors"]:
        return 1

    generator = CCodeGenerator()
    c_code = generator.generate_from_json(data)

    with open(output_path, "w") as f:
        f.write(c_code)

    return 0


if __name__ == "__main__":
    base_path = "/Users/phil/GitHub/phils_language/data/"
    json_path = "/Users/phil/GitHub/phils_language/data/parsed_code.json"
    output_path = "/Users/phil/GitHub/phils_language/data/generated_code.c"

    main(base_path=base_path, json_path=json_path, output_path=output_path)
