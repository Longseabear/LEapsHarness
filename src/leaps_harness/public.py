from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .models import ValidationResult, WorkflowPlan, WorkflowResult
from .planning import build_workflow_plan
from .runner import WorkflowRunner
from .validation import validate_workflow_file


PathLike = str | Path


def run_workflow(
    workflow: PathLike,
    *,
    configs: Iterable[PathLike] | PathLike | None = None,
    vars: dict[str, Any] | None = None,
    run_id: str | None = None,
    artifact_root: PathLike | None = None,
    resume_from: PathLike | None = None,
) -> WorkflowResult:
    runner = WorkflowRunner(
        workflow,
        run_id=run_id,
        artifact_root=artifact_root,
        config_paths=_as_list(configs),
        run_vars=vars,
        resume_from=resume_from,
    )
    return WorkflowResult(runner.run())


def plan_workflow(
    workflow: PathLike,
    *,
    configs: Iterable[PathLike] | PathLike | None = None,
    vars: dict[str, Any] | None = None,
    artifact_root: PathLike | None = None,
) -> WorkflowPlan:
    return WorkflowPlan(
        build_workflow_plan(
            workflow,
            config_paths=_as_list(configs),
            run_vars=vars,
            artifact_root=artifact_root,
        )
    )


def validate_workflow(
    workflow: PathLike,
    *,
    configs: Iterable[PathLike] | PathLike | None = None,
) -> ValidationResult:
    return ValidationResult(validate_workflow_file(workflow, config_paths=_as_list(configs)))


def _as_list(values: Iterable[PathLike] | PathLike | None) -> list[PathLike]:
    if values is None:
        return []
    if isinstance(values, (str, Path)):
        return [values]
    return list(values)
