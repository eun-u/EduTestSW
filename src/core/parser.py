import json

def parse_routine(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data
