import json
from pathlib import Path


def defaults(shape):
    return json.loads((Path(__file__).with_name("defaults.json")).read_text())[shape]
