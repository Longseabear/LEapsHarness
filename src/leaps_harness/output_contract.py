from __future__ import annotations

import json
from typing import Any


DEFAULT_REQUIRED_FIELDS = ["status", "summary", "result"]
DEFAULT_TRACE_FIELDS = ["decision_log", "uncertainties", "artifacts"]


class OutputContractError(RuntimeError):
    pass


def merge_output_contracts(*contracts: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {"mode": "wrap"}
    for contract in contracts:
        if contract in (None, ""):
            continue
        if not isinstance(contract, dict):
            raise OutputContractError("output_contract must be an object.")
        merged.update(contract)
    if merged.get("mode") not in {"wrap", "require_json", "off"}:
        raise OutputContractError("output_contract.mode must be 'wrap', 'require_json', or 'off'.")
    if "required_fields" in merged:
        _string_list(merged["required_fields"], "required_fields")
    if "trace_fields" in merged:
        _string_list(merged["trace_fields"], "trace_fields")
    if "summary_max_chars" in merged:
        value = merged["summary_max_chars"]
        if not isinstance(value, int) or value < 1:
            raise OutputContractError("output_contract.summary_max_chars must be a positive integer.")
    return merged


def build_output_envelope(
    raw_text: str,
    *,
    source: str,
    status: str,
    contract: dict[str, Any] | None = None,
    raw_output_artifact: str | None = None,
    metadata_artifact: str | None = None,
    input_artifact: str | None = None,
    extra_trace: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    contract = merge_output_contracts(contract)
    if contract.get("mode") == "off":
        return None

    parsed = _parse_json_object(raw_text)
    if contract.get("mode") == "require_json" and parsed is None:
        raise OutputContractError("Output contract requires a JSON object response.")

    required_fields = list(contract.get("required_fields", DEFAULT_REQUIRED_FIELDS))
    trace_fields = list(contract.get("trace_fields", DEFAULT_TRACE_FIELDS))
    summary_max_chars = int(contract.get("summary_max_chars", 240))

    if parsed is not None:
        if contract.get("mode") == "require_json":
            missing = [field for field in required_fields if field not in parsed]
            if missing:
                raise OutputContractError(f"Output contract missing required fields: {', '.join(missing)}")
        envelope = _normalize_parsed(parsed, raw_text, status, summary_max_chars)
    else:
        envelope = _wrap_raw(raw_text, status, summary_max_chars)

    trace = envelope.setdefault("trace", {})
    if not isinstance(trace, dict):
        trace = {"raw_trace": trace}
        envelope["trace"] = trace
    trace.setdefault("source", source)
    if raw_output_artifact:
        trace.setdefault("raw_output_artifact", raw_output_artifact)
    if metadata_artifact:
        trace.setdefault("metadata_artifact", metadata_artifact)
    if input_artifact:
        trace.setdefault("input_artifact", input_artifact)
    for key, value in (extra_trace or {}).items():
        trace.setdefault(key, value)
    for field in trace_fields:
        trace.setdefault(field, [])
    envelope["contract"] = {
        "mode": contract.get("mode", "wrap"),
        "required_fields": required_fields,
        "trace_fields": trace_fields,
    }
    return envelope


def build_output_instructions(contract: dict[str, Any] | None = None) -> str:
    contract = merge_output_contracts(contract)
    required_fields = list(contract.get("required_fields", DEFAULT_REQUIRED_FIELDS))
    trace_fields = list(contract.get("trace_fields", DEFAULT_TRACE_FIELDS))
    return "\n".join(
        [
            "",
            "Return the final answer as a JSON object.",
            f"Required top-level fields: {', '.join(required_fields)}.",
            "Use `summary` for a short operator-facing summary.",
            "Use `result` for the actual answer or output payload.",
            "Use `trace` for externally shareable execution notes.",
            f"Recommended trace fields: {', '.join(trace_fields)}.",
            "Do not include hidden chain-of-thought. Put only concise decision logs, evidence notes, uncertainties, and artifact references in trace.",
        ]
    )


def envelope_summary(envelope: dict[str, Any]) -> str:
    lines = [
        f"Status: {envelope.get('status', 'unknown')}",
        f"Summary: {envelope.get('summary', '')}",
    ]
    trace = envelope.get("trace", {})
    if isinstance(trace, dict):
        decision_log = trace.get("decision_log", [])
        uncertainties = trace.get("uncertainties", [])
        artifacts = trace.get("artifacts", [])
        lines.extend(
            [
                f"Decision log entries: {len(decision_log) if isinstance(decision_log, list) else 0}",
                f"Uncertainties: {len(uncertainties) if isinstance(uncertainties, list) else 0}",
                f"Trace artifacts: {len(artifacts) if isinstance(artifacts, list) else 0}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _parse_json_object(raw_text: str) -> dict[str, Any] | None:
    stripped = raw_text.strip()
    if not stripped:
        return None
    candidates = [stripped]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _normalize_parsed(parsed: dict[str, Any], raw_text: str, status: str, summary_max_chars: int) -> dict[str, Any]:
    result = parsed.get("result", parsed.get("output", raw_text))
    return {
        "status": str(parsed.get("status", status)),
        "summary": str(parsed.get("summary") or _summarize_raw(raw_text, summary_max_chars)),
        "result": result,
        "trace": _normalize_trace(parsed),
    }


def _normalize_trace(parsed: dict[str, Any]) -> dict[str, Any]:
    trace = parsed.get("trace", {})
    if not isinstance(trace, dict):
        trace = {"raw_trace": trace}
    for field in DEFAULT_TRACE_FIELDS:
        if field in parsed and field not in trace:
            trace[field] = parsed[field]
    return trace


def _wrap_raw(raw_text: str, status: str, summary_max_chars: int) -> dict[str, Any]:
    return {
        "status": status,
        "summary": _summarize_raw(raw_text, summary_max_chars),
        "result": raw_text,
        "trace": {
            "decision_log": [],
            "uncertainties": [],
            "artifacts": [],
        },
    }


def _summarize_raw(raw_text: str, max_chars: int) -> str:
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped:
            return _truncate(stripped, max_chars)
    return ""


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise OutputContractError(f"output_contract.{field} must be a list of non-empty strings.")
    return list(value)
