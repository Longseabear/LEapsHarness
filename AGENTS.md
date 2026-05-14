# AGENTS.md

Behavioral guidelines for coding agents.
Merge these with project-specific instructions as needed.

Tradeoff: these rules bias toward caution over speed.
For trivial one-line tasks, use judgment.

## 1. Think Before Coding

Do not silently assume.
Do not hide uncertainty.
Surface tradeoffs before implementation.

Before changing code:

- State important assumptions.
- If the request has multiple meanings, explain the options.
- If information is missing and the choice matters, ask.
- If a simpler approach exists, mention it.
- Push back when the requested approach seems risky or overbuilt.
- Stop when confused instead of guessing.

## 2. Simplicity First

Write the minimum code that solves the real problem.
Do not add speculative flexibility.

Avoid:

- Features the user did not ask for.
- Abstractions used only once.
- Configurability without a current need.
- Defensive code for impossible cases.
- Large rewrites when a small fix works.

After implementing, ask:

Could this be shorter, clearer, or more direct?
Would a senior engineer call this overcomplicated?
If yes, simplify before handing off.

## 3. Surgical Changes

Touch only what the task requires.
Clean up only the mess created by your own change.

When editing existing code:

- Do not improve adjacent code just because you noticed it.
- Do not reformat unrelated sections.
- Do not refactor unrelated modules.
- Match the existing style, even if you prefer another style.
- If unrelated dead code is found, mention it instead of deleting it.

When your change makes code unused:

- Remove imports, variables, or helpers made unused by your edit.
- Do not remove pre-existing dead code unless asked.

Every changed line should trace back to the user's request.

## 4. Goal-Driven Execution

Turn tasks into verifiable outcomes.
Define success criteria and loop until they are met.

Examples:

- "Add validation" becomes:
  write tests for invalid input, then make them pass.

- "Fix the bug" becomes:
  reproduce the bug with a test, then make the test pass.

- "Refactor this" becomes:
  preserve behavior and verify tests before and after.

For multi-step work, use a short plan:

1. Change the smallest relevant unit.
2. Verify with a focused check.
3. Broaden verification if the risk is larger.

Good success criteria let the agent proceed independently.
Weak success criteria create guesswork.

## Completion Checklist

Before finishing:

- The diff is focused.
- The solution is simpler than the obvious overbuilt version.
- No unrelated files were changed.
- Tests or checks were run when possible.
- Any skipped verification is explained.
- Remaining risks or follow-ups are named.

These guidelines are working when diffs get smaller,
clarifying questions happen earlier,
and fewer rewrites are needed after review.

## LEaps Custom Harness Project Instructions

This project builds a custom AI harness for environments where:

- The runtime may be connected to a closed network.
- Only approved LLMs may be used.
- CLI-version agents are available.
- Multiple processes must be connected to produce one service.
- Internal tools may need to run locally or inside the private environment.

The goal is to create a Dify-like orchestration layer for AI agents, LLMs, tools, and workflows, while keeping direct control over internal CLI execution, private tools, artifacts, logs, and runtime constraints.

The default execution model is `CLI-first`. API servers, UIs, and long-running services may be added later, but the initial design should prioritize local or internal process execution, file-based artifacts, explicit step execution, and reproducible logs.

## Core Concepts

- `Workflow`: The ordered flow or execution graph that produces a service outcome.
- `Step`: The smallest meaningful execution unit, with explicit inputs, outputs, failure conditions, and retry behavior.
- `Agent`: A CLI agent or LLM-backed worker that performs a defined role.
- `LLM Adapter`: A wrapper around approved LLM calls. Workflows and steps must not call model providers directly.
- `Tool Adapter`: A wrapper around internal tools, search tools, file processors, private systems, or local commands.
- `Artifact`: Any input snapshot, intermediate data, prompt, response, log, or final output created during a run.
- `Run Context`: The settings, paths, environment variables, trace id, user input, and execution state for one workflow run.
- `Prompt Builder`: A component that combines source data and templates into prompts for an LLM or agent.
- `Evaluator`: A component that checks whether a step or workflow result satisfies its success criteria.

## Design Principles

- Treat closed-network operation as the default. Call out any need for external network access, external SaaS, or package installation before adding it.
- Route every LLM call through an `LLM Adapter`. Do not hard-code a specific vendor or model call inside business logic.
- Represent CLI agent execution with explicit `command`, `cwd`, `env`, `timeout`, `logs`, and `artifacts`.
- Put internal tools behind `Tool Adapter` boundaries. Workflow steps should depend on input/output contracts, not tool implementation details.
- Make each workflow step rerunnable. The same input and environment should produce traceable artifacts.
- Preserve prompt construction history. Store the source data, template, assembly process, and final prompt as artifacts.
- Keep intermediate artifacts. They are needed for debugging, retries, audits, and quality improvement.
- Do not swallow failures. Expose the failing step, inputs, stdout/stderr, partial artifacts, and retry status.
- Add abstractions only when they remove real duplication or support a real replacement need.
- Prove workflows in the CLI before service-izing them behind APIs or UIs.
- Keep the harness general. Do not add weekly-report-specific logic to the runner, adapters, API, validation, manifest writer, or shared runtime.
- Put workflow-specific behavior in `workflows/<name>/tools`, `templates`, `schemas`, or workflow-local config.
- Prefer `command`, `agent`, `prompt`, `for_each`, `llm`, and `review` composition before adding a new built-in step type.
- Use `vars` and layered config files for environment differences instead of branching in code.

## Reference Scenario: Weekly Report Writer

The weekly report writer is a reference workflow for the harness.

1. Collect weekly report inputs from each person.
2. Normalize the collected inputs into `work` units.
3. Iterate over each `work` unit and let an agent search, inspect, or query the data needed for that unit.
4. Draft a report section for each `work` unit.
5. Build a final prompt that includes all source data, intermediate summaries, evidence, and constraints needed for the final report.
6. Use an approved LLM to generate the final weekly report.
7. Preserve the final result together with source inputs, the `work` list, agent execution logs, prompts, and LLM responses as artifacts.

This scenario is a reference case, not a hard-coded product constraint. The implementation should generalize the pattern so it can also support document generation, research, code generation, and internal operations workflows.

## Implementation Guidance

- Start with the smallest vertical slice that can run one workflow end to end from the CLI.
- Avoid choosing a large framework too early. Build only the runner, adapters, and artifact storage rules that the current workflow needs.
- Keep workflow definitions readable. An operator should be able to see which step produced which artifact.
- Before adding shared runtime code, ask whether the same need would appear in another workflow. If not, keep it workflow-local.
- Do not treat LLM or agent output as final truth by default. Add evaluator, reviewer, or human approval steps when the workflow needs them.
- Keep runtime paths, credentials, model endpoints, and environment-specific values in the run context or environment configuration, not in business logic.
- Do not build a plugin marketplace, visual workflow builder, or distributed scheduler until there is a current need.

## Completion Expectations

Before finishing project work, check that:

- The change directly traces back to the user request.
- Workflow, step, adapter, and artifact boundaries are not larger than needed.
- No dependency violates the closed-network or approved-LLM constraints.
- There is a reproducible CLI execution or verification path.
- Generated prompts, logs, and intermediate artifacts are traceable.
- The design still makes sense when applied to a reference workflow such as the weekly report writer.
