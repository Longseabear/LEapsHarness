# Internal Tooling Notes

The operations team needs a repeatable way to turn internal notes into concise decision-ready summaries.

## Current Pain

Important context is often scattered across meeting notes, chat exports, local files, and ad hoc investigation logs.
The same summary work is repeated by different people because intermediate artifacts are not preserved.

## Desired Direction

A CLI-first harness should keep raw input, deterministic preprocessing output, prompt text, model responses, and review results together.
The first implementation should stay small and avoid visual workflow builders until the execution contract is stable.

## Open Questions

- Which internal sources should be connected first?
- Which reviewers must approve generated summaries?
- How long should run artifacts be retained?
