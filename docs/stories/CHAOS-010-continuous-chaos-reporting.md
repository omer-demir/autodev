# CHAOS-010: Continuous chaos reporting and release gates

**Status:** Proposed  
**Priority:** P2  
**Estimate:** 8 points

## User story

As a release and operations owner, I want scheduled, comparable chaos evidence and explicit gates so that security/stability claims remain current and regressions block promotion without making CI unsafe.

## Scope

- map scenarios to controls, providers, profiles, agents, and release claims;
- schedule static/smoke checks in normal CI and isolated campaigns on dedicated infrastructure;
- define freshness windows, baseline comparisons, required coverage, quarantine, and waivers;
- publish redacted reports and observability signals;
- gate agent promotion and platform releases separately;
- track mean time to cleanup/recovery and unresolved containment gaps.

## Implementation tasks

1. Define a versioned campaign manifest pinned to scenario versions, runner image digest, sandbox image digest, provider profile, policy versions, and required result set.
2. Create a coverage matrix from attack class and architectural boundary to scenario and evidence freshness.
3. Add CI jobs: `static` on pull requests, `sandbox-smoke` on trusted main/release workflows, and `isolated-chaos` on schedule/manual approval.
4. Protect secrets and fork workflows so untrusted pull requests cannot invoke privileged runners or alter scenarios used by a gate.
5. Add baseline comparison for pass state, duration, denied actions, resource peaks, cleanup latency, and provider drift.
6. Define independent gates for agent promotion, sandbox/provider release, and platform release.
7. Add signed waivers with owner, exact failed controls, rationale, compensating controls, expiry, and review trail; waivers never rewrite results.
8. Export OTel metrics/logs/traces and dashboards with organization-safe dimensions and bounded cardinality.
9. Add notifications and runner quarantine for containment or cleanup failures.
10. Generate a release evidence bundle with machine-readable results, report summary, known gaps, waivers, and artifact digests.

## Acceptance criteria

1. Required scenario sets are selected by immutable manifest; code under test cannot silently remove or downgrade a mandatory scenario.
2. Untrusted/forked CI cannot access dedicated chaos runners, credentials, Docker host controls, or cloud subscriptions.
3. A mandatory `FAILED`, `ERROR`, `SKIPPED`, `ABORTED`, `INDETERMINATE`, stale, or cleanup-failed result blocks its configured gate.
4. Policy-only results cannot satisfy sandbox, agent, or infrastructure control requirements.
5. Baselines compare like-for-like scenario, runner, provider, image, and policy versions or explicitly report incompatibility.
6. Waivers are scoped, signed, expiring, visible in reports, and cannot waive canary disclosure or containment-loss findings without separate emergency governance.
7. Reports distinguish verified controls, unsupported checks, known gaps, and inferred assumptions.
8. A release bundle is content-addressed and traceable to source revision and campaign/evaluation IDs.
9. Alert tests prove containment/cleanup failures notify owners and quarantine the affected runner.
10. Retention and access controls prevent evidence from leaking tenant or synthetic canary content.

## Verification and evidence

- CI policy tests for pull-request trust boundaries and required jobs.
- Gate unit tests for every terminal result, stale evidence, missing scenario, incompatible baseline, and waiver expiry.
- Dashboard/alert tests using synthetic events.
- Release-bundle verification reconstructs digests and links results to source revision.
- Periodic game day validates operator abort, quarantine, cleanup, and incident handoff.

## Dependencies and risks

- Requires CHAOS-001 and should onboard CHAOS-002 through CHAOS-009 incrementally.
- Risk: flaky infrastructure blocks releases. Treat flakes as errors, fix the test/environment, and use transparent time-bounded waivers rather than converting errors to passes.
- Risk: metrics cardinality/cost. Use campaign/scenario/provider dimensions; keep task IDs in trace/log evidence rather than metric labels.

## Likely implementation areas

- evaluation/promotion services and CI workflows
- observability configuration and Grafana dashboards
- web evaluation/campaign reports and evidence storage

## References

- [Management and evaluation](../management-and-evaluation.md)
- [Runtime supervision adapters](../runtime-supervision-adapters.md)
- [Story index and safety contract](README.md)
