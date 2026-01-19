import os
import time

from tests.constants import p_path, c_path, base_path, json_path
from main import main


def run(P, C):
    global p_path, c_path, json_path

    seed = time.time()
    p_path = p_path.format(seed)
    c_path = c_path.format(seed)
    json_path = json_path.format(seed)

    with open(p_path, "w") as file:
        file.write(P)

    main(base_path=base_path, p_path=p_path, json_path=json_path, c_path=c_path)

    os.remove(p_path)
    os.remove(json_path)

    with open(c_path, "r") as file:
        output = file.read()

    assert C in output

    os.remove(c_path)
