# API Wrapper

The API wrapper is intentionally thin. It exists to service-ize a CLI-proven workflow without changing the workflow contract.

Start the server:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness serve --host 127.0.0.1 --port 8765 --workflow-root .
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Plan a workflow without running it:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/plans `
  -ContentType "application/json" `
  -Body '{"workflow_path":"workflows/weekly_report/workflow.json","vars":{"weekly_input":"C:/data/team_weekly_reports.json"}}'
```

Run a workflow synchronously:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/runs `
  -ContentType "application/json" `
  -Body '{"workflow_path":"workflows/weekly_report/workflow.json","run_id":"api-demo"}'
```

With one external adapter config:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/runs `
  -ContentType "application/json" `
  -Body '{"workflow_path":"workflows/weekly_report/workflow.json","config_path":"configs/claude_cli.example.json","run_id":"api-demo"}'
```

With multiple adapter configs, use `config_paths`. Files are applied in order, and later files override earlier adapter names:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/runs `
  -ContentType "application/json" `
  -Body '{"workflow_path":"workflows/weekly_report/workflow.json","config_paths":["configs/claude_cli.example.json","configs/local.override.json"],"run_id":"api-demo"}'
```

Policy configs are layered the same way:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/runs `
  -ContentType "application/json" `
  -Body '{"workflow_path":"workflows/weekly_report/workflow.json","config_paths":["configs/claude_cli.example.json","configs/policy.example.json"],"run_id":"guarded-api-demo"}'
```

Override runtime vars per request:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/runs `
  -ContentType "application/json" `
  -Body '{"workflow_path":"workflows/weekly_report/workflow.json","vars":{"weekly_input":"C:/data/team_weekly_reports.json"},"run_id":"api-demo"}'
```

Resume from a previous failed manifest:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/runs `
  -ContentType "application/json" `
  -Body '{"workflow_path":"workflows/weekly_report/workflow.json","resume_from":"workflows/weekly_report/.runs/failed-run/manifest.json","run_id":"retry-api-demo"}'
```

The response is the same run summary returned by the CLI. Generated artifacts are written by the normal runner.

This API is not yet an authenticated production service. Put authentication, authorization, queueing, and async run management in front of it before exposing it beyond a trusted internal environment.
