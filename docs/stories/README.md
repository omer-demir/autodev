---
title: Product and resilience stories
description: Implementation backlog for product adoption, environment isolation, and resilience assurance.
---

This backlog translates selected ideas from AutoDev/Xiuper and the current Autodev threat model into implementation-ready stories. It preserves Autodev's deterministic control plane: models may propose work, but policy, workflow scheduling, approvals, sandboxing, and evidence decisions remain outside the model.

Use the [root README](../../README.md) and [local setup guide](../local-setup.md)
for installation, development commands, and configuration. This directory is
an implementation backlog, not a product or operator runbook.

## How to use this backlog

Each story defines an outcome, scope, implementation tasks, acceptance criteria, required evidence, dependencies, and explicit non-goals. A story is complete only when its tests and operator-facing evidence are implemented; documentation alone is not completion.

Status values are `Proposed`, `Ready`, `In progress`, `Blocked`, and `Done`. Initial status is `Proposed`. Estimates are relative story points and should be revised during planning.

## Adoption epic

These stories adapt patterns rather than source code. AutoDev/Xiuper is MPL-2.0; implementation should be clean-room and should preserve third-party notices for any dependency or copied material.

| ID        | Story                                                                                          | Priority | Estimate | Depends on |
| --------- | ---------------------------------------------------------------------------------------------- | -------: | -------: | ---------- |
| ADOPT-001 | [Hierarchical repository instruction discovery](ADOPT-001-repository-instruction-discovery.md) |       P0 |        8 | —          |
| ADOPT-002 | [Tool-trajectory evaluation](ADOPT-002-tool-trajectory-evaluation.md)                          |       P0 |        8 | ADOPT-001  |
| ADOPT-003 | [Typed workflow artifacts](ADOPT-003-typed-workflow-artifacts.md)                              |       P0 |       13 | —          |
| ADOPT-004 | [Repository intelligence map](ADOPT-004-repository-intelligence.md)                            |       P1 |       13 | ADOPT-001  |
| ADOPT-005 | [Bounded specialist agents](ADOPT-005-bounded-specialist-agents.md)                            |       P1 |       13 | ADOPT-003  |
| ADOPT-006 | [Thin IDE integration](ADOPT-006-thin-ide-integration.md)                                      |       P2 |        8 | ADOPT-003  |

## Environment isolation epic

The current local setup retains project-scoped workspace bind mounts. A separate
VM-based mode is proposed for developers who do not want personal-machine folders
or the personal-machine Docker daemon exposed to the environment.

| ID          | Story                                                                    | Priority | Estimate | Depends on |
| ----------- | ------------------------------------------------------------------------ | -------: | -------: | ---------- |
| ISOLATE-001 | [Dedicated VM without host mounts](ISOLATE-001-dedicated-vm-isolation.md)   |       P1 |        8 | None       |

## Chaos and adversarial assurance epic

The chaos stories validate boundaries; they do not authorize uncontrolled exploitation. Every active probe must use synthetic secrets, disposable workspaces, controlled endpoints, resource ceilings, an explicit profile, and cleanup verification. Production and shared environments default to passive checks only.

| ID        | Story                                                                               | Priority | Estimate | Depends on    |
| --------- | ----------------------------------------------------------------------------------- | -------: | -------: | ------------- |
| CHAOS-001 | [Campaign foundation](CHAOS-001-campaign-foundation.md)                             |       P0 |       13 | —             |
| CHAOS-002 | [Credential isolation](CHAOS-002-credential-isolation.md)                           |       P0 |        8 | CHAOS-001     |
| CHAOS-003 | [Filesystem and mount boundaries](CHAOS-003-filesystem-and-mount-boundaries.md)     |       P0 |        8 | CHAOS-001     |
| CHAOS-004 | [Network, host, and metadata egress](CHAOS-004-network-host-and-metadata-egress.md) |       P0 |       13 | CHAOS-001     |
| CHAOS-005 | [Process and kernel boundaries](CHAOS-005-process-and-kernel-boundaries.md)         |       P1 |       13 | CHAOS-001     |
| CHAOS-006 | [Resource exhaustion and recovery](CHAOS-006-resource-exhaustion-and-recovery.md)   |       P1 |       13 | CHAOS-001     |
| CHAOS-007 | [Governance and approval bypass](CHAOS-007-governance-and-approval-bypass.md)       |       P0 |       13 | CHAOS-001     |
| CHAOS-008 | [MCP and tenant isolation](CHAOS-008-mcp-and-tenant-isolation.md)                   |       P1 |       13 | CHAOS-001     |
| CHAOS-009 | [Agent-driven attack chains](CHAOS-009-agent-driven-attack-chains.md)               |       P1 |       13 | CHAOS-002–008 |
| CHAOS-010 | [Continuous chaos reporting](CHAOS-010-continuous-chaos-reporting.md)               |       P2 |        8 | CHAOS-001–009 |

## Execution profiles

| Profile              | Intended environment                                        | Allowed activity                                                                                            |
| -------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `static`             | Every pull request                                          | Configuration, policy, schema, and command-construction assertions; no live sandbox attack                  |
| `sandbox-smoke`      | Trusted CI with Docker                                      | Short, harmless probes against disposable local sandboxes and synthetic canaries                            |
| `isolated-chaos`     | Dedicated self-hosted runner or ephemeral test subscription | Resource pressure, controlled network sinks, provider fault injection, and multi-step agent scenarios       |
| `production-passive` | Production                                                  | Read-only conformance checks and evidence freshness; no exploit simulation, exhaustion, or external traffic |

Profiles are deny-by-default. A scenario declares its minimum profile and maximum blast radius. A runner must reject a scenario whose requirements exceed the selected profile.

## Global safety contract

1. Never read, copy, print, or transmit real credentials. Provision uniquely identifiable synthetic canaries and verify only their hashes or detection IDs.
2. Never target public services, cloud metadata services, the Docker host, other tenants, or arbitrary IP addresses. Use local emulators and controlled sinks.
3. Never run a published exploit or attempt an actual container escape. Validate invariant enforcement with benign syscalls, namespace inspection, and negative capability checks.
4. Run active scenarios only in disposable, labeled resources with hard CPU, memory, PID, time, and egress limits.
5. Abort the campaign on containment uncertainty, unexpected egress, cleanup failure, control-plane health degradation, or evidence pipeline failure.
6. A skipped, timed-out, indeterminate, or errored probe is not a pass. The campaign is successful only when required probes pass and cleanup is independently confirmed.
7. Store bounded, redacted evidence. Command output must be size-limited and secret scanned before persistence.
8. Require a human approval for `isolated-chaos`; production remains passive unless a separately reviewed operational procedure explicitly permits more.

## Common definition of done

- Unit tests cover schema validation and fail-closed behavior.
- Provider contract tests cover Docker and Azure behavior where supported; unsupported behavior is reported, never silently passed.
- Events identify campaign, scenario, provider, sandbox, agent, policy version, expected result, actual result, and cleanup result.
- Evidence is organization-scoped, immutable or content-addressed, redacted, and linked to an evaluation run.
- A failed scenario cannot improve a promotion score, and required skipped/error scenarios block promotion.
- Operator documentation states prerequisites, cost, blast radius, abort conditions, and cleanup procedure.
- Existing architectural claims are updated only after executable evidence exists.

## Architectural references

- [Architecture](../architecture.md)
- [Threat model](../threat-model.md)
- [Executable workflow design](../design/workflow-orchestration.md)
- [Tool checks and governance](../design/tool-checks-and-governance.md)
- [MCP and A2A boundaries](../design/mcp-and-a2a.md)
- [Runtime supervision adapters](../runtime-supervision-adapters.md)
- [Executable multi-agent workflow ADR](../adr/0003-executable-multi-agent-workflows.md)
- [Layered capability governance ADR](../adr/0004-layered-capability-governance.md)
- [Sandbox provider ADR](../adr/0005-isolated-workspaces-and-sandbox-providers.md)
