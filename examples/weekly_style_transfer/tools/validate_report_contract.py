from __future__ import annotations

import json
import sys
from pathlib import Path


def _force_utf8_stdio() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


REQUIRED_HEADINGS = [
    "# 그룹 주간보고",
    "## 이번 주 종합",
    "## 주요 진행",
    "## 리스크 및 의사결정",
    "## 다음 주 초점",
]


REQUIRED_FACTS = [
    "210ms",
    "145ms",
    "2시간 40분",
    "1시간 55분",
    "0.6%",
    "11건",
    "7건",
    "수요일",
    "금요일",
]


def main() -> int:
    _force_utf8_stdio()
    if len(sys.argv) != 3:
        print("Usage: validate_report_contract.py <report.md> <work_units.json>", file=sys.stderr)
        return 2

    report_path = Path(sys.argv[1])
    work_units_path = Path(sys.argv[2])
    report = _normalize_text(report_path.read_text(encoding="utf-8"))
    work_units = json.loads(work_units_path.read_text(encoding="utf-8"))

    errors: list[str] = []
    for heading in REQUIRED_HEADINGS:
        if heading not in report:
            errors.append(f"Missing heading: {heading}")

    heading_positions = [report.find(heading) for heading in REQUIRED_HEADINGS]
    if all(position >= 0 for position in heading_positions) and heading_positions != sorted(heading_positions):
        errors.append("Headings are not in the required order.")

    if any(line.startswith(("  -", "\t-")) for line in report.splitlines()):
        errors.append("Nested bullets are not allowed in the group weekly format.")

    if "**" in report:
        errors.append("Bold markdown is not allowed in the group weekly format.")

    if "- 리스크:" not in report:
        errors.append("Missing compressed risk bullet starting with '- 리스크:'.")

    if "- 결정 필요:" not in report:
        errors.append("Missing compressed decision bullet starting with '- 결정 필요:'.")

    progress_section = _section_between(report, "## 주요 진행", "## 리스크 및 의사결정")

    for fact in REQUIRED_FACTS:
        if fact not in report:
            errors.append(f"Missing required fact: {fact}")

    for item in work_units.get("work_units", []):
        title = str(item.get("title", ""))
        if title and title not in report:
            errors.append(f"Missing work unit title: {title}")
        elif title:
            progress_lines = [line for line in progress_section.splitlines() if title in line]
            if not progress_lines:
                errors.append(f"Work unit title is missing from 주요 진행: {title}")
            elif not any(":" in line and len(line.split(":", 1)[1].strip()) >= 12 for line in progress_lines):
                errors.append(f"주요 진행 bullet lacks outcome detail for: {title}")

    result = {
        "passed": not errors,
        "error_count": len(errors),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


def _normalize_text(value: str) -> str:
    return value.replace("\u202f", " ").replace("\u00a0", " ")


def _section_between(value: str, start_heading: str, end_heading: str) -> str:
    start = value.find(start_heading)
    end = value.find(end_heading)
    if start == -1 or end == -1 or end <= start:
        return ""
    return value[start:end]


if __name__ == "__main__":
    raise SystemExit(main())
