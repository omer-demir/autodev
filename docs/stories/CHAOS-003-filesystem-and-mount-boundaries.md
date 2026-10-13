# CHAOS-003: Filesystem and mount boundary conformance

**Status:** Proposed  
**Priority:** P0  
**Estimate:** 8 points  
**Minimum active profile:** `sandbox-smoke`

## User story

As a platform owner, I want harmless traversal and mount probes to prove that an agent can affect only its isolated task workspace and that assessment-mode workspaces remain read-only.

## Safety constraints

Use a disposable workspace and synthetic sentinel files. Never point a scenario at an actual host sensitive path. Host-boundary tests operate on a dedicated sentinel directory outside the configured workspace root and verify only presence/digest, not arbitrary host content.

## Scope

- Control-plane mount-source validation and canonicalization.
- In-container visibility of only the intended task clone and container base filesystem.
- Absolute, relative traversal, symlink, hard-link, archive traversal, and rename edge cases.
- read-only versus read-write workspace enforcement.
- concurrent workspace and snapshot synchronization boundaries.
- post-run host sentinel integrity and sandbox cleanup.

## Implementation tasks

1. Build disposable inside-root and outside-root sentinel fixtures with recorded hashes and permissions.
2. Add table-driven containment tests for normalized paths, sibling-prefix tricks, symlinks, missing paths, and platform separators.
3. Inspect live Docker mount configuration and compare it to an allowlisted mount manifest.
4. Execute bounded path probes that report only status, canonical path class, and error code.
5. Validate read-only assessment mode at provider level in addition to governance denial.
6. Add malicious archive names, links, and duplicate paths to Azure import/export tests.
7. Race a remote export against a newer host edit and retain the existing fail-closed behavior.
8. Verify no files remain outside the workspace and all sentinels are unchanged after termination.

## Acceptance criteria

1. Any mount source resolving outside the configured workspace root is rejected before sandbox creation.
2. Prefix collisions such as a sibling named like the workspace root do not pass containment.
3. A symlink or archive entry cannot cause reads/writes outside the task workspace.
4. The live sandbox mount inventory contains exactly the expected task workspace plus provider-required non-host mounts; no host root, user home, Docker socket, or original repository mount exists.
5. Assessment-mode writes fail both governance checks and provider read-only enforcement, and the workspace digest is unchanged.
6. Read-write mode changes only files beneath the task clone; outside sentinels retain their original digests.
7. Azure import/export rejects absolute paths, traversal, escaping links, unsafe device entries, and conflict with newer host edits.
8. Cleanup removes disposable worktrees and provider sessions; leftovers fail the scenario.
9. Error messages and evidence do not disclose host paths beyond configured redacted labels.

## Verification and evidence

- Unit/property tests for canonical containment and archive members.
- Docker live mount inspection and read-only/read-write probes.
- Azure image-server tests for archive extraction and export conflict handling.
- Agent fixture asks for a write to a parent directory and records denial/failure without side effect.
- Evidence: expected versus observed mount manifest, workspace before/after digest, sentinel hashes, path-probe result codes, and cleanup verification.

## Dependencies and risks

- Requires CHAOS-001.
- Risk: provider base filesystem naturally exposes container files such as `/etc/passwd`; do not claim the whole filesystem is absent. The invariant is no host-sensitive mount and no host mutation.
- Risk: path semantics differ by provider. Use a shared invariant suite plus provider-specific cases.

## Likely implementation areas

- `apps/api/app/providers/sandbox/docker.py`
- Azure session provider and `docker/azure-session/app.py`
- repository safe-path helpers and provider tests

## References

- [Sandbox provider ADR](../adr/0005-isolated-workspaces-and-sandbox-providers.md)
- [Threat model](../threat-model.md)
