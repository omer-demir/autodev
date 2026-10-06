<div align="center">

# Autodev

### Governed software agents that produce reviewable changes and verifiable evidence

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](apps/web/package.json)
[![Microsoft Agent Framework](https://img.shields.io/badge/Microsoft-Agent_Framework-0078D4)](https://github.com/microsoft/agent-framework)
[![Agent Governance Toolkit 5](https://img.shields.io/badge/Agent_Governance_Toolkit-5.0-5C2D91)](https://github.com/microsoft/agent-governance-toolkit)

[Quick start](#quick-start) · [How it works](#how-it-works) · [Features](docs/product/features-and-how-to.md) · [Architecture](docs/architecture.md) · [Development](DEVELOPMENT.md) · [Governance status](docs/agent-governance-toolkit.md)

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
Connect repository → create isolated worktree → verify signed agent identity
	→ start Hypervisor workflow session → render promoted instructions
	→ govern every typed tool call → execute in Docker or Azure session
	→ collect diff/tests/scans/evidence → human approval → publish
```

The default agent follows an evidence-backed Research-Plan-Implement-Review loop. Internet agents and skills enter as unreviewed instruction data; their remote tool declarations never grant local authority.

## Run a task

Open <http://localhost:3000> and:

1. Select **Connect repository**.
2. Paste a public GitHub repository URL, connect GitHub to browse private repositories, or select an existing local Git checkout.
3. Create a task against that repository and choose one of the models reported by GitHub Copilot. Ollama is the fallback proving provider.
4. Steer the running coding agent from the **Chat** tab.
5. Inspect the real Git diff, tests, scanner output, governance decisions, and physical sandbox location.
6. Open the isolated task worktree in VS Code or use its provider-backed terminal.
7. Approve or deny the scoped commit, push, and optional pull-request publication.
8. Use **Sessions** to continue a terminal run from its persisted worktree or connect an MCP client.

Open `/management` to create and version agents, reusable skills, MCP declarations, tool harnesses, capability catalogs, policies, workflows, and evaluation suites. It can import Agent Skills `SKILL.md`, GitHub Copilot `.agent.md`, GitHub blob/raw links, direct HTTPS Markdown, and skills.sh links as unreviewed local definitions. Remote tool declarations never grant Workbench capabilities. New agent versions can be promoted only after meeting the configured evaluation gate. Open `/security` to actively probe effective policy decisions and, when configured, the Microsoft Foundry content filter without persisting attack prompts.

The control plane supports local identity and OIDC, organization-scoped records, RBAC, actor-aware approvals, and tenant-scoped MCP access. Review the deployment and identity guidance in [multi-user access and roles](docs/multi-user-and-roles.md) before exposing it to a team.

The coding runtime uses Microsoft Agent Framework's official GitHub Copilot agent and Ollama connector, with Microsoft Foundry Responses available as a configured provider. Framework-native function tools resolve from the agent's exact harness/catalog versions, pass through Workbench governance, and execute in Docker or an Azure Container Apps custom dynamic session; final assistant prose is not parsed as JSON. Copilot built-in permission requests remain denied and checkout-defined file hooks remain disabled. Every task clones source into `.workspaces/TASK-NNN/repo`; the original checkout is not modified. Ollama remains an automatic fallback. No host credentials are mounted into task sandboxes.

The default provider is `copilot` with model `auto`. Sign in through the Copilot CLI state stored under `WORKBENCH_COPILOT_HOME`, or set `COPILOT_GITHUB_TOKEN` to a token with Copilot access. The API enumerates models through the SDK. If Copilot is unavailable, the configured Ollama fallback is used.

Copilot turns wait up to `WORKBENCH_MODEL_REQUEST_TIMEOUT_SECONDS` (300 seconds by
default). A failed Agent Framework attempt is closed before retry, then the live task pauses before fallback.
The operator can retry the same model, select another Copilot model, use the configured Ollama
fallback, or cancel. The decision window is controlled by
`WORKBENCH_MODEL_RECOVERY_TIMEOUT_SECONDS` (600 seconds by default), after which fallback is
selected automatically.

The management page implements the promotion evidence lifecycle: generate candidate scenarios from the agent, suite, denied operations, capabilities, and MCP tools; edit and human-review them; freeze an immutable hash; run real Workbench native tasks plus Vally and Waza; score tests, security, policy, latency, tokens/model calls, and narrowly scoped LLM rubrics; compare against a prior agent version; then promote only a non-regressing candidate.

Promotion also renders the exact runtime system-prompt shape and evaluates it with Microsoft Agent Governance Toolkit `PromptDefenseEvaluator`. The gate fails closed if evaluation errors or the grade is below `WORKBENCH_PROMPT_DEFENSE_MIN_GRADE` (`C` by default). Promotion evidence stores the grade, score, defended-vector coverage, missing vectors, and prompt SHA-256. This is defense in depth; prompt quality never grants tools or replaces deterministic policy enforcement.

Public GitHub URLs work without authentication. For easy private-repository onboarding, configure one GitHub OAuth App and users can select **Connect GitHub**; the resulting token is held only in control-plane memory and is lost on restart. A fine-grained token in `WORKBENCH_GITHUB_TOKEN` is also supported for unattended local use. Tokens are used for GitHub API and clone authentication and are not written into project records, task prompts, sandboxes, or evidence.

## Services

- Web UI: <http://localhost:3000>
- Control API: <http://localhost:8000>
- OpenAPI: <http://localhost:8000/docs>
- MCP Streamable HTTP: <http://localhost:8000/gateway/mcp>
- MCP SSE: <http://localhost:8000/gateway/sse>
- Grafana: <http://localhost:3001> (anonymous viewer; local admin password `admin`)
- Prometheus: <http://localhost:9090>
- Tempo: <http://localhost:3200>

The Compose stack sends OpenTelemetry traces and metrics through the Collector to Tempo and
Prometheus. Each task is an `agent.session` trace with Agent Framework telemetry, and persisted
events carry trace/span correlation IDs. The in-app run view links correlated runs to Grafana.
Exported attributes intentionally exclude prompts, source, commands, paths, credentials, raw tool
output, and reasoning. For native API development inside the supplied dev container, set
`WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318` (`localhost:4318` when
running directly on the Docker host); without an endpoint, export is a no-op while the persisted
activity view continues to work.

For a specific task, use **Observability** for the product-level session report, **Model log** for
provider transitions and optional sensitive prompt/response logs, and **Timeline** for durable
workflow events. Grafana remains the infrastructure and cross-session debugging surface rather
than being duplicated inside the Workbench. The API terminal emits bounded lifecycle metadata at
INFO level so a stalled model turn is visible without printing prompts, source, commands, paths, or
tool output. Grafana has Prometheus metrics and Tempo traces, not a Loki logs datasource; exact
verbose prompts and responses remain in the task **Model log** because they are sensitive evidence.
Anonymous Viewer access is enabled for the local Grafana instance, so login is not required.

## Governance stack

| Layer                | Implementation                                                            | Enforcement                                            |
| -------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------ |
| Agent runtime        | Microsoft Agent Framework                                                 | Framework-native tools and sessions                    |
| Policy               | Local default-deny intersection plus optional AGT stateless kernel        | Every tool invocation                                  |
| Identity             | AgentMesh DID and Ed25519-signed marketplace manifest                     | Task creation and execution                            |
| Workflow supervision | Agent Hypervisor session and saga registration                            | Lifecycle transitions                                  |
| Isolation            | Per-task Git worktree plus Docker or Azure Container Apps dynamic session | Filesystem, process, network, CPU, and memory boundary |
| Prompt release       | AGT PromptDefenseEvaluator plus frozen behavioral evaluation              | Agent promotion                                        |
| Reliability          | Agent SRE bridge, durable events, OpenTelemetry                           | Runtime evidence and operator visibility               |

Autodev is **not fully Agent Hypervisor conformant**. Dynamic trust-based ring enforcement, temporary elevation, saga compensation, per-ring rate limiting, breach-triggered demotion, graceful kill handoff, and persisted audit-root commitments remain roadmap work. See the [evidence-based AGT status matrix](docs/agent-governance-toolkit.md).

## Security boundary

- Repository text, model output, imported agents, and skills are untrusted input.
- Agent declarations and local policy intersect; deny wins and missing capability means deny.
- Shell text is not exposed as a generic tool. Commands use argument vectors and a semantic capability allow-list.
- Task containers receive no host credentials and are disconnected from the network by default.
- Commit, push, pull-request creation, and deployment require an explicit deterministic path and approval.
- Prompt defenses reduce injection risk but are not treated as a security boundary.

See [threat model](docs/threat-model.md) and [known governance gaps](docs/agent-governance-toolkit.md) before exposing the service beyond a trusted development environment.

## Documentation

Start with the [developer runbook](DEVELOPMENT.md), [product documentation pack](docs/product/README.md), [features and how-to](docs/product/features-and-how-to.md), [technical drawings](docs/diagrams/README.md), [product roadmap](docs/product/roadmap.md), [market research](docs/product/market-research.md), [local setup](docs/local-setup.md), [multi-user access and roles](docs/multi-user-and-roles.md), [management and evaluation](docs/management-and-evaluation.md), [editors and model providers](docs/editors-and-model-providers.md), [architecture](docs/architecture.md), and the original [design brief](.context/initial-design.md).
