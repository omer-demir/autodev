# ADR 0004: Layered semantic capability governance

- Status: Accepted
- Date: 2026-10-06

## Context

Prompts can influence model behavior but cannot reliably authorize side effects. Tool names and shell strings are also unstable authorization units: several tools may perform the same semantic action, and one command tool can represent many risk levels. Agent declarations, deployment policy, human approvals, and runtime risk supervision have different owners and must remain independently enforceable.

## Decision

Autodev authorizes semantic capabilities such as `repository.read`, `repository.write`, `test.run`, `dependency.install`, and `git.push`, not arbitrary model intent. A versioned capability catalog defines the vocabulary. A pinned harness binds typed model tools and argument schemas to capabilities and runtime implementations.

Every tool invocation passes through ordered boundaries:

1. Framework argument validation and harness resolution.
2. Capability classification, including argument-vector command classification.
3. Agent declaration and selected governance-policy intersection.
4. Runtime-supervision decision for the current task/evaluation identity and agent.
5. Scoped human approval where the action requires it.
6. Sandbox-provider enforcement and execution.

Missing capability, unresolved harness/catalog version, policy disagreement, supervision error, or absent approval fails closed. Deny wins. Generic unrestricted shell is not model-visible; command execution uses argument vectors and a classified allow-list.

Agent Governance Toolkit and portable local implementations sit behind provider contracts. Runtime supervision owns trust score, execution tier, phase transitions, bounded elevation, breach handling, and termination. It is separate from static authorization so a permitted capability can still be denied in the current runtime state.

## Alternatives considered

- Encode permissions only in the system prompt. Rejected because prompt injection and model error can bypass prose.
- Authorize by tool name. Rejected because names do not capture argument-dependent semantics and make tool replacement a policy change.
- Let the sandbox be the only control. Rejected because filesystem/process containment cannot express business approvals or semantic intent.
- Merge agent declaration and deployment policy. Rejected because agent authors must not control organization-wide authority.
- Treat supervision errors as allow. Rejected because unavailable safety infrastructure must not expand authority.

## Consequences

Tool implementations carry more integration responsibility: schemas, classification, policy context, events, and evidence must agree. The benefit is provider-neutral authorization and an audit trail that explains why an action was allowed or denied.

Harness/catalog version changes are compatibility events. Policies can be edited without changing prompts, and denials apply on the next tool call. Agents may be useful but unable to complete a task when their declared capabilities are too narrow; that is a visible configuration failure rather than implicit escalation.

## Security and operations

Policy decisions must avoid logging credentials or unbounded tool output. Approval scope must include immutable action details or artifact hashes. Elevations are time-bounded and auditable, not permanent declaration edits. Runtime handles are keyed by execution identity and agent so specialist roles do not share trust state.

Provider parity is evidence-based: a local adapter must not claim upstream conformance it does not implement. The application documents implemented, partial, and missing Agent Hypervisor behavior.

## Validation and limits

Security evaluations probe expected catalog decisions, and workflow tests verify role-specific supervision. Current policy conditions are less expressive than a full attribute-based policy engine. Capability classification remains a sensitive code path and must gain tests whenever a new command or tool is introduced.
