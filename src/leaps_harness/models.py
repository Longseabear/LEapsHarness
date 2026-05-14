from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowResult:
    raw: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.raw.get("status", "unknown"))

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"

    @property
    def workflow(self) -> str:
        return str(self.raw.get("workflow", ""))

    @property
    def run_id(self) -> str:
        return str(self.raw.get("run_id", ""))

    @property
    def artifact_dir(self) -> Path:
        return Path(str(self.raw.get("artifact_dir", "")))

    @property
    def manifest_path(self) -> Path:
        return Path(str(self.raw.get("manifest_path", "")))

    @property
    def readable_manifest_path(self) -> Path:
        return Path(str(self.raw.get("readable_manifest_path", "")))

    @property
    def steps(self) -> list[dict[str, Any]]:
        steps = self.raw.get("steps", [])
        return steps if isinstance(steps, list) else []

    @property
    def error(self) -> str | None:
        value = self.raw.get("error")
        return str(value) if value is not None else None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class WorkflowPlan:
    raw: dict[str, Any]

    @property
    def valid(self) -> bool:
        return not self.validation_errors

    @property
    def workflow(self) -> str:
        return str(self.raw.get("workflow", ""))

    @property
    def artifact_root(self) -> Path:
        return Path(str(self.raw.get("artifact_root", "")))

    @property
    def step_count(self) -> int:
        return int(self.raw.get("step_count", 0))

    @property
    def steps(self) -> list[dict[str, Any]]:
        steps = self.raw.get("steps", [])
        return steps if isinstance(steps, list) else []

    @property
    def validation_errors(self) -> list[str]:
        errors = self.raw.get("validation_errors", [])
        return [str(error) for error in errors] if isinstance(errors, list) else []

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class ValidationResult:
    errors: list[str]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": list(self.errors)}
