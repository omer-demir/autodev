# Architecture

Implementation-oriented sketches are available in the [architecture design deep dives](design/README.md):

- [Agent mesh and identity](design/agent-mesh-and-identity.md)
- [Tool checks and governance](design/tool-checks-and-governance.md)
- [MCP and A2A boundaries](design/mcp-and-a2a.md)
- [Harness contracts](design/harness-contracts.md)
- [Workflow orchestration](design/workflow-orchestration.md)
- [End-to-end task execution](design/task-execution.md)

Editable technical views are available in the [Draw.io catalog](diagrams/README.md):

- [General architecture](diagrams/general-architecture.drawio)
- [System design](diagrams/system-design.drawio)
- [Cloud architecture](diagrams/cloud-architecture.drawio)
- [Local architecture](diagrams/local-architecture.drawio)
- [Adapter architecture](diagrams/adapters.drawio)

For product workflows and operational steps, see [Features and how-to](product/features-and-how-to.md).

Terminology is defined in the [Glossary](glossary.md). Non-obvious landscape choices and their tradeoffs are recorded in the [Architecture decision records](adr/README.md).

The task is the primary durable object. A session is the resumable view of that task, while an execution job represents one run or retry. The Next.js UI talks to the FastAPI control plane over REST and receives lifecycle invalidations over WebSocket. The workflow controller owns phase transitions; the model does not.

Behavioral evaluation is a separate durable context. An evaluation run owns scenario execution IDs, adapter results, metrics, comparisons, and evidence. Native evaluation invokes the governed agent runtime in isolated fixture workspaces without creating projects, tasks, sessions, execution jobs, task artifacts, or product approvals. Evaluator provider/model selection is explicit and defaults independently to Ollama `gemma4:e2b`.

Three boundaries remain separate:

1. **Sandbox** — where execution can happen.
2. **Governance** — which semantic capability an agent may use.
3. **Workflow** — when that capability is appropriate.

Public-preview governance integration remains behind `GovernanceProvider`. Sandbox execution remains behind `SandboxProvider`, with Docker and Azure Container Apps custom dynamic session implementations. The workflow materializes a Git worktree, drives Microsoft Agent Framework's GitHub Copilot agent, official Ollama connector, or Microsoft Foundry Responses through governed semantic tools, runs detected checks, records actual output, pauses for scoped publication approvals, and preserves the worktree and evidence.

## Agent execution loop

AutoDev uses a **governed agent loop** as the umbrella architecture. Inside each Microsoft Agent Framework invocation, the provider-native function-tool loop is **ReAct-like**: the model selects a typed tool, the governed runtime performs the action, the tool result returns to the same session as an observation, and subsequent tool choices can depend on that observation. AutoDev does not expose or persist private chain-of-thought; persisted evidence contains model-call metadata, explicit assistant output, tool requests/results, policy decisions, and optional operator-enabled prompt/response traces.

Reasoning-capable models can still perform their provider-managed private reasoning. When a provider reports reasoning-token usage, AutoDev records the count as telemetry, not the hidden reasoning content. Private chain-of-thought cannot be requested or persisted through the Copilot or Ollama Agent Framework connectors. For reviewable rationale, prompts should request a concise decision explanation, assumptions, and evidence in the final response; that generated explanation is auditable output rather than private reasoning.

The Workbench wraps that provider loop with a bounded outer control loop. It applies maximum-step and timeout limits, developer steering, taskless-response rejection, retry/model recovery, policy budgets, and provider fallback. Tool execution remains fail-closed through capability resolution, governance evaluation, runtime supervision, and sandbox isolation.

This is not primarily a CodeAct architecture. Agents normally act through multiple typed function tools. The governed command tool permits CodeAct-like shell or code execution when the agent and policy both authorize it, but command execution is one action in the broader function-tool loop rather than the universal action language.

`Task.workflow_id` selects an active YAML workflow contract. Executable workflows assign one responsible agent per stage, name artifact inputs and outputs, and define either sequential order or a dependency DAG. Dependency waves can run concurrently only for read-only agents. Each non-primary role receives an ephemeral sandbox matching its own environment declaration, while stage callbacks serialize durable event and message writes. The task stores stage-attributed events, named artifacts, and a `workflow-run` record so handoffs and failures survive process boundaries. The legacy `sdlc` definition continues through the original single-agent path.

An agent pins exact harness and capability-catalog versions. The harness is the single source for model tool schemas and runtime capability bindings; startup and invocation fail closed when a pinned version is unavailable. Active security evaluations exercise the resolved catalog against the selected governance provider and can add a sanitized Foundry content-filter canary.

Terminal tasks remain durable sessions. `SessionService` owns tenant-scoped history and continuation from persisted worktrees. The same service backs the browser and the authenticated MCP gateway, exposed over Streamable HTTP and SSE with `sessions.list`, `sessions.get`, and `sessions.continue`. Publication is a separate governed boundary: a clean worktree is required before push, credentials use an ephemeral askpass path, and pull-request creation is optional after approval.

## Task updates

The dashboard subscribes to the global event WebSocket. A selected task subscribes to a task-scoped WebSocket, so unrelated task traffic does not trigger a refetch. WebSocket messages are invalidations: durable task state remains in SQLite and the client refetches the complete selected task after each message. The selected-task page also refreshes every three seconds while visible and immediately on window focus or visibility restoration. This closes reconnect gaps without treating the in-memory WebSocket hub as durable storage.

For a multi-instance control plane, replace the in-process event hub with a shared broker such as PostgreSQL `LISTEN/NOTIFY`, Redis Streams, or NATS. Keep database events as the source of truth and authorize every subscription against organization and task membership.
