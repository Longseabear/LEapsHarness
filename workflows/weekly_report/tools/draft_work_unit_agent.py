from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        work_unit = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"Invalid work unit JSON: {exc}", file=sys.stderr)
        return 2

    evidence = work_unit.get("evidence", [])
    evidence_text = ", ".join(evidence) if evidence else "No evidence provided"
    print(f"## {work_unit.get('title', 'Untitled work')}")
    print("")
    print(f"- Owner: {work_unit.get('owner', 'unknown')}")
    print(f"- Summary: {work_unit.get('summary', '')}")
    print(f"- Evidence: {evidence_text}")
    print("- Draft note: Verify cited evidence before treating this section as final.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
