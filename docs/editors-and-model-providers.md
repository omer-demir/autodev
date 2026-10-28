# Editors and model providers

## Remote GitHub Copilot CLI and OpenCode

AutoDev exposes a standard MCP Streamable HTTP endpoint at:

```text
https://<api-host>/gateway/mcp
```

Register that URL as a remote MCP server in GitHub Copilot CLI or OpenCode and send the same OIDC bearer token used for the AutoDev API. For multi-organization users, also send `X-Organization-Id`. Local development uses the configured local principal and does not require a bearer token.

The server exposes tenant-scoped session tools and worker-owned workspace tools:

```text
sessions.list
sessions.get
sessions.continue
workspace.list_files
workspace.search_text
workspace.read_file
workspace.write_file
workspace.delete_file
workspace.run_command
```

Workspace calls are not executed by the API replica. Each call becomes a leased PostgreSQL job; a worker restores the latest Blob revision, creates an ephemeral Docker or Azure session, applies the existing agent capability policy and runtime supervision, executes the operation, checkpoints a new revision, and returns the execution job and revision IDs.

`workspace.run_command` accepts an argument array, not a shell string. The command classifier allows test, build, dependency installation, and read-only Git commands declared by the agent policy. Arbitrary shells and unclassified executables fail closed.

Connecting an MCP server does not intercept a client's own local terminal or built-in file tools. Configure the client or its agent instructions to use only the AutoDev `workspace.*` tools for repository actions. ACP session hosting remains the stronger future option for clients that support delegating their complete session runtime.

## Local VS Code

The **Open in VS Code** action runs `code -r <task-worktree>` from the API control plane. In the development container, the VS Code remote CLI opens the isolated `.workspaces/TASK-NNN/repo` folder in the current VS Code session. The `code` command must be available to the API process.

No repository credentials are passed to the task sandbox. VS Code extensions, including GitHub Copilot, run in the editor boundary using the user's normal VS Code authentication.

## Browser editor

The Workbench does not silently install or expose a browser IDE. Run a separately authenticated code-server or OpenVSCode Server instance, mount only `.workspaces`, and set:

```text
WORKBENCH_WEB_EDITOR_URL=http://localhost:8443/?folder={workspace}
```

`{workspace}` is replaced with the URL-encoded isolated task worktree. If the editor container uses a different mount path, configure its URL/routing layer so that path resolves correctly. Require editor authentication; never expose an unauthenticated editor or mount the Docker socket, host SSH directory, `.env`, or original repositories into it.

## Microsoft Foundry model provider

Set `WORKBENCH_MODEL_PROVIDER=foundry`,
`WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT`, and `WORKBENCH_FOUNDRY_MODEL` in the
project's `.env`. The devcontainer installs Azure CLI. Authenticate and start
development from its terminal:

```bash
az login
make dev
```

The API uses `DefaultAzureCredential`, whose credential chain includes the
Azure CLI identity from `az login`. The signed-in account must have permission
to invoke the deployed model. `make dev` runs the API and worker directly in
the devcontainer, where they can access the Azure CLI credentials.

The API and worker started by `docker compose up` are separate containers and
cannot see the devcontainer's Azure CLI login. Configure an identity for those
containers if you run them directly through Compose instead of `make dev`.

The chat model picker includes `WORKBENCH_FOUNDRY_MODEL` and any additional
comma-separated deployments in `WORKBENCH_FOUNDRY_MODELS`, for example
`gpt-6-sol,gpt-6.1-sol`. The default model remains available even if it is not
repeated in that list.

To add Anthropic models deployed in the same Microsoft Foundry resource, set
`WORKBENCH_FOUNDRY_ANTHROPIC_ENDPOINT` to the Messages API URL, such as
`https://<resource>.services.ai.azure.com/anthropic/v1/messages`. The base
`https://<resource>.services.ai.azure.com/anthropic` URL is also accepted. Set
`WORKBENCH_FOUNDRY_ANTHROPIC_MODEL` to the default deployment and optionally
list additional deployment names in the comma-separated
`WORKBENCH_FOUNDRY_ANTHROPIC_MODELS`. The chat model picker shows the Anthropic
deployments alongside Foundry Responses models. Repository-free chats let you
select a provider and deployment independently for each message. Repository
tasks continue to use their configured task model and do not support switching
providers per message.

If Anthropic is your only configured Foundry API, set
`WORKBENCH_MODEL_PROVIDER=foundry-anthropic` and
`WORKBENCH_MODEL_NAME` to the default Anthropic deployment.

The Anthropic Messages API uses the same Azure CLI sign-in and Entra ID scope as
the Foundry Responses API. AutoDev supports text, images, and PDF attachments
with these models. Audio transcription, native web search, and image-generation
tools are currently available only through the Foundry Responses API.

Foundry Responses chats and agent runs expose the native `web_search` tool. The
model decides whether to call it, and its inline citations are returned in the
chat response. Foundry routes searches through Grounding with Bing; Microsoft
states that search data flows outside compliance and geographic boundaries
and that usage can incur costs. See the [Foundry web-search documentation](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/web-search).

Repository-free chats stream generated text as it arrives for Foundry, Copilot,
and Ollama models. Repository-backed chats continue through the governed task
workflow and display its progress events.

Assistant messages show provider/model, input and output token counts, and an
estimated USD cost when a rate card is configured. Set
`WORKBENCH_MODEL_PRICING_JSON` to a JSON object keyed by
`foundry/<deployment-name>` or
`foundry-anthropic/<deployment-name>` with numeric `input_per_million_usd` and
`output_per_million_usd` rates. Optional cache-rate fields are
`cache_read_per_million_usd` and `cache_write_per_million_usd`. Foundry costs
vary by model and deployment, so AutoDev does not assume a price; token usage
remains visible when no matching rate is configured.

Image generation is optional. To enable it, deploy an image-generation model in
the same Foundry resource and set
`WORKBENCH_FOUNDRY_IMAGE_GENERATION_DEPLOYMENT` in `.env` to that deployment's
name. AutoDev then advertises the image-generation tool and lets the model
decide whether to call it. Without this setting, the tool is not sent.
Foundry requires the deployment name in the
`x-ms-oai-image-generation-deployment` request header; see the [Responses API
image-generation documentation](https://learn.microsoft.com/azure/ai-services/openai/how-to/responses?tabs=python-secure#image-generation).

For a separate Copilot profile, keep the settings in `.copilot.env` and run
`make dev-copilot`. This loads that file into the development processes without
replacing the Foundry settings in `.env`.

## GitHub Copilot agent provider

The existing GitHub repository OAuth connection is not automatically a model-provider credential. Keep source-control authorization and model-provider authorization separate.

Microsoft Agent Framework's official GitHub Copilot integration embeds the Copilot CLI agent runtime. It supports the models available through Copilot CLI, custom tools and MCP, permission handlers, sessions, middleware, and OpenTelemetry. Standard usage requires an eligible GitHub Copilot subscription and consumes the user's Copilot allowance.

`AgentRuntime` uses `GitHubCopilotAgent` in the control plane. It:

1. Uses Microsoft Agent Framework directly, without a Workbench model-provider abstraction.
2. Runs in the control plane, never in the task sandbox.
3. Uses persistent Copilot CLI sign-in state or `COPILOT_GITHUB_TOKEN`.
4. Enumerates available models at runtime; `auto` lets the SDK choose its default.
5. Exposes only Agent Framework function tools and denies unexpected Copilot built-in permission requests.
6. Disables repository-defined Copilot file hooks and invokes the existing governance and sandbox boundary inside every tool.
7. Uses Agent Framework sessions, usage reporting, middleware, and OpenTelemetry.
8. Treats final assistant content as natural-language text rather than parsing it as a tool-call envelope.
9. Optionally records the exact conversation prompt and raw final response when a task enables verbose tracing.

This separation follows the provider-native protocol: tool identity, typed arguments, results, and parallel calls travel through SDK events; user-facing prose remains prose. Structured output is still appropriate for typed business results such as evaluation scores, but it is not used to emulate tool calling.

Ollama is retained as the proving/fallback provider and is not the default.

### Run one task through Agent Framework

If `make dev` runs the API directly as the same OS user that ran `copilot login`, no token copy is needed. Native development now defaults `WORKBENCH_COPILOT_HOME` to `~/.copilot`, and the SDK uses the stored CLI login automatically. Use these non-secret settings for a strict test:

```text
WORKBENCH_MODEL_PROVIDER=copilot
WORKBENCH_MODEL_NAME=auto
WORKBENCH_MODEL_FALLBACK_PROVIDER=none
```

Then restart `make dev` and check <http://localhost:8000/api/runtime>.

Compose is a separate authentication boundary. The API process runs in a container and uses `/data/copilot` in the `workbench-data` Docker volume; it cannot see the VS Code/dev-container user's `~/.copilot` login. For Compose, authenticate that persistent container-side Copilot home or provide an SDK-supported token. If using the token path, put these values in the repository `.env` file. Enter the token locally; never paste it into task text, chat, source files, or evidence.

```text
WORKBENCH_MODEL_PROVIDER=copilot
WORKBENCH_MODEL_NAME=auto
WORKBENCH_MODEL_FALLBACK_PROVIDER=none
COPILOT_GITHUB_TOKEN=<token supported by Copilot SDK for an entitled account>
```

Recreate the API service so it receives the environment:

```text
docker compose up -d --force-recreate api
```

Open <http://localhost:8000/api/runtime>. Before creating the task, verify:

- `model_provider` and `active_model_provider` are `copilot`;
- `model_fallback_active` is `false`;
- `model_available` is `true`;
- `models` contains Copilot model entries.

Create a task in the UI and select `auto`, or select one of the reported Copilot model IDs. The task timeline records each successful completion as `copilot · <model>` and includes `provider: copilot` in event data. In strict mode, authentication or SDK errors fail the task instead of silently using Ollama, making this a valid SDK-path test.

After the test, restore `WORKBENCH_MODEL_FALLBACK_PROVIDER=ollama` and recreate the API if automatic fallback is desired. Provider selection is currently control-plane-wide; the model ID is task-specific.

Official framework: <https://github.com/microsoft/agent-framework>
