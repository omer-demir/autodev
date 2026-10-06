# Autodev developer guide

This runbook covers local startup, the embedded AgentMesh integration, debugging, and validation. Product usage belongs in [Features and how-to](docs/product/features-and-how-to.md); cloud sandbox deployment belongs in [Azure session deployment](docs/azure-deployment.md).

## Prerequisites

- Python 3.11 or newer.
- Node.js 22.12 or newer and npm.
- Docker CLI and a reachable Docker daemon.
- Git.
- One model path:
  - GitHub Copilot access through `COPILOT_GITHUB_TOKEN` or Copilot CLI login.
  - Ollama at `http://127.0.0.1:11434` with the configured fallback model.
  - Optional Microsoft Foundry Responses endpoint.

The API controls disposable task containers through the Docker socket. Use this only on a trusted development machine.

## Bootstrap

```bash
python3 -m venv .venv
make install
cp .env.example .env
```

The default `.env.example` uses Ollama for native development. Change `WORKBENCH_MODEL_PROVIDER` to `copilot` and configure Copilot credentials when required.

## Start locally

Run both hot-reload servers:

```bash
make dev
```

Or run them independently for focused debugging:

```bash
npm run dev:api
npm run dev:web
```

Open:

- Web: <http://localhost:3000>
- API health: <http://localhost:8000/health>
- OpenAPI: <http://localhost:8000/docs>
- Runtime readiness: <http://localhost:8000/api/runtime>

The runtime endpoint requires the configured application identity. Local mode provisions the local administrator automatically.

## Start with Compose

```bash
docker compose up --build --force-recreate
docker compose ps
docker compose logs -f api web
```

Compose starts Web, API, OpenTelemetry Collector, Tempo, Prometheus, and Grafana. It does not start Ollama; the API reaches host Ollama through `host.docker.internal:11434`.

Stop without deleting durable data:

```bash
docker compose down
```

Delete local Compose data only when intentionally resetting the workbench:

```bash
docker compose down --volumes
```

## Start AgentMesh

Autodev uses **embedded AgentMesh libraries**, not a separate mesh service:

1. FastAPI startup creates the database and local principal.
2. Every promoted agent is enrolled as an AgentMesh DID.
3. Its Ed25519 private key is stored under `WORKBENCH_AGENT_IDENTITY_DIR`.
4. A signed marketplace manifest binds the DID to the declared capabilities.
5. Task creation verifies identity status, capabilities, and manifest signature.
6. The workflow supervisor creates a one-participant Agent Hypervisor session.

Therefore `make dev` or `docker compose up` starts the Autodev mesh integration. Compose stores identity keys in `/data/agentmesh` on the `workbench-data` volume so they survive container recreation.

Inspect the embedded mesh:

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/api/marketplace/agents
```

In OIDC mode, pass the bearer token and organization headers required by the deployment. A successful task timeline contains `agent.identity_verified`, plus Hypervisor session and saga identifiers on workflow transitions.

Microsoft's standalone AgentMesh relay, registry, proxy, trust handshake, reward engine, and credential-rotation services are **not wired into Autodev**. Do not start `agentmesh run` and assume Autodev traffic uses it. That is a separate future integration described in [AGT governance status](docs/agent-governance-toolkit.md).

## Model setup

### GitHub Copilot

For native development, authenticate the Copilot CLI or export `COPILOT_GITHUB_TOKEN`. Compose persists Copilot state under the `workbench-data` volume.

For a strict Copilot check with no fallback:

```bash
WORKBENCH_MODEL_PROVIDER=copilot \
WORKBENCH_MODEL_FALLBACK_PROVIDER=none \
npm run dev:api
```

### Ollama

```bash
ollama pull gemma4:e2b
ollama serve
```

Set `WORKBENCH_MODEL_PROVIDER=ollama` and `WORKBENCH_MODEL_NAME=gemma4:e2b` for a local-only model path.

## Debugging

### Startup and readiness

```bash
make doctor
PYTHONPATH=apps/api:cli .venv/bin/python -m agentctl.main runtime
curl --fail http://localhost:8000/health
```

If task startup fails, verify `sandbox.ready`, Docker CLI, daemon access, model availability, and provider errors in `/api/runtime` before inspecting agent logic.

### API

Run Uvicorn directly with debug logging:

```bash
PYTHONPATH=apps/api .venv/bin/uvicorn app.main:app \
  --reload --reload-dir apps/api --port 8000 --log-level debug
```

For Compose:

```bash
docker compose logs -f api
docker compose exec api python -c "from hypervisor import Hypervisor; print(Hypervisor)"
```

Prompts, source, raw commands, credentials, and tool output are deliberately excluded from ordinary telemetry. Enable the task's explicit verbose model log only when sensitive content is acceptable in local evidence.

### Web

```bash
npm run dev:web
npm --workspace apps/web run lint
npm --workspace apps/web run build
```

Use the browser network panel for REST/WebSocket errors. The web app rewrites API requests during local development; direct API tests should target port 8000.

### Sandboxes and worktrees

Each task uses `.workspaces/TASK-NNN/repo` on the host and `/workspace/project` inside its disposable container. They are the same bind-mounted files.

```bash
docker ps --filter name=agentic-task
git -C .workspaces/TASK-001/repo status --short
```

Do not edit the connected source checkout when debugging a task. Reproduce changes in the task worktree.

### Observability

- Product session report: task **Observability** tab.
- Durable workflow events: task **Timeline** tab.
- Sensitive provider transcript: task **Model log** when enabled.
- Metrics: <http://localhost:9090>.
- Traces and dashboards: <http://localhost:3001>.
- Tempo API: <http://localhost:3200>.

## Test and validate

Run the backend suite and lint:

```bash
make test
.venv/bin/ruff check apps/api cli
```

Run frontend checks:

```bash
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

Run focused governance checks:

```bash
.venv/bin/pytest -q \
  apps/api/tests/test_governance.py \
  apps/api/tests/test_workflow_supervisor.py \
  apps/api/tests/test_agent_identity.py \
  apps/api/tests/test_behavioral_evaluation.py
```

Validate Compose interpolation:

```bash
docker compose config --quiet
```

The promotion tests exercise PromptDefense fail-closed behavior. The current rendered developer prompt is expected to meet the configured minimum grade; changing the Prompty, agent instructions, attached skills, or policy budgets can change its hash and grade.

## Common failures

| Symptom                                         | Check                                                                                               |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `/api/health` returns 404                       | Use `/health`                                                                                       |
| Docker socket exists but tasks fail             | Confirm the API process also has Docker CLI and `/api/runtime` reports `sandbox.ready=true`         |
| Model turn stalls                               | Inspect API lifecycle logs and configured model/turn timeout values                                 |
| Copilot fails after container recreation        | Reauthenticate or verify the persistent Copilot home volume                                         |
| Agent identity cannot refresh                   | Verify `WORKBENCH_AGENT_IDENTITY_DIR` is writable and persisted with the database                   |
| Promotion returns 409                           | Check latest behavioral adapters, safety/regression result, agent version, and prompt-defense grade |
| AgentMesh CLI is running but Autodev ignores it | Expected: standalone AgentMesh services are not integrated                                          |

## Change checklist

1. Add focused tests for the owning behavior.
2. Run backend Ruff and the affected pytest slice.
3. Run web lint/build for frontend changes.
4. Run `docker compose config --quiet` for topology changes.
5. Update architecture, threat, or governance docs when a trust boundary changes.
6. Never mark a missing Hypervisor capability as compliant without a conformance test and retained evidence.
