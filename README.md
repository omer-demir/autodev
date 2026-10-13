<div align="center">

# Autodev

### Governed software agents that produce reviewable changes and verifiable evidence

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](apps/web/package.json)
[![Microsoft Agent Framework](https://img.shields.io/badge/Microsoft-Agent_Framework-0078D4)](https://github.com/microsoft/agent-framework)
[![Agent Governance Toolkit 5](https://img.shields.io/badge/Agent_Governance_Toolkit-5.0-5C2D91)](https://github.com/microsoft/agent-governance-toolkit)

[Quick start](#quick-start) · [How it works](#how-it-works) · [Features](docs/product/features-and-how-to.md) · [Glossary](docs/glossary.md) · [Architecture](docs/architecture.md) · [Design deep dives](docs/design/README.md) · [ADRs](docs/adr/README.md) · [Development](DEVELOPMENT.md) · [Governance status](docs/agent-governance-toolkit.md)

</div>

> [!IMPORTANT]
> Autodev is an engineering workbench, not a compliance certification. It integrates selected Microsoft Agent Governance Toolkit controls and documents the exact implemented, partial, and missing Hypervisor capabilities.

Autodev is a local-first, policy-controlled environment where coding agents can research, plan, modify, test, review, and prepare changes while meaningful capabilities are governed, observable, and auditable.

## The problem

Coding agents can generate changes quickly, but production teams still need deterministic answers to five questions:

1. Which agent and instruction set produced this change?
2. What tools and repository scope could it access?
3. Which tests, scans, and policy decisions actually ran?
4. Who approved irreversible publication actions?
5. Can a new agent version be proven safer than the one it replaces?

Autodev keeps those controls outside the model. Prompts guide behavior; local policy, typed tools, sandbox boundaries, evaluation gates, and human approval determine authority.

## Quick start

### Native development

```text
make install
make dev
```

Prerequisite: create `.venv` first with Python 3.11 or newer. See [DEVELOPMENT.md](DEVELOPMENT.md) for model setup, debugging, AgentMesh identity inspection, and focused test commands.

### Docker Compose

```text
docker compose up --build --force-recreate
```

Then open <http://localhost:3000>. Verify the API at <http://localhost:8000/health>; the health endpoint is `/health`, not `/api/health`.

## How it works

```text
Connect repository or empty workspace → create isolated worktree → verify signed agent identity
	→ start provider-neutral supervised session → render promoted instructions
	→ govern every typed tool call → execute in Docker or Azure session
	→ collect diff/tests/scans/evidence → human approval → publish
```

The default agent follows an evidence-backed Research-Plan-Implement-Review loop. Internet agents and skills enter as unreviewed instruction data; their remote tool declarations never grant local authority.

## Run a task

Open <http://localhost:3000> and:

1. Select **Connect repository**.
2. Paste a public GitHub repository URL, connect GitHub to browse private repositories, select a local Git checkout, or create an empty workspace for discovery.
3. Create a change task against source code, or start an assessment in an empty workspace to capture initial research and product context.
4. Steer the running coding agent from the **Chat** tab.
5. Inspect the real Git diff, tests, scanner output, governance decisions, and physical sandbox location.
6. Open the isolated task worktree in VS Code or use its provider-backed terminal.
7. Approve or deny the scoped commit, push, and optional pull-request publication.
8. Use **Sessions** to continue a terminal run from its persisted worktree, hand it to another promoted agent, or connect an MCP client.

Open `/management` to create and version agents, reusable skills, MCP declarations, tool harnesses, capability catalogs, policies, workflows, and evaluation suites. It can import Agent Skills `SKILL.md`, GitHub Copilot `.agent.md`, GitHub blob/raw links, direct HTTPS Markdown, and skills.sh links as unreviewed local definitions. Remote tool declarations never grant Workbench capabilities. New agent versions can be promoted only after meeting the configured evaluation gate. Open `/security` to actively probe effective policy decisions and, when configured, the Microsoft Foundry content filter without persisting attack prompts.

The control plane supports local identity and an OIDC authorization-code flow with PKCE, opaque HttpOnly session cookies, organization-scoped records, membership administration, RBAC, actor-aware approvals, and tenant-scoped WebSocket/MCP access. Review the deployment and identity guidance in [multi-user access and roles](docs/multi-user-and-roles.md) before exposing it to a team.

The coding runtime uses Microsoft Agent Framework's official GitHub Copilot agent and Ollama connector, with Microsoft Foundry Responses available as a configured provider. Framework-native function tools resolve from the agent's exact harness/catalog versions, pass through Workbench governance, and execute in Docker or an Azure Container Apps custom dynamic session; final assistant prose is not parsed as JSON. Copilot built-in permission requests remain denied and checkout-defined file hooks remain disabled. Every task clones source into `.workspaces/TASK-NNN/repo`; the original checkout is not modified. Ollama remains an automatic fallback. No host credentials are mounted into task sandboxes.

The default provider is `copilot` with model `auto`. Sign in through the Copilot CLI state stored under `WORKBENCH_COPILOT_HOME`, or set `COPILOT_GITHUB_TOKEN` to a token with Copilot access. The API enumerates models through the SDK. If Copilot is unavailable, the configured Ollama fallback is used.

Copilot turns wait up to `WORKBENCH_MODEL_REQUEST_TIMEOUT_SECONDS` (300 seconds by
default). A failed Agent Framework attempt is closed before retry, then the live task pauses before fallback.
The operator can retry the same model, select another Copilot model, use the configured Ollama
fallback, or cancel. The decision window is controlled by
`WORKBENCH_MODEL_RECOVERY_TIMEOUT_SECONDS` (600 seconds by default), after which fallback is
selected automatically.

The management page implements the promotion evidence lifecycle: generate or reuse deterministic candidate scenarios from the agent, suite, denied operations, capabilities, and MCP tools; edit and human-review them; freeze an immutable hash; run isolated native evaluation plus Vally and Waza; score tests, security, policy, latency, tokens/model calls, and narrowly scoped LLM rubrics; compare against a prior agent version; then promote only a non-regressing candidate whose result is linked to the matching frozen dataset. Evaluation executions never create product tasks or sessions. The evaluator provider/model is independent from the agent and defaults to Ollama `gemma4:e2b`.

Promotion also renders the exact runtime system-prompt shape and evaluates it with Microsoft Agent Governance Toolkit `PromptDefenseEvaluator`. The gate fails closed if evaluation errors or the grade is below `WORKBENCH_PROMPT_DEFENSE_MIN_GRADE` (`C` by default). Promotion evidence stores the grade, score, defended-vector coverage, missing vectors, and prompt SHA-256. This is defense in depth; prompt quality never grants tools or replaces deterministic policy enforcement.

Public GitHub URLs work without authentication. For private repositories and governed publication, open **Connections** and create a GitHub connection. AutoDev uses GitHub's App Manifest flow to submit the reviewed permissions, receives the generated credentials through its callback, encrypts them in the database, and guides installation—no manual GitHub App `.env` configuration is required. The **Repositories** page then discovers repositories by connection and account and supports SSH or installation-token HTTPS transport. AutoDev mints repository-scoped installation tokens just in time; they expire after one hour and are never written into project records, task prompts, sandboxes, or evidence. Git commits and pull requests are attributed to the app bot, while AutoDev records requesting and approving users in its audit trail. OAuth, deployment-managed App settings, a fine-grained `WORKBENCH_GITHUB_TOKEN`, and local SSH publication remain compatibility fallbacks.

## Services

- Web UI: <http://localhost:3000>
- Control API: <http://localhost:8000>
- OpenAPI: <http://localhost:8000/docs>
- MCP Streamable HTTP: <http://localhost:8000/gateway/mcp>
- MCP SSE: <http://localhost:8000/gateway/sse>
- Grafana: <http://localhost:3001> (anonymous viewer; local admin password `admin`)
- Prometheus: <http://localhost:9090>
- Tempo: <http://localhost:3200>
- Loki: <http://localhost:3100>

The Compose stack sends OpenTelemetry traces and metrics through the Collector to Tempo and
Prometheus. PostgreSQL and Redis exporters add datastore metrics, Tempo derives span metrics and
service graphs with exemplars, and Alloy sends scoped API, worker, web, PostgreSQL, and Redis
container logs to Loki. Grafana provisions service-overview, API/worker, datastore, web, agent,
and logs dashboards with metric-to-trace and trace-to-log links. Each task is an `agent.session`
trace with Agent Framework telemetry, and persisted events carry trace/span correlation IDs. The
in-app run view links correlated runs to Grafana.
Exported attributes intentionally exclude prompts, source, commands, paths, credentials, raw tool
output, and reasoning. `make dev` starts the local telemetry backend and selects
`http://otel-collector:4318` inside the supplied dev container or `http://127.0.0.1:4318` when
running directly on the Docker host. Standalone native processes must use the corresponding
endpoint explicitly; without an endpoint, export is a no-op while the persisted activity view
continues to work.

For a specific task, use **Observability** for the product-level session report, **Model log** for
provider transitions and optional sensitive prompt/response logs, and **Timeline** for durable
workflow events. Grafana remains the infrastructure and cross-session debugging surface rather
than being duplicated inside the Workbench. The API terminal emits bounded lifecycle metadata at
INFO level so a stalled model turn is visible without printing prompts, source, commands, paths, or
tool output. Loki contains operational container output and bounded trace-correlated application
logs; exact verbose prompts and responses remain only in the task **Model log** because they are
sensitive evidence.
Anonymous Viewer access is enabled for the local Grafana instance, so login is not required.

## Governance stack

| Layer                | Implementation                                                            | Enforcement                                            |
| -------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------ |
| Agent runtime        | Microsoft Agent Framework                                                 | Framework-native tools and sessions                    |
| Policy               | Local default-deny intersection plus optional AGT stateless kernel        | Every tool invocation                                  |
| Identity             | AgentMesh DID and Ed25519-signed marketplace manifest                     | Task creation and execution                            |
| Workflow supervision | Provider contract; Microsoft Agent Hypervisor or portable local adapter   | Lifecycle and every allowed tool action                |
| Isolation            | Per-task Git worktree plus Docker or Azure Container Apps dynamic session | Filesystem, process, network, CPU, and memory boundary |
| Prompt release       | AGT PromptDefenseEvaluator plus frozen behavioral evaluation              | Agent promotion                                        |
| Reliability          | Agent SRE bridge, durable events, OpenTelemetry                           | Runtime evidence and operator visibility               |

The default Microsoft adapter enforces evaluation-backed rings, authorized TTL elevation, saga state/compensation, per-ring rate limits, breach-triggered demotion, kill handling, command checks, and terminal audit commitments. A portable local adapter and Python entry-point contract avoid vendor lock-in; see [runtime supervision adapters](docs/runtime-supervision-adapters.md).

Autodev is still **not certified or fully Agent Hypervisor conformant**. It has not passed an upstream complete conformance suite, and distributed sessions, VFS/resource locks, live substitute-agent handoff, and SRE-witness Ring 0 remain outside the implemented boundary. See the [evidence-based AGT status matrix](docs/agent-governance-toolkit.md).

## Security boundary

- Repository text, model output, imported agents, and skills are untrusted input.
- Agent declarations and local policy intersect; deny wins and missing capability means deny.
- Shell text is not exposed as a generic tool. Commands use argument vectors and a semantic capability allow-list.
- Task containers receive no host credentials and are disconnected from the network by default.
- Commit, push, pull-request creation, and deployment require an explicit deterministic path and approval.
- Prompt defenses reduce injection risk but are not treated as a security boundary.

See [threat model](docs/threat-model.md) and [known governance gaps](docs/agent-governance-toolkit.md) before exposing the service beyond a trusted development environment.

## Documentation

Start with the [developer runbook](DEVELOPMENT.md), [product documentation pack](docs/product/README.md), [glossary](docs/glossary.md), [features and how-to](docs/product/features-and-how-to.md), [technical drawings](docs/diagrams/README.md), [architecture design deep dives](docs/design/README.md), [architecture decision records](docs/adr/README.md), [product roadmap](docs/product/roadmap.md), [market research](docs/product/market-research.md), [local setup](docs/local-setup.md), [multi-user access and roles](docs/multi-user-and-roles.md), [management and evaluation](docs/management-and-evaluation.md), [editors and model providers](docs/editors-and-model-providers.md), [architecture](docs/architecture.md), and the original [design brief](.context/initial-design.md).
