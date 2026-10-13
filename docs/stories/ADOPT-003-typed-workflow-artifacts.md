# ADOPT-003: Typed and versioned workflow artifacts

**Status:** Proposed  
**Priority:** P0  
**Estimate:** 13 points

## User story

As a workflow author, I want stage outputs to conform to declared schemas so that handoffs are machine-verifiable, evolvable, and safer than summary-text conventions.

## Context

Executable workflows already declare named artifact inputs and outputs and enforce deterministic stage scheduling. Current named outputs are largely summary-oriented and do not prove that a producer emitted the structure a consumer expects.

## Scope

- Add a registry of versioned artifact types backed by JSON Schema.
- Let workflow stages declare output type/version and input-compatible version ranges.
- Validate output before publication and input before stage launch.
- Store canonical payload digest, schema digest, producer stage/run, timestamps, and validation result.
- Preserve immutable historical artifact versions and support explicit, deterministic migrations.
- Enforce organization, task, and workflow-run ownership on artifact reads.
- Keep large binaries in evidence storage with typed metadata and content-addressed references.

## Non-goals

- No model-generated schema at runtime.
- No automatic compatibility decision by an LLM.
- No mutable artifact aliases that change historical run meaning.
- No implicit cross-organization artifact sharing.

## Implementation tasks

1. Define `ArtifactEnvelope`, `ArtifactType`, compatibility rules, and stable validation errors.
2. Add registry loading with duplicate ID/version and invalid-schema rejection.
3. Extend workflow YAML validation for typed inputs/outputs and optional cardinality.
4. Canonicalize JSON payloads and compute payload and schema digests.
5. Validate producer output before making it visible; fail the stage without publishing invalid data.
6. Validate required inputs before sandbox creation to avoid paying for an impossible run.
7. Implement explicit migration functions with source/target versions, digest provenance, and replay tests.
8. Add retention and size limits; store blobs out of row storage.
9. Surface schema, version, validation errors, producer, consumers, and lineage in API/UI.
10. Convert one existing workflow end to end before making typing mandatory.

## Acceptance criteria

1. Workflow registration fails for unknown artifact types, invalid version ranges, duplicate output names, or an input with no compatible producer.
2. A stage output that violates its schema is not published and cannot be consumed.
3. A valid artifact has immutable envelope metadata and reproducible canonical digest.
4. Resuming a run uses the exact recorded artifact and schema versions, not the latest registry definition.
5. A migration executes only when explicitly registered, produces a new artifact, and records both source and target digests.
6. Artifact authorization denies cross-organization and unrelated-task reads before payload retrieval.
7. Concurrent read-only consumers receive the same immutable payload; one consumer cannot mutate another's input.
8. Missing evidence storage, oversized payloads, or digest mismatch fail closed.
9. Legacy untyped workflows remain supported during a documented migration window and are visibly marked `untyped`.
10. The converted reference workflow proves typed plan/review handoff through an integration test.

## Verification and evidence

- Schema registry and compatibility unit tests.
- Workflow graph validation tests, including parallel consumers and incompatible versions.
- Tamper test: alter stored payload and confirm digest verification blocks consumption.
- Authorization test across organizations, tasks, and workflow runs.
- Resume/replay test pinned to an older schema after registry upgrade.
- Events: `artifact.validated`, `artifact.published`, `artifact.rejected`, `artifact.migrated`, and `artifact.consumed`.

## Dependencies and risks

- Foundation for ADOPT-005 and ADOPT-006.
- Risk: schema churn blocks delivery. Start with a small set and compatibility guidance.
- Risk: database growth. Store payloads in the evidence provider and metadata in SQL.
- Risk: migration code becomes an execution surface. Migrations are trusted control-plane code, reviewed and tested; agents cannot upload them.

## Likely implementation areas

- `apps/api/app/workflow.py`
- `apps/api/app/workflow_orchestration.py`
- task artifact models and evidence providers
- workflow registry validation and workflow tests

## References

- [Executable workflow design](../design/workflow-orchestration.md)
- [Executable multi-agent workflow ADR](../adr/0003-executable-multi-agent-workflows.md)
