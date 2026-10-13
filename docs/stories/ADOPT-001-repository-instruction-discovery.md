# ADOPT-001: Hierarchical repository instruction discovery

**Status:** Proposed  
**Priority:** P0  
**Estimate:** 8 points

## User story

As an agent operator, I want task prompts to include the applicable repository instructions for the target path so that agents follow project-local conventions without replacing platform policy or requiring registry duplication.

## Context

`compose_agent_instructions()` currently combines the registered agent and attached skills. Repositories can contain root and nested instruction files, such as the existing web application instructions, but their selection and provenance are not part of the prompt contract. The useful pattern is hierarchical context discovery; the unsafe pattern is treating repository text as authority.

## Scope

- Discover supported instruction files from the task workspace root to a declared target path.
- Support `AGENTS.md` first; make additional names an explicit configuration rather than an implicit scan.
- Merge instructions in deterministic root-to-leaf order, with the nearest file last.
- Record path, digest, size, selected scope, and precedence for every included source.
- Label all repository instructions as untrusted project guidance subordinate to system, governance, task-mode, and capability rules.
- Bound file count, individual size, aggregate size, traversal depth, and parsing time.
- Recompute the instruction set when the target path changes between workflow stages.

## Non-goals

- Repository instructions cannot grant tools, capabilities, network access, approvals, or runtime tier.
- No discovery outside the isolated task clone and no user-home/global instruction lookup.
- No support for executable includes, URLs, symlink escapes, or model-selected instruction files.

## Implementation tasks

1. Define an `InstructionSource` schema with path, SHA-256 digest, scope directory, precedence, byte count, and truncation state.
2. Add a containment-safe discovery service beside prompt composition; resolve real paths and reject symlinks escaping the workspace.
3. Extend task/stage input with an optional target path. Default to the repository root when no target is known.
4. Render a clearly delimited repository-guidance section after platform agent/skill instructions and before task content.
5. Persist source metadata and the final composed-prompt digest without persisting secrets or hidden provider prompts.
6. Add policy limits and stable error codes for invalid path, oversized source, aggregate overflow, and decode failure.
7. Add preview support to show operators which files will apply before execution.
8. Document precedence and the non-authoritative status of repository guidance.

## Acceptance criteria

1. Given root and nested `AGENTS.md` files and a target below both, discovery returns each file exactly once in root-to-leaf order.
2. Given sibling instructions outside the target ancestry, those files are not included.
3. Given an absolute path, `..` traversal, or symlink resolving outside the workspace, discovery fails closed before content is read.
4. Given repository text asking to enable a forbidden capability, effective capabilities and governance decisions remain unchanged.
5. Given duplicate, oversized, binary, or undecodable sources, the configured deterministic behavior is recorded as rejected or truncated; it is never silently ignored.
6. Repeated discovery over an unchanged workspace yields identical source and aggregate digests.
7. Task evidence lists applicable paths, digests, and precedence without storing hidden system prompts.
8. Existing agents without repository instructions retain byte-for-byte equivalent composed agent/skill sections.

## Verification and evidence

- Unit tests for ancestry, precedence, limits, symlinks, traversal, encoding, and deterministic digests.
- Prompt tests proving repository content is delimited and cannot alter declared tool definitions.
- An integration fixture with root and nested instructions targeting two different subtrees.
- Event: `instructions.resolved` with source metadata, aggregate digest, target path, and policy-limit version.
- Security regression: malicious instructions request credential access and network enablement; both remain denied by the existing tool boundary.

## Dependencies and risks

- No prerequisite story.
- ADOPT-002 should consume the recorded instruction digest for reproducible evaluations.
- Risk: excessive context displaces task content. Mitigate with aggregate limits and explicit truncation evidence.
- Risk: instruction conflicts confuse the model. Mitigate with stable ordering and operator preview; do not attempt model-based conflict resolution.

## Likely implementation areas

- `apps/api/app/prompts.py`
- `apps/api/app/agent/runtime.py`
- task and event models
- `apps/api/tests/test_agent.py`

## References

- [Tool checks and governance](../design/tool-checks-and-governance.md)
- [Threat model](../threat-model.md)
