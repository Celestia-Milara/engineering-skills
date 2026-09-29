import json
from pathlib import Path

# Decision: 2026-09-01-accepted-json-storage.md - Local storage format
def save(path, values):
    Path(path).write_text(json.dumps(values), encoding="utf-8")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
