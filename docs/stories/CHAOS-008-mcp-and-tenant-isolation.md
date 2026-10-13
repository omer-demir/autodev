# CHAOS-008: MCP trust and tenant-isolation validation

**Status:** Proposed  
**Priority:** P1  
**Estimate:** 13 points  
**Minimum active profile:** `isolated-chaos`

## User story

As a hosted-platform owner, I want cross-organization and untrusted-MCP probes to prove that identities, records, artifacts, credentials, and tool calls remain tenant-scoped and origin-bound.

## Context

Organization-scoped durable records and RBAC exist, while shared filesystem registries and some local-mode credentials limit any claim of hostile multi-tenancy. This story must expose those limits rather than certify unsupported isolation.

## Safety constraints

Use two synthetic organizations, synthetic users/agents, and a campaign-owned fake MCP server. Never probe another real tenant or third-party MCP endpoint. The fake server returns canaries and malformed protocol responses but performs no external calls.

## Scope

- object-level authorization for tasks, sessions, events, approvals, artifacts, evaluations, identities, and connectors;
- organization binding across list/get/update/action endpoints and background jobs;
- MCP origin/host allowlists, authentication, capability mapping, schema validation, timeout, output limits, and secret redaction;
- confused-deputy attempts using IDs from another synthetic organization;
- cache, event stream, snapshot, and evidence-store partitioning;
- explicit blockers from shared registries or local credential slots.

## Implementation tasks

1. Create a reusable two-organization security fixture with identical-looking resource names and unique canaries.
2. Build an endpoint/action authorization matrix and parameterized tests for direct IDs, filters, pagination cursors, nested routes, and background continuation.
3. Verify storage queries include organization scope and do not rely only on UI filtering.
4. Run the fake MCP server on a campaign-owned endpoint with scenarios for wrong origin, redirect, auth failure, tool-name collision, oversized output, malformed JSON/schema, timeout, and canary return.
5. Map MCP tools to semantic capabilities and apply governance/supervision before dispatch.
6. Partition or key caches by organization, actor, server identity, and policy version.
7. Verify event streams and evidence URLs cannot be reused across organizations.
8. Add a conformance blocker listing shared registries/local credential features that prevent hostile multi-tenant certification.
9. Abort on any cross-org canary observation and preserve only redacted evidence.

## Acceptance criteria

1. Every tested resource action returns not-found/forbidden for the other synthetic organization and leaks no resource metadata through timing-independent response content where practical.
2. List, search, pagination, event streaming, exports, snapshots, and background jobs return only the active organization’s records.
3. Approval, artifact, task, or agent IDs from organization A cannot authorize or influence work in organization B.
4. MCP dispatch occurs only to an exact configured server identity/origin with valid service authentication; redirects and alternate origins are rejected.
5. MCP tool arguments and results pass versioned schema and size validation, redaction, capability governance, supervision, timeout, and evidence rules.
6. An MCP tool-name collision cannot substitute for a trusted built-in tool or inherit its capability.
7. Cache entries and durable evidence are partitioned; a cross-org canary observation fails and aborts the campaign.
8. Unsupported hostile-tenancy controls produce an explicit `NOT_CERTIFIED` result, not a pass based on local-mode assumptions.
9. The fake MCP server and all synthetic resources are removed and independently verified after the campaign.

## Verification and evidence

- Parameterized API authorization matrix and storage-query tests.
- MCP gateway contract/integration tests against only the fake server.
- Event/evidence signed-URL and cache-partition tests.
- Evidence: synthetic organization IDs, resource classes, decision/result codes, MCP server identity and protocol version, canary detection status, known certification blockers, and cleanup.

## Dependencies and risks

- Requires CHAOS-001.
- Risk: shared registries make full hostile-tenancy claims false. Keep the campaign result scoped and block certification until registries are organization-aware or immutable trusted control-plane data.
- Risk: test IDs leak existence. Normalize unauthorized responses and avoid returning object attributes.

## Likely implementation areas

- API routes, authorization dependencies, models, evidence/snapshot providers
- MCP gateway and tool mapping
- organization-aware registries, caches, and connector credentials

## References

- [MCP and A2A boundaries](../design/mcp-and-a2a.md)
- [Multi-user and roles](../multi-user-and-roles.md)
- [Identity, tenancy, and publication ADR](../adr/0009-identity-auth-tenancy-and-publication.md)
