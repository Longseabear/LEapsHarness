# LEaps Custom Harness

CLI-first orchestration harness for closed-network AI workflows.

This is a general-purpose harness, not a weekly-report-only tool. The weekly report workflow is the first operated vertical slice used to prove the runtime shape. New work should keep the core runtime reusable for other document generation, research, code generation, and internal operations workflows.

The harness provides:

- JSON workflow definitions.
- Sequential step execution.
- File-based artifacts and run manifests.
- CLI command steps for internal tools or agents.
- Prompt construction with stored source data.
- LLM adapter boundaries with an offline `echo` adapter and a command-backed adapter.

No runtime dependency outside the Python standard library is required.

## Design Goals

- Keep workflows portable across closed-network environments.
- Keep LLMs, CLI agents, and private tools behind adapters.
- Keep business-specific logic inside workflows, templates, tools, and configs rather than in the core runner.
- Preserve every important intermediate artifact for debugging, audit, retry, and review.
- Start from CLI-proven workflows, then expose them through a thin API only after the execution path is stable.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the harness-oriented agent architecture and control-plane principles.

## Generalization Rules

When adding features, prefer reusable runtime capabilities over workflow-specific behavior.

- Add a step type only when at least two workflows could plausibly use it.
- Put workflow-specific parsing, normalization, and drafting in `workflows/<name>/tools/`.
- Put reusable adapter behavior in `src/leaps_harness/agent.py`, `llm.py`, or future adapter modules.
- Use `vars` and layered `--config` files for environment-specific values.
- Keep prompt templates in the workflow directory unless they are genuinely shared.
- Do not hard-code weekly-report assumptions in the runner, API, adapters, manifest writer, or validator.
- If a feature is only needed by one workflow, implement it as a command/tool step first.

## Project Layout

The intended file structure is documented in [docs/FILE_STRUCTURE.md](docs/FILE_STRUCTURE.md).

Current growth points:

- `configs/`: non-secret runtime and adapter configuration templates.
- `docs/`: structure, workflow contracts, and operator guidance.
- `examples/`: runnable reference workflows.
- `workflows/`: first-party workflows intended for real use.
- `src/leaps_harness/`: CLI runner and harness runtime code.
- `tests/`: focused verification for runner behavior.

## Quick Start

The current runnable workflows are `workflows/weekly_report` and `workflows/document_digest`. Treat them as reference implementations for how operated workflows should be structured without making the core runtime domain-specific.

From PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness plan .\workflows\weekly_report\workflow.json
python -m leaps_harness validate .\workflows\weekly_report\workflow.json
python -m leaps_harness run .\workflows\weekly_report\workflow.json --run-id demo
```

The run writes artifacts under:

```text
workflows/weekly_report/.runs/demo/
```

Open `manifest.json` in that run directory to inspect the executed steps and artifacts.

Override workflow inputs with runtime vars:

```powershell
python -m leaps_harness run `
  .\workflows\weekly_report\workflow.json `
  --var weekly_input=C:\data\team_weekly_reports.json `
  --run-id demo
```

Preview merged configs, vars, and steps without running:

```powershell
python -m leaps_harness plan `
  .\workflows\weekly_report\workflow.json `
  --config .\configs\claude_cli.example.json `
  --var weekly_input=C:\data\team_weekly_reports.json
```

## Workflow Shape

Workflows are JSON files with a `name`, optional `artifact_root`, optional `vars`, optional adapters, and ordered `steps`.

Supported step types:

- `copy_file`: copy a source file into the run artifacts.
- `command`: run a local command or CLI agent and capture stdout, stderr, and metadata.
- `prompt`: render a template using literal values or previous artifacts.
- `agent`: send input to a CLI agent adapter and store the response.
- `for_each`: run a CLI agent adapter once per item in a JSON list.
- `llm`: send a prompt to an LLM adapter and store the response.
- `review`: run deterministic checks against an artifact.
- `iterative_review`: run a producer agent and reviewer LLM in a bounded feedback loop until the reviewer passes the result.

Workflow paths are resolved relative to the workflow file.

Workflow-specific code should live beside the workflow:

```text
workflows/<workflow_name>/
  workflow.json
  input/
  templates/
  tools/
  schemas/
```

The harness runtime should not need to know what the workflow is about.

## Feedback Loops

Use `iterative_review` when a workflow needs a producer to revise output based on structured reviewer feedback.

The step keeps each attempt as artifacts:

- producer prompt
- draft output
- reviewer prompt
- raw reviewer response
- parsed review JSON
- per-attempt metadata
- final output and iteration history

The reviewer must return JSON with either `status` or `passed`. The run succeeds when `status` is `success`, `passed`, `pass`, or `ok`, or when `"passed": true`.

Minimal shape:

```json
{
  "id": "revise_until_passed",
  "type": "iterative_review",
  "producer_adapter": "writer_agent",
  "reviewer_adapter": "style_reviewer",
  "producer_template": "templates/writer_prompt.txt",
  "reviewer_template": "templates/reviewer_prompt.txt",
  "max_attempts": 4,
  "data": {
    "source": {
      "from_artifact": "collect.path",
      "format": "text"
    }
  }
}
```

See [examples/style_review_loop](examples/style_review_loop) for a Claude-backed producer/reviewer example.
See [examples/weekly_style_transfer](examples/weekly_style_transfer) for a weekly-report style-transfer evaluation with style samples, hidden reference calibration, and a deterministic contract validator.

## Prompt Builder

Use the prompt builder when you want to keep a reusable prompt template and swap values with a dictionary.

Template:

```text
Write a report for {{ person.name }}.

Role: {{ person.role }}

Work units:
{{ work_units }}
```

Values:

```json
{
  "person": {
    "name": "Mina",
    "role": "파트장"
  },
  "work_units": [
    {
      "title": "API gateway cache",
      "status": "in progress"
    }
  ]
}
```

Render from the CLI:

```powershell
python -m leaps_harness render-prompt .\template.txt --values .\values.json --output .\prompt.txt
```

Override one value without editing the JSON:

```powershell
python -m leaps_harness render-prompt .\template.txt --values .\values.json --var person.role=그룹장
```

Use from Python:

```python
from leaps_harness import build_prompt

prompt = build_prompt(
    "Write a report for {{ person.name }}.\n\n{{ work_units }}",
    {
        "person": {"name": "Mina"},
        "work_units": [{"title": "API gateway cache"}],
    },
)
```

## LLM Adapters

The default adapter type is `echo`, which is useful for offline tests and harness development.

For approved local or internal LLM CLIs, use a command adapter:

```json
{
  "llm_adapters": {
    "default": {
      "type": "command",
      "command": ["claude", "-p"],
      "input_mode": "argument",
      "timeout_seconds": 300
    }
  }
}
```

By default, command adapters send the prompt on stdin. Set `input_mode` to `argument` for CLIs such as `claude -p` where the prompt should be appended as the final command argument. stdout is stored as the LLM response.

See [configs/claude_cli.example.json](configs/claude_cli.example.json) for a `claude -p` backed LLM and CLI agent adapter example.

You can inject approved adapter settings at runtime without editing the workflow:

```powershell
python -m leaps_harness run `
  .\workflows\weekly_report\workflow.json `
  --config .\configs\claude_cli.example.json `
  --run-id weekly-report-internal
```

`--config` may be repeated. Config files are applied left to right, and later files override earlier `llm_adapters` and `agent_adapters` with the same names:

```powershell
python -m leaps_harness run `
  .\workflows\weekly_report\workflow.json `
  --config .\configs\claude_cli.example.json `
  --config .\configs\local.override.json `
  --run-id weekly-report-internal
```

Configs may also provide `vars`, such as `weekly_input`, and CLI `--var` values override workflow/config vars.

## API Wrapper

After a workflow works from the CLI, it can be served through the thin stdlib API wrapper:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness serve --host 127.0.0.1 --port 8765 --workflow-root .
```

See [docs/API.md](docs/API.md) for request examples.

## Python Library Usage

The harness can also be used directly from Python code.

```python
from leaps_harness import plan_workflow, run_workflow, validate_workflow

workflow = "workflows/document_digest/workflow.json"

plan = plan_workflow(
    workflow,
    configs=["configs/claude_cli.example.json"],
    vars={"document_input": r"C:\data\source.md"},
)
if not plan.valid:
    raise RuntimeError(plan.validation_errors)

validation = validate_workflow(workflow, configs=["configs/claude_cli.example.json"])
if not validation.valid:
    raise RuntimeError(validation.errors)

result = run_workflow(
    workflow,
    configs=["configs/claude_cli.example.json"],
    vars={"document_input": r"C:\data\source.md"},
    run_id="doc-001",
)

print(result.status)
print(result.artifact_dir)
print(result.readable_manifest_path)
```

Public API objects:

- `WorkflowPlan`: merged plan, validation errors, step list, artifact root.
- `ValidationResult`: `valid` plus validation error list.
- `WorkflowResult`: status, run id, artifact paths, step summaries, raw manifest summary.

## Development Checks

Run tests with:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests
```

Before committing a workflow change, run:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness plan .\workflows\weekly_report\workflow.json
python -m leaps_harness validate .\workflows\weekly_report\workflow.json
python -m leaps_harness run .\workflows\weekly_report\workflow.json --run-id smoke
```

Generated `.runs/` directories are ignored by git and should not be committed.
