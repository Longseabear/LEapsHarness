from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import ConfigError, load_json_file, load_runtime_configs, merge_runtime_configs, normalize_config_paths
from .validation import OUTPUTS_BY_TYPE, validate_workflow_file


def build_workflow_plan(
    workflow_path: str | Path,
    *,
    config_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
    run_vars: dict[str, Any] | None = None,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    workflow_file = Path(workflow_path).resolve()
    resolved_config_paths = normalize_config_paths(config_paths=config_paths)
    workflow = load_json_file(workflow_file)
    workflow = merge_runtime_configs(workflow, load_runtime_configs(resolved_config_paths))
    vars_ = _merge_vars(workflow.get("vars", {}), run_vars or {})
    workflow["vars"] = vars_

    artifact_root_value = artifact_root or workflow.get("artifact_root", ".runs")
    artifact_root_path = _resolve_path(artifact_root_value, workflow_file.parent)

    steps = workflow.get("steps", [])
    if not isinstance(steps, list):
        raise ConfigError("Workflow field 'steps' must be a list.")

    return {
        "workflow": workflow.get("name", workflow_file.stem),
        "workflow_path": str(workflow_file),
        "config_paths": [str(path) for path in resolved_config_paths],
        "artifact_root": str(artifact_root_path),
        "vars": vars_,
        "policy": workflow.get("policy", {}),
        "output_contract": workflow.get("output_contract", {"mode": "wrap"}),
        "step_count": len(steps),
        "steps": [_step_plan(index, step) for index, step in enumerate(steps)],
        "validation_errors": validate_workflow_file(workflow_file, config_paths=resolved_config_paths),
    }


def _step_plan(index: int, step: Any) -> dict[str, Any]:
    if not isinstance(step, dict):
        return {"index": index, "error": "step is not an object"}
    step_type = step.get("type")
    planned = {
        "index": index,
        "id": step.get("id"),
        "type": step_type,
        "outputs": sorted(OUTPUTS_BY_TYPE.get(step_type, set())),
    }
    for key in (
        "adapter",
        "source",
        "template",
        "input_template",
        "item_path",
        "producer_adapter",
        "reviewer_adapter",
        "producer_template",
        "reviewer_template",
        "max_attempts",
    ):
        if key in step:
            planned[key] = step[key]
    if step_type == "command":
        planned["command"] = step.get("command")
    if step_type in {"llm", "agent", "for_each"} and "adapter" not in planned:
        planned["adapter"] = "default"
    return planned


def _merge_vars(workflow_vars: Any, run_vars: dict[str, Any]) -> dict[str, Any]:
    if workflow_vars is None:
        workflow_vars = {}
    if not isinstance(workflow_vars, dict):
        raise ConfigError("Workflow field 'vars' must be an object.")
    merged = dict(workflow_vars)
    merged.update(run_vars)
    return merged


def _resolve_path(value: str | Path, base: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()
