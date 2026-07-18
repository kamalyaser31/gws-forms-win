"""Small JSON file helpers shared by the command-line scripts."""

import json
import os
import tempfile
from pathlib import Path


def write_json_atomic(path: Path, content: object) -> None:
    """Replace a JSON file only after its complete replacement is durable."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as json_file:
            json.dump(content, json_file, ensure_ascii=False, indent=2)
            json_file.flush()
            os.fsync(json_file.fileno())
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
