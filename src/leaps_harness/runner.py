from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import AgentAdapterError, build_agent_adapter
from .artifacts import ArtifactStore, safe_name
from .config import ConfigError, load_json_file, load_runtime_configs, merge_runtime_configs, normalize_config_paths
from .llm import LLMAdapterError, build_llm_adapter
from .template import flatten_values, render_template


class WorkflowError(RuntimeError):
    pass


class StepExecutionError(WorkflowError):
    pass


class WorkflowRunner:
    def __init__(
        self,
        workflow_path: str | Path,
        *,
        run_id: str | None = None,
        artifact_root: str | Path | None = None,
        config_path: str | Path | None = None,
        config_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        run_vars: dict[str, Any] | None = None,
    ) -> None:
        self.workflow_path = Path(workflow_path).resolve()
        self.workspace_dir = self.workflow_path.parent
        self.config_paths = normalize_config_paths(config_path, config_paths)
        self.config_path = self.config_paths[0] if self.config_paths else None
        self.workflow = self._load_workflow(self.workflow_path, self.config_paths)
        self.run_vars = self._merge_run_vars(self.workflow.get("vars", {}), run_vars or {})
        self.workflow["vars"] = self.run_vars
        self.run_id = run_id or self._new_run_id()
        artifact_root_value = artifact_root or self.workflow.get("artifact_root", ".runs")
        self.artifact_root = self._resolve_path(artifact_root_value)
        self.artifacts = ArtifactStore(self.artifact_root, self.run_id)
        self.outputs: dict[str, dict[str, Any]] = {}
        self.step_summaries: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        started_at = self._now()
        status = "succeeded"
        error: str | None = None

        try:
            for step in self.workflow.get("steps", []):
                self._run_step(step)
        except Exception as exc:
            status = "failed"
            error = str(exc)
            summary = self._summary(status, started_at, error)
            self.artifacts.write_manifest(summary)
            if isinstance(exc, WorkflowError):
                raise
            raise WorkflowError(str(exc)) from exc

        summary = self._summary(status, started_at, error)
        self.artifacts.write_manifest(summary)
        return summary

    def _run_step(self, step: dict[str, Any]) -> None:
        step_id = step.get("id")
        step_type = step.get("type")
        if not step_id or not isinstance(step_id, str):
            raise WorkflowError("Each step requires a string 'id'.")
        if not step_type or not isinstance(step_type, str):
            raise WorkflowError(f"Step '{step_id}' requires a string 'type'.")

        started_at = self._now()
        start_time = time.monotonic()
        try:
            if step_type == "copy_file":
                outputs = self._copy_file(step_id, step)
            elif step_type == "command":
                outputs = self._command(step_id, step)
            elif step_type == "prompt":
                outputs = self._prompt(step_id, step)
            elif step_type == "agent":
                outputs = self._agent(step_id, step)
            elif step_type == "for_each":
                outputs = self._for_each(step_id, step)
            elif step_type == "llm":
                outputs = self._llm(step_id, step)
            elif step_type == "review":
                outputs = self._review(step_id, step)
            elif step_type == "iterative_review":
                outputs = self._iterative_review(step_id, step)
            else:
                raise StepExecutionError(f"Unsupported step type '{step_type}' in step '{step_id}'.")
        except Exception as exc:
            elapsed = round(time.monotonic() - start_time, 3)
            self.step_summaries.append(
                {
                    "id": step_id,
                    "type": step_type,
                    "status": "failed",
                    "started_at": started_at,
                    "elapsed_seconds": elapsed,
                    "error": str(exc),
                }
            )
            if isinstance(exc, WorkflowError):
                raise
            raise StepExecutionError(f"Step '{step_id}' failed: {exc}") from exc

        elapsed = round(time.monotonic() - start_time, 3)
        self.outputs[step_id] = outputs
        self.artifacts.write_json(step_id, "step.json", {"step": step, "outputs": outputs})
        self.step_summaries.append(
            {
                "id": step_id,
                "type": step_type,
                "status": "succeeded",
                "started_at": started_at,
                "elapsed_seconds": elapsed,
                "outputs": outputs,
            }
        )

    def _copy_file(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        source_value = step.get("source")
        if not source_value:
            raise StepExecutionError(f"Step '{step_id}' requires 'source'.")
        source = self._resolve_path(render_template(str(source_value), self._values()))
        if not source.exists():
            raise StepExecutionError(f"Step '{step_id}' source does not exist: {source}")
        artifact_name = step.get("artifact") or source.name
        path = self.artifacts.copy_file(step_id, str(artifact_name), source)
        return {"path": str(path.resolve())}

    def _command(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        command = step.get("command")
        if not isinstance(command, list) or not command:
            raise StepExecutionError(f"Step '{step_id}' requires non-empty list 'command'.")

        values = self._values()
        rendered_command = [render_template(str(part), values) for part in command]
        cwd = self._resolve_path(step.get("cwd", "."))
        env = os.environ.copy()
        env.update({key: render_template(str(value), values) for key, value in step.get("env", {}).items()})
        timeout_seconds = int(step.get("timeout_seconds", 120))
        stdin = self._resolve_value(step["stdin"]) if "stdin" in step else None

        try:
            completed = subprocess.run(
                rendered_command,
                cwd=cwd,
                env=env,
                input=stdin,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except OSError as exc:
            raise StepExecutionError(f"Step '{step_id}' command failed to start: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise StepExecutionError(f"Step '{step_id}' timed out after {timeout_seconds} seconds.") from exc

        stdout_path = self.artifacts.write_text(
            step_id,
            step.get("stdout_artifact", "stdout.txt"),
            completed.stdout,
        )
        stderr_path = self.artifacts.write_text(
            step_id,
            step.get("stderr_artifact", "stderr.txt"),
            completed.stderr,
        )
        metadata = {
            "command": rendered_command,
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "timeout_seconds": timeout_seconds,
        }
        metadata_path = self.artifacts.write_json(step_id, "command.json", metadata)

        outputs = {
            "stdout": str(stdout_path.resolve()),
            "stderr": str(stderr_path.resolve()),
            "metadata": str(metadata_path.resolve()),
            "returncode": completed.returncode,
        }
        if completed.returncode != 0 and not step.get("allow_failure", False):
            raise StepExecutionError(f"Step '{step_id}' command exited with code {completed.returncode}.")
        return outputs

    def _prompt(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        template_value = step.get("template")
        if not template_value:
            raise StepExecutionError(f"Step '{step_id}' requires 'template'.")
        template_path = self._resolve_path(render_template(str(template_value), self._values()))
        if not template_path.exists():
            raise StepExecutionError(f"Step '{step_id}' template does not exist: {template_path}")

        template_text = template_path.read_text(encoding="utf-8")
        values = self._values()
        for key, spec in step.get("data", {}).items():
            values[key] = self._stringify(self._resolve_value(spec))

        prompt = render_template(template_text, values)
        prompt_path = self.artifacts.write_text(step_id, step.get("artifact", "prompt.txt"), prompt)
        return {"prompt": str(prompt_path.resolve())}

    def _llm(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        prompt_spec = step.get("prompt")
        if prompt_spec is None:
            raise StepExecutionError(f"Step '{step_id}' requires 'prompt'.")
        prompt = self._stringify(self._resolve_value(prompt_spec))
        adapter_name = step.get("adapter", "default")
        adapters = self.workflow.get("llm_adapters", {"default": {"type": "echo"}})
        adapter_config = adapters.get(adapter_name)
        if adapter_config is None:
            raise StepExecutionError(f"Step '{step_id}' references unknown LLM adapter '{adapter_name}'.")

        try:
            adapter = build_llm_adapter(adapter_name, adapter_config, self.workspace_dir, self._values())
            result = adapter.generate(prompt)
        except LLMAdapterError as exc:
            raise StepExecutionError(f"Step '{step_id}' LLM adapter failed: {exc}") from exc

        response_path = self.artifacts.write_text(step_id, step.get("artifact", "response.txt"), result.text)
        metadata_path = self.artifacts.write_json(step_id, "llm.json", result.metadata)
        return {"response": str(response_path.resolve()), "metadata": str(metadata_path.resolve())}

    def _agent(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        input_text = self._render_input_text(step, self._values(), required_field="input")
        adapter_name = step.get("adapter", "default")
        adapters = self.workflow.get("agent_adapters", {"default": {"type": "echo"}})
        adapter_config = adapters.get(adapter_name)
        if adapter_config is None:
            raise StepExecutionError(f"Step '{step_id}' references unknown agent adapter '{adapter_name}'.")

        try:
            adapter = build_agent_adapter(adapter_name, adapter_config, self.workspace_dir, self._values())
            result = adapter.run(input_text)
        except AgentAdapterError as exc:
            raise StepExecutionError(f"Step '{step_id}' agent adapter failed: {exc}") from exc

        input_path = self.artifacts.write_text(step_id, step.get("input_artifact", "agent_input.txt"), input_text)
        response_path = self.artifacts.write_text(step_id, step.get("artifact", "agent_response.txt"), result.text)
        metadata_path = self.artifacts.write_json(step_id, "agent.json", result.metadata)
        return {
            "input": str(input_path.resolve()),
            "response": str(response_path.resolve()),
            "metadata": str(metadata_path.resolve()),
        }

    def _for_each(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        if "items" not in step:
            raise StepExecutionError(f"Step '{step_id}' requires 'items'.")
        items_value = self._resolve_value(step["items"])
        items = self._select_json_path(items_value, step.get("item_path"))
        if not isinstance(items, list):
            raise StepExecutionError(f"Step '{step_id}' items must resolve to a list.")

        adapter_name = step.get("adapter", "default")
        adapters = self.workflow.get("agent_adapters", {"default": {"type": "echo"}})
        adapter_config = adapters.get(adapter_name)
        if adapter_config is None:
            raise StepExecutionError(f"Step '{step_id}' references unknown agent adapter '{adapter_name}'.")

        template_value = step.get("input_template")
        if not template_value:
            raise StepExecutionError(f"Step '{step_id}' requires 'input_template'.")
        template_path = self._resolve_path(render_template(str(template_value), self._values()))
        if not template_path.exists():
            raise StepExecutionError(f"Step '{step_id}' input template does not exist: {template_path}")
        template_text = template_path.read_text(encoding="utf-8")

        item_results: list[dict[str, Any]] = []
        combined_sections: list[str] = []
        allow_item_failure = bool(step.get("allow_item_failure", False))
        for index, item in enumerate(items):
            item_id = self._item_id(item, index)
            child_step_id = f"{step_id}_{safe_name(item_id)}"
            item_values = self._item_values(item, index)
            values = self._values()
            values.update(item_values)
            input_text = render_template(template_text, values)
            input_path = self.artifacts.write_text(child_step_id, step.get("input_artifact", "agent_input.txt"), input_text)

            try:
                adapter = build_agent_adapter(adapter_name, adapter_config, self.workspace_dir, values)
                result = adapter.run(input_text)
            except AgentAdapterError as exc:
                error_path = self.artifacts.write_json(
                    child_step_id,
                    "agent_error.json",
                    {"error": str(exc), "item": item, "index": index},
                )
                item_results.append(
                    {
                        "item_id": item_id,
                        "status": "failed",
                        "input": str(input_path.resolve()),
                        "error": str(error_path.resolve()),
                    }
                )
                if not allow_item_failure:
                    raise StepExecutionError(f"Step '{step_id}' item '{item_id}' failed: {exc}") from exc
                continue

            response_path = self.artifacts.write_text(child_step_id, step.get("artifact", "agent_response.md"), result.text)
            metadata_path = self.artifacts.write_json(child_step_id, "agent.json", result.metadata)
            item_results.append(
                {
                    "item_id": item_id,
                    "status": "succeeded",
                    "input": str(input_path.resolve()),
                    "response": str(response_path.resolve()),
                    "metadata": str(metadata_path.resolve()),
                }
            )
            combined_sections.append(result.text.strip())

        results_path = self.artifacts.write_json(step_id, step.get("results_artifact", "results.json"), {"items": item_results})
        combined_path = self.artifacts.write_text(
            step_id,
            step.get("combined_artifact", "combined.md"),
            "\n\n".join(section for section in combined_sections if section),
        )
        return {
            "results": str(results_path.resolve()),
            "combined": str(combined_path.resolve()),
            "count": len(item_results),
        }

    def _review(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        if "target" not in step:
            raise StepExecutionError(f"Step '{step_id}' requires 'target'.")
        target_text = self._stringify(self._resolve_value(step["target"]))
        checks = step.get("checks") or [{"type": "not_empty"}]
        if not isinstance(checks, list):
            raise StepExecutionError(f"Step '{step_id}' checks must be a list.")

        check_results = [self._run_check(target_text, check) for check in checks]
        passed = all(result["passed"] or not result["required"] for result in check_results)
        review = {
            "passed": passed,
            "target_length": len(target_text),
            "checks": check_results,
        }
        review_path = self.artifacts.write_json(step_id, step.get("artifact", "review.json"), review)
        report_path = self.artifacts.write_text(step_id, step.get("report_artifact", "review.md"), self._render_review(review))
        if not passed and step.get("fail_on_error", True):
            raise StepExecutionError(f"Step '{step_id}' review failed.")
        return {
            "review": str(review_path.resolve()),
            "report": str(report_path.resolve()),
            "passed": passed,
        }

    def _iterative_review(self, step_id: str, step: dict[str, Any]) -> dict[str, Any]:
        max_attempts = int(step.get("max_attempts", 3))
        if max_attempts < 1:
            raise StepExecutionError(f"Step '{step_id}' max_attempts must be at least 1.")

        producer_template = self._read_template(step_id, step, "producer_template")
        reviewer_template = self._read_template(step_id, step, "reviewer_template")
        producer_adapter_name = step.get("producer_adapter", "default")
        reviewer_adapter_name = step.get("reviewer_adapter", "default")
        producer_config = self._adapter_config(step_id, "agent_adapters", producer_adapter_name)
        reviewer_config = self._adapter_config(step_id, "llm_adapters", reviewer_adapter_name)
        data_values = self._step_data_values(step)
        previous_feedback = str(step.get("initial_feedback", ""))
        history: list[dict[str, Any]] = []
        final_text = ""
        final_review: dict[str, Any] = {}
        passed = False

        for attempt in range(1, max_attempts + 1):
            attempt_step_id = f"{step_id}_attempt_{attempt}"
            values = self._values()
            values.update(data_values)
            values.update(
                {
                    "attempt": str(attempt),
                    "max_attempts": str(max_attempts),
                    "previous_feedback": previous_feedback,
                    "history_json": json.dumps(history, indent=2, sort_keys=True),
                }
            )
            producer_prompt = render_template(producer_template, values)
            producer_prompt_path = self.artifacts.write_text(attempt_step_id, "producer_prompt.txt", producer_prompt)

            try:
                producer = build_agent_adapter(producer_adapter_name, producer_config, self.workspace_dir, values)
                producer_result = producer.run(producer_prompt)
            except AgentAdapterError as exc:
                raise StepExecutionError(f"Step '{step_id}' producer failed on attempt {attempt}: {exc}") from exc

            final_text = producer_result.text
            draft_path = self.artifacts.write_text(attempt_step_id, step.get("draft_artifact", "draft.md"), final_text)
            producer_metadata_path = self.artifacts.write_json(attempt_step_id, "producer_agent.json", producer_result.metadata)

            review_values = dict(values)
            review_values["draft"] = final_text
            reviewer_prompt = render_template(reviewer_template, review_values)
            reviewer_prompt_path = self.artifacts.write_text(attempt_step_id, "reviewer_prompt.txt", reviewer_prompt)

            try:
                reviewer = build_llm_adapter(reviewer_adapter_name, reviewer_config, self.workspace_dir, review_values)
                reviewer_result = reviewer.generate(reviewer_prompt)
            except LLMAdapterError as exc:
                raise StepExecutionError(f"Step '{step_id}' reviewer failed on attempt {attempt}: {exc}") from exc

            review_raw_path = self.artifacts.write_text(attempt_step_id, "review_raw.txt", reviewer_result.text)
            reviewer_metadata_path = self.artifacts.write_json(attempt_step_id, "reviewer_llm.json", reviewer_result.metadata)
            final_review = self._parse_iterative_review(step_id, attempt, reviewer_result.text)
            review_path = self.artifacts.write_json(attempt_step_id, step.get("review_artifact", "review.json"), final_review)
            passed = self._iterative_review_passed(final_review)
            feedback = str(final_review.get("feedback", ""))
            history.append(
                {
                    "attempt": attempt,
                    "passed": passed,
                    "status": final_review.get("status"),
                    "feedback": feedback,
                    "draft": str(draft_path.resolve()),
                    "review": str(review_path.resolve()),
                    "producer_prompt": str(producer_prompt_path.resolve()),
                    "reviewer_prompt": str(reviewer_prompt_path.resolve()),
                    "review_raw": str(review_raw_path.resolve()),
                    "producer_metadata": str(producer_metadata_path.resolve()),
                    "reviewer_metadata": str(reviewer_metadata_path.resolve()),
                }
            )
            if passed:
                break
            previous_feedback = feedback

        history_path = self.artifacts.write_json(step_id, step.get("history_artifact", "iteration_history.json"), history)
        final_path = self.artifacts.write_text(step_id, step.get("final_artifact", "final.md"), final_text)
        final_review_path = self.artifacts.write_json(step_id, step.get("final_review_artifact", "final_review.json"), final_review)

        if not passed and step.get("fail_on_max_attempts", True):
            raise StepExecutionError(f"Step '{step_id}' did not pass review after {max_attempts} attempts.")

        return {
            "final": str(final_path.resolve()),
            "history": str(history_path.resolve()),
            "review": str(final_review_path.resolve()),
            "attempts": len(history),
            "passed": passed,
        }

    def _resolve_value(self, spec: Any) -> Any:
        if isinstance(spec, dict):
            if "from_artifact" in spec:
                artifact_path = self._artifact_path(str(spec["from_artifact"]))
                value_format = spec.get("format", "text")
                if value_format == "path":
                    return str(artifact_path)
                if value_format == "text":
                    return artifact_path.read_text(encoding="utf-8")
                if value_format == "json":
                    parsed = json.loads(artifact_path.read_text(encoding="utf-8"))
                    return json.dumps(parsed, indent=2, sort_keys=True)
                if value_format == "json_value":
                    return json.loads(artifact_path.read_text(encoding="utf-8"))
                raise WorkflowError(f"Unsupported artifact format '{value_format}'.")
            if "literal" in spec:
                return spec["literal"]
            return {key: self._resolve_value(value) for key, value in spec.items()}
        if isinstance(spec, str):
            return render_template(spec, self._values())
        return spec

    def _read_template(self, step_id: str, step: dict[str, Any], field: str) -> str:
        value = step.get(field)
        if not value:
            raise StepExecutionError(f"Step '{step_id}' requires '{field}'.")
        template_path = self._resolve_path(render_template(str(value), self._values()))
        if not template_path.exists():
            raise StepExecutionError(f"Step '{step_id}' {field} does not exist: {template_path}")
        return template_path.read_text(encoding="utf-8")

    def _adapter_config(self, step_id: str, adapter_field: str, adapter_name: str) -> dict[str, Any]:
        adapters = self.workflow.get(adapter_field, {"default": {"type": "echo"}})
        if not isinstance(adapters, dict):
            raise StepExecutionError(f"Workflow field '{adapter_field}' must be an object.")
        adapter_config = adapters.get(adapter_name)
        if adapter_config is None:
            raise StepExecutionError(f"Step '{step_id}' references unknown adapter '{adapter_name}'.")
        if not isinstance(adapter_config, dict):
            raise StepExecutionError(f"Adapter '{adapter_name}' must be an object.")
        return adapter_config

    def _step_data_values(self, step: dict[str, Any]) -> dict[str, str]:
        values: dict[str, str] = {}
        for key, spec in step.get("data", {}).items():
            values[key] = self._stringify(self._resolve_value(spec))
        return values

    @staticmethod
    def _parse_iterative_review(step_id: str, attempt: int, review_text: str) -> dict[str, Any]:
        stripped = review_text.strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start : end + 1]
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise StepExecutionError(
                f"Step '{step_id}' reviewer returned invalid JSON on attempt {attempt}: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise StepExecutionError(f"Step '{step_id}' reviewer JSON must be an object on attempt {attempt}.")
        if "status" not in parsed and "passed" not in parsed:
            raise StepExecutionError(f"Step '{step_id}' reviewer JSON requires 'status' or 'passed'.")
        return parsed

    @staticmethod
    def _iterative_review_passed(review: dict[str, Any]) -> bool:
        if isinstance(review.get("passed"), bool):
            return bool(review["passed"])
        status = str(review.get("status", "")).strip().lower()
        return status in {"success", "passed", "pass", "ok"}

    def _artifact_path(self, reference: str) -> Path:
        try:
            step_id, output_key = reference.split(".", 1)
        except ValueError as exc:
            raise WorkflowError(f"Artifact reference must be 'step.output': {reference}") from exc
        if step_id not in self.outputs:
            raise WorkflowError(f"Artifact reference uses unknown step '{step_id}'.")
        if output_key not in self.outputs[step_id]:
            raise WorkflowError(f"Artifact reference uses unknown output '{reference}'.")
        path = Path(str(self.outputs[step_id][output_key]))
        if not path.exists():
            raise WorkflowError(f"Artifact path does not exist for reference '{reference}': {path}")
        return path

    def _render_input_text(self, step: dict[str, Any], values: dict[str, str], required_field: str) -> str:
        if "input_template" in step:
            template_path = self._resolve_path(render_template(str(step["input_template"]), values))
            if not template_path.exists():
                raise StepExecutionError(f"Input template does not exist: {template_path}")
            template_text = template_path.read_text(encoding="utf-8")
            data_values = dict(values)
            for key, spec in step.get("data", {}).items():
                data_values[key] = self._stringify(self._resolve_value(spec))
            return render_template(template_text, data_values)
        if required_field not in step:
            raise StepExecutionError(f"Step requires '{required_field}' or 'input_template'.")
        return self._stringify(self._resolve_value(step[required_field]))

    @staticmethod
    def _select_json_path(value: Any, path: Any) -> Any:
        if path in (None, ""):
            return value
        current = value
        for part in str(path).split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
                continue
            raise WorkflowError(f"JSON path '{path}' could not be resolved at '{part}'.")
        return current

    @staticmethod
    def _item_id(item: Any, index: int) -> str:
        if isinstance(item, dict):
            for key in ("id", "title", "name"):
                if key in item and item[key]:
                    return str(item[key])
        return f"item-{index + 1}"

    @staticmethod
    def _item_values(item: Any, index: int) -> dict[str, str]:
        values = {
            "item_json": json.dumps(item, indent=2, sort_keys=True),
            "item.index": str(index),
            "item.index1": str(index + 1),
        }
        if isinstance(item, dict):
            values.update(flatten_values({"item": item}))
        else:
            values["item.value"] = str(item)
        return values

    @staticmethod
    def _run_check(target_text: str, check: Any) -> dict[str, Any]:
        if not isinstance(check, dict):
            raise WorkflowError("Review check must be an object.")
        check_type = check.get("type")
        required = bool(check.get("required", True))
        if check_type == "not_empty":
            passed = bool(target_text.strip())
            message = "target is not empty" if passed else "target is empty"
        elif check_type == "min_length":
            value = int(check.get("value", 1))
            passed = len(target_text.strip()) >= value
            message = f"target length is at least {value}" if passed else f"target length is below {value}"
        elif check_type == "contains":
            value = str(check.get("value", ""))
            case_sensitive = bool(check.get("case_sensitive", True))
            haystack = target_text if case_sensitive else target_text.lower()
            needle = value if case_sensitive else value.lower()
            passed = needle in haystack
            message = f"target contains {value!r}" if passed else f"target does not contain {value!r}"
        else:
            raise WorkflowError(f"Unsupported review check type '{check_type}'.")
        return {
            "type": check_type,
            "required": required,
            "passed": passed,
            "message": message,
        }

    @staticmethod
    def _render_review(review: dict[str, Any]) -> str:
        lines = [
            "# Review",
            "",
            f"- Passed: `{review['passed']}`",
            f"- Target length: `{review['target_length']}`",
            "",
            "## Checks",
            "",
        ]
        for check in review["checks"]:
            lines.append(
                f"- `{check['type']}`: `{check['passed']}` "
                f"(required: `{check['required']}`) - {check['message']}"
            )
        lines.append("")
        return "\n".join(lines)

    def _values(self) -> dict[str, str]:
        data = {
            "run": {
                "id": self.run_id,
                "artifact_dir": str(self.artifacts.run_dir.resolve()),
            },
            "workflow": {
                "name": self.workflow.get("name", self.workflow_path.stem),
                "path": str(self.workflow_path),
                "workspace_dir": str(self.workspace_dir),
            },
            "python": {
                "executable": sys.executable,
            },
            "var": self.run_vars,
            "artifact": self.outputs,
        }
        return flatten_values(data)

    def _summary(self, status: str, started_at: str, error: str | None) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "workflow": self.workflow.get("name", self.workflow_path.stem),
            "workflow_path": str(self.workflow_path),
            "config_path": str(self.config_path) if self.config_path else None,
            "config_paths": [str(path) for path in self.config_paths],
            "vars": self.run_vars,
            "run_id": self.run_id,
            "status": status,
            "started_at": started_at,
            "finished_at": self._now(),
            "artifact_dir": str(self.artifacts.run_dir.resolve()),
            "manifest_path": str(self.artifacts.manifest_path.resolve()),
            "readable_manifest_path": str(self.artifacts.readable_manifest_path.resolve()),
            "steps": self.step_summaries,
        }
        if error:
            summary["error"] = error
        return summary

    def _resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.workspace_dir / path
        return path.resolve()

    @staticmethod
    def _merge_run_vars(workflow_vars: Any, run_vars: dict[str, Any]) -> dict[str, Any]:
        if workflow_vars is None:
            workflow_vars = {}
        if not isinstance(workflow_vars, dict):
            raise WorkflowError("Workflow field 'vars' must be an object.")
        merged = dict(workflow_vars)
        merged.update(run_vars)
        return merged

    @staticmethod
    def _load_workflow(path: Path, config_paths: list[Path] | None = None) -> dict[str, Any]:
        if not path.exists():
            raise WorkflowError(f"Workflow does not exist: {path}")
        try:
            data = load_json_file(path)
            configs = load_runtime_configs(config_paths or [])
            data = merge_runtime_configs(data, configs)
        except ConfigError as exc:
            raise WorkflowError(str(exc)) from exc
        if not isinstance(data, dict):
            raise WorkflowError("Workflow JSON must be an object.")
        if not isinstance(data.get("steps", []), list):
            raise WorkflowError("Workflow 'steps' must be a list.")
        return data

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, indent=2, sort_keys=True)

    @staticmethod
    def _new_run_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{stamp}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
