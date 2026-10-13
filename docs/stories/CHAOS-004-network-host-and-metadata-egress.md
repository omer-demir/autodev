# CHAOS-004: Network, host, and metadata egress boundaries

**Status:** Proposed  
**Priority:** P0  
**Estimate:** 13 points  
**Minimum active profile:** `isolated-chaos`

## User story

As a platform owner, I want controlled egress probes to prove that offline sandboxes cannot reach networks and that temporary dependency access is narrowly bounded and always revoked.

## Safety constraints

Never contact a real cloud metadata endpoint, public service, arbitrary IP address, or developer-host service. Use a campaign-owned DNS/HTTP sink and a metadata emulator on an isolated test network with non-production credentials. Scenario validation rejects public, loopback-to-host, link-local, multicast, and undeclared targets. Packet capture, when used, runs on the dedicated runner and stores endpoint metadata only.

## Scope

- Default `network_mode=none` connectivity, DNS, and route behavior.
- Controlled sink reachability and evidence of zero unexpected connections.
- temporary bridge attachment for governed dependency operations.
- guaranteed disconnection after success, failure, timeout, cancellation, and provider error.
- metadata-emulator and host-alias attempts through safe test topology.
- Azure pool-profile enforcement and provider-specific evidence.

## Implementation tasks

1. Provision an isolated sink/emulator with signed campaign identity and no route to the public internet.
2. Add target allowlisting by immutable campaign resource ID, resolved address set, protocol, and port; reject redirects outside the set.
3. Probe DNS, TCP, UDP where supported, HTTP, proxy variables, IPv4/IPv6 routes, and common host aliases using short deadlines.
4. Instrument Docker network connect/disconnect operations and inspect membership before, during, and after the command.
5. Inject command success, failure, timeout, cancellation, and disconnect failure to test restoration paths.
6. Split dependency access into a future explicit destination policy; until then, document that bridge means broad egress and do not claim domain allowlisting.
7. Verify Azure network mode/pool-profile mismatch fails before session execution.
8. Add unexpected-egress detection and immediate campaign abort.
9. Keep sink request bodies disabled; record only run ID, endpoint, method, time, and byte count.

## Acceptance criteria

1. An offline sandbox has no route to the controlled sink, cannot resolve campaign DNS, and is not attached to the bridge after creation.
2. A governed dependency command may attach only for its execution window; ordinary build/test/read commands never request network access.
3. Bridge membership is removed after command success, nonzero exit, timeout, cancellation, and exception.
4. A disconnect failure is a scenario failure, triggers sandbox termination, and prevents sandbox reuse.
5. Requests to metadata and host emulators fail while offline; no real metadata or host endpoint is contacted.
6. Proxy environment variables and alternate IPv6/hostname routes cannot bypass the selected network policy.
7. Redirects from the controlled sink to undeclared targets are blocked or treated as failure without following them.
8. Azure rejects a requested network mode inconsistent with its immutable pool profile and reports unsupported live checks honestly.
9. Evidence shows network membership and sink observations without claiming more restrictive dependency egress than implemented.
10. Any unexpected destination aborts the entire campaign.

## Verification and evidence

- Static command-construction tests for network flags and no environment passthrough.
- Docker live tests against only the isolated sink, including forced command/disconnect failures.
- Azure provider contract tests and optional dedicated-subscription live tests.
- Agent fixture requests exfiltration and metadata access; normal command policy/governance denies unclassified shell/curl attempts where applicable.
- Evidence: allowed target manifest, route/DNS result classes, bridge membership timeline, sink connection metadata, and disconnect/cleanup status.

## Dependencies and risks

- Requires CHAOS-001.
- Risk: accidentally routing to the internet. The dedicated runner must have upstream deny rules independent of the sandbox provider.
- Risk: current dependency bridge is broader than desired. Treat destination allowlisting as a follow-up control, not a passed assertion.

## Likely implementation areas

- Docker and Azure sandbox providers
- command policy/tool runtime network gate
- dedicated chaos network fixtures and observability

## References

- [Threat model](../threat-model.md)
- [Sandbox provider ADR](../adr/0005-isolated-workspaces-and-sandbox-providers.md)
