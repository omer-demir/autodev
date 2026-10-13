# ADR 0009: Human identity, agent identity, tenancy, MCP, and publication

- Status: Accepted with limitations
- Date: 2026-10-06

## Context

Human authorization and agent capability are different trust domains. A promoted agent may be allowed to request a change, while only a human reviewer may approve publication. Browser, CLI, and MCP clients need consistent organization and permission checks. Agent versions also need a stable identity that can be compared with evaluation and capability evidence.

## Decision

The control plane supports local and OIDC auth modes. Local mode provisions a single local administrator for development. Production OIDC uses authorization code with PKCE, issuer/audience/signature validation, opaque HttpOnly browser sessions, and bearer-token support for CLI/MCP clients.

Human roles map to explicit permissions. Organization ID is stored on primary durable records and applied to API, WebSocket, evaluation, and MCP access. Actor identity is recorded on mutations and approval decisions.

Agent identity is a separate local DID and signed manifest backed by AgentMesh-compatible primitives. Promotion binds the exact declaration version and evidence to the agent identity. Agent capabilities never imply human permissions, and human RBAC never directly grants model tools.

The MCP gateway reuses session/task ownership, organization scope, promoted-agent checks, pending-approval checks, policy, queue, and sandbox execution. It is an alternate interface to the same control plane, not an escape hatch.

Commit, push, and pull-request publication are deterministic control-plane operations after agent work. They require scoped approvals and a clean expected worktree. Credentials are retrieved from configured credential providers and exposed only through ephemeral askpass/environment mechanisms with output redaction.

## Alternatives considered

- Use agent DID as the human actor. Rejected because accountability and separation of duties would collapse.
- Give browser clients long-lived provider tokens. Rejected in favor of opaque server-side sessions and bounded connector handling.
- Implement separate MCP authorization. Rejected because interface-specific policy would drift from REST behavior.
- Let agents run `git push` directly in the sandbox. Rejected because publication credentials and irreversible actions require a narrow approved path.
- Make local mode emulate full hostile multi-tenancy. Rejected as misleading; local mode is explicitly a trusted development configuration.

## Consequences

All new APIs and subscriptions must carry organization and permission checks. Publication can be resumed independently from model execution and remains auditable. Agent identity records require drift handling when declarations change.

OIDC integration adds session, membership, and claim-mapping operations. Connector credentials and filesystem registries remain deployment-scoped in places, so organization-scoped database rows alone do not make the current system a complete hostile-tenant boundary.

## Security and operations

Secure cookies, TLS, OIDC nonce/state/PKCE, JWKS rotation, role assignment, and session expiry are production requirements. Requester/approver separation should be enforced for high-risk actions. Credentials must never enter prompts, sandbox mounts, evidence, or logs.

MCP host/origin validation, bearer authentication, task membership, and pending-approval checks are mandatory. Signed agent manifests prove local declaration identity but do not constitute a public PKI or marketplace trust guarantee.

## Validation and limits

Auth tests cover local/OIDC dependencies, role permissions, organization scoping, and tenant-scoped subscriptions. Shared YAML registries and some connectors are not organization-owned. Approval expiry, revocation before execution, and cryptographic evidence signing need further hardening.
