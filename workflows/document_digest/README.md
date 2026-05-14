# Document Digest Workflow

This workflow is a second operated example used to keep the harness general.

It demonstrates a non-weekly-report flow:

1. Collect a source document.
2. Extract deterministic metadata and outline facts with a local tool.
3. Build a prompt from the source document and extracted facts.
4. Generate a concise digest through an LLM adapter.
5. Review the generated digest with deterministic checks.

Run it from the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness plan .\workflows\document_digest\workflow.json
python -m leaps_harness validate .\workflows\document_digest\workflow.json
python -m leaps_harness run .\workflows\document_digest\workflow.json --run-id document-digest-v0
```

Use another source document:

```powershell
python -m leaps_harness run `
  .\workflows\document_digest\workflow.json `
  --var document_input=C:\data\source.md `
  --run-id document-digest-v0
```

To use Claude CLI:

```powershell
python -m leaps_harness run `
  .\workflows\document_digest\workflow.json `
  --config .\configs\claude_cli.example.json `
  --run-id document-digest-claude
```
