# Local setup

## Native development

1. Use Python 3.11 or newer. Native Vally integration additionally requires Node.js 22.12 or newer; the Compose image includes it.
2. Create `.venv` and install the project with `pip install -e ".[dev]"`.
3. Run `npm install`.
4. Run `npm run dev` and open <http://localhost:3000>.

The default is real local mode with GitHub Copilot first and Ollama as a fallback. For Compose, set `COPILOT_GITHUB_TOKEN` to a token with Copilot access, or authenticate the Copilot CLI using the persistent `WORKBENCH_COPILOT_HOME`. For Ollama fallback, use `http://127.0.0.1:11434` when the API runs directly on the host and `http://host.docker.internal:11434` in Compose.

Every task has two locations:

- Host/control-plane worktree: `.workspaces/TASK-NNN/repo`
- Docker path: `/workspace/project`

These are the same files: the first path is a persistent, isolated task clone and the second is its read-write bind-mount location inside the disposable sandbox container. It is intentionally not a Docker named volume because VS Code and the control plane need direct access to the resulting Git worktree. The original connected checkout is never mounted or modified.

The task Terminal tab shows both the worktree and Docker container ID. **Open in VS Code** asks the local VS Code CLI to open the isolated worktree. For a browser editor, run a separately authenticated code-server or OpenVSCode Server instance and set `WORKBENCH_WEB_EDITOR_URL`, optionally using `{workspace}` as the isolated-path placeholder. See [editors and model providers](editors-and-model-providers.md).

## GitHub onboarding

Paste a URL such as `https://github.com/owner/repository` to connect a public repository without credentials.

For the **Connect GitHub** button, register a GitHub OAuth App once for the Workbench deployment:

1. In GitHub, open **Settings → Developer settings → OAuth Apps → New OAuth App**.
2. Use `http://localhost:3000` as the homepage URL.
3. Use `http://localhost:8000/api/connectors/github/oauth/callback` as the authorization callback URL.
4. Put its client ID and client secret in `.env` as `WORKBENCH_GITHUB_OAUTH_CLIENT_ID` and `WORKBENCH_GITHUB_OAUTH_CLIENT_SECRET`.
5. Restart the API. Users can now select **Connect GitHub**, authorize access, and browse repositories available to that account.

The default OAuth scope is `read:user repo`, because cloning private repositories requires repository access. OAuth access tokens are held only in API process memory and disappear on restart. They are never stored in SQLite or passed into task sandboxes.

For unattended local use, `WORKBENCH_GITHUB_TOKEN` accepts a fine-grained personal access token. Restrict it to selected repositories with read-only **Contents** and **Metadata** access. For a multi-user or hosted deployment, prefer a GitHub App: installation-scoped permissions and short-lived installation tokens provide stronger isolation than either OAuth Apps or personal access tokens. Do not place credentials in task text.

## Containers

Run `docker compose up --build --force-recreate`, then open <http://localhost:3000>. The API image contains Docker CLI, Microsoft Agent Framework's Copilot and Ollama integrations, Vally, and Waza; the Docker socket is mounted from the host.

If a task reports `[Errno 2] No such file or directory: 'docker'`, the API container predates the Docker CLI image layer. Rebuild **and recreate** it:

```text
docker compose down
docker compose up --build --force-recreate
```

Check `/api/runtime`: `docker.cli`, `docker.daemon`, and `docker.ready` must all be true before starting a task. A mounted socket without the CLI, or a CLI without daemon access, is reported separately.

For Azure Container Apps dynamic sessions, use the tested custom image and Bicep deployment in [Azure session deployment](azure-deployment.md). Azure mode synchronizes the persisted host worktree around each remote command and uses the same governed tool runtime as Docker mode.

## CLI

With `PYTHONPATH=apps/api:cli`, run `python -m agentctl.main doctor`, `runtime`, `sessions list`, `sessions continue TASK-001 "Follow up"`, `publication request TASK-001 --branch feature/task-001`, or `gateway status`. The CLI controls the same API; it contains no workflow business logic.

For OIDC deployments, set `WORKBENCH_ACCESS_TOKEN` and `WORKBENCH_ORGANIZATION_ID`. A separate terminal UI is intentionally not shipped: the browser application already provides the live timeline and management views, while `agentctl` covers scripted and terminal operations without duplicating workflow behavior.
