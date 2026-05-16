from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def main() -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Apply a structured knowledge update.")
    parser.add_argument("module")
    parser.add_argument("knowledge_root")
    parser.add_argument("worker_output")
    args = parser.parse_args()

    module = _safe_name(args.module)
    knowledge_root = Path(args.knowledge_root).resolve()
    worker_output = Path(args.worker_output)
    update = _parse_json_object(worker_output.read_text(encoding="utf-8"))
    _validate_update(module, update)

    _ensure_structure(knowledge_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    module_path = knowledge_root / "modules" / f"{module}.md"
    module_path.write_text(str(update["module_doc_markdown"]).strip() + "\n", encoding="utf-8", newline="\n")

    _update_module_index(
        knowledge_root / "maps" / "module_index.md",
        module,
        str(update.get("purpose", "TODO")),
        timestamp,
        str(update.get("confidence", "unknown")),
    )

    for pattern in update.get("patterns", []):
        _append_named_observation(knowledge_root / "patterns", pattern, module, timestamp, "Pattern")

    for skill in update.get("skills", []):
        _append_named_observation(knowledge_root / "skills", skill, module, timestamp, "Skill")

    review_path = knowledge_root / "reviews" / f"{module}_{timestamp}.md"
    review_path.write_text(_render_review(update, timestamp), encoding="utf-8", newline="\n")

    todos = update.get("todos", [])
    if todos:
        inbox = knowledge_root / "_inbox" / "discovered_notes.md"
        with inbox.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"\n## {module} - {timestamp}\n\n")
            for todo in todos:
                handle.write(f"- TODO: {todo}\n")

    result = {
        "module": module,
        "module_doc": str(module_path),
        "review_record": str(review_path),
        "patterns": [item.get("name") for item in update.get("patterns", [])],
        "skills": [item.get("name") for item in update.get("skills", [])],
        "todos": todos,
        "confidence": update.get("confidence", "unknown"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _force_utf8_stdio() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _parse_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise SystemExit("Worker output does not contain a JSON object.")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise SystemExit("Worker output JSON must be an object.")
    return parsed


def _validate_update(module: str, update: dict[str, Any]) -> None:
    if str(update.get("module")) != module:
        raise SystemExit(f"Worker output module must be {module!r}.")
    if not update.get("module_doc_markdown"):
        raise SystemExit("Worker output requires module_doc_markdown.")
    for field in ("patterns", "skills", "todos"):
        if field in update and not isinstance(update[field], list):
            raise SystemExit(f"Worker output field {field!r} must be a list.")


def _ensure_structure(root: Path) -> None:
    for path in (
        root,
        root / "maps",
        root / "modules",
        root / "patterns",
        root / "skills",
        root / "reviews",
        root / "_inbox",
    ):
        path.mkdir(parents=True, exist_ok=True)
    index = root / "maps" / "module_index.md"
    if not index.exists():
        index.write_text("# Module Index\n\n| Module | Purpose | Last Updated | Confidence |\n| --- | --- | --- | --- |\n", encoding="utf-8")


def _update_module_index(path: Path, module: str, purpose: str, timestamp: str, confidence: str) -> None:
    line = f"| `{module}` | {purpose} | {timestamp} | {confidence} |"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [item for item in existing.splitlines() if not item.startswith(f"| `{module}` |")]
    if not lines:
        lines = ["# Module Index", "", "| Module | Purpose | Last Updated | Confidence |", "| --- | --- | --- | --- |"]
    lines.append(line)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def _append_named_observation(root: Path, item: dict[str, Any], module: str, timestamp: str, kind: str) -> None:
    name = _safe_name(str(item.get("name", "unnamed")))
    markdown = str(item.get("markdown", "")).strip()
    if not markdown:
        return
    path = root / f"{name}.md"
    if not path.exists():
        path.write_text(f"# {kind}: {name}\n", encoding="utf-8", newline="\n")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n## Observation: {module} - {timestamp}\n\n")
        handle.write(markdown)
        handle.write("\n")


def _render_review(update: dict[str, Any], timestamp: str) -> str:
    lines = [
        f"# Review: {update.get('module')} - {timestamp}",
        "",
        f"- Confidence: `{update.get('confidence', 'unknown')}`",
        "",
        "## Summary",
        "",
        str(update.get("summary", "TODO")).strip(),
        "",
        "## TODOs",
        "",
    ]
    todos = update.get("todos", [])
    if todos:
        lines.extend(f"- {todo}" for todo in todos)
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _safe_name(value: str) -> str:
    cleaned = SAFE_NAME.sub("_", value.strip()).strip("._")
    if not cleaned:
        raise SystemExit("Name must not be empty.")
    return cleaned


if __name__ == "__main__":
    raise SystemExit(main())
