---
title: Features and how-to
description: Product capabilities and guides for using AutoDev
ms.date: 2026-10-27
ms.topic: how-to
---

## Features and how-to

### Product at a glance

Autodev is a governed software-development workbench for running coding agents against real repositories. It separates model reasoning from execution authority: agents can propose tool calls, while deterministic policy, sandbox, workflow, identity, and approval layers decide what can happen.

The primary user journey is:

```text
Connect repository or empty workspace -> select promoted agent and model -> run isolated task
-> research/plan/implement/review -> inspect evidence -> approve or deny publication
```

### Capability map

| Area                  | Capability                                                                                                   | State                |
| --------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------- |
| Chat                  | Persistent conversations with selected agents, additive skills, optional repository context, and model choice | Implemented          |
| Repository onboarding | Public GitHub URL, GitHub OAuth browsing, local checkout, or initialized empty Git workspace                 | Implemented          |
| Task execution        | Change and read-only assessment modes with live steering                                                     | Implemented          |
| Agent runtime         | Microsoft Agent Framework with GitHub Copilot, Ollama fallback, or configured Foundry Responses              | Implemented/optional |
| Agent lifecycle       | Versioned YAML definitions, signed identity records, draft/promotion gate                                    | Implemented          |
| Skills                | Native skills plus safe import of `SKILL.md`, `.agent.md`, GitHub raw/blob, and skills.sh sources            | Implemented          |
| RPI workflow          | Research, Plan, Implement, Review guidance and evidence artifacts                                            | Implemented          |
| Governance            | Agent declaration intersected with local policy; default deny; optional Agent Governance Toolkit enforcement | Implemented          |
| Tooling               | Version-pinned harness and capability catalog; governed file and command tools                               | Implemented          |
| Sandboxes             | Disposable Docker execution or Azure Container Apps custom dynamic sessions                                  | Implemented/optional |
| Approvals             | Scoped commit, push, and pull-request publication decisions                                                  | Implemented          |
| Evaluation            | Static declaration lint and frozen behavioral evaluation through native, Vally, and Waza adapters            | Implemented          |
| Security              | Semgrep, Trivy, Gitleaks, capability probes, and optional Foundry content-filter canary                      | Implemented/optional |
| Observability         | Durable events, artifacts, OpenTelemetry, Prometheus, Tempo, Grafana, and in-app telemetry                   | Implemented/optional |
| Identity and tenancy  | Local or OIDC login, opaque sessions, membership UI, RBAC, actor-aware approvals, transport authorization    | Implemented/optional |
| Interfaces            | Next.js UI, REST/OpenAPI, CLI, WebSocket invalidation, MCP Streamable HTTP and SSE                           | Implemented          |

### Quick start

#### Native development

Prerequisites are Python 3.11+, Node.js, npm, Git, and a reachable Docker daemon.

```bash
make install
make dev
```

Open <http://localhost:3000>. The API and OpenAPI pages are at <http://localhost:8000> and <http://localhost:8000/docs>.

Check the runtime before starting work:

```bash
PYTHONPATH=apps/api:cli .venv/bin/python -m agentctl.main doctor
curl --fail http://localhost:8000/api/runtime
```

#### Compose

```bash
docker compose up --build --force-recreate
```

Compose adds Prometheus, Tempo, Grafana, and the OpenTelemetry Collector. The API container needs Docker daemon access to create disposable task sandboxes.

### Run a coding task

1. Open the dashboard and select **Connect repository**.
2. Use a public GitHub URL, connect GitHub for private repositories, select a local checkout, or create an empty workspace.
3. Create a task and choose:
   - **Change repository** to permit governed writes.
   - **Read-only assessment** for reviews and analysis.
4. Select a promoted agent and an available model.
5. Optionally enable **Verbose LLM trace** only when prompt and response retention is acceptable.
6. Start the task and watch the phase, timeline, chat, observability, diff, tests, and security output.
7. During intake, planning, or implementation, add steering in **Chat**. Steering is delivered at the next safe model boundary.
8. Review the isolated worktree and evidence. A change task cannot succeed without a real diff.
9. Approve or deny the scoped commit. Push and optional pull-request publication require a repository remote and their own governed boundary.

For a product-discovery flow with no repository, create an **Empty workspace** and start in **Read-only assessment** mode. The final agent report and research evidence are retained with the durable session. In **Sessions**, choose another promoted agent and provide the next objective to hand off while preserving the worktree and task history.

The original repository is not modified. Each task works in `.workspaces/TASK-NNN/repo`, mounted at `/workspace/project` in a Docker sandbox.

### Chat

1. Open **Chat** and enter a question to start a conversation. You can attach an image or file, or record audio and review its transcript before sending.
2. Without a repository, AutoDev saves the conversation as chat history and sends it directly to the selected model. This chatbot mode does not create a task or workspace.
3. Open **Advanced options** to choose a repository, agent, skill, or model. Agents and skills are optional in chatbot mode. If you select a repository, AutoDev creates a task and uses the existing governed workflow. A repository task uses the Base Agent when you do not select an agent.
4. Repository changes run in an isolated workspace through governed tools. Policy-required actions pause for approval.
5. Continue a saved conversation from **Recent chats**. Repository-backed chats link to task details, while repository-free chats remain in the chat interface.
6. Assistant replies render formatted Markdown and syntax-highlighted code. Images and files returned by the selected model are saved with the message and can be opened or downloaded from chat history.
7. Foundry chat sessions expose the provider's native image-generation tool. Images and files returned by either provider are saved with the assistant message.

The **Sessions** page remains available for inspecting and continuing task-backed work sessions.

The built-in **AutoDev Base Agent** is the default agent for repository tasks. In chatbot mode, choose an agent only when you want its instructions to guide the response.

### Understand the RPI loop

The built-in developer agent attaches five skills:

```yaml
skills:
  - rpi-orchestrator
  - rpi-research
  - rpi-plan
  - rpi-implement
  - rpi-review
```

The skills guide model behavior, while the Python workflow records observed evidence:

| Phase     | Durable evidence                                                              |
| --------- | ----------------------------------------------------------------------------- |
| Research  | Retrieval tool events and `rpi-research` artifact                             |
| Plan      | Requirements, steps, acceptance checks, and `rpi-plan` artifact               |
| Implement | Final agent summary, changed files, status, and `rpi-implementation` artifact |
| Review    | Test counts, scanner results, acceptance criteria, and `rpi-review` artifact  |

Instruction text cannot claim authority. Tool results, task events, diffs, test output, and scanner output remain the source of truth.

### Bring your own skill

1. Open **Agents & tools** at `/management`.
2. In **Import agent or skill**, paste one of:
   - A direct public HTTPS `SKILL.md` URL.
   - A GitHub blob or raw URL.
   - `https://skills.sh/<owner>/<repository>/<skill>`.
3. Leave **Detect type** selected or choose **Skill**.
4. Optionally choose a lowercase local ID, then select **Import**.
5. Open **Skills**, inspect the normalized YAML, license, compatibility, source URL, and declared tool metadata.
6. Open **Agents**, select the target agent, and add the local skill ID:

```yaml
skills:
  - my-reviewed-skill
```

7. Increment the agent version, save it, regenerate its behavioral dataset, evaluate it, and promote it before production use.

Imported `allowed-tools` remains advisory provenance. It does not grant Workbench tools, capabilities, network access, or approval.

### Bring your own agent

1. Import a public `.agent.md` URL from `/management`.
2. Review the generated local agent. Imports are forced to `draft` with:
   - A local DID.
   - The local development policy and workspace harness.
   - Read-only repository, Git status, and Git diff capabilities.
   - Explicit write, dependency-install, deployment, and credential denials.
3. Review remote instructions as untrusted guidance. Remote tools, scripts, model settings, handoffs, and permissions are provenance only.
4. Assign operator-controlled policy, harness, environment, capabilities, approvals, denials, MCP servers, and attached skills.
5. Increment the version whenever behavior changes.
6. Run static lint, then the complete behavioral promotion workflow described below.

### Evaluate and promote an agent

1. In `/management`, select the agent and evaluation suite.
2. Run **Static declaration lint** for immediate capability and safety consistency. This does not execute the agent.
3. Generate behavioral candidates.
4. Review and edit every scenario; enter the reviewer identity.
5. Mark the dataset reviewed, then freeze it. The content hash makes the executed dataset immutable.
6. Confirm Docker, Vally, and Waza readiness.
7. Run **Docker + Vally + Waza**.
8. Inspect adapter-level results, evaluation execution IDs, latency, model calls, token coverage, policy evidence, test output, and security output. Evaluation runs do not create product tasks or sessions.
9. Promote only when the current version satisfies the configured aggregate and safety thresholds and does not regress beyond the allowed delta.

Changing the agent after dataset generation invalidates the dataset and requires a new one.

### Govern capabilities

An action executes only when the agent declaration grants it and the selected policy allows it. Explicit deny wins.

```text
agent capability AND policy decision AND harness binding = executable action
```

Typical decisions are:

- `ALLOW`: dispatch to the selected sandbox provider.
- `DENY`: record evidence and reject the call.
- `REQUIRE_APPROVAL`: stop at a human decision boundary.

Use `/governance` to inspect effective policy and `/security` to run active capability probes. Treat policy edits as code changes because they become active for agents that reference them.

### Configure model providers

The application defaults to GitHub Copilot with `auto` model selection and
Ollama fallback. The development container overrides this with the configured
Microsoft Foundry `gpt-6-sol` deployment.

Common settings:

```text
WORKBENCH_MODEL_PROVIDER=copilot
WORKBENCH_MODEL_NAME=auto
WORKBENCH_MODEL_FALLBACK_PROVIDER=ollama
WORKBENCH_MODEL_FALLBACK_NAME=gemma4:e2b
WORKBENCH_OLLAMA_URL=http://127.0.0.1:11434
```

Set `WORKBENCH_MODEL_PROVIDER=foundry`,
`WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT`, and `WORKBENCH_FOUNDRY_MODEL` to use
Foundry Responses. In the development container, run `az login`; the API's
`DefaultAzureCredential` uses the Azure CLI identity. Provider failure opens a
recovery decision: retry, change model, use fallback, or cancel.

### Configure sandbox providers

#### Docker

Docker is the default. Sandboxes use a task-only bind mount, dropped Linux capabilities, `no-new-privileges`, resource limits, and no network by default. Governed dependency installation can receive temporary bridge access and is disconnected afterward.

#### Azure dynamic sessions

Deploy the supplied Bicep and custom image, grant the API workload identity the **Azure ContainerApps Session Executor** role, then configure:

```text
WORKBENCH_SANDBOX_PROVIDER=azure
WORKBENCH_AZURE_SESSION_POOL_ENDPOINT=<https-endpoint>
WORKBENCH_AZURE_SESSION_POOL_NETWORK_MODE=none
WORKBENCH_AZURE_SESSION_POOL_PROFILE=python-hyperv-2cpu-2gi-no-egress
```

The control plane imports the worktree before a command, exports changes afterward, and rejects concurrent host modification using fingerprints.

### Identity, organizations, and RBAC

Local mode provisions a local administrator and organization. OIDC browser login uses authorization code with PKCE, validates the ID token against the configured issuer, audience, and JWKS, and creates an opaque HttpOnly server-side session. API and external MCP clients may continue to use bearer tokens. Membership and role are resolved on each request so revocation takes effect without waiting for session expiry.

Built-in roles are:

| Role      | Main permissions                                                   |
| --------- | ------------------------------------------------------------------ |
| Viewer    | Read                                                               |
| Developer | Read, project creation, task creation/operation, sandbox operation |
| Reviewer  | Read, approval decisions, evaluation management                    |
| Admin     | All permissions, including registry and membership management      |

Set `X-Organization-ID` for bearer-token requests when one identity belongs to multiple organizations. Browser sessions bind to the organization selected during login. REST, WebSocket, MCP, task, evaluation, marketplace, and approval operations are scoped to the active organization. Admins manage memberships at `/admin`.

### Continue sessions and connect MCP clients

The Sessions page exposes persisted task history and continuation from retained worktrees. The same session service backs:

- REST and browser workflows.
- `agentctl sessions list/get/continue`.
- MCP Streamable HTTP at `/gateway/mcp`.
- MCP SSE at `/gateway/sse`.

Continuation is accepted only when the previous run is terminal, no approval is pending, and any replacement agent is promoted.

### Observe and troubleshoot

Use these surfaces in order:

1. **Timeline**: durable lifecycle and governance events.
2. **Observability**: phase duration, model/tool latency, provider transitions, costs, and safety decisions.
3. **Diff / tests / security**: executable task evidence.
4. **Model log**: exact prompts and responses only when verbose tracing was enabled.
5. **Grafana**: cross-session infrastructure metrics and Tempo traces.

Useful checks:

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/api/runtime
docker compose config --quiet
uv run pytest -q
uv run ruff check apps/api cli
npm run lint --workspace apps/web
npm run build --workspace apps/web
```

### Security invariants

- Repository content, imported instructions, and model output are untrusted.
- The model is not an authorization boundary.
- Imported assets never inherit remote execution permissions.
- Task sandboxes do not receive host credentials or the Docker socket.
- The API is privileged in Docker mode because it owns sandbox lifecycle through the host daemon.
- Git publication uses scoped approvals and ephemeral credentials.
- Verbose traces may contain sensitive source or prompts and should be enabled deliberately.

See [Threat model](../threat-model.md), [Management and evaluation](../management-and-evaluation.md), and [Azure deployment](../azure-deployment.md) for operational detail.
