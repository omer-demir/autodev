# ADR 0010: Provider-neutral local and Azure deployment

- Status: Accepted with limitations
- Date: 2026-10-06

## Context

The product must be useful on a developer workstation and deployable as a resilient organizational control plane. Those environments differ in identity, database, eventing, storage, isolation, scaling, and failure modes. Hard-coding cloud services into domain logic would make local use impractical; pretending local components provide cloud guarantees would be unsafe.

## Decision

Domain services depend on explicit provider contracts for sandbox execution, governance, runtime supervision, evidence, workspace snapshots, credentials, model runtime, and event distribution. Provider selection is configuration, and readiness/guarantees are surfaced rather than inferred.

Local development uses Next.js, FastAPI, SQLite, local evidence/snapshots, in-process event invalidation, Docker sandboxes, and optional local Ollama. Docker Compose adds the observability stack while retaining local ownership.

Azure deployment separates externally reachable control-plane API from independently scaled workers. PostgreSQL Flexible Server stores durable records and job leases. Redis carries shared invalidations. Blob Storage holds snapshots and evidence. Key Vault and workload identity hold secrets and authorize managed services. Azure Container Apps custom dynamic sessions provide execution pools, with separate immutable network/profile configurations where needed.

The API does not execute queued product work in the production topology. Workers claim jobs and use dynamic sessions. Managed identity replaces embedded cloud credentials. Infrastructure alerts cover capacity, lease health, storage, and provider readiness.

## Alternatives considered

- One universal process and storage stack. Rejected because local simplicity and production availability have conflicting requirements.
- Cloud-only SaaS execution. Rejected because repository ownership, offline/local models, and customer-controlled infrastructure are product requirements.
- Local-only Docker architecture. Rejected because host-socket isolation and single-host state are insufficient for many production deployments.
- Couple domain services directly to Azure SDKs. Rejected because it prevents local substitutes and obscures guarantee differences.
- Execute jobs in API replicas. Rejected because model/sandbox latency would couple public API availability to untrusted workload execution.

## Consequences

Provider contracts become critical compatibility surfaces and require conformance tests. Local mode can run with fewer services, but its failure and isolation guarantees are explicitly weaker. Azure adds cost and operational complexity but separates scaling and trust boundaries.

Some provider capabilities cannot be normalized. For example, Azure session network mode is pool-defined, while Docker can disconnect a running container. The application must fail closed when a requested guarantee cannot be enforced rather than silently degrading.

## Security and operations

Production uses TLS, private networking where practical, workload identity, least-privileged role assignments, purge-protected Key Vault, database backups, Blob retention, and separated API/worker identities. Dynamic session images and registry content are supply-chain assets that require controlled promotion.

Provider readiness is a deployment gate. Multi-instance APIs require shared event distribution and durable workspace snapshots. Capacity exhaustion must surface as a schedulable operational failure rather than an unexplained model error.

## Validation and limits

Local and Azure provider tests validate common contracts and explicit mismatch failures. The repository supplies an Azure reference deployment, not a guarantee of compliance or universal scale. Disaster-recovery objectives, cross-region failover, and tenant-dedicated infrastructure remain deployment-specific work.
