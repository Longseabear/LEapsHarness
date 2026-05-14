# Harness-Oriented Agent Architecture

LEaps Custom Harness is a harness-oriented agent framework.

It is not a chatbot wrapper. It is an orchestration runtime for managing AI workers safely, reproducibly, and modularly.

Core philosophy:

- LLMs are workers, not the operating system.
- The harness controls execution, permissions, workflows, validation, artifacts, and durable state.
- Agents are ephemeral and task-scoped.
- Durable state lives outside the LLM session.
- Workers may propose changes, but the harness validates and commits them.

The harness is the control plane for AI workers. LLMs and CLI agents may reason, draft, review, or propose actions, but they do not own durable state, permissions, validation, or final commit authority.

## Core Concepts

### Harness

The harness is the top-level orchestrator and runtime.

Responsibilities:

- task decomposition
- workflow orchestration
- session lifecycle management
- validation and guardrails
- state persistence
- artifact storage
- logging and auditability
- retry and recovery
- policy enforcement
- tool routing
- approval gating

The harness is the source of truth for orchestration state, execution records, artifacts, approvals, and validation results. Domain systems remain the source of truth for their own data. For example, a broker or portfolio database may own trading positions, while the harness owns the run history, validation trail, and action proposals.

### Worker Agent

A worker agent is an isolated, task-scoped execution unit.

Examples:

- research worker
- coding worker
- review worker
- testing worker
- reporting worker
- trading signal worker

Worker sessions are intentionally short-lived. They should receive only relevant context, operate within explicit boundaries, produce structured outputs, and avoid hidden state assumptions.

Workers do not own durable memory. They may read state snapshots and write proposed outputs as artifacts.

### Durable State

Persistent state is stored externally by the harness or by domain systems that the harness integrates with.

Examples:

- decision logs
- task graphs
- memory store
- execution history
- runtime state
- portfolio state
- validation records
- reports
- prompt and response artifacts

Agents may read snapshots of state, but the harness owns persistence and lineage.

### Artifact Lineage

Every important output should be traceable to the inputs and execution context that produced it.

For a final artifact, the harness should preserve:

- input snapshots
- templates and prompt construction
- rendered prompts
- worker adapter name and config reference
- stdout, stderr, and metadata
- intermediate drafts
- reviewer results
- deterministic validation results
- retry history
- final manifest

This is especially important for report generation. A final report line should be traceable back to source memos, normalized work units, review feedback, and contract validation.

## Worker Contract

Workers are replaceable only when their boundaries are explicit.

A worker contract should define:

- worker role
- input context
- allowed tools
- writable artifacts
- forbidden actions
- expected output schema
- success criteria
- retry policy
- validation checks

Example:

```json
{
  "worker_id": "weekly_style_reviewer",
  "role": "review",
  "input_context": [
    "draft",
    "style_packet",
    "source_facts",
    "hidden_reference"
  ],
  "allowed_tools": [],
  "output_schema": {
    "status": "success | fail",
    "feedback": "string",
    "scores": {
      "format_match": "number",
      "tone_match": "number",
      "content_preservation": "number",
      "hallucination_risk": "number"
    },
    "missing_facts": "array",
    "unsupported_facts": "array"
  },
  "success_criteria": [
    "status is success",
    "missing_facts is empty",
    "unsupported_facts is empty"
  ],
  "retry_policy": {
    "max_attempts": 4,
    "feedback_field": "feedback"
  }
}
```

## Guardrails

Guardrails must be enforced outside the LLM. Prompt instructions alone are insufficient.

### Hard Guardrails

Hard guardrails are deterministic or policy-backed. Failure rejects the result, stops the run, or requires an explicit override.

Examples:

- JSON schema validation
- forbidden file checks
- command allowlists
- path policy checks
- risk limits
- required artifact existence
- required fields and section headers
- tool permission checks
- sandbox restrictions

### Soft Guardrails

Soft guardrails are judgment-based. They usually produce feedback for retry or human review.

Examples:

- LLM reviewer
- style evaluator
- content preservation review
- semantic consistency review
- quality scoring
- risk commentary

Soft guardrails can improve output quality, but hard guardrails decide whether the system may commit the result.

## State Mutation Model

Workers should not mutate durable state directly.

Preferred model:

1. Worker receives a bounded task and relevant context.
2. Worker writes a proposed output as an artifact.
3. Harness validates the proposal.
4. Harness either rejects, retries, asks for approval, or commits.
5. The commit writes durable state and audit records.

Examples:

- Coding worker proposes a patch; harness checks the diff and runs tests before merge.
- Reporting worker proposes a report; harness runs style, fact, and contract checks before publishing.
- Trading worker proposes an order; harness runs risk and exposure checks before execution.

## Work-Oriented Execution

The framework prefers many small isolated sessions over one infinitely growing session.

Reasons:

- reproducibility
- failure isolation
- reduced context pollution
- deterministic retry behavior
- parallelization
- auditability
- easier worker replacement

The harness may maintain long-running orchestration state, while workers remain task-scoped.

## Execution Model

Typical flow:

```text
User / Scheduler
  -> Harness Orchestrator
  -> Task Planner
  -> Worker Session
  -> Tool / CLI / MCP / Shell
  -> Validation Layer
  -> State Store / Logs
```

Step flow:

1. Harness receives a goal.
2. Harness decomposes work.
3. Harness creates a worker session.
4. Worker executes a bounded task.
5. Worker returns a structured result.
6. Harness validates the result.
7. Harness commits, rejects, retries, or asks for approval.
8. Harness schedules follow-up work.

## Retry Policy

Retries should be explicit and bounded.

A retry policy should define:

- maximum attempts
- feedback source
- retryable failure conditions
- non-retryable failure conditions
- artifacts retained per attempt
- final failure behavior

The `iterative_review` step follows this model. A producer creates a draft, a reviewer returns structured feedback, and the harness retries until the review passes or `max_attempts` is reached.

## Example Guarded Coding Flow

```text
Harness
  -> create isolated worktree
  -> launch coding worker
  -> worker edits allowed files only
  -> harness checks git diff
  -> run tests, lint, and preflight
  -> accept, reject, or request revision
```

## Example Weekly Report Flow

```text
part reports / work units
  -> style packet builder
  -> writer worker
  -> style reviewer
  -> content preservation reviewer
  -> deterministic contract validator
  -> final report artifact
  -> manifest / audit log
```

The weekly style-transfer example follows this pattern:

- Group-lead samples define the target format.
- Part-lead reports and work units define source facts.
- A writer worker drafts the group-level report.
- A reviewer worker checks format, tone, missing facts, and unsupported facts.
- A deterministic validator checks required headings, exact titles, required facts, and markdown constraints.
- The harness records each attempt and final result as artifacts.

## Example Trading Flow

```text
preflight
  -> universe build
  -> signal generation
  -> risk validation
  -> order proposal
  -> execution guard
  -> broker execution
  -> reporting
```

The LLM may assist reasoning, but the harness controls execution safety.

## Design Principles

### 1. LLMs Are Probabilistic

Never rely solely on prompt obedience. Always validate externally.

### 2. Structure Over Conversation

Prioritize workflows, schemas, policies, reproducibility, state machines, and artifacts over freeform conversation continuity.

### 3. Explicit Boundaries

Workers should know what they can modify, what they cannot modify, which tools are available, expected output schemas, and validation requirements.

### 4. Harness Owns Memory

Avoid relying on hidden conversational memory. Durable information belongs in files, databases, structured state, logs, and manifests.

### 5. Workers Are Replaceable

Any worker session should be restartable, rerunnable, or replaceable without corrupting system state.

### 6. Validate Before Commit

Workers propose. The harness validates and commits.

## Framework Goal

The purpose of this framework is to support:

- scalable agent orchestration
- reliable automation
- safe execution
- modular agent composition
- reproducible AI workflows
- production-grade agent systems

This is closer to an agent runtime and orchestration control plane than a chatbot architecture.
