# Prompt Builder

The Prompt Builder renders reusable prompt templates with dictionary values.

Use it when a workflow or service needs stable prompt structure while changing only runtime data, such as person fields, work units, source documents, style packets, review feedback, or policy constraints.

The builder is intentionally small:

- template syntax is `{{ key }}`
- nested dictionaries can be referenced with dot paths such as `{{ person.name }}`
- dictionaries and lists can be inserted as formatted JSON
- missing values fail fast
- rendering is available from Python and the CLI

## Template Syntax

Template:

```text
Write a weekly report for {{ person.name }}.

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

Rendered prompt:

```text
Write a weekly report for Mina.

Role: 파트장

Work units:
[
  {
    "status": "in progress",
    "title": "API gateway cache"
  }
]
```

## CLI Usage

Render with a values JSON file:

```powershell
python -m leaps_harness render-prompt .\template.txt --values .\values.json
```

Write to a file:

```powershell
python -m leaps_harness render-prompt .\template.txt --values .\values.json --output .\prompt.txt
```

Override values at runtime:

```powershell
python -m leaps_harness render-prompt .\template.txt --values .\values.json --var person.role=그룹장
```

Use only inline values:

```powershell
python -m leaps_harness render-prompt .\template.txt --var person.name=Mina --var person.role=그룹장
```

`--var` values are applied after `--values`, so they override matching keys from the JSON file.

## Python Usage

Render from a string:

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

Render from a file:

```python
from leaps_harness import build_prompt_from_file

prompt = build_prompt_from_file(
    "templates/weekly_report_prompt.txt",
    {
        "person": {"name": "Mina", "role": "그룹장"},
        "work_units": [{"title": "API gateway cache"}],
    },
)
```

Missing values raise `PromptBuildError`.

```python
from leaps_harness import PromptBuildError, build_prompt

try:
    build_prompt("Hello {{ name }}", {})
except PromptBuildError as exc:
    print(exc)
```

## Workflow Relationship

The `prompt` workflow step already renders templates and stores the result as a run artifact.

Use the standalone Prompt Builder when:

- a service endpoint needs to preview a prompt before running a workflow
- a test needs to verify prompt assembly directly
- an operator wants to generate a prompt artifact manually
- a workflow-local tool needs prompt assembly without invoking a full workflow

Use the workflow `prompt` step when prompt rendering is part of a reproducible run and should be captured in the manifest.

## Design Notes

Prompt rendering should remain deterministic and boring.

Avoid adding hidden model behavior, automatic summarization, implicit memory lookup, or provider-specific logic to the Prompt Builder. Those belong in workflow steps, adapters, or explicit tools.

Prompt Builder responsibilities:

- render templates
- expose missing value errors
- preserve structured values as JSON
- support CLI and Python usage

Non-responsibilities:

- calling LLMs
- choosing models
- storing durable memory
- mutating workflow state
- silently fetching external context
