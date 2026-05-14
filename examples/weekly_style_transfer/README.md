# Weekly Style Transfer Example

This example is closer to the real weekly-report goal than the literary style loop.

It tests whether the harness can convert a part-lead weekly report into a group-lead weekly report shape while preserving source facts.

The reusable pattern is:

1. Build a style packet from group-lead weekly report samples.
2. Provide raw part-lead notes and normalized work units.
3. Let a producer agent draft the group-level report.
4. Let a reviewer LLM check format, tone, fact preservation, unsupported facts, risks, and decisions.
5. Retry with reviewer feedback until the reviewer passes or `max_attempts` is reached.
6. Run a deterministic contract validator against the final report.
7. Build a human-readable evaluation report that compares group style samples, the hidden reference, generated attempts, reviewer feedback, and validation results.

The hidden reference is only used by the reviewer prompt as calibration. The producer prompt does not include it.

## Run With Claude CLI

From the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness validate .\examples\weekly_style_transfer\workflow.json --config .\configs\claude_weekly_style_transfer.example.json
python -m leaps_harness plan .\examples\weekly_style_transfer\workflow.json --config .\configs\claude_weekly_style_transfer.example.json
python -m leaps_harness run .\examples\weekly_style_transfer\workflow.json --config .\configs\claude_weekly_style_transfer.example.json --run-id weekly-style-transfer-claude
```

Useful artifacts:

- `steps/build_style_packet/style_packet.md`
- `steps/transfer_to_group_style_attempt_*/draft_group_weekly.md`
- `steps/transfer_to_group_style_attempt_*/review.json`
- `steps/transfer_to_group_style/iteration_history.json`
- `steps/transfer_to_group_style/group_weekly_report.md`
- `steps/validate_report_contract/contract_validation.json`
- `steps/build_evaluation_report/evaluation_report.md`

## What This Evaluates

- Format match: title, section order, bullet style.
- Tone match: group-level summary rather than part-level implementation log.
- Content preservation: metrics, dates, risks, decisions, and next actions from work units.
- Hallucination risk: facts that are not present in source inputs.
- Contract compliance: deterministic headings and required facts.

`evaluation_report.md` is the easiest artifact to inspect after a run. It shows the group style samples, hidden reference, each generated attempt, the feedback between attempts, final reviewer scores, and deterministic contract validation.
