# ADR 0006: Model runtime and context boundaries

- Status: Accepted
- Date: 2026-10-06

## Context

Model providers differ in authentication, session behavior, tool protocols, model catalogs, usage reporting, and failure modes. The control plane must remain authoritative when providers change. Large repositories cannot be injected wholesale, and parsing free-form assistant prose as a command protocol would be fragile.

## Decision

Microsoft Agent Framework is the model-agent runtime. GitHub Copilot and Ollama use official framework connectors; Microsoft Foundry Responses is an optional provider behind a compatible boundary. Framework-native function tools carry typed arguments into the same governed `ToolRuntime`. Final assistant prose is never decoded as an action envelope.

The product runtime defaults to Copilot model `auto`, with configurable Ollama fallback. Provider failures are observable and support retry, model change, fallback, or cancellation. Fallback creates a new provider-native session from immutable task and persisted context; provider session internals are not translated.

Evaluation provider/model selection is independent of production agent preferences. Its default is Ollama `gemma4:e2b` and is persisted in run provenance.

Application prompts are `.prompty` assets loaded with strict variables. Agent-specific instructions and skills are rendered into the system prompt, while task/stage/session context is supplied separately. Prompt files are reloadable without recompiling application code.

Repository context uses progressive, governed retrieval: paginated file listing, bounded reads, literal search with globs and capped matches, and exclusion of generated dependency trees. Tool-call and shell-call budgets are policy-derived. Steering is persisted and injected between model turns only while a conversational execution phase is active.

Verbose prompt/response logging is opt-in because it may contain source and sensitive content. Operational events record bounded provider/model/error metadata even when verbose logging is disabled.

## Alternatives considered

- Build a custom model protocol per provider. Rejected because official connectors handle provider-specific sessions and tool calls.
- Parse JSON commands from final assistant text. Rejected because prose, formatting errors, and injection make it unreliable.
- Translate conversation sessions across providers. Rejected because provider state is opaque and semantically incompatible.
- Send the whole repository in the initial prompt. Rejected because of context limits, cost, stale evidence, and injection surface.
- Hard-code prompts in Python. Rejected because prompt review and iteration should be asset-level changes.
- Enable verbose traces globally. Rejected because they can become a sensitive source-code archive.

## Consequences

Providers remain replaceable at the execution boundary, but not behaviorally identical. Usage and cost metrics are shown only when trustworthy metadata exists. Ollama has zero API-price estimates but local infrastructure cost is explicitly excluded.

Agents must retrieve evidence iteratively and may require more turns. Bounded observations improve control but can hide relevant context if budgets are too small. Prompt edits affect future renders immediately and therefore need the same review discipline as code.

## Security and operations

Copilot built-in permission requests are denied; local deterministic tools own authority. Checkout-defined hooks are disabled. Model errors, fallbacks, and rejected taskless responses are recorded without exposing secrets. Timeouts bound provider stalls and operator-recovery windows.

Foundry and remote Ollama endpoints require network and identity controls outside this ADR. Provider names in evidence must represent actual execution, not merely a requested setting.

## Validation and limits

Agent tests verify session reuse, steering, timeouts, permissions, and fallback behavior. Context budgets are character- and call-based rather than fully model-token-aware. There is no cross-provider deterministic replay of model generations.
