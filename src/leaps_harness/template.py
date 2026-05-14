from __future__ import annotations

import re
from typing import Any


_TOKEN = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")


class TemplateRenderError(KeyError):
    pass


def render_template(template: str, values: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise TemplateRenderError(f"Missing template value '{key}'.")
        return str(values[key])

    return _TOKEN.sub(replace, template)


def flatten_values(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(flatten_values(value, full_key))
        else:
            flattened[full_key] = str(value)
    return flattened
