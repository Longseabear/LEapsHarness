from __future__ import annotations

from pathlib import Path
from typing import Any


class PolicyError(RuntimeError):
    pass


class ExecutionPolicy:
    def __init__(self, raw: dict[str, Any], workspace_dir: Path) -> None:
        self.raw = raw
        self.workspace_dir = workspace_dir.resolve()
        self.allowed_commands = _string_list(raw.get("allowed_commands", []), "allowed_commands")
        self.allowed_cwd_roots = _path_list(raw.get("allowed_cwd_roots", []), "allowed_cwd_roots", self.workspace_dir)
        self.blocked_env = set(_string_list(raw.get("blocked_env", []), "blocked_env"))
        self.max_timeout_seconds = _optional_int(raw.get("max_timeout_seconds"), "max_timeout_seconds")

    @classmethod
    def from_workflow(cls, raw: Any, workspace_dir: Path) -> "ExecutionPolicy":
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise PolicyError("Workflow field 'policy' must be an object.")
        return cls(raw, workspace_dir)

    def check_command(
        self,
        label: str,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: int,
        env: dict[str, str] | None = None,
    ) -> None:
        if not command:
            raise PolicyError(f"{label} command must not be empty.")
        if self.allowed_commands and not self._command_is_allowed(command[0]):
            allowed = ", ".join(self.allowed_commands)
            raise PolicyError(f"{label} command '{command[0]}' is not allowed by policy. Allowed: {allowed}")
        if self.allowed_cwd_roots and not any(_is_relative_to(cwd.resolve(), root) for root in self.allowed_cwd_roots):
            roots = ", ".join(str(root) for root in self.allowed_cwd_roots)
            raise PolicyError(f"{label} cwd '{cwd}' is outside allowed_cwd_roots: {roots}")
        if self.max_timeout_seconds is not None and timeout_seconds > self.max_timeout_seconds:
            raise PolicyError(
                f"{label} timeout_seconds {timeout_seconds} exceeds policy max_timeout_seconds "
                f"{self.max_timeout_seconds}."
            )
        env_keys = set((env or {}).keys())
        blocked = sorted(env_keys & self.blocked_env)
        if blocked:
            raise PolicyError(f"{label} sets blocked env vars: {', '.join(blocked)}")

    def _command_is_allowed(self, executable: str) -> bool:
        executable_path = Path(executable)
        executable_name = _normalize_command_name(executable_path.name or executable)
        executable_value = str(executable_path.resolve()).lower() if executable_path.is_absolute() else ""
        for allowed in self.allowed_commands:
            allowed_path = Path(allowed)
            if allowed_path.is_absolute() and executable_value == str(allowed_path.resolve()).lower():
                return True
            if _normalize_command_name(allowed_path.name or allowed) == executable_name:
                return True
        return False


def _string_list(value: Any, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise PolicyError(f"Policy field '{field}' must be a list of non-empty strings.")
    return list(value)


def _path_list(value: Any, field: str, workspace_dir: Path) -> list[Path]:
    paths = _string_list(value, field)
    resolved: list[Path] = []
    for path_value in paths:
        path = Path(path_value)
        if not path.is_absolute():
            path = workspace_dir / path
        resolved.append(path.resolve())
    return resolved


def _optional_int(value: Any, field: str) -> int | None:
    if value in (None, ""):
        return None
    if not isinstance(value, int) or value < 1:
        raise PolicyError(f"Policy field '{field}' must be a positive integer.")
    return value


def _normalize_command_name(value: str) -> str:
    lowered = value.lower()
    return lowered[:-4] if lowered.endswith(".exe") else lowered


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
