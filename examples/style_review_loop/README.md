# Style Review Loop Example

This example tests a generic framework behavior: one producer creates a draft, one reviewer returns structured feedback, and the harness retries the producer until the review succeeds or `max_attempts` is reached.

The reviewer prompt intentionally fails attempts 1, 2, and 3 so the run proves that at least three feedback rounds are preserved before success is possible.

The story task is intentionally just a sample domain. The reusable part is the `iterative_review` step.

The prompt uses an abstract prose profile instead of asking for imitation of a named living author. The reviewer is also instructed to avoid author names and return only structural feedback.

## Run With Claude CLI

From the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m leaps_harness validate .\examples\style_review_loop\workflow.json --config .\configs\claude_style_loop.example.json
python -m leaps_harness plan .\examples\style_review_loop\workflow.json --config .\configs\claude_style_loop.example.json
python -m leaps_harness run .\examples\style_review_loop\workflow.json --config .\configs\claude_style_loop.example.json --run-id style-loop-claude
```

Artifacts are written under:

```text
examples/style_review_loop/.runs/style-loop-claude/
```

Useful artifacts:

- `steps/rewrite_until_profile_match_attempt_*/producer_prompt.txt`
- `steps/rewrite_until_profile_match_attempt_*/draft.md`
- `steps/rewrite_until_profile_match_attempt_*/reviewer_prompt.txt`
- `steps/rewrite_until_profile_match_attempt_*/review.json`
- `steps/rewrite_until_profile_match/iteration_history.json`
- `steps/rewrite_until_profile_match/final_story.md`

The workflow is successful only when the reviewer returns JSON with `status` set to `success`, `passed`, `pass`, or `ok`, or with `"passed": true`.
