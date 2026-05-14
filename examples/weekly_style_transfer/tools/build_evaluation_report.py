from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _force_utf8_stdio() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    _force_utf8_stdio()
    if len(sys.argv) != 6:
        print(
            "Usage: build_evaluation_report.py "
            "<style_sample_dir> <hidden_reference.md> <iteration_history.json> "
            "<final_review.json> <contract_validation.json>",
            file=sys.stderr,
        )
        return 2

    style_sample_dir = Path(sys.argv[1])
    hidden_reference_path = Path(sys.argv[2])
    history_path = Path(sys.argv[3])
    final_review_path = Path(sys.argv[4])
    contract_path = Path(sys.argv[5])

    history = _load_json(history_path)
    final_review = _load_json(final_review_path)
    contract = _load_json(contract_path)

    print("# Weekly Style Transfer Evaluation")
    print()
    _print_summary(history, final_review, contract)
    _print_group_style(style_sample_dir)
    _print_markdown_file("Hidden Group Reference", hidden_reference_path)
    _print_attempts(history)
    _print_json_block("Final Reviewer Result", final_review)
    _print_json_block("Deterministic Contract Validation", contract)
    return 0


def _print_summary(history: Any, final_review: dict[str, Any], contract: dict[str, Any]) -> None:
    attempts = history if isinstance(history, list) else []
    failed_attempts = [item for item in attempts if not item.get("passed")]
    passed_attempts = [item for item in attempts if item.get("passed")]
    print("## Summary")
    print()
    print(f"- Attempts: `{len(attempts)}`")
    print(f"- Failed attempts: `{len(failed_attempts)}`")
    print(f"- Passed attempts: `{len(passed_attempts)}`")
    print(f"- Final reviewer status: `{final_review.get('status', 'unknown')}`")
    print(f"- Contract passed: `{contract.get('passed', False)}`")
    scores = final_review.get("scores")
    if isinstance(scores, dict):
        print("- Scores:")
        for key, value in scores.items():
            print(f"  - `{key}`: `{value}`")
    print()


def _print_group_style(style_sample_dir: Path) -> None:
    print("## Group Style Samples")
    print()
    for path in sorted(style_sample_dir.glob("*.md")):
        _print_markdown_file(path.name, path, heading_level=3)


def _print_attempts(history: Any) -> None:
    print("## Generated Attempts")
    print()
    if not isinstance(history, list) or not history:
        print("_No attempts were recorded._")
        print()
        return

    for item in history:
        attempt = item.get("attempt", "unknown")
        passed = item.get("passed", False)
        status = item.get("status", "unknown")
        feedback = str(item.get("feedback", ""))
        draft_path = Path(str(item.get("draft", "")))

        print(f"### Attempt {attempt}")
        print()
        print(f"- Passed: `{passed}`")
        print(f"- Reviewer status: `{status}`")
        print(f"- Feedback: {feedback if feedback else '_none_'}")
        print()
        if draft_path.exists():
            _print_fenced(draft_path.read_text(encoding="utf-8"))
        else:
            print(f"_Draft artifact not found: `{draft_path}`_")
            print()


def _print_markdown_file(title: str, path: Path, heading_level: int = 2) -> None:
    marker = "#" * heading_level
    print(f"{marker} {title}")
    print()
    if path.exists():
        _print_fenced(path.read_text(encoding="utf-8"))
    else:
        print(f"_File not found: `{path}`_")
        print()


def _print_json_block(title: str, value: dict[str, Any]) -> None:
    print(f"## {title}")
    print()
    print("```json")
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    print("```")
    print()


def _print_fenced(value: str) -> None:
    print("```markdown")
    print(value.strip())
    print("```")
    print()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
