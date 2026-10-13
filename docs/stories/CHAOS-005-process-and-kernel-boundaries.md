# CHAOS-005: Process, privilege, and kernel boundary conformance

**Status:** Proposed  
**Priority:** P1  
**Estimate:** 13 points  
**Minimum active profile:** `isolated-chaos`

## User story

As a security owner, I want non-destructive kernel and process probes to verify namespace, capability, privilege, and device isolation without running an actual exploit.

## Safety constraints

Do not execute public exploit code, fuzz the host kernel, load modules, access real devices, use host namespaces, or attempt a true container escape. Probes are limited to inspection and known-safe failing syscalls against fixture processes/resources inside a disposable sandbox. Run only on a dedicated runner with an outer timeout and host health watchdog.

## Scope

- Effective/permitted/bounding Linux capabilities.
- `no-new-privileges`, UID/GID, namespace identity, process visibility, and PID ceiling.
- access to sensitive device nodes, kernel interfaces, host IPC, and Docker socket.
- benign denied operations such as namespace creation, mount, ptrace of a fixture process where policy expects denial, raw socket creation, and privilege transition.
- image user and runtime-flag conformance.
- provider-specific evidence and unsupported-state reporting.

## Implementation tasks

1. Define a reviewed allowlist of probe binaries/syscalls and immutable arguments; agents cannot supply arbitrary kernel operations.
2. Add a minimal signed probe helper image or binary with machine-readable result codes and no exploit payloads.
3. Inspect `/proc/self/status`, namespace identifiers, UID/GID, capability sets, and `NoNewPrivs`.
4. Compare visible processes to campaign-created fixture process IDs; do not collect host command lines.
5. Attempt only the approved failing operations with per-probe deadlines.
6. Inventory sensitive device/socket paths by boolean existence and type, never by content.
7. Add host watchdog checks for CPU, memory, process count, Docker health, and unexpected namespaces; abort on threshold.
8. Verify sandbox termination and runner recovery after every probe set.
9. Pin the sandbox image by digest for campaign evidence and add supply-chain verification as a prerequisite for production claims.

## Acceptance criteria

1. Docker sandbox effective, permitted, and bounding capabilities match the expected empty/minimal set, and `NoNewPrivs` is enabled.
2. The process runs as the configured unprivileged numeric UID/GID and cannot transition to elevated privilege through the approved benign probe.
3. Sandbox process views and namespace identifiers do not expose campaign fixture processes outside the sandbox.
4. Approved mount, raw-socket, namespace, and ptrace probes fail with expected permission/result classes and no host side effect.
5. Sensitive host devices, Docker socket, and host IPC endpoints are not mounted into the sandbox.
6. PID use remains within the configured ceiling; the scenario avoids an unbounded fork loop and uses a finite, counted process burst.
7. Any unexpected success, host-health change, or ambiguous observation aborts the campaign and quarantines the runner for review.
8. No conclusion is reported for controls not observable on a provider; unsupported checks are explicit non-passes for required claims.
9. Evidence includes image digest, runtime flags, kernel/platform fingerprint, capability/namespace summaries, and cleanup result without host process details.

## Verification and evidence

- Static tests assert secure Docker arguments and rejection of unsupported modes.
- Dedicated-runner live test executes the signed probe suite in a disposable sandbox.
- Negative test intentionally removes one flag in a mocked command and proves conformance fails.
- Host watchdog and abort-path tests use simulated threshold events.
- Events separate `probe.denied_as_expected` from `probe.failed_to_run`; the latter is never a pass.

## Dependencies and risks

- Requires CHAOS-001.
- A seccomp/AppArmor/SELinux profile is not currently an established control; report its absence rather than implying enforcement.
- Risk: kernel-specific differences create noise. Pin runner classes and expected profiles, and version provider expectations.

## Likely implementation areas

- Docker sandbox command construction
- sandbox image and dedicated probe helper
- provider conformance tests and campaign runner

## References

- [Threat model](../threat-model.md)
- [Sandbox provider ADR](../adr/0005-isolated-workspaces-and-sandbox-providers.md)
