from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "artifact"


class ArtifactStore:
    def __init__(self, artifact_root: Path, run_id: str) -> None:
        self.run_dir = artifact_root / safe_name(run_id)
        self.steps_dir = self.run_dir / "steps"
        self.manifest_path = self.run_dir / "manifest.json"
        self.readable_manifest_path = self.run_dir / "manifest.md"
        self.records: list[dict[str, Any]] = []
        self.steps_dir.mkdir(parents=True, exist_ok=True)

    def step_dir(self, step_id: str) -> Path:
        path = self.steps_dir / safe_name(step_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def copy_file(self, step_id: str, name: str, source: Path) -> Path:
        target = self.step_dir(step_id) / safe_name(name)
        shutil.copyfile(source, target)
        self._record(step_id, "file", name, target)
        return target

    def write_text(self, step_id: str, name: str, content: str) -> Path:
        target = self.step_dir(step_id) / safe_name(name)
        target.write_text(content, encoding="utf-8", newline="\n")
        self._record(step_id, "text", name, target)
        return target

    def write_json(self, step_id: str, name: str, data: Any) -> Path:
        target = self.step_dir(step_id) / safe_name(name)
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        self._record(step_id, "json", name, target)
        return target

    def write_manifest(self, summary: dict[str, Any]) -> None:
        manifest = dict(summary)
        manifest["artifacts"] = self.records
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
            newline="\n",
        )
        self.readable_manifest_path.write_text(
            self._render_readable_manifest(manifest),
            encoding="utf-8",
            newline="\n",
        )

    def _record(self, step_id: str, kind: str, name: str, path: Path) -> None:
        self.records.append(
            {
                "step_id": step_id,
                "kind": kind,
                "name": name,
                "path": str(path.resolve()),
            }
        )

    @staticmethod
    def _render_readable_manifest(manifest: dict[str, Any]) -> str:
        lines = [
            f"# Run Manifest: {manifest.get('run_id', 'unknown')}",
            "",
            f"- Workflow: `{manifest.get('workflow', 'unknown')}`",
            f"- Status: `{manifest.get('status', 'unknown')}`",
            f"- Started: `{manifest.get('started_at', '')}`",
            f"- Finished: `{manifest.get('finished_at', '')}`",
            f"- Artifact directory: `{manifest.get('artifact_dir', '')}`",
        ]
        if manifest.get("error"):
            lines.append(f"- Error: `{manifest['error']}`")

        lines.extend(["", "## Steps", ""])
        for step in manifest.get("steps", []):
            lines.append(f"### {step.get('id', 'unknown')} ({step.get('type', 'unknown')})")
            lines.append("")
            lines.append(f"- Status: `{step.get('status', 'unknown')}`")
            lines.append(f"- Elapsed seconds: `{step.get('elapsed_seconds', '')}`")
            if step.get("error"):
                lines.append(f"- Error: `{step['error']}`")
            outputs = step.get("outputs", {})
            if outputs:
                lines.append("- Outputs:")
                for key, value in outputs.items():
                    lines.append(f"  - `{key}`: `{value}`")
            lines.append("")

        lines.extend(["## Artifacts", ""])
        for record in manifest.get("artifacts", []):
            lines.append(
                f"- `{record.get('step_id', '')}` / `{record.get('name', '')}` "
                f"({record.get('kind', '')}): `{record.get('path', '')}`"
            )
        lines.append("")
        return "\n".join(lines)
