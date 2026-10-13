# Microsoft Agent Governance Toolkit integration status

Status date: October 6, 2026. Evaluated dependency: `agent-governance-toolkit-core==5.0.0` with `agent-governance-toolkit-compliance==5.0.0`.

## Executive answer

Autodev is **not fully compliant with the Agent Hypervisor feature set or the wider Agent Governance Toolkit specifications**. It integrates a useful subset and has equivalent controls in several areas, but it has not run or passed Microsoft's complete conformance suite and must not present the toolkit's standards-compliance claims as Autodev certification.

The current integration provides:

- Agent OS stateless policy enforcement layered over Autodev's default-deny policy.
- AgentMesh DID creation and Ed25519-signed marketplace manifests.
- Provider-neutral runtime supervision with a Microsoft Agent Hypervisor adapter and portable local adapter.
- Evaluation-backed execution rings, TTL elevation, per-ring limits, breach demotion, kill handling, saga evidence, and terminal commitments in the Microsoft adapter.
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

| Hypervisor capability         | Status                         | Autodev evidence and limitation                                                                                                                                                                           |
| ----------------------------- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Session lifecycle             | Integrated                     | The selected adapter starts, transitions, and terminates one session per task workflow. Microsoft state is process-local and not a distributed Hypervisor deployment.                                     |
| Session isolation             | Partial                        | Hypervisor session plus one-participant limit is used; practical isolation comes from per-task Git worktrees and Docker/Azure sandboxes. Hypervisor VFS snapshots and resource locks are not integrated.  |
| Execution rings               | Integrated/partial             | Promoted behavioral score, or a bounded configured fallback, determines the initial ring. Every policy-allowed tool action is mapped and checked before side effects. External trust consensus is absent. |
| Temporary ring elevation      | Integrated/partial             | Reviewer-authorized Ring 1/2 elevation has bounded TTL, trust checks, expiry, and Ring 1 attestation. Ring 0 and SRE-witness integration remain unavailable.                                              |
| Saga orchestration            | Integrated/partial             | Workflow phases use steps with undo descriptors, timeout, retry, and failure/cancellation compensation. Tool side effects and transactional resource locks are not part of the workflow saga.             |
| Kill switch and handoff       | Integrated/partial             | Terminal workflows invoke `KillSwitch` with reason and in-flight steps, producing compensation/handoff evidence. No live substitute agent is registered for actual reassignment.                          |
| Per-ring rate limiting        | Integrated                     | Every supervised tool action consumes the Microsoft `AgentRateLimiter` bucket for its effective ring; rejection fails closed and is retained as an event.                                                 |
| Breach detection and demotion | Integrated                     | `RingBreachDetector` observes every action/ring pair. High or critical findings revoke elevation, demote to Ring 3, reset rate limits, and hold the circuit breaker closed.                               |
| Hash-chained audit            | Integrated/partial             | The returned Hypervisor root is persisted. An empty upstream chain gets a labeled Autodev SHA-256 terminal-evidence commitment, which is not represented as a Hypervisor delta-chain root.                |
| Causal consistency            | Partial                        | OpenTelemetry provides trace/span correlation. Hypervisor vector clocks, VFS version counters, and saga isolation levels are not integrated.                                                              |
| Command denylist              | Integrated plus local controls | Commands use argument vectors and a semantic allow-list, then invoke `RingEnforcer.check_command()` before sandbox execution. Generic shell access remains unavailable.                                   |
| Resource controls             | Implemented outside Hypervisor | Docker applies CPU, memory, PID, capability, user, network, and `no-new-privileges` controls; Azure uses custom dynamic-session limits.                                                                   |
| Observability                 | Implemented/partial            | Durable normalized provider decisions, elevation, transitions, termination, and commitments are retained. Dedicated ring/breach Prometheus series are not yet exported.                                   |

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
2. Add upstream-versioned conformance tests beyond Autodev's adapter tests.
3. Replace score-derived trust with an external durable trust/consensus service when multi-agent sessions require it.
4. Add transactional resource locks and compensation for tool side effects, not only workflow semantics.
5. Register and test live substitute agents for kill handoff.
6. Integrate Ring 0 SRE-witness and attestation infrastructure if administrative agent actions are introduced.
7. Decide whether standalone AgentMesh relay/registry/proxy services are part of the product topology; if so, authenticate and test every bridge.
8. Map each claimed OWASP/NIST/SOC 2 control to executable tests and retained evidence.
9. Obtain an independent review before using the word certified or fully compliant.

## Verification commands

```bash
.venv/bin/pytest -q \
  apps/api/tests/test_governance.py \
  apps/api/tests/test_runtime_supervision.py \
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
