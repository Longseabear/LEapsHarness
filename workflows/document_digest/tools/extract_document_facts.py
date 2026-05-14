from __future__ import annotations

import json
import re
import sys
from pathlib import Path


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: extract_document_facts.py <document>", file=sys.stderr)
        return 2

    source = Path(sys.argv[1])
    text = source.read_text(encoding="utf-8")
    headings = []
    for line in text.splitlines():
        match = HEADING_PATTERN.match(line.strip())
        if match:
            headings.append({"level": len(match.group(1)), "title": match.group(2)})

    facts = {
        "source_name": source.name,
        "line_count": len(text.splitlines()),
        "word_count": len(re.findall(r"\S+", text)),
        "heading_count": len(headings),
        "headings": headings,
    }
    print(json.dumps(facts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
