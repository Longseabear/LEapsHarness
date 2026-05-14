# Workflow Contract Draft

Workflows are JSON files executed by the CLI runner.

The contract must stay workflow-agnostic. The runner should understand execution primitives, artifact references, adapters, vars, and checks. It should not understand weekly reports, research reports, code reviews, or any other business-specific domain.

Each workflow should define:

- `name`: stable workflow name.
- `artifact_root`: optional output root for generated run artifacts.
- `llm_adapters`: optional map of approved LLM adapters.
- `agent_adapters`: optional map of approved CLI agent adapters.
- `steps`: ordered list of executable steps.

Runtime config may be supplied separately with repeated CLI `--config` flags or API `config_path` / `config_paths`. Config files are applied left to right. Later configs override earlier `llm_adapters` and `agent_adapters` with the same names.

Workflows may also define `vars`. Runtime configs can override `vars`, and CLI `--var KEY=VALUE` or API `vars` can override them for a specific run.

Each step must define:

- `id`: stable step id used by later artifact references.
- `type`: built-in step type.
- Step-specific inputs.

Each step should produce:

- Explicit output paths or metadata.
- Captured logs where applicable.
- A `step.json` artifact with resolved outputs.

## Artifact References

Later steps may read earlier outputs through references shaped like:

```text
step_id.output_key
```

For example:

```json
{
  "from_artifact": "build_prompt.prompt",
  "format": "text"
}
```

Supported formats:

- `text`: read the artifact as UTF-8 text.
- `json`: parse JSON and re-emit formatted JSON text.
- `json_value`: parse JSON and pass the resulting object to the step.
- `path`: pass the artifact path as a string.

## Step Types

- `copy_file`: copy a file into the run artifact directory.
- `command`: run an internal command or CLI agent and capture stdout, stderr, and metadata.
- `prompt`: render a prompt template using literal data and previous artifacts.
- `agent`: pass input to a configured CLI agent adapter and capture its response.
- `for_each`: select a JSON list and run a configured CLI agent adapter once per item.
- `llm`: call an approved LLM adapter and store the response.
- `review`: run deterministic checks such as `not_empty`, `min_length`, and `contains`.

Add new built-in step types cautiously. If the behavior is specific to one workflow, prefer a `command` or `agent` step that calls workflow-local code. A built-in step should be generic enough to serve multiple workflows.

## Failure Policy

- A step failure should stop the workflow unless that step explicitly allows failure.
- A failed run should still write a manifest.
- Failure details should expose the step id, command metadata when available, stdout/stderr artifacts, and partial outputs.
- Every run writes both `manifest.json` and a human-readable `manifest.md`.

## Validation

Preview the merged execution plan before running:

```powershell
python -m leaps_harness plan .\workflows\weekly_report\workflow.json
```

`plan` does not create artifacts. It shows the merged workflow name, config paths, vars, artifact root, ordered steps, expected output keys, and validation errors.

Use the static validator before running an operated workflow:

```powershell
python -m leaps_harness validate .\workflows\weekly_report\workflow.json
```

With external adapter config:

```powershell
python -m leaps_harness validate .\workflows\weekly_report\workflow.json --config .\configs\claude_cli.example.json
```

With layered configs:

```powershell
python -m leaps_harness validate `
  .\workflows\weekly_report\workflow.json `
  --config .\configs\claude_cli.example.json `
  --config .\configs\local.override.json
```

Validation checks step shape, duplicate ids, known step types, common path fields, adapter references, and previous-step artifact references.

## Runtime Vars

Use `vars` for run-specific values such as input file paths:

```json
{
  "vars": {
    "weekly_input": "input/team_weekly_reports.json"
  }
}
```

Reference vars in workflow fields with template tokens:

```json
{
  "id": "collect_inputs",
  "type": "copy_file",
  "source": "{{ var.weekly_input }}"
}
```

Override from the CLI:

```powershell
python -m leaps_harness run .\workflows\weekly_report\workflow.json --var weekly_input=C:\data\team_weekly_reports.json
```

Use vars for environment-specific values, source paths, mode flags, and non-secret runtime choices. Do not use vars to hide complex business logic that belongs in workflow-local tools or templates.

## Command Adapter Input Modes

Command adapters default to `stdin`, which sends the prompt or agent input to the process on standard input.

Use `argument` for CLIs such as `claude -p`, where the harness should append the prompt or agent input as the final command argument:

```json
{
  "type": "command",
  "command": ["claude", "-p"],
  "input_mode": "argument"
}
```
