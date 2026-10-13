# Glossary

This glossary defines Autodev terms by their implemented ownership and lifecycle. The distinctions matter because similarly named objects have different durability, authority, and user-visible effects.

## Core work objects

### Task

A **task** is the primary durable work aggregate for a requested repository outcome. It owns the selected project, workflow, mode, assigned agent, lifecycle status, progress, events, messages, approvals, artifacts, and execution attempts. A task survives process restarts and sandbox deletion. Creating a task means asking Autodev to perform product work.

A task is not a model conversation and not one worker attempt. One task may have several execution jobs and can be viewed or continued through a session.

### Session

A **session** is the resumable, user-facing history and continuation view of a task. It exposes the task's persisted messages, events, artifacts, approvals, and worktree state through the browser, CLI, and MCP gateway. Continuing a terminal session adds instructions and schedules another execution against the same durable task and restored workspace.

A session is not a second copy of a task, an in-memory model chat, or a sandbox. In the current implementation its identity is derived from the task it presents.

### Execution job

An **execution job** is one queued or running attempt to execute or retry a task. Jobs carry lease, heartbeat, attempt, deduplication, and outcome data so workers can recover from process failure without duplicating the durable task.

A retry creates or reuses execution-job state; it does not create a new task or session.

### Evaluation run

An **evaluation run** is a durable record of testing an agent declaration against an evaluation dataset. It belongs to the evaluation subsystem, not the product task/session subsystem. Native evaluation uses evaluation-owned fixture workspaces, sandbox executions, events, metrics, and evidence IDs. It must not create projects, tasks, sessions, execution jobs, task artifacts, or task approvals.

### Evaluation execution

An **evaluation execution** is one scenario-level agent invocation within an evaluation run. Its `execution_id` identifies isolated runtime evidence but is not a task ID and does not appear in task or session history.

## Agent and workflow objects

### Agent declaration

An **agent declaration** is versioned YAML describing an agent's identity, instructions, skills, model preference, policy, exact harness, semantic capabilities, denials, approvals, and sandbox environment. It is reviewed configuration, not a running process.

New or edited declarations are `draft`. Only a declaration with qualifying behavioral evidence can become `promoted`.

### Draft agent

A **draft agent** can be edited and evaluated but cannot be assigned to product task execution. Draft status does not imply that evaluation data or results exist.

### Promoted agent

A **promoted agent** is the exact declaration version that passed the promotion gate. Promotion requires a completed qualifying behavioral run linked to a matching human-reviewed frozen dataset, all required adapters, score and safety thresholds, no unacceptable regression, and prompt-defense acceptance.

### Workflow

A **workflow** is a versioned YAML execution contract selected by `Task.workflow_id`. It defines stages, responsible agents, order or dependencies, named artifact inputs and outputs, and handoff content. The controller, not the model, owns workflow transitions.

### Stage

A **stage** is one responsibility within an executable workflow. Exactly one declared agent owns each stage. A stage receives bounded context and named input artifacts, runs in the assigned agent's sandbox profile, and publishes named output artifacts.

### Handoff

A **handoff** is a durable, named artifact transfer between workflow stages. It is explicit data governed by the workflow contract, not an untracked conversation between agents.

### Skill

A **skill** is a reusable instruction asset attached to an agent declaration. Skills influence behavior but do not grant capabilities, tools, network access, or approval.

## Evaluation objects

### Evaluation suite

An **evaluation suite** is a versioned YAML source of scenario requirements and constraints. It is authoring input used to generate an agent-version-specific dataset.

### Evaluation dataset

An **evaluation dataset** is the concrete collection of scenarios bound to an agent version and suite version. Candidate generation is deterministic and reuses an existing identical dataset for the same organization, agent version, and suite version.

### Reviewed dataset

A **reviewed dataset** is a candidate whose scenario content has been inspected and accepted by an identified human reviewer. Review alone does not make it executable for promotion evidence.

### Frozen dataset

A **frozen dataset** is reviewed scenario content sealed by a canonical SHA-256 hash. Frozen content is immutable. Behavioral runs must reference this dataset and record the same hash.

### Verified behavioral result

A **verified behavioral result** is a completed behavioral run whose dataset ID and hash resolve to a frozen dataset with the same organization, agent, agent version, suite, and suite version. For promotion it must also include the required native, Vally, and Waza evidence, meet score and safety thresholds, and avoid a blocking regression.

A declaration lint result is not a verified behavioral result.

### Evaluator provider and model

The **evaluator provider and model** execute and judge evaluation scenarios independently from the evaluated agent's production model preference. The defaults are Ollama and `gemma4:e2b`. Both values are persisted in evaluation provenance. External adapters may have their own executor limitations, which must be reported rather than represented as the selected native provider.

### Native, Vally, and Waza adapters

The **native adapter** invokes the real governed agent runtime in an isolated evaluation-owned Docker workspace and records deterministic checks plus rubric evidence. **Vally** and **Waza** translate the same frozen scenarios into their evaluator formats and normalize their results. Their evidence is required by the current promotion policy.

## Execution and governance objects

### Sandbox

A **sandbox** is the disposable process, filesystem, network, and resource boundary in which commands run. Docker is the local provider; Azure Container Apps dynamic sessions are the cloud provider. Deleting a sandbox does not delete durable task or evaluation records.

### Worktree or workspace

A **worktree** is the isolated Git checkout used for product work. A **workspace** is the broader provider-neutral filesystem location mounted into a sandbox. Product task workspaces persist for continuation; evaluation fixture workspaces belong only to evaluation evidence.

### Capability

A **capability** is a semantic action such as `repository.read`, `repository.write`, `test.run`, or `dependency.install`. It is independent of a specific tool schema or command spelling.

### Capability catalog

A **capability catalog** is a versioned registry of semantic capabilities. It provides the vocabulary used by harnesses, agent declarations, policies, evaluation scenarios, and evidence.

### Harness

A **harness** is the versioned binding from model-visible tools to semantic capabilities and runtime implementations. Agents pin an exact harness and catalog version; unresolved pins fail closed.

### Policy

A **policy** is deterministic authorization configuration evaluated at tool-dispatch time. Effective authority is the intersection of the agent declaration, selected policy, runtime supervision, sandbox boundary, and any required approval. Deny wins.

### Runtime supervision

**Runtime supervision** tracks an agent execution identity, trust tier, workflow phase, action decisions, elevations, and termination independently from prompt behavior. Evaluation executions receive supervision handles without becoming product tasks.

### Approval

An **approval** is a durable human decision over a bounded action and scope, such as a specific commit or publication operation. It is not a general permission grant.

## Evidence and integration objects

### Artifact

An **artifact** is structured durable output such as a plan, handoff, diff summary, test result, security result, or workflow-run state. Product artifacts are attached to tasks; evaluation evidence is attached to evaluation runs and adapter evidence paths.

### Event

An **event** is a timestamped lifecycle or runtime observation. Persisted task events are the product source of truth. WebSocket and Redis messages are invalidations, not the authoritative event record.

### Evidence

**Evidence** is independently inspectable data supporting a claim: tool decisions, diffs, command results, scanner output, hashes, adapter output, model usage, or approvals. Model prose can summarize evidence but is not evidence by itself.

### Project

A **project** identifies a source repository or empty workspace that product tasks target. Evaluation fixtures do not create projects.

### MCP gateway

The **MCP gateway** exposes governed session and workspace operations to authenticated clients. It reuses task/session ownership, RBAC, policy, sandbox, and approval rules; it does not bypass the control plane.

### Provider

A **provider** is a replaceable implementation behind a stable boundary, such as model, sandbox, governance, supervision, evidence, snapshot, credential, or event-stream provider. Provider portability does not mean all providers offer identical guarantees; unsupported guarantees must fail closed or be reported explicitly.
