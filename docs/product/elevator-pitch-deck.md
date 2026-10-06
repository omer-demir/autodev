---
marp: true
theme: default
paginate: true
title: Autodev - Governed Agentic Software Delivery
description: Elevator pitch deck for Autodev
---

# Autodev

## The control plane for agentic software delivery

Bring any coding agent. Keep deterministic control.

<!-- Speaker note: Autodev is not another chatbot. It is the layer that makes autonomous development governable, portable, and provable. -->

---

# The shift

Coding assistants now:

- Research repositories
- Edit and run code
- Use tools and external systems
- Work asynchronously
- Prepare pull requests

The unit of risk has moved from **generated text** to **executed action**.

---

# The operating gap

Teams need answers to five questions:

1. What can this agent do?
2. Where will it execute?
3. Which human decisions remain required?
4. How do we know a new agent version is better and safe?
5. Can we prove what happened after the run?

Prompts alone cannot answer them deterministically.

---

# The product

Autodev separates three boundaries:

| Boundary   | Decision                              |
| ---------- | ------------------------------------- |
| Sandbox    | Where can execution happen?           |
| Governance | Which semantic capability is allowed? |
| Workflow   | When is the capability appropriate?   |

The model requests. The control plane decides. The evidence records.

---

# The user journey

```text
Connect repository
      ↓
Select promoted agent + model
      ↓
Research → Plan → Implement → Review
      ↓
Inspect diff + tests + security + policy
      ↓
Approve commit / push / pull request
```

The original checkout remains untouched.

---

# Bring your own ecosystem

- Agents: local YAML or imported `.agent.md`
- Skills: native packs, `SKILL.md`, GitHub, skills.sh
- Models: Copilot, Ollama, Foundry
- Sandboxes: Docker, Azure dynamic sessions
- Governance: local policy, Microsoft Agent Governance Toolkit
- Evaluators: native, Vally, Waza
- Interfaces: Web, REST, CLI, MCP

Remote declarations never grant local authority.

---

# Evidence-backed RPI

Each task follows Research, Plan, Implement, Review.

Autodev records:

- Retrieval and tool events
- Requirements and acceptance checks
- Real changed files and Git diff
- Test commands and output
- Semgrep, Trivy, and Gitleaks findings
- Model/tool latency and usage
- Policy decisions and approvals

Model prose is a summary, not proof.

---

# Promotion, not hope

Agent changes move through:

```text
Draft → Static lint → Human-reviewed dataset → Frozen hash
      → Native + Vally + Waza → Regression comparison → Promotion
```

The evaluated agent version and dataset must match exactly.

---

# Local to cloud

**Local**

- Next.js + FastAPI
- SQLite and file evidence
- Docker worktree sandboxes
- Prometheus, Tempo, Grafana

**Cloud**

- OIDC and organization RBAC
- Azure Container Apps dynamic sessions
- Workload identity and ACR
- Log Analytics and capacity alerting

One provider contract, one evidence model.

---

# Market position

Most coding-agent products optimize the agent experience.

Autodev optimizes the **control plane**:

- Agent and model portability
- Policy at tool-dispatch time
- Local or cloud execution ownership
- Behavioral release gates
- Evidence portability
- Human approval boundaries

Complement coding agents instead of betting the platform on one.

---

# Roadmap

**Now:** import review, auth hardening, signed evidence, evaluation reliability

**Next:** PostgreSQL/HA, fine-grained policy, managed sandbox broker, trusted asset catalog

**Then:** adapter SDK, continuous evaluation, compliance exports, fleet SRE

**North star:** every autonomous software change is policy-bound, independently verifiable, and reversible.

---

# The ask

Pilot Autodev with one bounded engineering workflow:

1. Select a repetitive but meaningful task class.
2. Encode its agent, skills, policy, and frozen evaluation suite.
3. Measure accepted changes, human review time, failures, cost, and policy decisions.
4. Expand only when evidence supports it.

**Bring any coding agent. Keep control.**
