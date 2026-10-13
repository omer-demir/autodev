# CHAOS-001: Safe chaos campaign foundation

**Status:** Proposed  
**Priority:** P0  
**Estimate:** 13 points

## User story

As a security and reliability owner, I want a governed campaign runner for active boundary probes so that adversarial claims are repeatable, safe, auditable, and separate from policy-only security evaluation.

## Context

The current `security-v1` evaluator actively checks expected governance decisions and an optional provider guardrail. It does not launch a comprehensive sandbox conformance or agent-driven chaos campaign. Those layers must remain distinct so a policy simulation is never reported as proof of kernel, network, or cleanup isolation.

## Scope

Define four result families:

1. `policy`: deterministic governance and supervision decisions without agent execution.
2. `sandbox-conformance`: bounded commands in a disposable sandbox.
3. `agent-adversarial`: an agent receives hostile fixtures and attempts declared actions through normal tools.
4. `infrastructure-fault`: provider/API/evidence dependency faults in an isolated environment.

Build a versioned scenario schema and runner with execution profiles, preflight, leases, abort rules, evidence collection, cleanup verification, and scoring.

## Scenario contract

Each scenario declares ID/version, family, provider support, minimum profile, required capabilities, forbidden targets, fixtures, canaries, steps, expected observations, timeout, CPU/memory/PID/network ceilings, evidence fields, cleanup assertions, and whether it is mandatory.

Result states are `PASSED`, `FAILED`, `ERROR`, `SKIPPED`, `ABORTED`, and `INDETERMINATE`. Only `PASSED` counts positively. Mandatory non-pass states fail the campaign.

## Implementation tasks

1. Add a schema validator and immutable scenario registry; reject unknown fields and unsafe target forms.
2. Add environment preflight for provider, dedicated-runner label, workspace root, image digest, resource controls, evidence availability, and controlled sink identity.
3. Create campaign/run/scenario models scoped by organization and linked to task/evaluation evidence.
4. Acquire a campaign lease to prevent overlapping destructive-profile runs on one runner.
5. Generate per-run synthetic canaries; persist only IDs and hashes outside the fixture store.
6. Apply hard wall-clock, command, tool, token, CPU, memory, PID, output, artifact, and cost limits.
7. Implement a kill switch and automatic abort on containment uncertainty, unexpected egress, control-plane degradation, evidence failure, or cleanup failure.
8. Independently verify sandbox deletion, network detachment, worktree cleanup, lease release, and absence of leftover provider resources.
9. Add structured redaction and secret scanning before any output becomes durable evidence.
10. Produce machine-readable and operator-readable reports without merging scores into `security-v1`.

## Acceptance criteria

1. No active scenario runs unless its profile requirements and all preflight checks pass.
2. Scenario configuration cannot specify public hosts, link-local metadata addresses, host paths, privileged flags, host namespaces, Docker socket mounts, or unbounded resources.
3. Every scenario has a deadline and ceilings; runner enforcement does not depend on the agent honoring prompt instructions.
4. Abort prevents new scenarios, kills active sandboxes, attempts cleanup, and preserves redacted partial evidence.
5. A skipped, errored, timed-out, truncated, or cleanup-failed mandatory scenario cannot be scored as passed.
6. Campaign reports clearly separate policy, sandbox, agent, and infrastructure evidence.
7. Cleanup is independently queried after provider `kill`; a successful API response alone is insufficient.
8. Running the same frozen scenario version records comparable expected observations and identifies environmental differences.
9. Production profile rejects all active/exhaustion scenarios and performs only passive checks.
10. Campaign data and controls enforce organization boundaries.

## Verification and evidence

- Schema fuzz tests and unsafe-target rejection tests.
- Runner tests for timeout, cancellation, output truncation, event loss, lease conflict, and each terminal result.
- Provider contract tests with deliberate create/execute/kill failures.
- Evidence includes scenario and runner versions, environment fingerprint, image digest, limits, policy versions, start/end, observations, redactions, abort reason, and cleanup assertions.
- Metrics include active sandboxes, cleanup latency/failures, scenario duration, failure class, and unexpected egress count.

## Dependencies and risks

- Foundation for CHAOS-002 through CHAOS-010.
- Risk: test framework becomes an exploit framework. Keep scenario operations allowlisted and reviewed; do not accept arbitrary shell scripts from users or agents.
- Risk: false confidence from provider mocks. Label mocked, local live, and cloud live evidence distinctly.

## Likely implementation areas

- new chaos campaign service and models under `apps/api/app`
- sandbox provider contract and evaluation APIs
- dedicated scenario registry under `evaluations`
- API tests and web evidence views

## References

- [Threat model](../threat-model.md)
- [Sandbox provider ADR](../adr/0005-isolated-workspaces-and-sandbox-providers.md)
- [Story index and safety contract](README.md)
