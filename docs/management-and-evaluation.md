# Agent, policy, MCP, workflow, and evaluation management

Open `/management` in the Workbench. Definitions remain YAML files in the repository so changes can be reviewed and versioned with Git.

## Registries

- Agents: `agents/*.yaml`
- Skills: `skills/*.yaml`
- Governance policies: `policies/*.yaml`
- MCP server declarations: `mcp/servers/*.yaml`
- Tool harnesses: `harnesses/*.yaml`
- Capability catalogs: `capability-catalogs/*.yaml`
- Workflow declarations: `workflows/*.yaml`
- Evaluation suites: `evaluations/suites/*.yaml`

Agent definitions include a stable DID, semantic version, model binding, exact harness version, `policy` ID, capabilities, attached skill IDs, approval-required actions, denied actions, and allowed MCP server IDs. A harness pins its capability catalog and defines canonical tool schemas and capability bindings. Saving agent YAML always returns it to `status: draft`; manually writing `promoted` cannot bypass the behavioral gate. The effective decision is the intersection of the agent declaration and its selected governance policy; either side can deny an action. Policies are active immediately after saving, so review policy changes like code.

The Management page supports creating, selecting, editing, and deleting these YAML definitions. To build an agent, create its agent declaration, select or create its governance policy, create an evaluation suite, run the declaration check, generate/review/freeze a behavioral dataset, run native + Vally + Waza, and then select **Promote agent**. Compose bind-mounts every registry back to the workspace, so UI edits survive container recreation.

The MCP registry describes allowed servers and harness bindings. External clients can use the tenant-scoped Workbench gateway at `/gateway/mcp` or `/gateway/sse`; its session tools enforce the same authentication, RBAC, promoted-agent, pending-approval, and terminal-state rules as the REST API. Saving an MCP declaration does not execute arbitrary commands. Workflow declarations do not rewrite the active Python controller.

## Bring your own agents and skills

Management imports public HTTPS sources in GitHub Copilot `.agent.md` or Agent Skills `SKILL.md` format. GitHub blob links are converted to raw content, and `https://skills.sh/<owner>/<repo>/<skill>` is resolved to the repository's single matching `SKILL.md`. Imports are limited to 250 KB, use bounded timeouts and redirects, and reject credentials or hosts that resolve to private, loopback, link-local, or otherwise non-public addresses.

Imported content is instruction data, not execution authority. Agent imports are always saved as `draft` with a local DID, the development policy, the workspace harness, read-only repository capabilities, and explicit write/install/deploy/credential denials. Remote `tools`, `allowed-tools`, handoffs, model settings, scripts, and permissions are retained only as source provenance. Skill imports retain their instruction body and advisory metadata; they execute only when an operator adds the skill ID to a local agent's `skills` list. The governing system prompt, local agent declaration, harness, policy, sandbox, and approval gate always take precedence.

The built-in developer agent attaches the native Research-Plan-Implement-Review skill pack. The controller records `rpi-plan` before model execution and persists `rpi-research`, `rpi-implementation`, and `rpi-review` artifacts from actual retrieval calls, repository changes, tests, and security scans. Corresponding `rpi.*` timeline events make phase evidence visible without trusting model self-report.

## Durable sessions and publication

The Sessions page and `agentctl sessions` expose persisted task history and continuation. Continuation is accepted only after the current run is terminal, no approval is pending, and any selected replacement agent is promoted. A fresh isolated runtime imports the persisted worktree before execution.

Completed changes can request governed publication with `agentctl publication` or the Sessions page. Push and optional pull-request creation require scoped approval. Publication refuses a dirty worktree, uses ephemeral Git credentials, redacts tokens from output, and records the resulting evidence.

Docker is the default sandbox provider. Azure deployments can select the custom dynamic session provider; host and remote workspaces synchronize before and after commands with fingerprint checks that reject concurrent host changes. See [Azure session deployment](azure-deployment.md).

## Agent run telemetry

Select an agent and open **Telemetry** to inspect operational evidence across its latest runs. Summary cards show run outcomes, token coverage, provider/model usage, estimated cost coverage, average duration, model errors, fallbacks, and denied actions. Select a task to drill into phase timing, individual model and tool latency, safety and policy decisions, persisted developer and agent messages, scanner findings, approvals, and the timestamped event timeline.

Telemetry is derived from persisted task events, messages, approvals, and security artifacts, so historical runs remain visible without a separate metrics database. New runs store precise model and tool latency; older runs infer latency from adjacent event timestamps. Token counts are shown only when the provider reports them. Missing usage is displayed as unavailable rather than zero.

Copilot estimates use the selected model's token prices advertised by the authenticated Copilot CLI. The CLI reports prices in GitHub AI Credits, which the Workbench converts at the published rate of one AI Credit to $0.01 USD, including cache and long-context tiers when available. `WORKBENCH_MODEL_PRICING_JSON` remains an operator override; keys can target `provider/model` or `provider/*`, and values support `input_per_million_usd`, `output_per_million_usd`, cache rates, and `per_request_usd`. Ollama has a zero model-API charge, but that estimate explicitly excludes local hardware and energy. Estimates always display priced-call coverage and are usage estimates rather than an invoice or the fixed subscription fee.

## Task execution and retry

Choose **Change repository** for implementation work and **Read-only assessment** for reviews, architecture analysis, and security assessments. Assessment tasks can complete without a diff or commit; change tasks fail clearly when the agent produces no changes.

Every run and retry reloads the current agent YAML. Every tool decision also reloads the current agent and selected policy, so capability and policy edits made in Management apply to the retry. Existing task identity and worktree are retained.

Environment setup belongs to the agent, not to language detection in the controller. Each agent can declare an `environment.image` and `environment.setup_instructions`. The image supplies the appropriate toolchain; the agent inspects the actual repository, chooses its package manager commands, installs dependencies, and runs checks through governed tools. For example, a Go agent can use a pinned Go image, while Rust, Python, JVM, or polyglot agents can use independently maintained images.

Commands classified as `dependency.install` receive temporary Docker bridge access only after both the agent declaration and selected policy allow that capability. The bridge is removed immediately after the command, and all other sandbox work remains disconnected. Common Node, Python, Go, Rust, Ruby, PHP, Java, and .NET setup commands are classified, but the controller does not decide which command a repository needs.

The declared image must be a trusted, pinned image that can run `sleep infinity` and the agent's argument-safe commands as the sandbox UID. Missing non-default images are pulled by the control plane at sandbox creation. For stronger supply-chain control, use image digests and pre-pull approved images.

Task containers exist only for active execution and optional inspection while a change waits for commit approval. The controller removes the container after an assessment completes, after an approved change is committed, or when a task fails or is cancelled. Container cleanup does not remove the host worktree, commit, artifacts, events, or durable evidence. Cleanup failures are recorded as `sandbox.cleanup_failed` events without replacing the task's primary outcome.

Semgrep, Trivy, and Gitleaks are control-plane scanners, not project dependencies. `unavailable` means the scanner binary is not installed in the API runtime; granting `dependency.install` to an agent does not authorize it to modify the control plane.

## Verbose model log

Enable **Verbose LLM trace** when creating a task to add a realtime **Model log** tab. The provider emits the exact Copilot conversation prompt immediately before invocation and the raw final response after completion. Native tool requests and results appear as their own governed task events. Ollama emits its complete request payload and raw response. When Copilot fails and configured fallback activates, the log also records the primary provider error before the fallback request. Events use the task-scoped WebSocket, so the selected task updates without refreshing.

Verbose traces can contain source code, repository instructions, tool output, and model responses. They are stored as task events and evidence-adjacent operational data, so leave tracing disabled for sensitive repositories unless the deployment's access and retention controls are appropriate. Responses are recorded per completed model turn rather than token-by-token, avoiding one database event per token.

## Steering

Steering is accepted only while the coding agent is in intake, planning, or implementation. Instructions are persisted, injected between model turns, and shown with the agent's subsequent response in the task Chat tab. The agent performs a second steering check after every model response, so guidance submitted while a final response is in flight triggers another model turn instead of being silently stranded. Once testing or review begins there is no active conversational loop; the API returns a conflict and the UI asks the developer to retry the task rather than pretending the message will receive a response.

## Static checks versus behavioral evaluation

The instant **Static declaration lint** is not an agent evaluation and does not call a model. It compares the YAML declaration's capabilities with required and forbidden capabilities, and its run provenance records `agent_executed: false`.

A real evaluation uses the **Frozen behavioral datasets** workflow: generate scenarios, review and freeze them, then run **Docker + Vally + Waza**. Native scenarios materialize fixture repositories and execute the production task workflow; Vally and Waza execute their own adapters. Behavioral provenance records `agent_executed: true`, and only this evidence can promote an agent.

Management numbers the required review and freeze actions, explains the exact reason the run action is disabled, and reports Docker, Vally, and Waza readiness before execution. The API container includes both evaluator CLIs; native development must make `vally` and `waza` available on the API process `PATH`.

The Security page also runs `security-v1` active probes. These simulate rogue-agent requests for every expected catalog decision and persist only actions, policy outcomes, versions, and safe provider metadata. An optional Microsoft Foundry canary reports `COMPLETED`, `SKIPPED`, or `ERROR`; a skipped or errored provider check is never presented as a pass, and attack prompts are not persisted.

## Prompty prompt assets

Application model instructions live under the top-level `prompts/` directory as `.prompty` files with YAML frontmatter, declared inputs, and Jinja-compatible templates. The API loads them with strict undefined-variable handling. Agent declarations continue to own agent-specific environment guidance; Python code supplies typed runtime values but does not contain application prompt prose.

Prompt assets are read from disk on every render so edits apply without restarting the API. The initial Agent Framework run receives the immutable task id, title, required outcome, governance constraints, and current developer steering. Repository file reads default to 6,000-character pages and are bounded to 24,000 characters per request. Copilot turns time out after 300 seconds by default so operator recovery or task failure remains observable rather than hanging indefinitely.

If a model nevertheless responds by asking the developer to provide a task, the control plane rejects that response rather than marking the task complete, records an `agent.response.rejected` warning, and continues the same Agent Framework session with a focused instruction. Provider errors and Copilot-to-Ollama transitions are recorded even when verbose prompt logging is disabled. If both agents fail, the task error includes both the original Copilot failure and the Ollama fallback failure.

Copilot and Ollama tool calls use Agent Framework function tools instead of a prompt-defined JSON assistant envelope. Typed arguments are validated by the framework, then routed through the same policy and sandbox code. Final assistant prose is never searched for or decoded as JSON. A fallback starts a new Ollama Agent Framework session from the immutable task prompt because provider-native session state is intentionally not translated between runtimes.

## Large repository context

The workbench does not send an entire repository to the model. Agents receive governed retrieval tools: paginated and filterable file listing, bounded file chunks, and literal text search with file globs and capped matches. Dependency and generated directories are excluded. These built-in tools are declared by the workspace MCP registry and can later be replaced by an external MCP implementation without changing the context policy.

Conversation and provider context are owned by Agent Framework sessions rather than a Workbench-specific message ledger or compaction protocol. Workbench still bounds every repository observation, excludes generated dependency trees, caps searches and listings, and limits total tool invocations. Agents should re-read targeted evidence instead of requesting repository dumps. This keeps governance and evidence deterministic while allowing each official connector to apply its native context behavior.

This policy follows several reusable context-engineering patterns:

- [Agent Skills for Context Engineering: context compression](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering/tree/main/skills/context-compression) recommends anchored iterative state, mandatory artifact sections, observation masking before conversational compression, explicit provenance, and recall/artifact/continuation/decision probes.
- [Awesome Agent Skills](https://github.com/heilcheng/awesome-agent-skills) uses three-stage progressive disclosure: lightweight discovery, task-triggered instructions, then on-demand resources. The workbench applies the same principle to repository discovery, search, and bounded reads.
- [Awesome Copilot](https://github.com/github/awesome-copilot) demonstrates bounded planning context, evidence by reference, resumable progress records, precise repository retrieval, and progressive loading rather than eager context injection.
- [Awesome AI Agents](https://github.com/Jenqyang/Awesome-AI-Agents) highlights durable structured memory, provenance-tagged retrieval, per-type token pools, checkpoint/resume, and verification from external evidence rather than agent self-report.

Character limits remain a deterministic cross-provider safety boundary, not an exact model-token calculation. A later provider-aware layer should reserve separate token pools for immutable instructions, tool schemas, working state, retrieved evidence, recent turns, and response headroom. Compression quality should be evaluated behaviorally with frozen probes for factual recall, artifact tracking, continuation, decisions, constraints, and re-fetch frequency; lexical summary similarity is not a sufficient metric.

## Evaluation and promotion

The fast authoring evaluator is `declaration-v1`. It checks every suite scenario for:

- required capability coverage;
- forbidden-capability safety;
- an immutable association with the evaluated agent and suite versions.

Promotion requires a successful `behavioral-v1` run of the current agent version and frozen dataset through all three adapters: native Workbench Docker, Vally, and Waza. The aggregate score must be at least 85%, safety must be 100%, and the candidate must not regress by more than 0.02 against the latest successful prior-version behavioral run.

Immediately before promotion, the API also renders the candidate's runtime system prompt with its attached local skills and policy budgets, then runs Microsoft Agent Governance Toolkit `PromptDefenseEvaluator`. Evaluation fails closed. The grade must meet `WORKBENCH_PROMPT_DEFENSE_MIN_GRADE` (`C` by default), and the resulting grade, vector coverage, missing vectors, and prompt hash are stored in promotion metadata. This gate checks defensive instruction quality; it does not grant authority or replace tool-time policy enforcement.

The behavioral runner materializes a Git fixture for each scenario and sends it through the same task, agent, governance, Docker, test, security, and evidence workflow used by normal work. Mechanical checks run first. LLM judging is limited to explicit rubric items that cannot be decided mechanically. Token counts are recorded when providers return them; Copilot costs use CLI billing metadata, while other paid providers require a trusted operator rate card.

## External evaluation adapters

Vally and Waza are active adapters behind a common runner contract. The API image includes `@microsoft/vally-cli` and the checksum-verifying official Waza binary installer. Each adapter generates its native specs from the same frozen dataset, uses the Copilot SDK executor, persists raw output under the evaluation evidence directory, and returns normalized scores, versions, latency, and evidence paths. Native Docker evidence remains mandatory because neither external tool's tool policy is a host/container sandbox.

Recommended lifecycle:

1. Generate candidate scenarios from agent purpose, capabilities, denied actions, and MCP declarations.
2. Human-review and version the dataset.
3. Execute it against an isolated fixture repository.
4. Apply deterministic checks first and an LLM judge only for rubric items that cannot be checked mechanically.
5. Compare against the currently promoted version, including regressions and confidence intervals.
6. Require policy thresholds and human approval before promotion.

Agent-to-tool routing should use only promoted agent versions and evaluation results for suites tagged to the requested tool/domain. Do not select solely by one aggregate score; enforce mandatory safety and capability constraints first, then rank eligible agents by task-relevant dimensions.
