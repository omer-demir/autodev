# ADR 0003: Executable multi-agent workflow contracts

- Status: Accepted
- Date: 2026-10-06

## Context

A metadata-only workflow cannot guarantee who performs a responsibility, which evidence crosses a handoff, or whether two agents may safely mutate the same repository concurrently. Model-directed delegation is also insufficient because it makes lifecycle, authority, and durable state depend on unstructured output.

Ideation, design, planning, and implementation need different specialist roles, while simple tasks still benefit from a legacy single-agent path.

## Decision

Workflow YAML is executable controller input. A workflow selects `sequential` or `dag` execution, sets a parallelism ceiling, and declares stages with exactly one responsible local agent DID, responsibility, inputs, named outputs, dependencies, and handoff content.

Sequential workflows follow declaration order. DAG workflows are validated for unknown dependencies, self-dependencies, cycles, duplicate outputs, and artifact ancestry. The controller computes dependency waves. A wave may execute concurrently only when every assigned agent is read-only. Any write-capable stage remains serialized to prevent concurrent worktree mutation.

Stage output is a named durable artifact. A downstream stage receives only declared context and artifacts from earlier sequential stages or DAG ancestors. Model prose cannot create undeclared dependencies.

Each stage runs with the assigned agent's identity, policy, harness, model context, and sandbox environment. Non-primary role sandboxes are ephemeral and always cleaned up. Persistence callbacks are serialized even when read-only model work is parallel, because SQL sessions and ordered event history are not concurrency-safe shared mutable state.

The legacy `sdlc` workflow remains supported through the original single-agent controller path. New ideation, design, planning, and implementation recipes use specialist declarations that must be promoted before task creation.

## Alternatives considered

- Let a lead model dynamically choose and prompt subagents. Rejected as the authoritative mechanism because assignments, authority, and handoffs would not be reviewable or deterministic.
- Allow arbitrary DAG parallelism. Rejected because two writers can corrupt or produce nondeterministic worktree state.
- Give every stage the entire task history and all artifacts. Rejected because it increases prompt-injection surface, context cost, and accidental coupling.
- Create one permanent sandbox per role. Rejected because idle resources and stale cross-task state would weaken isolation.
- Replace the legacy path immediately. Rejected to preserve compatibility while executable recipes mature.

## Consequences

Workflow changes are reviewable and validator-enforced. Failures can be attributed to a stage and responsible agent. Handoffs survive restarts and can be inspected without replaying conversations. Read-only stages can reduce elapsed time, but write-heavy workflows remain intentionally sequential.

Workflow authors must explicitly design artifact contracts. This is more work than informal delegation but makes responsibilities testable. Changing a stage output name is a contract change and should require a workflow version bump.

## Security and operations

Task creation fails unless the workflow is active and all assigned roles are promoted. Stage sandboxes apply the role's least-privileged network and workspace access. Runtime supervision uses task-plus-agent handles so one role cannot inherit another role's trust identity.

Parallel execution must not share mutable database sessions. Cleanup failures are recorded separately from primary stage failures. The durable workflow snapshot prevents a retry from adopting a newly malicious stage assignment.

## Validation and limits

Tests cover waves, cycles, read-only parallelism, artifact filtering, handoff propagation, role-specific supervision, sandbox configuration, and cleanup. Stage-level retry and compensation are currently represented at task/workflow level; there is no independent stage queue or stage approval lifecycle yet.
