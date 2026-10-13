# PowerPoint prompt: Agent Governance in the Agentic SDLC

Copy the prompt below into PowerPoint Copilot or another presentation generator. Give the generator access to this repository when possible so it can use the cited sources without inventing details.

---

## Prompt

Create a polished, executive-friendly PowerPoint presentation titled:

**Agent Governance: From Autonomous Actions to a Governed Agentic SDLC**

Subtitle:

**How Autodev applies the Microsoft Agent Governance Toolkit through identity, policy, supervision, evaluation, evidence, and human approval**

### Audience and purpose

The audience is a mixed group of engineering leaders, architects, security/governance specialists, and software practitioners. Explain why agent governance matters, introduce the Microsoft Agent Governance Toolkit, show how its ideas apply to an Agentic SDLC, and demonstrate how this repository implements those ideas as composable building blocks.

The presentation must be understandable without prior knowledge of this repository. Use plain language first, then introduce precise technical terms.

### Hard constraints

- Maximum presentation time: **15 minutes**, including transitions.
- Create **10 main slides** with a target speaking time of **12–14 minutes**.
- Put concise speaker notes under every slide, including the target time.
- Use no more than 4 short bullets on most slides.
- Prefer visual storytelling over paragraphs or dense tables.
- Create all diagrams with editable PowerPoint shapes, connectors, icons, and labels—not screenshots.
- Use a modern, minimal, enterprise architecture style.
- Use a dark navy or charcoal background, white text, teal/blue for control-plane components, amber for deterministic gates, gray for durable evidence, green for allowed actions, red for denied or high-risk actions, and purple for external providers.
- Use subtle build animations only where they clarify a flow.
- Add a small source footer to technical slides using repository-relative paths.
- Do not invent product metrics, customer claims, certifications, benchmark results, or toolkit compliance claims.
- Do not show private chain-of-thought. Describe only explicit outputs, tool requests/results, decisions, and evidence.

### Central message

Use this sentence as the narrative spine:

> **Prompts guide behavior; deterministic controls grant authority; durable evidence proves what happened.**

The story should move through four questions:

1. Why does agentic software delivery create a new governance problem?
2. What governance primitives does the Agent Governance Toolkit provide?
3. How does Autodev turn those primitives into practical building blocks?
4. How do those blocks create a governed Agentic SDLC without removing useful autonomy?

### Slide plan

#### Slide 1 — Agent Governance: From Autonomous Actions to a Governed Agentic SDLC

**Target time: 0:45**

- Use the title and subtitle above.
- Add the statement: **“The unit of risk has moved from generated text to executed action.”**
- Visual: a coding-agent icon moving toward a repository, with a transparent control-plane shield between them.
- Speaker note: Open by contrasting a chatbot that suggests code with an agent that reads files, executes commands, changes a repository, and prepares publication.

#### Slide 2 — The governance gap

**Target time: 1:15**

Show five questions as large visual cards:

1. Which agent and exact version acted?
2. What tools, data, and repository scope could it access?
3. Which policy, tests, and security checks actually ran?
4. Which irreversible actions required a human decision?
5. Can a replacement agent be shown to be safer, not merely newer?

End with: **“A prompt cannot be its own authorization boundary.”**

Visual: put “Prompt” in the center and show the five unanswered questions around it. Avoid fear-based imagery; frame this as an engineering-control problem.

#### Slide 3 — Agent Governance Toolkit: the trust primitives

**Target time: 1:15**

Introduce the Microsoft Agent Governance Toolkit as a set of governance primitives, not as a magic safety layer. Organize the slide into four columns or quadrants:

- **Agent OS / policy:** deterministic, stateless policy enforcement.
- **AgentMesh:** DID identity, human sponsor binding, signed manifest, revocation, and capability-drift checks.
- **Agent Hypervisor:** execution rings, rate limits, temporary elevation, breach detection, demotion, kill/saga evidence, and audit commitments.
- **Agent Compliance:** PromptDefense evaluation and governance-oriented checks.

Use one sentence at the bottom:

**“Toolkit controls complement—rather than replace—local policy, typed tools, sandbox isolation, workflow rules, and approval.”**

Source footer: `docs/agent-governance-toolkit.md`

#### Slide 4 — How this repository is assembled: composable building blocks

**Target time: 1:30**

Create an editable architecture drawing titled **“Declarative control plane + governed runtime”**.

Draw three horizontal layers:

**Layer 1 — Versioned declarations**

- Agents
- Skills
- Workflows
- Policies
- Harnesses
- Capability catalog
- Evaluation suites

**Layer 2 — Deterministic control plane**

- Task / session / execution job
- Workflow controller
- Governance provider
- Identity verification
- Evaluation and promotion
- Approval controller

**Layer 3 — Bounded execution and proof**

- Docker or Azure sandbox
- Isolated Git worktree
- Durable artifacts and events
- Diffs, tests, scans, traces, and publication evidence

Show these relationships:

- Skills influence behavior but grant no authority.
- A harness maps typed tools to semantic capabilities.
- Effective authority is the intersection of agent declaration and policy, with explicit deny winning.
- The workflow controller—not the model—selects stages and completion.
- The sandbox constrains where an already-authorized action executes.

Use a side label: **“Model requests; control plane decides; evidence records.”**

Source footer: `docs/architecture.md`, `agents/`, `skills/`, `workflows/`, `policies/`, `harnesses/`, `capability-catalogs/`, `evaluations/`

#### Slide 5 — Drawing 1: every tool call crosses the governance stack

**Target time: 1:30**

Create a left-to-right editable flow drawing:

**Model request** → **Pinned harness + schema** → **Budget check** → **Capability classification** → **Agent ∩ policy decision** → **Runtime supervision** → **Scoped approval when required** → **Sandbox operation** → **Durable event/result**

Add three visible branches:

- Unknown or malformed request → **DENY**
- Policy or runtime refusal → **DENY + evidence**
- High-risk controller action → **PAUSE FOR HUMAN APPROVAL**

Add a small rule box:

- Agent deny OR policy deny = **DENY**
- Agent approval declaration OR policy requires approval = **REQUIRE APPROVAL**
- Agent capability AND policy allow = **ALLOW**
- Everything else = **DENY**

Make clear that `ToolRuntime` executes only `ALLOW`; commit, push, and pull-request approval are deterministic controller boundaries rather than model-controlled pauses.

Source footer: `docs/design/tool-checks-and-governance.md`, `policies/development.yaml`, `harnesses/workspace.yaml`

#### Slide 6 — Drawing 2: governance across the Agentic SDLC

**Target time: 1:30**

Create an editable lifecycle drawing with these stages:

**Connect / scope** → **Research** → **Plan / design** → **Implement** → **Test + security** → **Review** → **Approve** → **Commit / push / PR** → **Observe + learn**

Overlay four continuous governance rails beneath the stages:

1. **Identity:** promoted, signed, non-revoked agent definitions.
2. **Authority:** typed tools, capability policy, runtime rings, budgets.
3. **Evidence:** named artifacts, actual diff, test output, scanner output, decisions, traces.
4. **Human control:** steering and scoped approval at irreversible boundaries.

Show that Autodev has specialist roles such as product planner, architect, backend/frontend/infrastructure/mobile implementers, tester, security, and delivery reviewer. Use named durable artifacts as handoff envelopes between roles.

State these precise orchestration rules:

- Agents perform assigned stages; they do not select the next role.
- Stage inputs and outputs are declared in versioned workflow YAML.
- Read-only independent stages may run in parallel in DAG workflows.
- Write-capable stages remain serialized in the current shared workspace design.
- The active `implementation` workflow is sequential; use it as the example for controlled specialist handoffs, not as a parallel DAG.

Source footer: `docs/design/workflow-orchestration.md`, `workflows/implementation.yaml`, `workflows/design.yaml`

#### Slide 7 — Drawing 3: identity, evaluation, and promotion before execution

**Target time: 1:30**

Create an editable gated pipeline:

**Draft agent** → **Static declaration lint** → **Human-reviewed scenarios** → **Frozen dataset + SHA-256** → **Native + Vally + Waza runs** → **Safety / regression checks** → **PromptDefense** → **Promotion or rejection** → **DID + Ed25519-signed manifest** → **Pre-run verification**

Annotate the pre-run gate with:

- identity exists and is active;
- current capabilities match the signed record;
- marketplace entry points to the same DID;
- signature validates;
- any mismatch fails closed.

Add a small callout:

**“Evaluation asks whether the agent is ready. Runtime governance still decides whether each action is allowed.”**

Mention that an explicit, authorized, reason-recorded evaluation bypass can make an agent runnable but unevaluated; do not present bypass as equivalent to promotion evidence.

Source footer: `docs/design/agent-mesh-and-identity.md`, `docs/management-and-evaluation.md`, `evaluations/suites/`, `agents/developer.yaml`

#### Slide 8 — What “durable and auditable” means

**Target time: 1:15**

Use a timeline drawing with three lanes:

- **Work:** durable Task → one or more ExecutionJobs → terminal or approval-paused state.
- **Workspace:** isolated worktree → checkpoint/snapshot → continuation or handoff.
- **Evidence:** stage-attributed events → named artifacts → diff/tests/scans → approval → publication record.

Explain in no more than four bullets:

- A task survives retries, approval pauses, sandbox deletion, and process restart.
- A session is the resumable view; an execution job is one run or retry.
- Evidence comes from real tool output and repository state, not agent prose alone.
- OpenTelemetry, Prometheus, Tempo, Loki, and Grafana extend operational visibility.

Source footer: `docs/architecture.md`, `docs/adr/0001-durable-task-session-and-execution-semantics.md`, `observability/`

#### Slide 9 — Honest integration status: useful subset, not full compliance

**Target time: 1:20**

Use a simple three-column matrix: **Integrated**, **Partial / local equivalent**, **Not integrated**.

Include representative examples:

**Integrated**

- Stateless policy enforcement
- Agent DID and Ed25519 manifest verification
- Per-ring rate limiting
- Breach detection and demotion
- PromptDefense promotion gate

**Partial / local equivalent**

- Session isolation
- Score-derived execution rings
- TTL elevation for Rings 1/2
- Saga, kill/handoff evidence, hash commitments
- Audit and causal correlation

**Not integrated**

- Full conformance suite / certification
- Ring 0 and SRE-witness elevation
- External trust consensus
- Standalone AgentMesh relay/registry
- Peer trust handshake and A2A delegation chains

Put this statement prominently at the bottom:

**“Autodev integrates a useful subset of Agent Governance Toolkit 5.0.0. It is not certified or fully compliant.”**

Source footer: `docs/agent-governance-toolkit.md`

#### Slide 10 — The operating model for a governed Agentic SDLC

**Target time: 1:00**

Use a final six-part checklist around a central shield:

1. **Declare** identity, role, tools, capabilities, workflow, and policy.
2. **Evaluate** behavior against a frozen, reviewed dataset.
3. **Promote** only with retained evidence—or record an explicit authorized bypass.
4. **Execute** through typed tools in isolated sandboxes.
5. **Approve** exact irreversible actions at human boundaries.
6. **Observe and improve** using durable evidence and regression comparison.

Close with this exact takeaway:

> **Governance does not remove agent autonomy. It turns autonomy into bounded, attributable, reviewable software delivery.**

Optional final spoken sentence:

**“Start with one bounded workflow, one policy, one promoted agent set, and expand only when the evidence supports it.”**

### Speaker-note guidance

For every slide:

- Include a one-sentence transition from the previous slide.
- Explain the visual instead of reading bullets.
- Define technical terms the first time they appear.
- Keep speaker notes to roughly 90–170 words depending on the allocated time.
- Keep the total scripted delivery below 14 minutes so normal pauses remain within 15 minutes.

### Factual guardrails

Apply these rules throughout the deck:

- Say **“Agent Governance Toolkit”** or **“Microsoft Agent Governance Toolkit”** on first use.
- Say that Autodev integrates a useful subset of version 5.0.0; never say certified, fully compliant, or conformant.
- Distinguish identity from authorization: a valid DID and signature do not grant a tool action.
- Distinguish sandbox from policy: isolation limits execution location; it does not decide authority.
- Distinguish skills from permissions: skills guide behavior and never grant tools, capabilities, network access, or approval.
- Distinguish evaluation from runtime enforcement: passing an evaluation does not bypass policy.
- Distinguish AgentMesh-compatible identity primitives from a distributed execution mesh.
- Do not claim peer-to-peer agent communication; current handoffs use workflow-selected, named durable artifacts.
- Do not claim that all workflows run stages in parallel. Current parallelism is only for dependency-ready read-only stages; the implementation workflow is sequential.
- Do not claim that provider-native private reasoning is stored. Only explicit outputs, requests/results, decisions, and optional operator-enabled traces are retained.
- Describe Ring 0, external trust consensus, standalone relay/registry, peer handshakes, and A2A delegation as not currently integrated.
- If discussing the developer agent, avoid treating its current repository-local evaluation override as evidence that all agents passed the full promotion gate.

### Repository sources

Use these files as the factual source of truth:

- `README.md`
- `docs/architecture.md`
- `docs/agent-governance-toolkit.md`
- `docs/design/tool-checks-and-governance.md`
- `docs/design/workflow-orchestration.md`
- `docs/design/agent-mesh-and-identity.md`
- `docs/design/task-execution.md`
- `docs/design/harness-contracts.md`
- `docs/management-and-evaluation.md`
- `docs/runtime-supervision-adapters.md`
- `docs/product/features-and-how-to.md`
- `docs/diagrams/README.md`
- `agents/developer.yaml`
- `workflows/implementation.yaml`
- `workflows/design.yaml`
- `policies/development.yaml`
- `harnesses/workspace.yaml`
- `capability-catalogs/governance.yaml`
- `evaluations/suites/`

For visual inspiration, use—but redraw with native PowerPoint shapes—the editable sources under `docs/diagrams/` and the Mermaid sketches in `docs/design/`. Do not paste screenshots of source diagrams.

### Required output

Return:

1. The complete 10-slide presentation.
2. Editable diagrams on Slides 4–8.
3. Speaker notes with timing for every slide.
4. Repository source footers on technical slides.
5. A final timing summary proving the scripted presentation is under 15 minutes.
