# ADR 0002: Versioned declarative control plane

- Status: Accepted with limitations
- Date: 2026-10-06

## Context

Agents depend on instructions, skills, capabilities, tool schemas, policies, workflows, sandbox profiles, MCP declarations, and evaluation suites. Hiding these choices in application code or database rows would make reviews difficult and would allow runtime behavior to drift without a corresponding repository change.

Imported internet agents and skills are useful authoring sources but are untrusted instruction data. Their tool declarations cannot be allowed to grant local authority.

## Decision

Git-reviewable YAML registries are the source of truth for agents, skills, policies, workflows, harnesses, capability catalogs, MCP servers, and evaluation suites. Registry validation resolves cross-references and rejects malformed states before execution.

Agents and workflows carry semantic versions. Agents pin an exact harness version, and a harness pins a capability catalog. Missing pins fail closed. Saving an agent returns it to `draft`; status cannot be set to promoted by editing YAML.

At task creation, the selected executable workflow definition is stored as an immutable task artifact. Retries use the captured definition rather than silently adopting later workflow edits. Runtime policy and agent declarations are intentionally reloaded for retries and each tool decision so operators can revoke authority immediately; the immutable workflow preserves orchestration shape while current policy preserves revocation.

Imported `.agent.md`, `SKILL.md`, GitHub, and skills.sh content is normalized into local definitions. Remote model, tool, permission, script, and handoff declarations are retained only as provenance. New imports receive conservative local policy and draft status.

## Alternatives considered

- Store all definitions in relational tables. Rejected for the initial control plane because code review, environment promotion, and repository-local reproducibility are primary requirements.
- Compile definitions into application code. Rejected because it couples operational policy changes to releases and obscures ownership.
- Trust imported tool declarations. Rejected because an external document must not expand local authority.
- Always load the latest workflow during retry. Rejected because a task could change meaning midway through its history.
- Freeze all policy with the task. Rejected because incident response needs immediate revocation of dangerous capabilities.

## Consequences

A reviewer can inspect behavior-affecting declarations in Git. Registry versions become part of evidence. Workflow reproducibility and policy revocation follow deliberately different rules and must be explained in the UI and documentation.

Deployment-wide files are simple locally but do not provide per-organization registry ownership. Concurrent UI edits and Git edits require operational discipline because the filesystem, not a transactional registry service, is authoritative.

## Security and operations

Validation must reject path traversal, unknown references, duplicate IDs, cycles, unsafe artifact ancestry, and manual promotion. Compose bind mounts make local UI edits durable; cloud deployment must define how registry revisions are distributed and audited.

Imported content is subject to bounded size, redirect, timeout, and public-address checks to limit SSRF and resource abuse. Instruction sanitization is defense in depth; deterministic capability and policy checks remain authoritative.

## Validation and limits

Registry tests cover cross-reference resolution, workflow DAGs, cycles, status transitions, and artifact ancestry. Shared registries and connector definitions are not yet a hostile multi-tenant boundary. A future registry service may retain Git as the review source while adding organization ownership, optimistic concurrency, and an audit log.
