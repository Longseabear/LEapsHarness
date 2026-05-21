from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable


class ConfigError(RuntimeError):
    pass


def load_json_file(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise ConfigError(f"JSON file does not exist: {resolved}")
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {resolved}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"JSON file must contain an object: {resolved}")
    return data


def merge_runtime_config(workflow: dict[str, Any], config: dict[str, Any] | None) -> dict[str, Any]:
    merged = copy.deepcopy(workflow)
    if not config:
        return merged

    for key in ("llm_adapters", "agent_adapters", "vars", "policy", "output_contract"):
        if key in config:
            config_value = config[key]
            if not isinstance(config_value, dict):
                raise ConfigError(f"Config field '{key}' must be an object.")
            workflow_value = merged.get(key, {})
            if not isinstance(workflow_value, dict):
                raise ConfigError(f"Workflow field '{key}' must be an object.")
            merged[key] = {**workflow_value, **copy.deepcopy(config_value)}

    return merged


def merge_runtime_configs(workflow: dict[str, Any], configs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    merged = copy.deepcopy(workflow)
    for config in configs:
        merged = merge_runtime_config(merged, config)
    return merged


def load_runtime_configs(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    return [load_json_file(path) for path in paths]


def normalize_config_paths(
    config_path: str | Path | None = None,
    config_paths: Iterable[str | Path] | str | Path | None = None,
) -> list[Path]:
    paths: list[str | Path] = []
    if config_path:
        paths.append(config_path)
    if config_paths:
        if isinstance(config_paths, (str, Path)):
            paths.append(config_paths)
        else:
            paths.extend(config_paths)
    return [Path(path).resolve() for path in paths]
