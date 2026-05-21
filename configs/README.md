# configs

Configuration templates and local runtime configuration examples live here.

Use this directory for:

- Approved LLM adapter examples.
- Internal tool adapter examples.
- Environment-specific runtime templates.
- Non-secret defaults that help operators run workflows consistently.

Do not commit credentials, private endpoints, or machine-specific secrets.

See `claude_cli.example.json` for the expected shape of `claude -p` backed LLM and CLI agent adapters.
See `claude_style_loop.example.json` for a producer/reviewer loop where both adapters are backed by `claude -p`.
See `claude_weekly_style_transfer.example.json` for the weekly-report style-transfer evaluation loop.
See `claude_github_review_knowledge.example.json` for the one-module GitHub review knowledge worker.
See `policy.example.json` for command allowlist, cwd, timeout, and env-key execution policy.
See `output_contract.example.json` for normalized `status`, `summary`, `result`, and trace envelope settings.

Multiple config files can be layered with repeated `--config` flags. Apply broad defaults first and local overrides last.

Use `local.override.example.json` as a starting point for local runtime variables. Copy it to a non-secret local config name when needed.
