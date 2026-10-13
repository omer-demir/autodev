# Architecture decision records

These records capture Autodev's non-obvious technical landscape choices. They intentionally omit ordinary implementation-language and infrastructure-language selections such as Python or Bicep. Each ADR describes a durable boundary or a choice whose reversal would change product semantics, security posture, data ownership, or operations.

| ADR                                                             | Decision area                                                                               |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [0001](0001-durable-task-session-and-execution-semantics.md)    | Task, session, execution job, retry, and continuation semantics                             |
| [0002](0002-versioned-declarative-control-plane.md)             | YAML registries, version pinning, immutable workflow snapshots, and imported content        |
| [0003](0003-executable-multi-agent-workflows.md)                | Agent-owned stages, handoffs, sequential execution, and safe DAG parallelism                |
| [0004](0004-layered-capability-governance.md)                   | Capabilities, harnesses, policy intersection, supervision, and approvals                    |
| [0005](0005-isolated-workspaces-and-sandbox-providers.md)       | Git worktrees, Docker/Azure sandboxes, stage environments, and credential boundaries        |
| [0006](0006-model-runtime-and-context-boundaries.md)            | Model providers, recovery, Prompty assets, tools, steering, and bounded retrieval           |
| [0007](0007-independent-behavioral-evaluation-and-promotion.md) | Evaluation-owned execution, frozen datasets, evaluator selection, adapters, and promotion   |
| [0008](0008-durable-state-jobs-events-and-evidence.md)          | SQL state, worker leases, event invalidation, snapshots, artifacts, telemetry, and evidence |
| [0009](0009-identity-auth-tenancy-and-publication.md)           | OIDC/local auth, RBAC, organization scope, agent identity, MCP, and publication             |
| [0010](0010-provider-neutral-local-and-azure-deployment.md)     | Control-plane/worker split, managed services, provider abstractions, and deployment modes   |
| [0011](0011-web-client-and-realtime-state.md)                   | Next.js client, REST ownership, WebSocket invalidation, polling, and operational UI         |

## Status vocabulary

- **Accepted**: implemented and expected to remain the default architecture.
- **Accepted with limitations**: implemented, but known limits constrain its production use.
- **Proposed**: agreed direction not fully implemented.
- **Superseded**: retained for history and linked to its replacement.

## Decision inventory coverage

The records include the following choices: durable task/session/job separation; executable workflow contracts; one responsible agent per stage; immutable workflow snapshots; safe read-only DAG waves; explicit handoff artifacts; stage-specific sandboxes; semantic capabilities independent from tools; exact harness/catalog pins; default-deny policy intersection; per-agent runtime supervision; scoped approvals; isolated worktrees; provider-neutral Docker/Azure sessions; no host credential mounts; Copilot/Ollama/Foundry runtime boundaries; model recovery; Prompty assets; framework-native typed tools; bounded repository retrieval; evaluation execution separated from product tasks; deterministic dataset deduplication; human review and frozen hashes; evaluator provider/model separation; native/Vally/Waza evidence; prompt-defense and regression gates; SQLModel durable state; leased execution jobs; Redis/in-process invalidation; workspace snapshots; local/Blob evidence; event-derived telemetry; local/OIDC auth; organization-scoped records; RBAC; AgentMesh identity; MCP reuse of session governance; approval-gated publication; local/cloud deployment topology; API/worker separation; and WebSocket plus polling client consistency.
