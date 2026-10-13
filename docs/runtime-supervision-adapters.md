# Runtime supervision adapters

Autodev treats Agent Hypervisor as a replaceable runtime-supervision provider. Workflow and tool code depend only on `RuntimeSupervisorProvider`; vendor imports remain inside the selected adapter.

## Select a provider

```dotenv
WORKBENCH_RUNTIME_SUPERVISOR_PROVIDER=microsoft_agent_hypervisor
WORKBENCH_RUNTIME_SUPERVISOR_DEFAULT_TRUST=0.7
```

Built-in values:

- `microsoft_agent_hypervisor`: Microsoft Agent Hypervisor sessions, rings, TTL elevation, saga state and compensation, per-ring rate limiting, breach detection/demotion, kill handling, and audit commitments.
- `local`: portable lifecycle/evidence behavior. It reports unsupported advanced capabilities and rejects elevation instead of simulating it.

The default trust score is used only when an agent has no promoted behavioral score. Scores are bounded to `[0, 1]`; promoted evaluation evidence takes precedence.

## Provider contract

Implement `RuntimeSupervisorProvider` from
`apps/api/app/runtime_supervision/provider.py` (also exported by
`app.runtime_supervision`):

```python
class AcmeSupervisor(RuntimeSupervisorProvider):
    provider_id = "acme"
    provider_version = "1.2.0"
    capabilities = ProviderCapabilities(dynamic_rings=True)

    async def start(self, *, task_id, agent_id, trust_score, phases): ...
    async def before_action(self, handle, action): ...
    async def transition(self, handle, *, phase_id): ...
    async def elevate(self, handle, *, target_tier, ttl_seconds, reason, attestation=None): ...
    async def terminate(self, handle, *, reason): ...
```

The hooks return normalized handles, decisions, grants, transitions, and termination results. Set capability flags only for behavior the adapter enforces. Unsupported operations must fail clearly. A selected provider error fails the task closed where enforcement is claimed.

Every tool action reaches `before_action` after deterministic policy allows it and before file, process, or network side effects. Runtime supervision supplements policy and sandbox controls; it does not replace them.

## Register a provider

For development, select an import directly:

```dotenv
WORKBENCH_RUNTIME_SUPERVISOR_PROVIDER=acme_autodev:AcmeSupervisor
```

For a packaged adapter, publish an entry point:

```toml
[project.entry-points."autodev.runtime_supervisors"]
acme = "acme_autodev:AcmeSupervisor"
```

Then set `WORKBENCH_RUNTIME_SUPERVISOR_PROVIDER=acme`. No workflow, agent-runtime, or API changes are required.

## Source layout

The backend uses package facades: callers keep stable imports such as
`app.agent`, `app.models`, and `app.runtime_supervision`, while implementation
objects live in domain-named files.

```text
apps/api/app/
├── agent/                  # model orchestration and governed workspace tools
├── agent_identity/         # AgentMesh enrollment and verification
├── auth/                   # principals, permissions, OIDC, FastAPI dependencies
├── database/               # engine, sessions, migrations, local identity seed
├── evaluation/             # declaration scoring, run queries, promotion
├── evaluation_adapters/    # adapter contract, Vally, Waza, normalized results
├── foundry/                # Azure Foundry provider, protocol, parsing, errors
├── github_auth/            # GitHub identity and credential store
├── harness/                # harness resolution and tool schema projection
├── integrations/           # safe external agent and skill imports
├── model_catalog/          # Copilot/Ollama discovery, pricing, text generation
├── model_recovery/         # recovery decisions, requests, and broker
├── models/
│   ├── identity/       # users, organizations, memberships, agent identities
│   ├── projects/       # projects and sandboxes
│   ├── tasks/          # tasks, events, approvals, artifacts, messages
│   └── evaluations/    # evaluation runs and datasets
├── schemas/
│   ├── projects/       # project and publication requests
│   ├── tasks/          # task, message, mode, and elevation requests
│   ├── sessions/       # continuation, terminal, and recovery requests
│   ├── github/         # GitHub connection requests
│   ├── registry/       # definition and integration import requests
│   └── evaluations/    # evaluation and dataset requests
├── providers/
│   ├── governance/     # local and Agent OS policy enforcement
│   └── sandbox/        # Docker and Azure Container Apps execution
├── runtime_supervision/
│   ├── actions/        # action specification, decision, and tier derivation
│   ├── errors/         # configuration, denial, and elevation failures
│   └── providers/      # local and Microsoft runtime adapters
└── workflow_supervisor/
    ├── supervisor.py   # lifecycle coordinator
    ├── task_workflow.py
    └── phase_transition.py
```

Each package `__init__.py` is a compatibility facade, not an implementation
module. New behavior belongs in the file that owns the corresponding object;
implementation files contain at most one class.

## Elevation

Reviewers and administrators can request Ring 2 or Ring 1 elevation for an active task:

```bash
curl -X POST http://localhost:8000/api/tasks/TASK-001/runtime-elevation \
  -H 'Content-Type: application/json' \
  -d '{
    "target_tier": 1,
    "ttl_seconds": 300,
    "reason": "Approved release operation",
    "attestation": "reviewer:approved"
  }'
```

Microsoft Agent Hypervisor caps TTL at one hour, rejects Ring 0 through this API, checks trust thresholds, and requires attestation for Ring 1. Expired grants are removed before the next action check.

## Evidence

The `runtime-supervision` task artifact records:

- provider ID, version, and capability flags;
- session, saga, tier, and trust score;
- phase transition and elevation history;
- kill reason, handoff/compensation outcome, and terminal audit commitment.

If Microsoft Agent Hypervisor returns an empty delta-chain root, Autodev stores a SHA-256 commitment over normalized terminal evidence and identifies its source as `autodev_terminal_evidence`. It is not presented as an upstream Hypervisor delta-chain root.

Run adapter conformance checks with:

```bash
.venv/bin/pytest -q apps/api/tests/test_runtime_supervision.py
```
