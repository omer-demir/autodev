# ADR 0005: Isolated workspaces and sandbox providers

- Status: Accepted with limitations
- Date: 2026-10-06

## Context

Agents need real filesystem and process access, but running directly in the control plane or original checkout would expose credentials, allow cross-task interference, and make rollback difficult. Local developers need a low-friction runtime; production deployments need stronger isolation and independently scalable execution.

## Decision

Every product task operates on an isolated Git worktree under the managed workspace root. The original checkout is never mounted into the agent sandbox. Change and assessment modes share this boundary but have different completion rules: change tasks require meaningful changes and publication handling; assessments can complete read-only without a commit.

`SandboxProvider` abstracts create, execute, argument-vector execution, readiness, and kill operations. Docker is the local provider. It uses a dedicated image, non-root UID/GID, CPU/memory/PID limits, dropped capabilities, `no-new-privileges`, controlled bind mounts, and network disconnection by default. Dependency operations may receive temporary bridge access only when governance allows it.

Azure Container Apps custom dynamic sessions are the cloud provider. They use pool-defined Hyper-V isolation, immutable network profiles, workload identity, remote workspace synchronization, and fingerprint checks that reject concurrent host changes.

Executable workflow stages use the assigned agent's declared image, network mode, workspace access, pool profile, and environment. Secondary stage sandboxes are ephemeral. The primary task worktree remains the durable handoff surface; optional snapshots preserve it across hosts.

Evaluation uses separate fixture workspaces and evaluation-owned sandboxes. These workspaces never create projects or tasks.

No sandbox receives host SSH state, control-plane environment files, original repositories, cloud credentials, or the Docker socket. Publication credentials are injected only into deterministic control-plane operations through ephemeral askpass mechanisms.

## Alternatives considered

- Run tools directly in the API process. Rejected because one agent compromise would become control-plane compromise.
- Modify the user's checkout. Rejected because concurrent tasks and failed runs could damage local work.
- Standardize on Docker everywhere. Rejected because production isolation and elastic session requirements differ from local development.
- Standardize on Azure everywhere. Rejected because local development should not require cloud identity or cost.
- Keep stage containers alive for the task lifetime. Rejected because role-specific environments should not accumulate stale state or idle resources.
- Give all sandboxes network access. Rejected because most repository work does not require egress and dependency installation is a separately governable capability.

## Consequences

Provider implementations must preserve common semantics while reporting guarantee differences. Images become trusted supply-chain inputs and should be pinned by digest in production. Large repositories and snapshots consume storage and may dominate startup time.

Deleting a sandbox does not delete task state, artifacts, or the worktree. Cleanup failure is operational evidence and must not overwrite the primary task outcome. Remote provider synchronization adds latency and conflict handling.

## Security and operations

Mount-source calculation and path containment are security-critical. Docker socket access remains a control-plane risk: sandbox containers do not receive it, but a compromised API container with the host socket may control Docker. Production should isolate the execution broker from the public API and prefer a managed session boundary.

Network profile mismatch fails closed. Workspace snapshots should be required for multi-host durable continuation. Scanner tools run in the trusted control plane and are not installed by agents.

## Validation and limits

Provider tests cover network/profile rejection, workspace synchronization, and cleanup. Docker container isolation is not equivalent to Hyper-V isolation. Filesystem persistence is host-dependent when local snapshots are disabled, and there is no content-addressed workspace deduplication yet.
