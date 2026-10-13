# ADR 0008: Durable state, leased jobs, events, snapshots, and evidence

- Status: Accepted with limitations
- Date: 2026-10-06

## Context

Long-running agent work must survive API restarts and must remain inspectable after transient infrastructure disappears. At the same time, local development should not require a large distributed stack. Queue coordination, live updates, durable business state, workspace bytes, and evidence blobs have different consistency and retention needs.

## Decision

Relational storage through SQLModel is authoritative for projects, tasks, jobs, messages, events, approvals, artifacts, datasets, evaluation runs, identities, organizations, and memberships. SQLite is the local default; PostgreSQL is the production target.

Execution is coordinated by durable `ExecutionJob` rows. Workers claim jobs with a lease token, renew heartbeats, observe maximum attempts, and use deduplication keys. Embedded dispatch is suitable for local development; API and worker processes are separate deployment roles in production.

The `Event` table is the source of truth for task lifecycle and runtime observations. The live event hub carries invalidations only. It uses in-process publish/subscribe locally and Redis Streams when configured for shared-instance delivery. Clients refetch durable state rather than applying event messages as authoritative patches.

Structured stage and task outputs are JSON artifacts. Large or provider-native evidence is written behind `EvidenceProvider` to local files or Azure Blob. Workspace revisions use a separate snapshot provider because repository bytes have different restore and conflict semantics from evidence.

Task telemetry is derived from persisted events, messages, approvals, and artifacts instead of copied into an independent analytics database. OpenTelemetry trace/span IDs are attached where available for infrastructure correlation. Sensitive prompt/response content remains opt-in evidence rather than a default metric label.

## Alternatives considered

- Use an external queue as the only job record. Rejected because broker retention and delivery do not provide complete business history.
- Treat WebSocket/Redis messages as state. Rejected because reconnects and trimming would lose authoritative transitions.
- Put repository snapshots and large raw evidence in relational JSON. Rejected because size, streaming, retention, and restore patterns differ.
- Require PostgreSQL, Redis, and Blob locally. Rejected because the local-first experience should run with minimal dependencies.
- Maintain a separate metrics database from day one. Rejected because durable events already contain the initial operational facts and duplicate ingestion would create consistency work.

## Consequences

Local and production topologies share business semantics but differ in durability guarantees. In-process invalidations may be lost on restart; polling and full refetch close UI gaps. Redis stream trimming is acceptable because relational events remain authoritative.

On-read telemetry can be more expensive than pre-aggregated metrics and historical records may lack precise provider usage. Evidence retention and database retention must be coordinated so records do not point to deleted blobs without an explicit tombstone policy.

## Security and operations

Every relational query is organization-scoped at the API boundary. Blob and snapshot object keys must include tenant/task context and resist path injection. Evidence must redact credentials and avoid unbounded output. Lease expiry permits recovery but can produce duplicate side effects unless stage operations are idempotent or guarded by durable state.

Production requires PostgreSQL backups, Blob soft deletion/versioning, Redis TLS, and workload identity or managed credentials. Snapshot fingerprint conflicts fail closed rather than overwriting concurrent work.

## Validation and limits

Queue tests cover claiming, heartbeat, retry, and deduplication. Client behavior combines WebSocket invalidation and polling. There is no dead-letter queue or event-sourced state reconstruction; relational rows remain the canonical current state. At very high volume, polling queues and on-read telemetry will require dedicated scaling work.
