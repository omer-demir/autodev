# Microsoft Agent Governance Toolkit integration status

Status date: October 6, 2026. Evaluated dependency: `agent-governance-toolkit-core==5.0.0` with `agent-governance-toolkit-compliance==5.0.0`.

## Executive answer

Autodev is **not fully compliant with the Agent Hypervisor feature set or the wider Agent Governance Toolkit specifications**. It integrates a useful subset and has equivalent controls in several areas, but it has not run or passed Microsoft's complete conformance suite and must not present the toolkit's standards-compliance claims as Autodev certification.

The current integration provides:

- Agent OS stateless policy enforcement layered over Autodev's default-deny policy.
- AgentMesh DID creation and Ed25519-signed marketplace manifests.
- Agent Hypervisor sessions and saga step registration for workflow phases.
- Agent SRE audit-entry bridge and SLO status.
- PromptDefense evaluation as a fail-closed agent-promotion gate.
- Docker or Azure session isolation, typed tool mediation, durable evidence, and OpenTelemetry.

## Prompt promotion

Agent promotion evaluates the same rendered system-prompt shape used for a change task. Microsoft `PromptDefenseEvaluator` checks 17 conversational and agentic defense vectors deterministically.

Promotion fails closed when:

- the evaluator cannot run;
- `WORKBENCH_PROMPT_DEFENSE_MIN_GRADE` is invalid;
- the report grade is below the configured minimum.

The promoted definition records the minimum grade, achieved grade, score, coverage, defended/total counts, missing vectors, and prompt SHA-256. The default minimum is `C`. The baseline developer prompt currently grades `B` under AGT 5.0.0; tests should be treated as the source of truth because evaluator rules can change with dependency upgrades.

Prompt defense is not the authorization layer. All tool calls still pass through typed harness resolution, capability classification, local policy, AGT kernel enforcement, sandbox execution, and approval state.

## Agent Hypervisor matrix

| Hypervisor capability         | Status                         | Autodev evidence and limitation                                                                                                                                                                          |
| ----------------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Session lifecycle             | Integrated                     | `WorkflowSupervisor` creates, joins, activates, and terminates one session per task workflow. State is process-local and not a distributed Hypervisor deployment.                                        |
| Session isolation             | Partial                        | Hypervisor session plus one-participant limit is used; practical isolation comes from per-task Git worktrees and Docker/Azure sandboxes. Hypervisor VFS snapshots and resource locks are not integrated. |
| Execution rings               | Partial                        | The agent joins with static `sigma_raw=0.5`; the resulting ring is not used to map or enforce Autodev capabilities. No dynamic trust provider is connected.                                              |
| Temporary ring elevation      | Missing                        | No `RingElevationManager`, TTL elevation, SRE witness, or approval-to-ring mapping.                                                                                                                      |
| Saga orchestration            | Partial                        | Workflow phases are registered and executed as saga steps. Steps have no `undo_api`, compensation handler, retry policy, or transactional resource lock.                                                 |
| Kill switch and handoff       | Partial/equivalent             | Operators can cancel tasks and sandbox providers kill execution. Hypervisor `KillSwitch`, reason taxonomy, in-flight handoff, and compensation trigger are not wired.                                    |
| Per-ring rate limiting        | Missing                        | Autodev has total tool/shell budgets and timeouts, not `AgentRateLimiter` token buckets by ring.                                                                                                         |
| Breach detection and demotion | Missing                        | No `RingBreachDetector`, anomaly window, automatic demotion, or circuit-breaker action.                                                                                                                  |
| Hash-chained audit            | Partial                        | Hypervisor audit is enabled, but termination root commitments are not persisted or exposed in evidence bundles. Durable Autodev events are not a substitute for Hypervisor chain verification.           |
| Causal consistency            | Partial                        | OpenTelemetry provides trace/span correlation. Hypervisor vector clocks, VFS version counters, and saga isolation levels are not integrated.                                                             |
| Command denylist              | Equivalent, not conformant     | Commands use argument vectors and a semantic allow-list; shell access is not generic. Hypervisor `RingEnforcer.check_command()` and its denylist are not invoked.                                        |
| Resource controls             | Implemented outside Hypervisor | Docker applies CPU, memory, PID, capability, user, network, and `no-new-privileges` controls; Azure uses custom dynamic-session limits.                                                                  |
| Observability                 | Implemented/partial            | Durable events, Prometheus, Tempo, Grafana, and OpenTelemetry exist. Hypervisor ring-transition and breach metrics are absent because those controls are absent.                                         |

## AgentMesh matrix

| AgentMesh capability            | Status                                                                   |
| ------------------------------- | ------------------------------------------------------------------------ |
| DID and Ed25519 identity        | Implemented for promoted agents                                          |
| Human sponsor binding           | Implemented from the authenticated principal                             |
| Signed marketplace manifest     | Implemented and verified before task execution                           |
| Capability drift detection      | Implemented by comparing declaration and identity record                 |
| Identity revocation             | Implemented through marketplace API                                      |
| Standalone relay/registry       | Not integrated                                                           |
| Peer trust handshake / IATP     | Not integrated into task traffic                                         |
| Dynamic reward/trust scoring    | Not integrated                                                           |
| Ephemeral credential rotation   | Not integrated                                                           |
| A2A delegation and scope chains | Not integrated                                                           |
| MCP trust proxy                 | Autodev has its own authenticated MCP gateway; it is not AgentMesh Proxy |

## What full alignment would require

1. Define the exact upstream specification/version and run its conformance suite in CI.
2. Replace static trust with a durable, evidence-backed trust provider and enforce returned rings on every capability.
3. Add bounded TTL elevation tied to actor approval and attestation.
4. Register compensation for reversible saga steps and persist transaction outcomes.
5. Apply `AgentRateLimiter` and `RingBreachDetector`; demote or terminate on verified breaches.
6. Integrate Hypervisor kill handoff and reasoned incident evidence.
7. Persist and verify the audit root returned at termination.
8. Decide whether standalone AgentMesh relay/registry/proxy services are part of the product topology; if so, authenticate and test every bridge.
9. Map each claimed OWASP/NIST/SOC 2 control to executable tests and retained evidence.
10. Obtain an independent review before using the word certified or fully compliant.

## Verification commands

```bash
.venv/bin/pytest -q \
  apps/api/tests/test_governance.py \
  apps/api/tests/test_workflow_supervisor.py \
  apps/api/tests/test_agent_identity.py \
  apps/api/tests/test_behavioral_evaluation.py

.venv/bin/ruff check apps/api cli
docker compose config --quiet
```

## Upstream references

- [Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit)
- [Prompt defense governance example](https://github.com/microsoft/agent-governance-toolkit/blob/main/agent-governance-python/agent-compliance/examples/prompt_defense_governance.py)
- [Agent Hypervisor](https://github.com/microsoft/agent-governance-toolkit/tree/main/agent-governance-python/agent-hypervisor)
- [AgentMesh](https://github.com/microsoft/agent-governance-toolkit/tree/main/agent-governance-python/agent-mesh)

Upstream pages were reviewed on October 6, 2026. Public-preview APIs and claims may change.
