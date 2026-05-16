from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SKIP_DIRS = {".git", ".runs", "build", "out", "dist", "__pycache__"}
TEXT_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".md", ".txt", ".json", ".yaml", ".yml"}
INCLUDE_PATTERN = re.compile(r'#include\s+[<"]([^>"]+)[>"]')


def main() -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Select files related to one module.")
    parser.add_argument("repo_root")
    parser.add_argument("module")
    parser.add_argument("--max-files", type=int, default=16)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    module = _safe_module(args.module)
    if not repo_root.exists():
        print(f"Repository root does not exist: {repo_root}", file=sys.stderr)
        return 1

    all_files = [path for path in _iter_text_files(repo_root)]
    module_files = _module_matches(repo_root, all_files, module)
    dependency_files = _dependency_matches(repo_root, all_files, module_files)
    selected = _dedupe(module_files + dependency_files)

    warnings: list[str] = []
    if len(selected) > args.max_files:
        warnings.append(f"Selection truncated from {len(selected)} to max_files={args.max_files}.")
        selected = selected[: args.max_files]

    result = {
        "repo_root": str(repo_root),
        "module": module,
        "scope_rule": "one-module-only",
        "selected_files": [
            {
                "path": _relative(repo_root, path),
                "bytes": path.stat().st_size,
                "reason": "module match" if path in module_files else "included dependency",
            }
            for path in selected
        ],
        "excluded_summary": {
            "text_files_seen": len(all_files),
            "selected_count": len(selected),
        },
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _force_utf8_stdio() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _safe_module(value: str) -> str:
    module = value.strip()
    if not module or module in {".", ".."} or "/" in module or "\\" in module:
        raise SystemExit("Module must be a simple name such as bpc, demosaic, or gamma.")
    return module


def _iter_text_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.append(path)
    return sorted(files)


def _module_matches(repo_root: Path, files: list[Path], module: str) -> list[Path]:
    module_lower = module.lower()
    matches: list[Path] = []
    for path in files:
        rel = _relative(repo_root, path).lower()
        parts = Path(rel).parts
        if module_lower in parts or module_lower in path.stem.lower():
            matches.append(path)
    return matches


def _dependency_matches(repo_root: Path, files: list[Path], module_files: list[Path]) -> list[Path]:
    rel_to_path = {_relative(repo_root, path).replace("\\", "/"): path for path in files}
    dependencies: list[Path] = []
    for path in module_files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for include in INCLUDE_PATTERN.findall(text):
            normalized = include.replace("\\", "/")
            if normalized in rel_to_path:
                candidate = rel_to_path[normalized]
                if candidate not in module_files:
                    dependencies.append(candidate)
    return dependencies


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
