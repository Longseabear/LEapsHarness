from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import ConfigError, load_json_file, load_runtime_configs, merge_runtime_configs, normalize_config_paths


SUPPORTED_STEP_TYPES = {"copy_file", "command", "prompt", "agent", "for_each", "llm", "review", "iterative_review"}
OUTPUTS_BY_TYPE = {
    "copy_file": {"path"},
    "command": {"stdout", "stderr", "metadata", "returncode"},
    "prompt": {"prompt"},
    "agent": {"input", "response", "metadata"},
    "for_each": {"results", "combined", "count"},
    "llm": {"response", "metadata"},
    "review": {"review", "report", "passed"},
    "iterative_review": {"final", "history", "review", "attempts", "passed"},
}
TOKEN_PATTERN = re.compile(r"{{.*?}}")


def validate_workflow_file(
    workflow_path: str | Path,
    config_path: str | Path | None = None,
    config_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
) -> list[str]:
    workflow_file = Path(workflow_path).resolve()
    errors: list[str] = []
    try:
        workflow = load_json_file(workflow_file)
        resolved_config_paths = normalize_config_paths(config_path, config_paths)
        configs = load_runtime_configs(resolved_config_paths)
        workflow = merge_runtime_configs(workflow, configs)
    except ConfigError as exc:
        return [str(exc)]

    workspace_dir = workflow_file.parent
    steps = workflow.get("steps")
    if not isinstance(steps, list):
        return ["Workflow field 'steps' must be a list."]

    seen_ids: set[str] = set()
    known_outputs: dict[str, set[str]] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"steps[{index}] must be an object.")
            continue
        step_id = step.get("id")
        step_type = step.get("type")
        if not isinstance(step_id, str) or not step_id:
            errors.append(f"steps[{index}] requires a non-empty string id.")
            continue
        if step_id in seen_ids:
            errors.append(f"Step id '{step_id}' is duplicated.")
        seen_ids.add(step_id)

        if not isinstance(step_type, str) or step_type not in SUPPORTED_STEP_TYPES:
            errors.append(f"Step '{step_id}' has unsupported type '{step_type}'.")
            continue

        errors.extend(_validate_step_shape(step_id, step_type, step, workflow, workspace_dir))
        errors.extend(_validate_artifact_refs(step_id, step, known_outputs))
        known_outputs[step_id] = OUTPUTS_BY_TYPE[step_type]

    return errors


def _validate_step_shape(
    step_id: str,
    step_type: str,
    step: dict[str, Any],
    workflow: dict[str, Any],
    workspace_dir: Path,
) -> list[str]:
    errors: list[str] = []
    if step_type == "copy_file":
        errors.extend(_require_fields(step_id, step, ["source"]))
        source = step.get("source")
        if isinstance(source, str):
            errors.extend(_validate_existing_path(step_id, "source", source, workspace_dir))
    elif step_type == "command":
        errors.extend(_require_fields(step_id, step, ["command"]))
        if not isinstance(step.get("command"), list) or not step.get("command"):
            errors.append(f"Step '{step_id}' field 'command' must be a non-empty list.")
    elif step_type == "prompt":
        errors.extend(_require_fields(step_id, step, ["template"]))
        template = step.get("template")
        if isinstance(template, str):
            errors.extend(_validate_existing_path(step_id, "template", template, workspace_dir))
    elif step_type == "agent":
        if "input" not in step and "input_template" not in step:
            errors.append(f"Step '{step_id}' requires 'input' or 'input_template'.")
        errors.extend(_validate_adapter(step_id, step, workflow, "agent_adapters"))
        errors.extend(_validate_input_template(step_id, step, workspace_dir))
    elif step_type == "for_each":
        errors.extend(_require_fields(step_id, step, ["items", "input_template"]))
        errors.extend(_validate_adapter(step_id, step, workflow, "agent_adapters"))
        errors.extend(_validate_input_template(step_id, step, workspace_dir))
    elif step_type == "llm":
        errors.extend(_require_fields(step_id, step, ["prompt"]))
        errors.extend(_validate_adapter(step_id, step, workflow, "llm_adapters"))
    elif step_type == "review":
        errors.extend(_require_fields(step_id, step, ["target"]))
    elif step_type == "iterative_review":
        errors.extend(_require_fields(step_id, step, ["producer_template", "reviewer_template"]))
        errors.extend(_validate_iterative_adapter(step_id, step, workflow, "producer_adapter", "agent_adapters"))
        errors.extend(_validate_iterative_adapter(step_id, step, workflow, "reviewer_adapter", "llm_adapters"))
        producer_template = step.get("producer_template")
        reviewer_template = step.get("reviewer_template")
        if isinstance(producer_template, str):
            errors.extend(_validate_existing_path(step_id, "producer_template", producer_template, workspace_dir))
        if isinstance(reviewer_template, str):
            errors.extend(_validate_existing_path(step_id, "reviewer_template", reviewer_template, workspace_dir))
    return errors


def _require_fields(step_id: str, step: dict[str, Any], fields: list[str]) -> list[str]:
    return [f"Step '{step_id}' requires '{field}'." for field in fields if field not in step]


def _validate_adapter(
    step_id: str,
    step: dict[str, Any],
    workflow: dict[str, Any],
    adapter_field: str,
) -> list[str]:
    adapter_name = step.get("adapter", "default")
    adapters = workflow.get(adapter_field, {"default": {"type": "echo"}})
    if not isinstance(adapters, dict):
        return [f"Workflow field '{adapter_field}' must be an object."]
    if adapter_name not in adapters:
        return [f"Step '{step_id}' references unknown adapter '{adapter_name}' in '{adapter_field}'."]
    return []


def _validate_iterative_adapter(
    step_id: str,
    step: dict[str, Any],
    workflow: dict[str, Any],
    step_adapter_field: str,
    workflow_adapter_field: str,
) -> list[str]:
    adapter_name = step.get(step_adapter_field, "default")
    adapters = workflow.get(workflow_adapter_field, {"default": {"type": "echo"}})
    if not isinstance(adapters, dict):
        return [f"Workflow field '{workflow_adapter_field}' must be an object."]
    if adapter_name not in adapters:
        return [f"Step '{step_id}' references unknown adapter '{adapter_name}' in '{workflow_adapter_field}'."]
    return []


def _validate_input_template(step_id: str, step: dict[str, Any], workspace_dir: Path) -> list[str]:
    template = step.get("input_template")
    if isinstance(template, str):
        return _validate_existing_path(step_id, "input_template", template, workspace_dir)
    return []


def _validate_existing_path(step_id: str, field: str, value: str, workspace_dir: Path) -> list[str]:
    if TOKEN_PATTERN.search(value):
        return []
    path = Path(value)
    if not path.is_absolute():
        path = workspace_dir / path
    if path.exists():
        return []
    return [f"Step '{step_id}' field '{field}' path does not exist: {path.resolve()}"]


def _validate_artifact_refs(
    step_id: str,
    value: Any,
    known_outputs: dict[str, set[str]],
) -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        if "from_artifact" in value:
            reference = str(value["from_artifact"])
            parts = reference.split(".", 1)
            if len(parts) != 2:
                errors.append(f"Step '{step_id}' artifact reference must be 'step.output': {reference}")
            else:
                referenced_step, output_key = parts
                if referenced_step not in known_outputs:
                    errors.append(f"Step '{step_id}' references unknown or later step '{referenced_step}'.")
                elif output_key not in known_outputs[referenced_step]:
                    errors.append(f"Step '{step_id}' references unknown output '{reference}'.")
        for item in value.values():
            errors.extend(_validate_artifact_refs(step_id, item, known_outputs))
    elif isinstance(value, list):
        for item in value:
            errors.extend(_validate_artifact_refs(step_id, item, known_outputs))
    return errors
