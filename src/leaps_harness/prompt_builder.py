from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .template import TemplateRenderError, render_template


class PromptBuildError(RuntimeError):
    pass


def build_prompt(template: str, values: dict[str, Any]) -> str:
    if not isinstance(values, dict):
        raise PromptBuildError("Prompt values must be a dictionary.")
    try:
        return render_template(template, _prompt_values(values))
    except TemplateRenderError as exc:
        raise PromptBuildError(str(exc)) from exc


def build_prompt_from_file(template_path: str | Path, values: dict[str, Any]) -> str:
    path = Path(template_path)
    if not path.exists():
        raise PromptBuildError(f"Prompt template does not exist: {path.resolve()}")
    return build_prompt(path.read_text(encoding="utf-8"), values)


def _prompt_values(values: dict[str, Any]) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, value in values.items():
        key_text = str(key)
        flattened[key_text] = _stringify(value)
        if isinstance(value, dict):
            flattened.update(_flatten_nested(value, key_text))
    return flattened


def _flatten_nested(values: dict[str, Any], prefix: str) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, value in values.items():
        full_key = f"{prefix}.{key}"
        flattened[full_key] = _stringify(value)
        if isinstance(value, dict):
            flattened.update(_flatten_nested(value, full_key))
    return flattened


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return str(value)
