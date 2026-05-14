from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_WORK_UNIT_FIELDS = {
    "id": str,
    "owner": str,
    "title": str,
    "summary": str,
    "evidence": list,
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_work_units.py <work_units.json>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    document = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_document(document)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


def validate_document(document: dict[str, Any]) -> list[str]:
    errors = []
    if document.get("schema_version") != "work_units.v0":
        errors.append("schema_version must be 'work_units.v0'.")
    if not isinstance(document.get("week"), str):
        errors.append("week must be a string.")
    work_units = document.get("work_units")
    if not isinstance(work_units, list):
        errors.append("work_units must be a list.")
        return errors
    for index, unit in enumerate(work_units):
        if not isinstance(unit, dict):
            errors.append(f"work_units[{index}] must be an object.")
            continue
        for field, expected_type in REQUIRED_WORK_UNIT_FIELDS.items():
            value = unit.get(field)
            if not isinstance(value, expected_type):
                errors.append(f"work_units[{index}].{field} must be {expected_type.__name__}.")
            elif expected_type is str and not value.strip():
                errors.append(f"work_units[{index}].{field} must not be empty.")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
