# ADOPT-004: Bounded repository intelligence map

**Status:** Proposed  
**Priority:** P1  
**Estimate:** 13 points

## User story

As a coding or review agent, I want a compact, deterministic map of relevant repository symbols and relationships so that I can navigate large codebases with fewer broad searches and less context waste.

## Context

Agents currently have bounded file listing, search, and paginated reads. A repository map inspired by tree-sitter-based systems can improve orientation, but it must not become a hidden authority, an unbounded indexing job, or a route around repository-read controls.

## Scope

- Build language-aware symbol indexes for an explicitly supported language set.
- Capture file, symbol kind, qualified name, declaration range, imports, and best-effort reference edges.
- Apply repository exclusions, file/byte/time limits, and workspace containment.
- Incrementally update changed files by digest.
- Rank map slices from deterministic task terms, target paths, and declared stage inputs.
- Expose the map through a governed read-only tool and typed artifact.
- Fall back to a clearly marked lexical outline for unsupported or parse-failing files.

## Non-goals

- No full semantic compiler replacement.
- No indexing dependency directories, VCS internals, secrets, binary files, or files outside the task clone.
- No background upload or external embedding service by default.
- No automatic capability expansion based on symbols found.

## Implementation tasks

1. Define a versioned repository-map schema and parser adapter contract.
2. Select parsers and document their licenses, supported grammar versions, and update process.
3. Reuse repository exclusion and safe-path behavior from agent repository tools.
4. Add incremental cache keys from file digest, parser version, and map schema version.
5. Implement deterministic ranking and token/entry budgets with truncation metadata.
6. Add `repository.map.read` or map it explicitly to `repository.read`; preserve governance and supervision checks.
7. Emit a typed artifact usable by workflow stages and evaluations.
8. Add operator metrics for parse failures, index duration, cache hit rate, and map truncation.
9. Add prompt rendering that identifies the map as derived, potentially incomplete context.

## Acceptance criteria

1. The same repository, parser versions, and request produce an identical canonical map digest.
2. Excluded, binary, oversized, and out-of-workspace files never appear in map content or provenance.
3. A one-file edit reparses that file and affected edges without rebuilding unrelated files.
4. Unsupported syntax produces a bounded fallback entry and diagnostic rather than fabricated semantic edges.
5. Requests exceeding file, time, or token limits return deterministic truncation markers and never silently claim completeness.
6. Reading the map passes through governance and runtime supervision like other repository reads.
7. An agent can resolve a symbol to its source path/range and must use normal file reads for source content.
8. A benchmark demonstrates reduced file-read/search calls on representative repositories without lowering task success or safety.
9. Parser dependencies pass license and supply-chain review.

## Verification and evidence

- Golden maps for Python and TypeScript fixtures, plus one unsupported language fixture.
- Tests for malformed files, symlinks, exclusions, generated directories, cache invalidation, and deterministic ranking.
- Evaluation comparison reporting success, tool calls, tokens, index cost, and parse coverage.
- Events: `repository_map.started`, `repository_map.completed`, and `repository_map.partial` with digests and limits.

## Dependencies and risks

- ADOPT-001 provides target-path context and compatible instruction scope.
- ADOPT-003 is preferred for artifact publication.
- Risk: parser CVEs and grammar drift. Pin versions, scan dependencies, and treat source as hostile input.
- Risk: stale maps mislead agents. Bind maps to workspace snapshot and file digests; reject mismatches.

## Likely implementation areas

- new repository-intelligence service under `apps/api/app`
- `apps/api/app/agent/repository.py`
- harness/tool declarations
- evaluation fixtures and observability dashboards

## References

- [Architecture](../architecture.md)
- [Harness contracts](../design/harness-contracts.md)
