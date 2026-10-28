---
title: Architecture design deep dives
description: Implementation-oriented guides to AutoDev workflow and governance boundaries.
---

This series explains how Autodev turns a task into governed agent work. It complements the [architecture overview](../architecture.md), [ADRs](../adr/README.md), and formal [Draw.io catalog](../diagrams/README.md) with implementation-oriented, hand-drawn views.

## Reading map

| Question                                              | Design document                                             |
| ----------------------------------------------------- | ----------------------------------------------------------- |
| What is inside the agent mesh and what does it prove? | [Agent mesh and identity](agent-mesh-and-identity.md)       |
| How is every tool request checked?                    | [Tool checks and governance](tool-checks-and-governance.md) |
| Where does MCP fit, and how could A2A fit later?      | [MCP and A2A boundaries](mcp-and-a2a.md)                    |
| What belongs in a harness?                            | [Harness contracts](harness-contracts.md)                   |
| How are detailed multi-agent workflows controlled?    | [Workflow orchestration](workflow-orchestration.md)         |
| How does one task run from request to publication?    | [End-to-end task execution](task-execution.md)              |

## Status notation

Every document separates implemented behavior from future design:

- **Current** means implemented in this repository and linked to its owning code or ADR.
- **Proposed** means a design direction, not a claim about current runtime behavior.
- **Out of scope** marks a boundary that another component owns.

The inline Mermaid diagrams use Mermaid's `handDrawn` look. They are source-controlled sketches rather than exported bitmaps, so their labels and architecture can evolve with the code. The formal deployment and trust-boundary drawings remain editable Draw.io sources.

## Design rules shared by the series

1. The deterministic controller owns workflow state; models do not choose their own authority.
2. Human identity, agent identity, and runtime execution identity remain separate.
3. A tool name is not an authorization unit; semantic capability is.
4. MCP is an interface to governed services, not a bypass around them.
5. Handoffs contain declared artifacts, not unrestricted conversation history.
6. Missing identity, schema, policy, supervision, approval, or sandbox state fails closed.

## Source hierarchy

When prose and implementation differ, use this order to resolve the discrepancy:

1. Accepted ADRs describe intended invariants and tradeoffs.
2. Versioned YAML definitions describe selected agents, workflows, harnesses, and policies.
3. Runtime code describes the behavior currently enforced.
4. Tests demonstrate the behavior currently verified.

Update the relevant ADR when changing an invariant. Update a deep dive when changing an implementation path or adding a supported integration.
