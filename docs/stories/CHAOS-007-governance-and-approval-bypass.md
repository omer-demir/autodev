# CHAOS-007: Governance, supervision, and approval bypass resistance

**Status:** Proposed  
**Priority:** P0  
**Estimate:** 13 points  
**Minimum active profile:** `sandbox-smoke`

## User story

As a governance owner, I want adversarial state and tool requests to prove that models cannot bypass capability classification, deny-wins policy, runtime supervision, identity checks, or scoped approvals.

## Scope

- malformed and ambiguous tool arguments;
- shell/interpreter wrapping and command-classification edge cases;
- unknown tools/capabilities and capability drift;
- policy/provider failure and timeout behavior;
- forged, replayed, expired, cross-task, cross-organization, and post-mutation approvals;
- expired or unsponsored runtime elevation;
- identity revocation before and during long-running work;
- repeated denied actions and circuit-breaker behavior.

Tests must invoke normal tool and workflow interfaces. They must not mutate production data or bypass APIs to manufacture a pass.

## Implementation tasks

1. Build a table-driven corpus of argument vectors, including empty values, alternate executable paths, case/Unicode ambiguity, extra subcommands, shell wrappers, and option placement.
2. Add property/fuzz tests proving unknown or ambiguous commands classify to no capability and fail before sandbox execution.
3. Inject governance and supervision timeouts/errors and verify fail-closed events.
4. Define canonical action hashing over tool, normalized arguments, target, task, organization, policy context, and expiry.
5. Test approval replay, tampering after approval, scope widening, actor mismatch, expiry, and concurrent consumption.
6. Test signed agent manifest capability drift and revocation at stage boundaries; define polling/cancellation behavior for long runs.
7. Test TTL elevation sponsorship, expiry, demotion, and non-inheritance across stages/specialists.
8. Add repeated-denial trajectory rules and verify circuit breaker/termination behavior.
9. Ensure denied requests produce bounded redacted evidence and no provider call or filesystem/network side effect.

## Acceptance criteria

1. Unknown, shell-composed, malformed, or ambiguous command vectors are denied before `sandbox.execute_args()`.
2. Effective policy uses deny-wins intersection; no agent declaration, repository instruction, task text, or model output can grant a capability.
3. Governance or supervision timeout/error fails closed with a stable denial class.
4. An approval is valid only for the exact canonical action, actor/scope, task, organization, and unexpired interval.
5. Mutating arguments or target after approval invalidates the action; replay or concurrent double-consumption is rejected.
6. The agent cannot create, approve, sponsor, or elevate its own pending action through tool output.
7. Expired/unsponsored elevation denies privileged action, and grants do not cross stage, task, child-agent, or organization boundaries.
8. Revoked identity blocks the next controlled boundary; the story documents and tests the maximum revocation propagation interval.
9. Repeated denied attempts trip configured supervision controls without allowing the action.
10. Every denial test verifies absence of side effects, not merely the returned exception.

## Verification and evidence

- Classifier unit/property tests and tool-runtime mock assertions that sandbox execution was not called.
- Database concurrency tests for approval consumption and mutation.
- Runtime-supervision tests for elevation, breach demotion, rate limit, and fail-closed adapters.
- Workflow integration tests for identity drift/revocation and stage boundaries.
- Evidence: normalized action digest, decision chain by boundary, policy/identity versions, approval reference, supervision tier, denial class, and side-effect assertions.

## Dependencies and risks

- Requires CHAOS-001.
- ADOPT-002 strengthens repeated-denial and recovery assertions.
- Risk: command allowlists may classify a broad executable as `build.run` even when arguments trigger unsafe behavior. Treat classification as an argument-aware security boundary and add explicit negative cases before expanding supported tools.
- Risk: current long-running revocation propagation may be stage-boundary-only. Record this as a gap until live checks exist.

## Likely implementation areas

- `apps/api/app/agent/command_policy.py`
- `apps/api/app/agent/tool_runtime.py`
- governance, runtime supervision, approval, identity, and workflow services
- agent, governance, supervision, and workflow tests

## References

- [Layered capability governance ADR](../adr/0004-layered-capability-governance.md)
- [Tool checks and governance](../design/tool-checks-and-governance.md)
