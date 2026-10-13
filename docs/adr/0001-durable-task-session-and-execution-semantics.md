# ADR 0001: Durable task, session, and execution semantics

- Status: Accepted
- Date: 2026-10-06

## Context

Autonomous work lasts longer than an HTTP request and can cross model failures, worker restarts, approvals, sandbox replacement, and human follow-up. Treating a model conversation, queue message, or container as the unit of work would lose business identity whenever one of those transient mechanisms changes. The UI, CLI, MCP gateway, retry logic, and evidence layer also need one consistent answer to what is being continued.

## Decision

`Task` is the primary durable work aggregate. It owns the requested outcome, project, mode, selected workflow and agent, lifecycle, messages, events, approvals, artifacts, and references to execution attempts.

A session is the resumable presentation and continuation contract for a task. It is not a second persistence aggregate. Session APIs reconstruct history from durable task records and persisted workspace state. Continuation is allowed only when the prior attempt is terminal, no approval is pending, and the selected replacement agent is promoted.

`ExecutionJob` represents one queue attempt or retry. Jobs have deduplication keys, attempt limits, lease tokens, heartbeats, and outcomes. A retry does not create a new task or erase prior history. Workers may be replaced while the task remains stable.

A sandbox is transient execution infrastructure, not session state. Product worktrees and optional snapshots preserve repository state after a sandbox is removed.

Evaluation runs are explicitly outside this hierarchy. They have evaluation IDs and must not manufacture tasks or sessions merely to invoke an agent.

## Alternatives considered

- Make each model conversation a session and attach tasks to it. Rejected because provider-native conversation state is not durable or portable and does not own approvals or repository state.
- Make every retry a new task. Rejected because audit history, user intent, approvals, and worktree continuity would fragment.
- Treat the sandbox/container as the session. Rejected because containers are intentionally disposable and provider-specific.
- Store all state in queue payloads. Rejected because leases and queues coordinate work; they are not the authoritative business record.

## Consequences

The task ID remains stable across retries and continuation. APIs must distinguish task mutation from job scheduling. Cleanup can remove a container without deleting user history. UI status reflects durable task state rather than worker process state.

The model must not own lifecycle transitions. The controller records transitions before and after execution and can recover from interrupted attempts. Session continuation must restore or locate the persisted worktree before scheduling a new job.

## Security and operations

Stable task identity allows approvals, policy decisions, actor identity, and evidence hashes to be correlated across attempts. Deduplication and leases reduce duplicate execution but do not replace idempotent stage behavior. Operators must monitor expired leases and failed cleanup separately from task outcome.

Workspace snapshot failure may block continuation when snapshots are configured as required. In local mode, host worktrees remain a durability dependency.

## Validation and limits

API tests cover draft cancellation, retries, terminal continuation constraints, and organization scoping. The current session identity is task-derived rather than a separately versioned aggregate. Per-stage execution records are represented through workflow artifacts and events rather than a dedicated `StageExecution` table; that may change if stage-level retry becomes a requirement.
