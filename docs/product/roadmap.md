# Product roadmap

## Product direction

Autodev should become the control plane for governed software agents across models, runtimes, repositories, and evaluation systems. The roadmap prioritizes proof, policy, and portability over adding another conversational coding surface.

This is an outcome roadmap, not a delivery commitment. Horizons start from October 2026 and should be re-ranked using adoption and reliability evidence.

## Current baseline: shipped

- End-to-end isolated repository task workflow with approval-gated publication.
- Microsoft Agent Framework runtime with Copilot, Ollama fallback, and Foundry Responses option.
- Local/Agent Governance Toolkit policy boundary, signed agent identities, organization scope, and RBAC.
- Docker and Azure Container Apps dynamic-session sandbox providers.
- Versioned agents, skills, policies, harnesses, catalogs, workflows, and evaluation suites.
- Safe `.agent.md` and `SKILL.md` imports plus native RPI skills.
- Frozen behavioral datasets with native, Vally, and Waza evidence.
- Durable sessions, MCP access, security probes, telemetry, and OpenTelemetry export.
- Five-item recent-task dashboard plus server-side task filtering, sorting, and pagination.
- OIDC authorization-code login with PKCE, opaque server-side sessions, membership administration, and tested WebSocket/MCP role boundaries.
- Empty Git workspace onboarding for discovery tasks and promoted-agent handoff through durable session continuation.

## Horizon 1: operational trust (0-3 months)

### Outcome: teams can operate Autodev repeatedly without hidden manual work

| Initiative                    | Deliverable                                                                                                                            | Exit measure                                                       |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Import review UX              | Attach/detach skills visually, provenance diff, trust decision, license warning, content hash                                          | 90% of imported assets activated without direct YAML editing       |
| Production auth hardening     | Session rotation/revocation operations, provider setup profiles, break-glass recovery, and complete REST/WebSocket/MCP route inventory | 100% route authorization coverage in automated tests               |
| Agent release workflow        | Draft comparison, changelog, prompt/skill dependency graph, rollback to prior promoted version                                         | Every promotion links immutable definition and dependency hashes   |
| Evaluation reliability        | Retry semantics, adapter health history, confidence intervals, flaky-scenario quarantine                                               | Less than 2% infrastructure-caused false failures                  |
| Evidence portability          | Signed evidence bundle with policy, agent, dataset, adapter, and artifact manifests                                                    | Independent verifier can validate a completed run offline          |
| Hypervisor control completion | Dynamic trust/ring enforcement, TTL elevation, rate limiting, breach demotion, saga compensation, kill handoff, persisted audit root   | Upstream-versioned conformance suite passes with retained evidence |
| Documentation and examples    | Golden-path demos for Python, TypeScript, monorepo, assessment, and imported skill                                                     | New operator completes first governed task in under 20 minutes     |

## Horizon 2: team-scale control plane (3-6 months)

### Outcome: multiple teams can safely share infrastructure and reusable assets

| Initiative                  | Deliverable                                                                                                                   | Exit measure                                                          |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| PostgreSQL and event broker | Replace inline schema upgrades with versioned migrations; certify HA-safe leasing, Redis invalidation, failover, and recovery | Two API replicas pass failover and recovery tests                     |
| Fine-grained authorization  | Project membership, path/task/environment conditions, separation of duties, expiring approvals                                | Policy tests cover every human and agent action class                 |
| Managed sandbox service     | Replace direct Docker socket with least-privilege broker; pool quotas and image allowlist                                     | API compromise cannot control the host daemon                         |
| Agent/skill catalog         | Search, dependency versions, signatures, publisher trust, compatibility, deprecation                                          | Assets can be promoted across organizations without losing provenance |
| Multi-repository tasks      | Coordinated worktrees, per-repository policy, atomic review bundle                                                            | One task can produce a linked multi-repo change set                   |
| FinOps controls             | Cost allocation, quotas, per-project budgets, anomaly alerts                                                                  | At least 95% of paid model calls allocated to project and actor       |

## Horizon 3: enterprise agent platform (6-12 months)

### Outcome: Autodev becomes the evidence and policy plane for heterogeneous agents

| Initiative            | Deliverable                                                                                                      | Exit measure                                                       |
| --------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Adapter SDK           | Stable contracts and conformance suite for model, sandbox, governance, evaluator, repository, and event adapters | Third-party adapter ships without core changes                     |
| Policy as product     | Simulation, staged rollout, policy diff, blast-radius analysis, organization templates                           | Policy changes can be previewed against historical evidence        |
| Continuous evaluation | Scheduled suites, production drift detection, regression bisect, canary agent versions                           | Promotion quality tracked against post-promotion outcomes          |
| Compliance evidence   | Control mappings and export profiles for internal audit, SOC 2, NIST AI RMF, and OWASP Agentic risks             | Auditor can trace control to policy decision and evidence artifact |
| Fleet SRE             | Agent SLOs, error budgets, circuit breakers, kill switches, capacity forecasting                                 | Automated halt on configured safety or reliability breach          |
| Deployment modules    | Harden the existing Azure Bicep reference and add Kubernetes/Terraform patterns                                  | Reproducible deployment with documented recovery objectives        |

## Horizon 4: ecosystem (12+ months)

- Federated agent and skill exchange with trust and revocation.
- Domain-specific workflow packs for security remediation, modernization, compliance, and platform engineering.
- Cross-organization evidence attestations and policy interoperability.
- Benchmark exchange using portable frozen datasets and evaluator manifests.
- Human/agent work allocation based on risk, confidence, cost, and queue health.

## Product metrics

### Trust

- Policy decision correctness and fail-closed rate.
- Percentage of completed changes with complete test, security, and review evidence.
- Escaped safety incidents per 1,000 tasks.
- Mean time to revoke an agent, skill, model, or adapter.

### Quality

- Behavioral evaluation pass rate versus post-promotion success rate.
- Regression rate by agent version and skill dependency.
- Human rejection and rework rate.
- Flaky evaluation rate.

### Efficiency

- Median time from task creation to reviewable change.
- Human minutes per accepted change.
- Sandbox queue and startup time.
- Model cost per accepted change, with priced-call coverage.

### Adoption

- Weekly active operators and organizations.
- Promoted agents and reviewed skills in active use.
- Repeat task rate after first successful run.
- Percentage of tasks using non-default adapters or providers.

## Explicit non-goals

- Replacing Git hosting, issue tracking, CI/CD, or IDEs.
- Treating prompts as security policy.
- Automatically trusting internet agents or skills.
- Optimizing a single model at the expense of provider portability.
- Auto-deploying production changes without independent authorization.
