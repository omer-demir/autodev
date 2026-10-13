# ADOPT-006: Thin IDE integration over the control-plane API

**Status:** Proposed  
**Priority:** P2  
**Estimate:** 8 points

## User story

As a developer, I want to create, observe, approve, cancel, and inspect governed tasks from my editor so that I can stay in context without moving governance or execution into the extension.

## Context

A thin IDE client is useful when the server remains authoritative for identity, workflow, policy, sandboxing, approvals, and evidence. Embedding a second agent runtime in the editor would create inconsistent controls and expose local credentials and files.

## Scope

- Define a versioned client contract using existing authenticated HTTP APIs and resumable event streaming.
- Provide commands for task creation, task status, evidence/artifact viewing, scoped approval, cancellation, and opening produced diffs.
- Send repository identity, revision, selected workspace-relative paths, task text, and optional editor diagnostics only with explicit user action.
- Display server-provided sandbox, organization, agent, model, workflow, policy, and approval state.
- Implement reconnect from a durable event cursor and idempotency keys for mutating requests.
- Produce a reference VS Code extension only after the API contract and threat review are complete.

## Non-goals

- No direct model-provider calls, local shell execution, sandbox management, or policy evaluation in the extension.
- No automatic upload of the whole workspace, editor history, environment, credentials, or unsaved buffers.
- No hidden approval or one-click blanket approval.
- No direct database, Docker, MCP, or evidence-store access.

## Implementation tasks

1. Inventory current APIs and define missing DTOs, error codes, idempotency, cursor, and capability-discovery endpoints.
2. Add a server endpoint that reports supported client/API versions and feature flags.
3. Threat-model repository mapping, symlinks, untrusted task content, deep links, token storage, and approval phishing.
4. Implement an SDK generated from the API schema with organization and correlation headers.
5. Build commands and read-only tree views; make security-relevant state prominent and non-spoofable by task text.
6. Use VS Code secret storage for the user session token and OS/browser auth flow; never expose it to tasks or logs.
7. Add confirmation showing exact action digest, scope, expiry, and server identity before approval.
8. Add telemetry opt-in, local redaction, bounded logs, and a diagnostics export with no token values.
9. Test reconnect, duplicate requests, server version skew, organization switching, and revoked sessions.

## Acceptance criteria

1. All execution and authorization decisions occur server-side; disabling the extension leaves task semantics unchanged.
2. Creating a task requires explicit user action and sends only fields shown in a pre-submit preview.
3. Paths are workspace-relative, normalized, and validated server-side; the extension cannot request host paths as task mounts.
4. Approval UI renders server-signed/returned action details and requires explicit confirmation for each scope.
5. Retrying after disconnect does not create duplicate tasks or approvals.
6. Event streaming resumes from the last acknowledged durable cursor without presenting missing history as complete.
7. Revoked/expired auth fails closed, clears cached organization state, and does not leak token material to output logs.
8. Unsupported server versions disable incompatible actions with an actionable message.
9. Extension tests prove no local shell, Docker, provider, or governance implementation is bundled.
10. Security review confirms untrusted repository text cannot spoof trusted approval or policy UI regions.

## Verification and evidence

- Contract tests generated from the OpenAPI specification.
- Integration tests with reconnects, 401/403 responses, idempotent retries, and organization changes.
- Extension package-content audit and secret-pattern scan.
- Server events identify client name/version, request correlation ID, actor, and idempotency key without editor content not required for the action.

## Dependencies and risks

- ADOPT-003 enables reliable artifact rendering.
- Risk: extension scope grows into a second control plane. Enforce architectural checks and package audits.
- Risk: repository content spoofs trusted UI. Separate trusted chrome from rendered untrusted content and sanitize Markdown/webviews.

## Likely implementation areas

- API routes and OpenAPI DTOs under `apps/api`
- a future dedicated VS Code extension package
- authentication, task-event, approval, and artifact endpoints

## References

- [Editors and model providers](../editors-and-model-providers.md)
- [Identity, tenancy, and publication ADR](../adr/0009-identity-auth-tenancy-and-publication.md)
