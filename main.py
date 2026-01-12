import os
import sys
import json

from src.parser import Parser
from src.debug import JSONValidator
from src.compiler import CCodeGenerator
from src.modules.logger import logger


def main(base_path: str, p_path: str, json_path: str, c_path: str):
    with open(p_path, "r") as file:
        code = file.read()

    # PARSER
    print("\n=========== PARSER ===========\n")

    parser = Parser(base_path=base_path)
    data = parser.parse_code(code)

    json_output = json.dumps(data, indent=2, default=str)
    with open(json_path, "w") as f:
        f.write(json_output)

    # DEBUGGER
    print("\n=========== DEBUGGER ===========\n")

    validator = JSONValidator()
    result_validation = validator.validate(data)

    print("\nРезультат валидации:")
    print(f"Валидный: {result_validation['is_valid']}")
    print(f"Ошибок: {result_validation['error_count']}")
    print(f"Предупреждений: {result_validation['warning_count']}")

    if result_validation["warnings"]:
        print("\nПредупреждения:")
        for warning in result_validation["warnings"]:
            logger.warning(f"Строка {warning['line_number']}: {warning['message']}")

    if result_validation["errors"]:
        print("\nОшибки:")
        for error in result_validation["errors"]:
            logger.error(f"Строка {error['line_number']}: {error['message']}")

    if not result_validation["errors"]:
        print("\nOK")

    print("\n=========== CCodeGenerator ===========\n")

    generator = CCodeGenerator()
    c_code = generator.generate_from_json(data)

    with open(c_path, "w") as f:
        f.write(c_code)


if __name__ == "__main__":
    p_path = "/Users/phil/GitHub/phils_language/examples/main.p"
    base_path = "/Users/phil/GitHub/phils_language/examples/"
    json_path = "/Users/phil/GitHub/phils_language/examples/parsed_code.json"
    c_path = "/Users/phil/GitHub/phils_language/examples/generated_code.c"
    output_path = "/Users/phil/GitHub/phils_language/examples/generated_code"

    main(base_path=base_path, p_path=p_path, json_path=json_path, c_path=c_path)

    command = f"gcc {c_path} -o {output_path}"

    os.system(command)

    sys.exit(0)
