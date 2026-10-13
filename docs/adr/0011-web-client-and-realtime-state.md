# ADR 0011: Web client and realtime state consistency

- Status: Accepted
- Date: 2026-10-06

## Context

Agent runs are long-lived and produce frequent events, but the browser must not become a second state machine. WebSocket delivery can disconnect, duplicate, or arrive out of order, and an in-process hub is not durable. Operational screens also need dense, inspectable data rather than a chat-only representation.

## Decision

The web application uses the Next.js App Router and a shared authenticated shell. FastAPI REST resources are authoritative for projects, tasks, sessions, registries, evaluations, security, and management actions.

WebSocket messages are invalidations, not state patches. The dashboard receives global invalidations; a selected task uses task-scoped subscription so unrelated events do not trigger refetches. On invalidation, the client fetches the complete durable resource.

A visible selected-task page polls every three seconds and refetches immediately on focus or visibility restoration. Polling closes reconnect and process-restart gaps. Hidden documents reduce polling work. Multi-instance delivery may use Redis Streams, but the browser behavior remains full refetch from REST.

The UI separates product tasks/sessions from evaluation runs. Evaluation scenarios show evaluation execution IDs and adapter evidence; they do not link to fabricated tasks. Provider/model inputs are explicit, with evaluator defaults shown to the operator.

Operational interfaces prioritize lifecycle, diff, tests, security, policy, approvals, evidence, and telemetry. Model chat is one interaction surface, not the authoritative representation of completion.

## Alternatives considered

- Apply WebSocket event payloads directly to client state. Rejected because missed or reordered messages could make the browser authoritative and inconsistent.
- Poll every resource continuously. Rejected because it wastes bandwidth and increases database load.
- Use WebSockets only. Rejected because reconnect gaps and local hub restarts would leave stale state.
- Represent all activity as chat messages. Rejected because structured approvals, artifacts, policy decisions, and failures need dedicated views.
- Show evaluation executions as tasks. Rejected because it conflates bounded contexts and pollutes product history.

## Consequences

REST response completeness and query efficiency matter because invalidations trigger refetches. The design favors correctness and simple reconciliation over minimal payload size. UI components must tolerate eventual invalidation and duplicate refreshes.

Task-scoped subscriptions require authorization at connection time and must not leak cross-organization IDs. Evaluation polling refreshes long-running adapter results without depending on product event streams.

## Security and operations

Cookies/tokens apply equally to REST and WebSocket handshakes. Organization/task membership is checked before subscription. UI text must not overstate readiness, pass status, provider identity, or evidence; disabled actions expose concrete blockers.

Polling intervals are operational defaults, not consistency guarantees. API rate limits and query indexes must account for active browser populations.

## Validation and limits

Frontend lint/build and responsive browser checks validate implementation. There is no offline mutation queue or optimistic write reconciliation. Very high event rates may justify incremental read models later, but durable REST state remains the source of truth.
