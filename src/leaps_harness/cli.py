from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .api import serve
from .config import ConfigError, load_json_file
from .planning import build_workflow_plan
from .prompt_builder import PromptBuildError, build_prompt_from_file
from .runner import WorkflowError, WorkflowRunner
from .validation import validate_workflow_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leaps-harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a workflow JSON file.")
    run_parser.add_argument("workflow", type=Path, help="Path to workflow.json.")
    run_parser.add_argument("--run-id", help="Optional run id for artifact output.")
    run_parser.add_argument("--artifact-root", type=Path, help="Override artifact root directory.")
    run_parser.add_argument(
        "--config",
        type=Path,
        action="append",
        default=[],
        help="Runtime config JSON for adapters. May be repeated; later files override earlier files.",
    )
    run_parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Runtime variable override. May be repeated.",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate a workflow JSON file without running it.")
    validate_parser.add_argument("workflow", type=Path, help="Path to workflow.json.")
    validate_parser.add_argument(
        "--config",
        type=Path,
        action="append",
        default=[],
        help="Runtime config JSON for adapters. May be repeated; later files override earlier files.",
    )

    plan_parser = subparsers.add_parser("plan", help="Print the merged workflow execution plan without running it.")
    plan_parser.add_argument("workflow", type=Path, help="Path to workflow.json.")
    plan_parser.add_argument("--artifact-root", type=Path, help="Override artifact root directory.")
    plan_parser.add_argument(
        "--config",
        type=Path,
        action="append",
        default=[],
        help="Runtime config JSON for adapters. May be repeated; later files override earlier files.",
    )
    plan_parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Runtime variable override. May be repeated.",
    )

    render_prompt_parser = subparsers.add_parser(
        "render-prompt",
        help="Render a prompt template with JSON values and KEY=VALUE overrides.",
    )
    render_prompt_parser.add_argument("template", type=Path, help="Path to a prompt template file.")
    render_prompt_parser.add_argument("--values", type=Path, help="JSON object with template values.")
    render_prompt_parser.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Template value override. May be repeated.",
    )
    render_prompt_parser.add_argument("--output", type=Path, help="Optional output file for the rendered prompt.")

    serve_parser = subparsers.add_parser("serve", help="Run the stdlib HTTP API wrapper.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    serve_parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    serve_parser.add_argument(
        "--workflow-root",
        type=Path,
        default=Path.cwd(),
        help="Base directory for relative workflow_path values.",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            runner = WorkflowRunner(
                args.workflow,
                run_id=args.run_id,
                artifact_root=args.artifact_root,
                config_paths=args.config,
                run_vars=_parse_vars(args.var),
            )
            summary = runner.run()
        except WorkflowError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    if args.command == "validate":
        errors = validate_workflow_file(args.workflow, config_paths=args.config)
        if errors:
            print("Workflow validation failed:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(f"Workflow validation passed: {args.workflow}")
        return 0

    if args.command == "plan":
        try:
            plan = build_workflow_plan(
                args.workflow,
                config_paths=args.config,
                run_vars=_parse_vars(args.var),
                artifact_root=args.artifact_root,
            )
        except (ConfigError, WorkflowError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 1 if plan["validation_errors"] else 0

    if args.command == "render-prompt":
        try:
            values = load_json_file(args.values) if args.values else {}
            values.update(_parse_vars(args.var))
            prompt = build_prompt_from_file(args.template, values)
        except (ConfigError, PromptBuildError, WorkflowError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if args.output:
            args.output.write_text(prompt, encoding="utf-8", newline="\n")
        else:
            print(prompt)
        return 0

    if args.command == "serve":
        serve(args.host, args.port, args.workflow_root)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _parse_vars(pairs: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise WorkflowError(f"Invalid --var value '{pair}'. Expected KEY=VALUE.")
        key, value = pair.split("=", 1)
        if not key:
            raise WorkflowError("Invalid --var value. KEY must not be empty.")
        values[key] = value
    return values
