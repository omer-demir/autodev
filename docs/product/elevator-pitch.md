# Elevator pitch

## One line

Autodev is the open control plane for governed multi-agent software delivery: reviewable workflows, least-privileged execution, human approvals, and evidence that proves what happened.

## 30-second pitch

Coding agents can now research, design, implement, test, and prepare real software, but most teams still choose between productivity and control. Autodev turns those roles into reviewable workflows while keeping authority outside the models. Every specialist runs with its own policy and sandbox profile; handoffs are durable artifacts; sensitive actions require scoped approval; and agent versions cannot be promoted without frozen, independently linked behavioral evidence. It is not another coding chatbot. It is the governance and operations layer for agentic software delivery.

## Two-minute pitch

The market is moving from code completion to autonomous software agents. That creates a new operational problem: a model can be useful and still be unpredictable, over-privileged, difficult to evaluate, and hard to audit.

Autodev addresses that problem with three independent boundaries. The sandbox decides where code executes. Governance decides which semantic capability is allowed. The workflow decides when that capability is appropriate. The model can request a file write, command, commit, or push, but deterministic code makes the decision and records the result.

An operator connects a repository, chooses an executable workflow, and creates a change or assessment task. Ideation, design, planning, frontend, backend, infrastructure, testing, and delivery review can be assigned to distinct promoted agents. Named artifacts cross explicit handoffs; read-only DAG stages may run in parallel; write-capable work remains serialized. The workbench captures the actual diff, tests, scanner output, model and tool telemetry, policy decisions, stage ownership, and approval history. Commit and publication remain human-controlled.

Autodev is deliberately portable. It supports GitHub Copilot, Ollama, and Microsoft Foundry; Docker locally and Azure Container Apps dynamic sessions in cloud deployments; local or Microsoft Agent Governance Toolkit policy enforcement; and native, Vally, and Waza evaluation. Evaluation is its own governed subsystem, not synthetic product work: it uses isolated fixture workspaces, an explicitly selected evaluator provider/model (Ollama `gemma4:e2b` by default), immutable datasets, and cryptographically linked results. Teams can import agents and skills from public ecosystems, but remote declarations never grant local authority.

The result is a platform engineering layer for organizations that want agent productivity without surrendering control, evidence, deployment choice, or model choice.

## Audience-specific versions

### Engineering leader

Increase throughput with coding agents while keeping changes reviewable, test-backed, and approval-gated. Autodev gives one operating model across local development and cloud sandboxes instead of a different trust story for every agent.

### Security and risk leader

Prompts are guidance, not controls. Autodev intercepts tool calls in deterministic code, applies default-deny capability policy, isolates execution, requires scoped approvals, and produces evidence linked to agent, policy, dataset, and run.

### Platform engineer

Bring models, specialist agents, skills, MCP tools, workflows, sandboxes, and evaluators behind stable provider boundaries. Manage them as versioned definitions while keeping tasks, resumable sessions, execution attempts, and evaluation runs semantically separate.

### Developer

Delegate a real task, steer it while it works, inspect the actual worktree and test results, and take over in VS Code. Your original checkout stays untouched and nothing is committed without approval.

## Positioning statement

For engineering organizations adopting autonomous coding agents, Autodev is a governed SDLC workbench that makes agent execution portable, observable, evaluable, and approval-controlled. Unlike model-specific coding agents, Autodev treats the agent as replaceable and makes policy plus evidence the durable platform.

## Tagline options

- Governed software agents, real delivery evidence.
- Bring any coding agent. Keep control.
- The control plane for agentic software delivery.
- Autonomous coding inside deterministic boundaries.

## Proof points

- Every tool call resolves to a semantic capability before execution.
- Docker and Azure sandboxes share one governed runtime contract.
- Imported agents and skills cannot grant themselves authority.
- Executable workflows assign one accountable agent per stage and persist named handoffs.
- Promotion requires a completed result cryptographically linked to a matching frozen dataset, with native, Vally, and Waza evidence.
- Evaluation runs never manufacture product tasks or sessions.
- Commit, push, and pull-request publication remain scoped approval boundaries.
- Durable events and artifacts make model claims independently inspectable.
