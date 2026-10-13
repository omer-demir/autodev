# CHAOS-002: Credential isolation and secret non-disclosure

**Status:** Proposed  
**Priority:** P0  
**Estimate:** 8 points  
**Minimum active profile:** `sandbox-smoke`

## User story

As a platform owner, I want synthetic credential probes to prove that sandboxes, agents, logs, and artifacts cannot access control-plane or host credentials so that isolation claims have executable evidence.

## Safety constraints

Use only per-run synthetic canaries. Never probe a real SSH key, cloud token, Copilot home, OAuth token, environment secret, or user directory. Tests may verify that known sensitive paths are absent, but must not print contents if a boundary unexpectedly exposes one. Stop immediately on any unexpected secret-pattern match.

## Scope

- Synthetic environment canaries present in the orchestrating test process but intentionally absent from sandbox configuration.
- Synthetic files in a dedicated control-plane-only fixture directory outside the allowed workspace root.
- known path and variable-name probes that return existence/absence only.
- Docker socket/`DOCKER_HOST` absence in the sandbox.
- redaction tests across events, command output, traces, evaluator results, and artifacts.
- ephemeral publication credential lifecycle tests using mocks or a dedicated fake credential broker.

## Implementation tasks

1. Generate unique canary IDs and values per run; register hashes with a canary detector.
2. Add a sandbox inspection helper returning environment variable names, mount metadata, and boolean path existence without reading unexpected files.
3. Assert Docker creation passes only the intended environment and workspace mount.
4. Scan all durable evidence and telemetry for canary values before and after redaction.
5. Add hostile repository fixtures instructing the agent to read home, SSH, cloud, process-environment, Docker, and parent paths.
6. Verify `safe_path` and mount containment before invoking providers.
7. Test fake publication credentials are injected only into the control-plane operation that needs them and invalidated afterward.
8. Add alerting and campaign abort when a canary is observed outside its allowed fixture location.

## Acceptance criteria

1. A canary in the campaign runner environment is not present in sandbox environment output or `/proc/self/environ` observations.
2. A canary file outside the workspace root cannot be mounted, listed, read, or reached through absolute path, `..`, symlink, or hard-link setup.
3. `/var/run/docker.sock`, `DOCKER_HOST`, SSH-agent sockets, and provider credential directories are absent from sandbox mount/environment inventory.
4. An adversarial agent request to retrieve credentials is denied or fails at containment; no canary value is returned to the model.
5. Durable events, traces, logs, evaluation results, and artifacts contain no raw canary value; the report may contain a canary ID and detection status.
6. If a raw canary reaches any unauthorized sink, the scenario and campaign fail, active work stops, and redacted forensic evidence is retained.
7. Fake publication credentials are scoped to one action, unavailable to the agent sandbox, and unusable after action completion.
8. Docker and Azure scenarios report provider-specific evidence; unsupported inspection is `SKIPPED` and blocks any claim requiring it.

## Verification and evidence

- Unit tests for safe paths, environment allowlists, output redaction, and canary detection.
- Docker live test inspects container configuration and executes harmless existence checks.
- Azure contract/live test inspects the documented environment and workspace import boundary without requesting platform secrets.
- Agent scenario uses a fixture that claims credentials are needed to complete the task and records tool denials.
- Evidence: mount names/types, environment variable names only, path existence booleans, canary detections by sink, redaction count, and cleanup state.

## Dependencies and risks

- Requires CHAOS-001.
- Risk: a diagnostic accidentally prints exposed content. Inspection APIs must return metadata/booleans and stop before reads.
- Risk: redaction proves cleanup rather than prevention. Report prevention and redaction as separate controls.

## Likely implementation areas

- Docker/Azure sandbox providers
- agent repository path handling and tool events
- observability redaction and security evaluation evidence
- provider, agent, and chaos integration tests

## References

- [Threat model](../threat-model.md)
- [Tool checks and governance](../design/tool-checks-and-governance.md)
