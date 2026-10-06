# Architecture

Editable technical views are available in the [Draw.io catalog](diagrams/README.md):

- [General architecture](diagrams/general-architecture.drawio)
- [System design](diagrams/system-design.drawio)
- [Cloud architecture](diagrams/cloud-architecture.drawio)
- [Local architecture](diagrams/local-architecture.drawio)
- [Adapter architecture](diagrams/adapters.drawio)

For product workflows and operational steps, see [Features and how-to](product/features-and-how-to.md).

The task is the primary durable object. The Next.js UI talks to the FastAPI control plane over REST and receives lifecycle invalidations over WebSocket. The SDLC controller owns phase transitions; the model does not.

Three boundaries remain separate:

1. **Sandbox** — where execution can happen.
2. **Governance** — which semantic capability an agent may use.
3. **Workflow** — when that capability is appropriate.

Public-preview governance integration remains behind `GovernanceProvider`. Sandbox execution remains behind `SandboxProvider`, with Docker and Azure Container Apps custom dynamic session implementations. The workflow materializes a Git worktree, drives Microsoft Agent Framework's GitHub Copilot agent, official Ollama connector, or Microsoft Foundry Responses through governed semantic tools, runs detected checks, records actual output, pauses for scoped publication approvals, and preserves the worktree and evidence.

An agent pins exact harness and capability-catalog versions. The harness is the single source for model tool schemas and runtime capability bindings; startup and invocation fail closed when a pinned version is unavailable. Active security evaluations exercise the resolved catalog against the selected governance provider and can add a sanitized Foundry content-filter canary.

Terminal tasks remain durable sessions. `SessionService` owns tenant-scoped history and continuation from persisted worktrees. The same service backs the browser and the authenticated MCP gateway, exposed over Streamable HTTP and SSE with `sessions.list`, `sessions.get`, and `sessions.continue`. Publication is a separate governed boundary: a clean worktree is required before push, credentials use an ephemeral askpass path, and pull-request creation is optional after approval.

## Task updates

The dashboard subscribes to the global event WebSocket. A selected task subscribes to a task-scoped WebSocket, so unrelated task traffic does not trigger a refetch. WebSocket messages are invalidations: durable task state remains in SQLite and the client refetches the complete selected task after each message. The selected-task page also refreshes every three seconds while visible and immediately on window focus or visibility restoration. This closes reconnect gaps without treating the in-memory WebSocket hub as durable storage.

For a multi-instance control plane, replace the in-process event hub with a shared broker such as PostgreSQL `LISTEN/NOTIFY`, Redis Streams, or NATS. Keep database events as the source of truth and authorize every subscription against organization and task membership.
