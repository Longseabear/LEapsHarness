from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Build a bounded review packet from selected files.")
    parser.add_argument("selection_json")
    parser.add_argument("--max-bytes", type=int, default=50000)
    args = parser.parse_args()

    selection_path = Path(args.selection_json)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    repo_root = Path(selection["repo_root"])
    selected_files = selection.get("selected_files", [])

    print(f"# Review Packet: {selection.get('module', 'unknown')}")
    print()
    print("## Scope Guardrails")
    print()
    print("- This packet contains only the selected module and directly included dependencies.")
    print("- Do not infer full-repository architecture from this packet.")
    print("- Mark uncertainty explicitly.")
    print()
    print("## Selection")
    print()
    print("```json")
    print(json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=True))
    print("```")
    print()
    print("## Files")
    print()

    remaining = args.max_bytes
    for item in selected_files:
        rel_path = item["path"]
        path = repo_root / rel_path
        print(f"### {rel_path}")
        print()
        if remaining <= 0:
            print("_Content omitted because max-bytes limit was reached._")
            print()
            continue
        text = path.read_text(encoding="utf-8")
        chunk = text[:remaining]
        remaining -= len(chunk.encode("utf-8"))
        print("```")
        print(chunk.rstrip())
        print("```")
        if len(chunk) < len(text):
            print()
            print("_File truncated by max-bytes limit._")
        print()
    return 0


def _force_utf8_stdio() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
