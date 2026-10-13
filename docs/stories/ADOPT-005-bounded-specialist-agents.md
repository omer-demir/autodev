# ADOPT-005: Bounded specialist agents as workflow helpers

**Status:** Proposed  
**Priority:** P1  
**Estimate:** 13 points

## User story

As a workflow author, I want a stage to request a narrowly scoped specialist analysis so that reusable expertise is available without giving one model authority to create an uncontrolled agent hierarchy.

## Context

Autodev deliberately uses a deterministic controller and one declared agent per workflow stage. The useful agent-as-tool pattern is a bounded helper invocation. The unsafe pattern is model-directed delegation with inherited authority, recursive spawning, or opaque side effects.

## Scope

- Add a controller-owned `specialist.invoke` operation for allowlisted, read-only specialist contracts.
- The workflow definition declares eligible specialist IDs, request schema, output artifact type, budget, timeout, and maximum invocations.
- The caller supplies data through typed artifacts; the controller filters inputs and starts a separate sandbox/session where required.
- Specialists receive an independently resolved identity, prompt, tools, policy, and runtime-supervision handle.
- Results return as typed, immutable artifacts with complete parent/child lineage.
- First release supports read-only research, security assessment, and review helpers only.

## Non-goals

- No recursive specialist invocation.
- No transfer of approvals, elevation grants, credentials, network state, or caller session memory.
- No write, commit, publish, deploy, administrative, or infrastructure capabilities.
- No dynamic discovery from arbitrary remote agents or model-authored agent definitions.

## Implementation tasks

1. Define a versioned invocation contract and child-run state machine.
2. Add workflow validation for eligible helper IDs, acyclic invocation, schemas, and aggregate budgets.
3. Intersect specialist capabilities with caller, workflow, organization policy, and helper-specific ceiling; deny wins.
4. Start a child supervision session and sandbox with fresh IDs and default network isolation.
5. Filter typed input artifacts and validate typed output before returning it.
6. Enforce depth one, per-stage count, aggregate token/tool/time/cost budgets, cancellation propagation, and fail-closed timeouts.
7. Persist parent task, stage, invocation, agent identity/version, policy, prompt digest, inputs, outputs, and terminal state.
8. Define required versus advisory helper failure behavior in workflow YAML.
9. Add operator visualization and a kill control that terminates the child without losing evidence.

## Acceptance criteria

1. Only workflow-declared specialists can be invoked, and the model cannot supply a new agent definition or tool list.
2. Effective child capabilities are the deny-wins intersection; caller approval or elevation state is absent from the child.
3. A specialist cannot invoke another specialist, even if its prompt requests one.
4. Input and output schema violations fail the child and publish no usable output.
5. Cancellation, timeout, or budget exhaustion terminates child resources, records partial evidence, and follows declared required/advisory semantics.
6. Parent and child event streams are independently ordered and linked by stable IDs.
7. Concurrent read-only helpers cannot share mutable workspaces or mutate parent artifacts.
8. A security specialist attempting a write, dependency install, network access, or publication is denied before side effect.
9. Replay can identify exact specialist version, prompt/instruction digest, artifact digests, and policy versions.
10. Integration tests demonstrate one successful review helper and one denied authority-escalation attempt.

## Verification and evidence

- Workflow validation tests for cycles, undeclared helpers, bad schemas, and budget overflow.
- Governance tests for capability intersection and non-inheritance of elevation/approval.
- Cancellation and cleanup tests across parent and child runs.
- Events: `specialist.requested`, `specialist.started`, `specialist.completed`, `specialist.denied`, and `specialist.cleanup_failed`.
- Metrics: child count, duration, tokens, denied actions, failure mode, and cleanup latency.

## Dependencies and risks

- Requires ADOPT-003 for typed handoffs.
- Benefits from ADOPT-002 to evaluate helper trajectories.
- Risk: cost amplification. Enforce aggregate budgets at the controller before launch and on every call.
- Risk: authority laundering. Never derive child authority from caller prose or model output.

## Likely implementation areas

- `apps/api/app/workflow.py`
- `apps/api/app/workflow_orchestration.py`
- agent runtime, supervisor, event models, and workflow schemas

## References

- [Executable multi-agent workflow ADR](../adr/0003-executable-multi-agent-workflows.md)
- [Executable workflow design](../design/workflow-orchestration.md)
