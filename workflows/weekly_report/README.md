# Weekly Report Workflow v0

This is the first operated workflow for the harness.

It demonstrates the intended pattern:

1. Collect source weekly report inputs.
2. Normalize source inputs into `work_units`.
3. Validate the `work_units` contract.
4. Run a CLI agent once per work unit.
5. Build the final report prompt from source data, work units, and per-work drafts.
6. Generate the final report through an approved LLM adapter.
7. Review the final report with deterministic checks.

Run it from the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness plan .\workflows\weekly_report\workflow.json
python -m leaps_harness validate .\workflows\weekly_report\workflow.json
python -m leaps_harness run .\workflows\weekly_report\workflow.json --run-id weekly-v0
```

Generated artifacts are written under `.runs/` inside this directory.

Use another source input file:

```powershell
python -m leaps_harness run `
  .\workflows\weekly_report\workflow.json `
  --var weekly_input=C:\data\team_weekly_reports.json `
  --run-id weekly-v0
```

To run with approved internal adapters, pass a config file:

```powershell
python -m leaps_harness run `
  .\workflows\weekly_report\workflow.json `
  --config .\configs\claude_cli.example.json `
  --run-id weekly-v0-internal
```

Multiple configs can be layered:

```powershell
python -m leaps_harness run `
  .\workflows\weekly_report\workflow.json `
  --config .\configs\claude_cli.example.json `
  --config .\configs\local.override.json `
  --run-id weekly-v0-internal
```

`weekly_input` paths are resolved relative to `workflows/weekly_report/` unless the path is absolute.
