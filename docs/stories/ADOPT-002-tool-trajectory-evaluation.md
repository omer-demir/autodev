# ADOPT-002: Declarative tool-trajectory evaluation

**Status:** Proposed  
**Priority:** P0  
**Estimate:** 8 points

## User story

As an evaluation owner, I want behavioral suites to assert how an agent used tools, not only its final files and prose, so that promotion detects unsafe, wasteful, or non-verifying behavior.

## Context

Native behavioral evaluation already records tool events and checks outputs, tests, capabilities, scores, and rubric terms. Promotion can therefore miss an agent that reaches the expected output through repeated denied calls, unsafe ordering, or a write without subsequent verification.

## Scope

Add a versioned `trajectory` section to evaluation scenarios with declarative checks for:

- allowed and forbidden tool/capability names;
- minimum and maximum call counts;
- ordered and unordered subsequences;
- argument predicates over redacted structured arguments;
- required verification after a write;
- denial count and repeated-denial limits;
- recovery behavior after a failed call;
- total tool and shell budgets;
- optional latency ceilings that do not affect safety scoring unless explicitly required.

Trajectory evaluation is deterministic. An LLM judge may explain a trace but cannot decide whether a mandatory trajectory rule passed.

## Example contract

A developer scenario can require at least one repository read before the first write, forbid network-bearing dependency installation, require a test after the final write, and reject more than one repeated call with identical normalized arguments.

## Implementation tasks

1. Define and validate a versioned trajectory schema in suite loading.
2. Normalize native tool events into ordered records containing sequence number, tool, capability, argument digest, decision, result class, latency, and sandbox identifier.
3. Redact values before persistence and expose predicates only over allowlisted fields.
4. Implement deterministic matchers with precise failure messages and source rule IDs.
5. Mark missing or truncated required trace evidence as `INDETERMINATE`, which fails mandatory checks.
6. Add trajectory scores separately from output quality and include them in safety/promotion policy.
7. Extend baseline comparison to report newly introduced denials, retries, and call inflation.
8. Render a timeline and failed rule details in evaluation evidence APIs and the web UI.
9. Migrate one developer and one security scenario as reference fixtures.

## Acceptance criteria

1. Suite validation rejects unknown operators, impossible ranges, secret-bearing raw-value matches, and unsupported schema versions.
2. A required ordered subsequence passes only when matching calls occur in order; unrelated calls may be allowed only when configured.
3. A write followed by no successful test fails `verification_after_write` even if expected files exist.
4. Repeating the same denied action beyond the declared limit fails the scenario.
5. Argument matching uses normalized structured arguments and never stores raw secret values.
6. Trace truncation, event loss, or missing sequence numbers cannot produce a pass.
7. The report links every failure to rule ID and matching event sequence numbers.
8. Existing suites without a trajectory section retain their current result.
9. Promotion policy can require a trajectory safety score of 1.0 independently of rubric quality.

## Verification and evidence

- Matcher unit tests for ordering, cardinality, predicates, retries, writes, test verification, and malformed traces.
- Golden traces covering pass, fail, skipped, truncated, and out-of-order cases.
- End-to-end native evaluator test proving stored events produce the same result after replay.
- Evidence includes the suite version, trajectory schema version, normalized trace digest, matched sequence numbers, and rule results.
- Compare native, Vally, and Waza runs without pretending providers expose equivalent trace detail.

## Dependencies and risks

- ADOPT-001 supplies prompt/instruction provenance for reproducibility but is not required for the first matcher implementation.
- Risk: overfitting agents to one exact sequence. Prefer invariants and subsequences over full trace equality.
- Risk: sensitive arguments enter evidence. Use field allowlists, hashing, and centralized redaction before storage.
- Risk: parallel read-only calls have nondeterministic completion order. Evaluate request sequence or partial-order groups, not wall-clock completion order.

## Likely implementation areas

- `apps/api/app/behavioral_evaluation.py`
- evaluation suite schema/loading code
- `evaluations/suites/developer.yaml`
- `evaluations/suites/security.yaml`
- behavioral evaluation tests and web evidence views

## References

- [Management and evaluation](../management-and-evaluation.md)
- [Executable workflow design](../design/workflow-orchestration.md)
