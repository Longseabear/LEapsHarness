# Workflow and Run Diagrams

The harness can generate Mermaid Markdown diagrams from source workflow files and run manifests.

Use this when you want the diagram to reflect the actual framework state instead of a manually maintained drawing.

## Workflow Diagram

Generate a workflow diagram before execution:

```powershell
python -m leaps_harness diagram workflow .\workflows\weekly_report\workflow.json --output .\workflow_diagram.md
```

Layer runtime config files the same way as `run`, `plan`, and `validate`:

```powershell
python -m leaps_harness diagram workflow `
  .\examples\github_review_knowledge\workflow.json `
  --config .\configs\claude_github_review_knowledge.example.json `
  --output .\github_review_workflow_diagram.md
```

The diagram includes:

- each workflow step
- step type
- dashed execution-order edges
- solid artifact-dependency edges
- validation status and validation errors when present

Artifact dependencies are extracted from:

- `{"from_artifact": "step.output"}` specs
- template references such as `{{ artifact.step.output }}`

## Run Diagram

Generate a run-status diagram after execution:

```powershell
python -m leaps_harness diagram run `
  .\workflows\weekly_report\.runs\demo\manifest.json `
  --output .\weekly_report_run_diagram.md
```

The run diagram includes:

- run id
- workflow status
- step status
- elapsed seconds
- reused steps when a run resumes from a previous manifest
- iterative review attempts and pass/fail values when present

## Python Usage

```python
from leaps_harness import build_run_diagram, build_workflow_diagram

workflow_markdown = build_workflow_diagram(
    "examples/github_review_knowledge/workflow.json",
    config_paths=["configs/claude_github_review_knowledge.example.json"],
)

run_markdown = build_run_diagram("workflows/weekly_report/.runs/demo/manifest.json")
```

## Design Notes

Diagram generation is read-only. It does not execute steps, call LLMs, or mutate run artifacts.

Keep diagrams generated from workflow and manifest files whenever possible. Manual Mermaid should be treated as explanatory documentation, not source of truth.
