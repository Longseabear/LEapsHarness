# workflows

First-party workflow definitions intended for real use live here.

Use `examples/` for sample data and reference scenarios. Use this directory when a workflow is ready to become an operated internal workflow.

Generated run artifacts should go under `.runs/` and must not be committed.

Current workflows:

- `weekly_report/`: reference workflow for work-unit-based report generation.
- `document_digest/`: generic document digest workflow used to keep the harness workflow-agnostic.
