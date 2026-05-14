# File Structure Draft

This repository should stay CLI-first and artifact-first while it grows. The structure below is the intended direction, not a requirement to create every module before it is needed.

```text
LEapsCustomHarness/
  AGENTS.md
  README.md
  pyproject.toml
  configs/
  docs/
  examples/
  workflows/
    weekly_report/
  src/
    leaps_harness/
      cli.py
      __main__.py
      core/
      adapters/
      steps/
      runtime/
  tests/
```

## Top-Level Directories

- `configs/`: non-secret configuration templates for approved LLMs, internal tools, and runtime defaults.
- `docs/`: architecture notes, prompt builder usage, file structure, workflow contracts, and operator guidance.
- `examples/`: runnable reference workflows that are not operated workflows.
- `workflows/`: first-party workflow definitions intended for real use. The current v0 workflow is `workflows/weekly_report/`.
- `src/leaps_harness/`: harness runtime package.
- `tests/`: focused tests for runner behavior, adapters, workflow contracts, and example workflows.

## Package Growth Points

- `core/`: workflow runner, artifact store, run context, manifest handling, and shared errors.
- `adapters/`: LLM adapters, tool adapters, and CLI agent adapters.
- `steps/`: built-in step implementations such as `copy_file`, `command`, `prompt`, `llm`, and future evaluators.
- `runtime/`: configuration loading, environment resolution, run ids, path policy, and operator-facing runtime utilities.

The current implementation is intentionally smaller than this target shape. Move code into these packages only when a file becomes too large or a second implementation makes the boundary useful.

## Rules of Thumb

- Keep runnable examples under `examples/` only when they are not operated workflows.
- Keep real reusable workflow definitions under `workflows/`.
- Keep workflow-specific code in that workflow's `tools/`, `templates/`, and `schemas/` directories.
- Keep shared runtime code domain-neutral. The `src/leaps_harness/` package should not contain weekly-report assumptions.
- Keep generated run output under `.runs/`; never commit generated run artifacts.
- Keep private settings out of git. Commit templates, not secrets.
- Prefer adding one small module over introducing a large framework.
