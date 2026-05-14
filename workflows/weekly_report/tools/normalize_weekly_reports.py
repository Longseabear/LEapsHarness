from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "work"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: normalize_weekly_reports.py <team_weekly_reports.json>", file=sys.stderr)
        return 2

    source = Path(sys.argv[1])
    data = json.loads(source.read_text(encoding="utf-8"))
    work_units = []

    for person in data.get("people", []):
        owner = person.get("name", "unknown")
        for index, item in enumerate(person.get("items", []), start=1):
            title = item.get("title", "Untitled work")
            work_units.append(
                {
                    "id": f"{slug(owner)}-{index}-{slug(title)}",
                    "owner": owner,
                    "title": title,
                    "summary": item.get("summary", ""),
                    "evidence": item.get("evidence", []),
                }
            )

    print(
        json.dumps(
            {
                "week": data.get("week", ""),
                "schema_version": "work_units.v0",
                "work_units": work_units,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
