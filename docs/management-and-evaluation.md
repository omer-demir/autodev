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
- Initial evaluation dataset seeds: `evaluations/suites/*.yaml`

Each built-in agent names a repo seed used only to create its initial dataset. The seed contains role-specific prompts, repository fixtures, deterministic checks, and semantic rubrics. Users edit and version datasets in the dataset UI; they never select or edit a suite during an evaluation run. Read-only scenarios use `task_mode: assessment`, require no repository changes, and can gate the final response with `checks.required_output_terms`; implementation and planning scenarios use `task_mode: change` plus executable fixture checks. The `baseline` seed remains a generic fallback for custom agents.

Agent definitions include a stable DID, semantic version, model binding, exact harness version, `policy` ID, capabilities, attached skill IDs, approval-required actions, denied actions, and allowed MCP server IDs. A harness pins its capability catalog and defines canonical tool schemas and capability bindings. Saving agent YAML always returns it to `status: draft`; manually writing `promoted` cannot bypass the behavioral gate. The effective decision is the intersection of the agent declaration and its selected governance policy; either side can deny an action. Policies are active immediately after saving, so review policy changes like code.

Agents require evaluation and promotion by default. An administrator may select **Allow without evaluation** for a draft agent and provide a reason; this writes `evaluation_required: false` plus approver, reason, and timestamp metadata into the Git-reviewable agent YAML. Such an agent can run immediately without being represented as evaluated or promoted. The override does not bypass identity verification, declared capabilities, governance policy, sandbox isolation, denied operations, or approval gates. Select **Require evaluation** to revoke it. Directly setting `evaluation_required: false` in a repository-managed declaration has the same runtime effect and therefore requires the same protected repository access and code review as other control-plane policy changes. Skills do not have an independent promotion lifecycle; they receive authority only through the agent that attaches them.

The Management page supports the runtime registries but does not expose dataset seeds as editable definitions. To evaluate an agent, create or update its declaration, select or create its governance policy, review and freeze a dataset version, select the agent and dataset independently on the Evaluations page, run native + Vally + Waza, and then select **Promote agent**. Native development edits the workspace files directly. The default Compose deployment embeds registries in the API and worker images; rebuild and recreate both services after repository edits. Management edits inside an image-backed API container are not durable across recreation and are not shared with a separate worker, so use repository commits and deployment reconciliation for deployed environments.

The MCP registry describes allowed servers and harness bindings. External clients can use the tenant-scoped Workbench gateway at `/gateway/mcp` or `/gateway/sse`; its session tools enforce the same authentication, RBAC, promoted-agent, pending-approval, and terminal-state rules as the REST API. Saving an MCP declaration does not execute arbitrary commands.

Executable workflow declarations assign one local agent DID to each stage and define responsibilities, context or artifact inputs, named outputs, dependencies, and handoff contents. Sequential workflows use list order. DAG workflows use `depends_on`; independent stages may run concurrently only when every assigned agent is read-only. Artifact inputs must come from an earlier sequential stage or a DAG dependency ancestor. Task creation fails closed unless the workflow is active and every assigned agent is promoted or has an administrator-approved evaluation bypass.

The built-in `ideation`, `design`, `planning`, and `implementation` recipes are active definitions, but their new specialist roles intentionally start as drafts. Evaluate and promote each assigned role before running its workflow. The legacy `sdlc` recipe remains available for the promoted developer agent.

Each non-primary stage receives a stage-scoped sandbox using its own declared image, network mode, workspace access, and pool profile. Stage sandboxes are removed after execution; the durable task keeps stage-attributed events, named handoff artifacts, workflow-run state, and the repository worktree. Write-capable stages remain sequential.

## Bring your own agents and skills

Management imports public HTTPS sources in GitHub Copilot `.agent.md` or Agent Skills `SKILL.md` format. GitHub blob links are converted to raw content, and `https://skills.sh/<owner>/<repo>/<skill>` is resolved to the repository's single matching `SKILL.md`. Imports are limited to 250 KB, use bounded timeouts and redirects, and reject credentials or hosts that resolve to private, loopback, link-local, or otherwise non-public addresses.

Imported content is instruction data, not execution authority. Agent imports are always saved as `draft` with a local DID, the development policy, the workspace harness, read-only repository capabilities, and explicit write/install/deploy/credential denials. Remote `tools`, `allowed-tools`, handoffs, model settings, scripts, and permissions are retained only as source provenance. Skill imports retain their instruction body and advisory metadata; they execute only when an operator adds the skill ID to a local agent's `skills` list. The governing system prompt, local agent declaration, harness, policy, sandbox, and approval gate always take precedence.

The built-in specialist roles adapt role boundaries from the MIT-licensed [GitHub Awesome Copilot](https://github.com/github/awesome-copilot) collection. [Awesome AI Agents](https://github.com/Jenqyang/Awesome-AI-Agents) and [Awesome Agents](https://github.com/kyrolabs/awesome-agents) were used only as discovery indexes. Every adapted declaration records this provenance, is locally constrained, and remains a draft until behavioral promotion.

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

Native development reads `agents/*.yaml` directly, so a valid saved file is visible to the next registry request, run, retry, and governed tool decision without an API restart. An invalid or partially written YAML file fails validation on the next read. A packaged deployment sees repository edits only when that directory is mounted into the running API and workers; image-embedded registries require an image rebuild/redeployment. In multi-process deployments, mount the same registry revision into every API and worker to avoid inconsistent execution.

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

The instant **Static declaration lint** is not an agent evaluation and does not call a model. It compares the YAML declaration's capabilities with required and forbidden capabilities, and its run provenance records `agent_executed: false`. It cannot satisfy the verified-result promotion requirement.

A real evaluation uses the **Frozen behavioral datasets** workflow: review and freeze scenario definitions, select the current agent and dataset independently, then run **Docker + Vally + Waza**. Repeated deterministic seed generation reuses an existing matching candidate instead of creating duplicate rows. Dataset JSON contains scenarios and fixtures only; those scenarios are hashed and immutable at freeze. At run time, Vally and Waza artifacts are generated from the selected agent version and frozen scenarios, preventing stale agent instructions from being embedded in the dataset. Native scenarios materialize evaluation-owned fixture repositories and invoke the selected governed agent directly in isolated Docker sandboxes. They do not create product projects, tasks, sessions, execution jobs, approvals, or task artifacts. Behavioral provenance records `agent_executed: true`, and only qualifying evidence can promote an agent.

## Evaluation run observability

The Evaluations page provides a run-detail experience modeled after experiment trackers such as MLflow. A running evaluation persists progress after every native scenario and external adapter, so the current adapter, current scenario, completed-step count, and partial adapter results remain visible before the run finishes. Run details are organized into:

- **Overview**: aggregate and per-adapter scores, progress, latency, tokens, safety, comparison, and immutable run configuration;
- **Live timeline**: durable run, adapter, scenario, model, tool, governance, judge, and failure events;
- **Model calls**: provider, resolved model, latency, input/output/cache/reasoning token counts, and fallback state when the provider reports them;
- **Tools**: ordered governed calls with capability, arguments, result excerpts, latency, and status;
- **Logs**: bounded, redacted Vally/Waza console excerpts and optional native model traces;
- **Artifacts**: generated evaluator specifications, candidate declarations, result files, and console files with size and bounded text previews.

The UI polls the durable run/event APIs while the run is active, and a run-scoped WebSocket is also available at `/api/evaluations/<run-id>/events/ws`. Historical events remain queryable at `/api/evaluations/<run-id>/events`; they are not dependent on Redis stream retention. Artifact previews are bounded and common GitHub token forms are redacted.

Running behavioral evaluations can be cancelled from the run inspector. Cancellation stops the owning asynchronous evaluation task, terminates active Vally/Waza process groups, closes the native runtime supervisor, and removes its evaluation sandbox. The run ends as `CANCELLED`, records a durable `evaluation.run.cancelled` event, and retains partial metrics, adapter results, logs, and artifacts produced before cancellation. Completed, failed, and already-cancelled runs cannot be cancelled.

Evaluation execution is currently owned by an in-process API task. In a horizontally scaled deployment, a cancellation request must reach the API replica that owns that task; otherwise the database run can be marked cancelled but remote process termination is not guaranteed. Move evaluation ownership and cancellation signaling to the durable execution queue before scaling behavioral runners across replicas.

Enable **Verbose LLM trace** only when exact native model prompts and responses are required. Verbose traces may contain source code, fixture content, model output, and other sensitive context. They are persisted with the evaluation event history. The default records model identity, usage, latency, tools, governance, summaries, tests, diffs, and evaluator logs without persisting dedicated prompt/response events.

Missing model usage or price data is displayed as unavailable rather than inferred. Vally and Waza expose the metrics present in their result formats plus process duration, exit status, record count, and raw console evidence; they do not fabricate token or cost values when the external evaluator does not report them.

External results are normalized to one score in the inclusive range 0–1 per scenario before adapter and run aggregation. Vally uses each `trial-result.gradeResult.score`; nested deterministic-grader and rubric-scale scores are supporting evidence and are not averaged again. Waza uses each result summary's aggregate score. The run score is the mean of the selected adapter scores, while run success separately requires every selected adapter to pass.

## Run evaluations with GitHub Copilot

Source-control GitHub OAuth is not a Copilot model credential. The API process, Vally, and Waza need an eligible GitHub Copilot account through either persistent Copilot CLI login state or `COPILOT_GITHUB_TOKEN`.

For native development:

1. Run `copilot login` as the same OS user that starts the API. The default `WORKBENCH_COPILOT_HOME=~/.copilot` reuses that login.
2. Set `WORKBENCH_EVALUATOR_PROVIDER=copilot` and `WORKBENCH_EVALUATOR_MODEL=auto` before starting the API. `auto` avoids selecting a model that the account cannot use.
3. Start the workbench with `make dev`.
4. Open `/api/runtime` and verify `active_model_provider` is `copilot`, `model_available` is true, and the model catalog contains Copilot models.
5. On the Evaluations page, select **GitHub Copilot**, use model `auto`, select a frozen dataset, and start the behavioral run.

Compose is a separate authentication boundary: it cannot read the dev-container user's `~/.copilot` directory. Choose one of these approaches:

1. **Persistent CLI login (preferred for an interactive local deployment):** start the API, then run `docker compose exec api sh -lc 'COPILOT_HOME=/data/copilot copilot login'`. The `/data/copilot` directory is in the persistent `workbench-data` volume. Recreate the API only if other environment settings changed.
2. **Token:** set `COPILOT_GITHUB_TOKEN` in the uncommitted repository `.env` file. The account behind the token must be entitled to Copilot. Never put the token in an evaluation prompt, dataset, source file, or evidence.

For a Copilot-backed Compose evaluation, set:

```text
WORKBENCH_EVALUATOR_PROVIDER=copilot
WORKBENCH_EVALUATOR_MODEL=auto
```

Then recreate the control-plane processes so they receive the settings:

```text
docker compose up -d --force-recreate api worker
```

Verify `/api/runtime` before launching a run. In the evaluation UI, explicitly select **GitHub Copilot** and `auto`; the run provenance must show `model_provider: copilot`. Native uses Agent Framework's Copilot agent directly. Vally uses its `copilot-sdk` executor, and Waza inherits the same process authentication chain. Do not set the Ollama `COPILOT_PROVIDER_*` overrides for a Copilot run.

For an authentication-path test, temporarily set `WORKBENCH_MODEL_FALLBACK_PROVIDER=none`. This prevents a product task from silently falling back to Ollama; behavioral evaluation providers are already explicit and fail rather than changing providers. Restore the fallback after verification if automatic task recovery is desired.

The evaluator provider and model are explicit evaluation inputs, independent from the evaluated agent's production model declaration. They default to `ollama` and `gemma4:e2b` and are stored in run provenance. Vally and Waza both use their `copilot-sdk` harness, but that does not imply hosted GitHub Copilot inference: the adapters explicitly route the harness to Ollama's OpenAI-compatible endpoint when Ollama is selected. Run provenance records the inference provider separately from the harness.

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

Promotion requires at least one dataset and a successful, verified `behavioral-v1` result for the current agent version through all three adapters: native Workbench Docker, Vally, and Waza. The result must reference a frozen dataset with the same organization, agent, agent version, suite, suite version, and SHA-256 content hash. The aggregate score must be at least 85%, safety must be 100%, and the candidate must not regress by more than 0.02 against the latest successful prior-version behavioral run. Missing or mismatched evidence blocks promotion; the system never fabricates a result for a draft agent.

Immediately before promotion, the API also renders the candidate's runtime system prompt with its attached local skills and policy budgets, then runs Microsoft Agent Governance Toolkit `PromptDefenseEvaluator`. Evaluation fails closed. The grade must meet `WORKBENCH_PROMPT_DEFENSE_MIN_GRADE` (`C` by default), and the resulting grade, vector coverage, missing vectors, and prompt hash are stored in promotion metadata. This gate checks defensive instruction quality; it does not grant authority or replace tool-time policy enforcement.

The behavioral runner materializes a Git fixture for each scenario and invokes the same governed agent tools, policy, runtime supervision, Docker boundary, tests, and security checks without entering the task/session subsystem. Mechanical checks run first. LLM judging is limited to explicit rubric items that cannot be decided mechanically. Token counts are recorded when providers return them; Copilot costs use CLI billing metadata, while other paid providers require a trusted operator rate card.

## External evaluation adapters

Vally and Waza are active adapters behind a common runner contract. The API image includes `@microsoft/vally-cli` and a pinned, checksum-verified Waza 0.38.10 binary. Waza 0.38.9 and newer are required with Copilot runtime 1.0.85 because they select the model at session creation instead of passing the removed runtime `--model` argument. Synthetic native specs are generated once with the dataset from the selected agent and suite versions. The adapters materialize those reviewed, frozen artifacts into the run evidence directory rather than reconstructing behavioral intent at execution time. Only provider and model transport fields are overlaid at run time, so environment-specific Ollama URLs and credentials are not frozen into customer-authored assets. Each adapter uses the Copilot SDK harness, persists raw output, and returns normalized scores, versions, latency, and evidence paths. Native Docker evidence remains mandatory because neither external tool's tool policy is a host/container sandbox.

For Vally, the canonical bundle contains one `<scenario>.eval.yaml` object and fixture per scenario plus the agent-specific `candidate.agent.md` evidence artifact. At execution these become `<evidence>/<run-id>/vally/<scenario>.eval.yaml`, `fixtures/<scenario>/`, and `candidate.agent.md`. Vally's standalone Copilot SDK session cannot switch to a discovered custom agent, so the frozen candidate profile is embedded in each stimulus and explicitly tells the executor to perform the task itself rather than delegate. The candidate file is retained for inspection but is not copied into `.github/agents` in the trial workspace. The spec is a capability evaluation with deterministic file and command graders. Dataset rubric items add a prompt judge with trajectory and repository evidence. With Ollama selected, both the executor and judge receive a run-time provider block pointing to `WORKBENCH_OLLAMA_URL` with `/v1` appended. The adapter runs the equivalent of:

```bash
vally eval \
	--eval-spec <scenario>.eval.yaml \
	--output-dir <evidence>/<run-id>/vally/results \
	--output jsonl --require-pass --workers 1
```

For Waza, the canonical bundle contains `<scenario>/eval.yaml`, `<scenario>/tasks/task.yaml`, `<scenario>/candidate.agent.md`, and `<scenario>/fixtures/<scenario-id>/`. At execution each scenario gets the corresponding `<evidence>/<run-id>/waza/<scenario>/` evidence directory plus `results.json` and `console.log`. Waza discovers the candidate as a custom agent, enforces its declared tool aliases, and materializes the fixture into a fresh task workspace. With Ollama selected, the adapter sets `COPILOT_PROVIDER_BASE_URL=<ollama-url>/v1`, `COPILOT_PROVIDER_TYPE=openai`, and `COPILOT_PROVIDER_WIRE_API=completions`, then runs the equivalent of:

```bash
waza run <scenario>/eval.yaml \
	--context-dir <scenario>/fixtures/<scenario-id> \
	--output <scenario>/results.json --no-cache
```

With Copilot selected, neither adapter sets a custom provider. Both receive the configured `WORKBENCH_COPILOT_HOME`; Vally also opts out of its default per-run empty Copilot home with `EVALUATE_USE_HOST_COPILOT_HOME=1`. This lets native development reuse the dev container's `~/.copilot` login and lets Compose reuse `/data/copilot`, while an inherited `COPILOT_GITHUB_TOKEN` remains supported. A missing OAuth token is therefore an authentication error only for a Copilot-backed run. For an Ollama-backed run, `Provider: custom (<ollama-host>)` in Waza evidence or a Vally provider block in the generated spec confirms correct routing. After execution starts, a missing file, failed command, or low judge score is a valid behavioral failure rather than an adapter authentication failure.

Recommended lifecycle:

1. Author representative scenarios and fixtures for the agent's actual role, then generate Vally/Waza artifacts from its purpose, capabilities, denied actions, MCP declarations, and suite checks.
2. Human-edit, review, and version the complete dataset bundle.
3. Execute it against an isolated fixture repository.
4. Apply deterministic checks first and an LLM judge only for rubric items that cannot be checked mechanically.
5. Compare against the currently promoted version, including regressions and confidence intervals.
6. Require policy thresholds and human approval before promotion.

Agent-to-tool routing should use only promoted agent versions and evaluation results for suites tagged to the requested tool/domain. Do not select solely by one aggregate score; enforce mandatory safety and capability constraints first, then rank eligible agents by task-relevant dimensions.
