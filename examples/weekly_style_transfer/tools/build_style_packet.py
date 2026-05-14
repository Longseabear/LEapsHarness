from __future__ import annotations

import sys
from pathlib import Path


def _force_utf8_stdio() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    _force_utf8_stdio()
    if len(sys.argv) != 2:
        print("Usage: build_style_packet.py <group_style_samples_dir>", file=sys.stderr)
        return 2

    sample_dir = Path(sys.argv[1])
    if not sample_dir.exists():
        print(f"Style sample directory does not exist: {sample_dir}", file=sys.stderr)
        return 1

    samples = sorted(sample_dir.glob("*.md"))
    if not samples:
        print(f"No markdown style samples found in: {sample_dir}", file=sys.stderr)
        return 1

    print("# Group Weekly Style Packet")
    print()
    print("## Observed Format")
    print("- Title is exactly `# 그룹 주간보고`.")
    print("- Sections appear in this order: 이번 주 종합, 주요 진행, 리스크 및 의사결정, 다음 주 초점.")
    print("- Each section uses concise bullets rather than long paragraphs.")
    print("- The report favors outcomes, metrics, risks, decisions, and next actions over implementation detail.")
    print("- Risk and decision items are compressed into group-level implications.")
    print()
    print("## Source Samples")
    print()
    for path in samples:
        print(f"### {path.name}")
        print()
        print(path.read_text(encoding="utf-8").strip())
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
