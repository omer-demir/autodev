# Agentic SDLC Workbench

A local-first, policy-controlled development environment where coding agents can plan, modify, test, review, and prepare changes while every meaningful capability is governed, observable, and auditable.

## Play locally

```text
make install
make dev
```

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

See [local setup](docs/local-setup.md), [multi-user access and roles](docs/multi-user-and-roles.md), [management and evaluation](docs/management-and-evaluation.md), [editors and model providers](docs/editors-and-model-providers.md), [architecture](docs/architecture.md), and the original [design brief](.context/initial-design.md).
