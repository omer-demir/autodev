# ADR 0007: Independent behavioral evaluation and evidence-gated promotion

- Status: Accepted
- Date: 2026-10-06

## Context

An agent declaration is executable configuration. Static capability lint can detect obvious mismatches but cannot prove behavior. Promotion must be reproducible, tied to exact inputs, resistant to repeated candidate noise, and isolated from product task/session history. Evaluation also needs a model/provider choice independent of the agent's production preference to avoid circular self-selection.

The former native adapter created product projects and tasks to invoke the workflow. That polluted dashboards, conflated evaluation with customer work, and inherited task approvals and session semantics that evaluation does not own.

## Decision

Behavioral evaluation is a separate bounded context with `EvaluationDataset`, `EvaluationRun`, scenario execution IDs, adapter results, metrics, comparison, provenance, and evidence paths. It does not create `Project`, `Task`, session, `ExecutionJob`, task artifacts, or product approvals.

Candidate scenarios are canonicalized and SHA-256 hashed at generation. For the same organization, agent/version, suite/version, and content hash, generation returns the existing dataset rather than inserting duplicates. A human reviewer must review the scenarios; freezing recomputes the canonical hash and makes the dataset immutable.

Native scenarios materialize isolated Git fixture workspaces, create evaluation-owned Docker sandboxes, invoke the real governed `AgentRuntime` directly, collect in-memory tool/model/supervision events, run deterministic file/test/security checks, and apply rubric judging only where necessary. Scenario evidence uses an evaluation execution ID, not a task ID. Runtime-supervision handles and containers are terminated at scenario completion.

The evaluator provider and model are explicit run inputs and provenance. Defaults are Ollama and `gemma4:e2b`; they are not inherited from the evaluated agent. Vally and Waza receive the same frozen scenarios through adapters and record their actual executor limitations and raw evidence. The current promotion policy requires native, Vally, and Waza evidence.

Promotion requires the latest behavioral run to be completed, score at least 0.85, safety exactly 1.0, no blocking regression, and all required adapters. The run must reference a frozen dataset with the same organization, agent, agent version, suite, suite version, and content hash. The current declaration version must match the run. PromptDefense evaluation then runs fail-closed against the rendered runtime prompt.

No result is fabricated to make a draft promotable. Draft specialists require real dataset review and real completed evidence.

## Alternatives considered

- Reuse product tasks for native evaluation. Rejected because evaluation would pollute task/session state and acquire unrelated workflow semantics.
- Promote from declaration lint. Rejected because declarations do not prove runtime behavior.
- Generate a new candidate row on every click. Rejected because deterministic duplicates obscure review and evidence lineage.
- Let the evaluated agent choose its evaluator. Rejected because it creates circular and non-comparable evidence.
- Auto-freeze or fabricate passing seed results. Rejected because it removes human review and falsely claims verification.
- Use only one adapter. Rejected for the current policy because independent implementations expose integration-specific failures, though this raises availability cost.

## Consequences

Evaluation history is understandable and does not appear as product work. The evaluator can be changed explicitly, and provenance supports comparison. Promotion is intentionally unavailable when Vally or Waza is missing or failing.

Frozen datasets consume storage but provide reproducibility. Editing scenarios after review creates a new review obligation. Deterministic candidate reuse means callers must understand that generation can return an existing reviewed or frozen dataset.

## Security and operations

Evaluation still executes untrusted model behavior and therefore uses the same capability, governance, supervision, and sandbox boundaries. Fixture paths are containment-checked. Containers and supervision handles are cleaned up independently. Rubric evidence is bounded before model judging.

External CLIs currently use Copilot-oriented executors; the system must not label those executions as Ollama. Provider parity and adapter versions belong in evidence.

## Validation and limits

Tests prove repeated generation reuses one dataset, native evaluation does not change the task table, provider/model defaults are persisted, and promotion rejects an unlinked result. Vally and Waza availability remains an operational dependency. Statistical confidence intervals and multi-trial variance are not yet part of the promotion gate.
