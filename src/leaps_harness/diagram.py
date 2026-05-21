from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import ConfigError, load_json_file, load_runtime_configs, merge_runtime_configs, normalize_config_paths
from .validation import validate_workflow_file


ARTIFACT_REFERENCE_PATTERN = re.compile(r"artifact\.([A-Za-z0-9_-]+)\.[A-Za-z0-9_.-]+")


class DiagramError(RuntimeError):
    pass


def build_workflow_diagram(
    workflow_path: str | Path,
    *,
    config_paths: list[str | Path] | tuple[str | Path, ...] | str | Path | None = None,
) -> str:
    workflow_file = Path(workflow_path).resolve()
    workflow = _load_merged_workflow(workflow_file, config_paths)
    validation_errors = validate_workflow_file(workflow_file, config_paths=config_paths)

    steps = workflow.get("steps", [])
    if not isinstance(steps, list):
        raise DiagramError("Workflow field 'steps' must be a list.")

    step_ids = [str(step.get("id")) for step in steps if isinstance(step, dict) and step.get("id")]
    known_steps = set(step_ids)
    dependency_edges: set[tuple[str, str]] = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str):
            continue
        for dependency in _artifact_dependencies(step):
            if dependency in known_steps and dependency != step_id:
                dependency_edges.add((dependency, step_id))

    return _render_workflow_markdown(workflow_file, workflow, steps, dependency_edges, validation_errors)


def build_run_diagram(manifest_path: str | Path) -> str:
    manifest_file = Path(manifest_path).resolve()
    if not manifest_file.exists():
        raise DiagramError(f"Manifest does not exist: {manifest_file}")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DiagramError(f"Invalid JSON in manifest: {manifest_file}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise DiagramError(f"Manifest JSON must contain an object: {manifest_file}")

    steps = manifest.get("steps", [])
    if not isinstance(steps, list):
        raise DiagramError("Manifest field 'steps' must be a list.")

    return _render_run_markdown(manifest_file, manifest, steps)


def _load_merged_workflow(
    workflow_file: Path,
    config_paths: list[str | Path] | tuple[str | Path, ...] | str | Path | None,
) -> dict[str, Any]:
    try:
        workflow = load_json_file(workflow_file)
        configs = load_runtime_configs(normalize_config_paths(config_paths=config_paths))
        return merge_runtime_configs(workflow, configs)
    except ConfigError as exc:
        raise DiagramError(str(exc)) from exc


def _artifact_dependencies(value: Any) -> set[str]:
    dependencies: set[str] = set()
    if isinstance(value, dict):
        reference = value.get("from_artifact")
        if isinstance(reference, str) and "." in reference:
            dependencies.add(reference.split(".", 1)[0])
        for item in value.values():
            dependencies.update(_artifact_dependencies(item))
    elif isinstance(value, list):
        for item in value:
            dependencies.update(_artifact_dependencies(item))
    elif isinstance(value, str):
        dependencies.update(ARTIFACT_REFERENCE_PATTERN.findall(value))
    return dependencies


def _render_workflow_markdown(
    workflow_file: Path,
    workflow: dict[str, Any],
    steps: list[Any],
    dependency_edges: set[tuple[str, str]],
    validation_errors: list[str],
) -> str:
    name = str(workflow.get("name") or workflow_file.stem)
    valid_steps = [step for step in steps if isinstance(step, dict) and isinstance(step.get("id"), str)]
    node_ids = {str(step["id"]): f"s{index}" for index, step in enumerate(valid_steps)}

    lines = [
        f"# Workflow Diagram: {name}",
        "",
        f"- Source: `{workflow_file}`",
        f"- Steps: `{len(valid_steps)}`",
        f"- Validation: `{'failed' if validation_errors else 'passed'}`",
        "",
        "```mermaid",
        "flowchart TD",
    ]

    if not valid_steps:
        lines.append('  empty["No steps"]')
    for step in valid_steps:
        step_id = str(step["id"])
        step_type = str(step.get("type", "unknown"))
        label = _escape_mermaid_label(f"{step_id}<br/>{step_type}")
        lines.append(f'  {node_ids[step_id]}["{label}"]')

    for previous, current in zip(valid_steps, valid_steps[1:]):
        previous_id = str(previous["id"])
        current_id = str(current["id"])
        if (previous_id, current_id) not in dependency_edges:
            lines.append(f"  {node_ids[previous_id]} -. execution order .-> {node_ids[current_id]}")

    for source, target in sorted(dependency_edges):
        lines.append(f"  {node_ids[source]} --> {node_ids[target]}")

    lines.extend(
        [
            "  classDef step fill:#f7f9fc,stroke:#748094,color:#1f2937;",
        ]
    )
    if valid_steps:
        lines.append("  class " + ",".join(node_ids.values()) + " step;")
    lines.append("```")

    if validation_errors:
        lines.extend(["", "## Validation Errors", ""])
        lines.extend(f"- {error}" for error in validation_errors)
    lines.append("")
    return "\n".join(lines)


def _render_run_markdown(manifest_file: Path, manifest: dict[str, Any], steps: list[Any]) -> str:
    run_id = str(manifest.get("run_id") or manifest_file.parent.name)
    workflow_name = str(manifest.get("workflow") or "unknown")
    valid_steps = [step for step in steps if isinstance(step, dict) and isinstance(step.get("id"), str)]
    node_ids = {str(step["id"]): f"s{index}" for index, step in enumerate(valid_steps)}

    lines = [
        f"# Run Diagram: {run_id}",
        "",
        f"- Workflow: `{workflow_name}`",
        f"- Status: `{manifest.get('status', 'unknown')}`",
        f"- Manifest: `{manifest_file}`",
        "",
        "```mermaid",
        "flowchart TD",
    ]

    if not valid_steps:
        lines.append('  empty["No steps"]')
    for step in valid_steps:
        step_id = str(step["id"])
        step_type = str(step.get("type", "unknown"))
        status = str(step.get("status", "unknown"))
        details = [step_id, step_type, status]
        elapsed = step.get("elapsed_seconds")
        if elapsed not in (None, ""):
            details.append(f"{elapsed}s")
        outputs = step.get("outputs")
        if isinstance(outputs, dict):
            if "attempts" in outputs:
                details.append(f"attempts: {outputs['attempts']}")
            if "passed" in outputs:
                details.append(f"passed: {outputs['passed']}")
        if step.get("error"):
            details.append("error")
        label = _escape_mermaid_label("<br/>".join(details))
        lines.append(f'  {node_ids[step_id]}["{label}"]')

    for previous, current in zip(valid_steps, valid_steps[1:]):
        lines.append(f"  {node_ids[str(previous['id'])]} --> {node_ids[str(current['id'])]}")

    lines.extend(
        [
            "  classDef succeeded fill:#e7f7ec,stroke:#278650,color:#0f3f24;",
            "  classDef reused fill:#e8f1ff,stroke:#3777c2,color:#17345f;",
            "  classDef failed fill:#fde8e8,stroke:#c24141,color:#7f1d1d;",
            "  classDef unknown fill:#f3f4f6,stroke:#8b95a5,color:#374151;",
        ]
    )
    class_nodes: dict[str, list[str]] = {"succeeded": [], "reused": [], "failed": [], "unknown": []}
    for step in valid_steps:
        step_id = str(step["id"])
        status = str(step.get("status", "unknown"))
        class_name = status if status in class_nodes else "unknown"
        class_nodes[class_name].append(node_ids[step_id])
    for class_name, nodes in class_nodes.items():
        if nodes:
            lines.append("  class " + ",".join(nodes) + f" {class_name};")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _escape_mermaid_label(value: str) -> str:
    return value.replace('"', "&quot;")
