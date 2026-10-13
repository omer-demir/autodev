# CHAOS-006: Resource exhaustion, cancellation, and recovery

**Status:** Proposed  
**Priority:** P1  
**Estimate:** 13 points  
**Minimum active profile:** `isolated-chaos`

## User story

As a reliability owner, I want bounded pressure and fault tests to prove that one agent cannot exhaust shared capacity and that the platform terminates, records, and recovers from resource failures.

## Safety constraints

Run only on dedicated disposable capacity. Use finite stressors with ceilings below runner reserves; never use fork bombs, infinite loops without an outer kill, disk-fill-to-host-capacity, or uncontrolled allocation. A host watchdog must retain reserved CPU, memory, disk, and PID headroom and independently terminate the campaign.

## Scope

- sandbox memory, CPU, PID, wall-clock, output, and workspace-size boundaries;
- tool and shell invocation budgets;
- model token/cost and retry budgets;
- cancellation during model call, command execution, network attachment, artifact upload, and cleanup;
- API/sandbox responsiveness during pressure;
- orphan detection, queue recovery, and evidence preservation.

## Implementation tasks

1. Define finite stress helpers parameterized below sandbox limits and signed/versioned with the campaign.
2. Add runner-reserve preflight and watchdog thresholds stricter than host exhaustion.
3. Exercise memory pressure to a controlled threshold, finite CPU saturation, counted child processes, bounded output, and workspace quota.
4. Test the exact maximum and first-over-limit behavior for tool, shell, token, retry, and elapsed-time budgets.
5. Inject cancellation/failure at each lifecycle phase and verify idempotent cleanup.
6. Distinguish expected enforcement from infrastructure failure using explicit result codes and cgroup/provider evidence.
7. Verify neighboring control-plane health with a lightweight canary request and queue-latency measurement.
8. Detect and reap orphan containers/sessions/worktrees; retain a cleanup incident when removal fails.
9. Add cooldown and runner quarantine after watchdog intervention or provider cleanup failure.

## Acceptance criteria

1. Finite memory pressure is contained by the sandbox limit without crossing the runner's reserved headroom; the task reaches a deterministic failed/cancelled state.
2. CPU stress is throttled to the configured sandbox allocation and the control-plane health canary remains within its threshold.
3. Counted process creation reaches an expected limit/failure class without exceeding the sandbox PID ceiling or affecting host/control-plane processes.
4. The first tool and shell invocation beyond policy budget is denied before execution and is represented in evidence.
5. Command timeout and user cancellation terminate execution and prevent subsequent tool calls.
6. Output and artifact size limits truncate or reject data with explicit metadata; truncation cannot be mistaken for complete test evidence.
7. Network attachment, sandbox, workspace, and leases are cleaned after every injected failure point.
8. A cleanup failure, missing cgroup/provider observation, or unhealthy neighbor changes the result to failed/indeterminate and quarantines the runner.
9. Queue processing and a fresh benign task recover within the declared objective after the scenario.
10. Production-passive mode runs no pressure helper.

## Verification and evidence

- Unit tests for every budget boundary and cancellation state transition.
- Provider integration tests with deterministic fake failures plus dedicated-runner live pressure tests.
- Evidence: configured/effective limits, peak provider metrics, termination reason, budget counters, control-plane canary latency, orphan scan, cleanup attempts, and recovery time.
- Metrics and alerts for resource denials, OOM/termination class, timeouts, cleanup failures, and quarantined runners.

## Dependencies and risks

- Requires CHAOS-001.
- Risk: resource limits may be unavailable under some container runtimes. Preflight must observe enforcement, not infer it from requested flags.
- Risk: OOM events can affect the runner when nesting is misconfigured. Require dedicated capacity, conservative thresholds, and an outer watchdog.

## Likely implementation areas

- sandbox providers and task cancellation
- tool/runtime/model budget accounting
- worker lifecycle, evidence storage, and observability

## References

- [Runtime supervision adapters](../runtime-supervision-adapters.md)
- [Threat model](../threat-model.md)
