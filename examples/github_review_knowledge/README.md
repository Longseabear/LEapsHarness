# GitHub Review Knowledge Example

This example builds an incremental knowledge system for a large GitHub repository.

It is adapted for LEaps Harness rather than copied directly from a prompt. The harness owns file selection, artifacts, validation boundaries, and knowledge persistence. The LLM worker only receives a bounded review packet for one selected module.

## Goal

Analyze one module per run and accumulate reusable engineering knowledge.

Knowledge layers:

- `maps/`: module index and dependency map.
- `modules/`: one document per reviewed module.
- `patterns/`: reusable engineering mechanisms.
- `skills/`: procedural engineering workflows.
- `reviews/`: per-run review records.
- `_inbox/`: unresolved TODOs.

## Scope Guardrails

- Never analyze the full repository.
- Select one module with `--var module=<name>`.
- The file selection tool chooses only module-matching files and directly included dependencies.
- The review worker only sees the generated review packet.
- The apply tool requires structured JSON before mutating the knowledge store.

## Run With Claude CLI

From the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness validate .\examples\github_review_knowledge\workflow.json --config .\configs\claude_github_review_knowledge.example.json
python -m leaps_harness plan .\examples\github_review_knowledge\workflow.json --config .\configs\claude_github_review_knowledge.example.json
python -m leaps_harness run .\examples\github_review_knowledge\workflow.json --config .\configs\claude_github_review_knowledge.example.json --run-id github-review-bpc
```

Analyze a different module in a local checkout:

```powershell
python -m leaps_harness run `
  .\examples\github_review_knowledge\workflow.json `
  --config .\configs\claude_github_review_knowledge.example.json `
  --var repo_root=C:\src\large_cpp_repo `
  --var module=gamma `
  --var knowledge_root=C:\src\large_cpp_repo\ISP_KNOWLEDGE `
  --run-id github-review-gamma
```

## Workflow

1. `select_module_files`: bounded file selection for one module.
2. `build_review_packet`: creates the only context the worker receives.
3. `draft_knowledge_update`: Claude-backed worker returns structured JSON.
4. `apply_knowledge_update`: writes module docs, index updates, patterns, skills, reviews, and TODOs.

## Output Requirements

Each run produces:

- analyzed module
- files created or updated
- reusable patterns
- skills
- unresolved TODOs
- confidence level

These are captured in `apply_summary.json` and the knowledge store.
