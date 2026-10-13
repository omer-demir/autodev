# Local setup

## Native development

1. Use Python 3.11 or newer. Native Vally integration additionally requires Node.js 22.12 or newer; the Compose image includes it.
2. Create `.venv` and install the project with `pip install -e ".[dev]"`.
3. Run `npm install`.
4. Run `make dev` and open <http://localhost:3000>.

`make dev` starts Docker PostgreSQL and Redis, then runs the API, web server,
and durable worker natively. The API and worker share PostgreSQL execution jobs;
Redis Streams carries realtime event invalidations. It stops Compose API, web,
and worker containers first so two control planes or workers do not compete.
When VS Code runs in the included Docker-outside-of-Docker dev container,
`make dev` joins that container to the Compose `control` network. Set the
database and Redis hosts to `postgres` and `redis` in the dev container's
`.env`; use the published `127.0.0.1` ports when running the apps directly on
the Docker host.

The default is real local mode with GitHub Copilot first and Ollama as a fallback. For Compose, set `COPILOT_GITHUB_TOKEN` to a token with Copilot access, or authenticate the Copilot CLI using the persistent `WORKBENCH_COPILOT_HOME`. For Ollama fallback, use `http://127.0.0.1:11434` when the API runs directly on the host and `http://host.docker.internal:11434` in Compose.

Every task has two locations:

- Host/control-plane worktree: `.workspaces/TASK-NNN/repo`
- Docker path: `/workspace/project`

These are the same files: the first path is a persistent, isolated task clone and the second is its read-write bind-mount location inside the disposable sandbox container. It is intentionally not a Docker named volume because VS Code and the control plane need direct access to the resulting Git worktree. The original connected checkout is never mounted or modified.

The task Terminal tab shows both the worktree and Docker container ID. **Open in VS Code** asks the local VS Code CLI to open the isolated worktree. For a browser editor, run a separately authenticated code-server or OpenVSCode Server instance and set `WORKBENCH_WEB_EDITOR_URL`, optionally using `{workspace}` as the isolated-path placeholder. See [editors and model providers](editors-and-model-providers.md).

## GitHub onboarding

Paste a URL such as `https://github.com/owner/repository` to connect a public repository without credentials.

## GitHub App integration

The recommended integration is created from the **Connections** page. It removes the need to manually copy GitHub App values into `.env`, mount users' SSH directories for HTTPS transport, or share personal access tokens. GitHub attributes installation-token API operations to `<app-slug>[bot]`; AutoDev separately records the task requester and publication approver in the PR body and audit events.

1. Open **Connections → Create connection** and select GitHub.
2. Enter a friendly connection name. AutoDev adds a random suffix to the GitHub App registration because GitHub App names are globally unique across GitHub. Optionally enter a GitHub organization when the organization, rather than your personal account, should own the private app.
3. Continue to GitHub and sign in. AutoDev submits an official GitHub App Manifest containing the callback URLs and permissions. Review and create the app on GitHub.
4. GitHub returns the generated App ID, client ID, client secret, private key, and webhook secret directly to the callback. AutoDev encrypts secrets with `WORKBENCH_CREDENTIAL_MASTER_KEY` and stores the configuration in the database; plaintext credentials are not returned to the browser or written to `.env`.
5. Back on **Connections**, select **Install on GitHub**, choose the account and repositories AutoDev may manage, and authorize the installation.
6. Open **Repositories → Add GitHub repository**, select the connection and installed account, search the repository typeahead, choose SSH or HTTPS transport, and add it.

The manifest requests **Contents: Read and write**, **Workflows: Read and write**, **Pull requests: Read and write**, **Actions: Read-only**, **Checks: Read-only**, and **Metadata: Read-only**. It requests no organization permissions and disables webhook events. AutoDev uses the temporary installation user token only to verify that the callback's installation is accessible to the installing user, then discards it.

AutoDev signs a short-lived app JWT from the encrypted database credential, requests a token restricted to the target repository and operation, and discards that installation token after clone, push, or PR creation. Installation tokens expire after one hour and are not persisted. Back up the database and credential master key together; losing the master key makes encrypted connector credentials unrecoverable.

SSH is the default selectable Git transport and requires a usable SSH agent or key in the control plane. HTTPS uses just-in-time GitHub App installation tokens and requires no user SSH key. Pull-request and future GitHub API operations use the selected connection regardless of Git transport.

Repositories can be removed from **Repositories**. Removal permanently deletes every attached task and its AutoDev-owned history, artifacts, workspaces, snapshots, and evidence; it does not delete the source repository from its provider. Active tasks must be cancelled before their repository can be removed.

GitHub callbacks use `WORKBENCH_WEB_APP_URL` with an `/api/...` path so browser authentication and state cookies remain on one origin. Keep the web application's `/api` proxy enabled. Do not mix `localhost` and `127.0.0.1` in the browser-facing URL: browsers treat them as different cookie hosts.

Commits use `<app-slug>[bot]` and GitHub's bot noreply address. Commit trailers include the AutoDev task and requester. Pull-request bodies include the task, requester, approving user, and agent. This gives GitHub a stable automation identity while preserving human accountability in AutoDev.

For deployment-managed compatibility, the `WORKBENCH_GITHUB_APP_ID`, `WORKBENCH_GITHUB_APP_SLUG`, `WORKBENCH_GITHUB_APP_CLIENT_ID`, `WORKBENCH_GITHUB_APP_CLIENT_SECRET`, and private-key settings remain supported. New installations should use the database-backed Connections flow.

### Legacy OAuth and token fallback

For the legacy **Connect GitHub** flow, register a GitHub OAuth App once for the Workbench deployment:

1. In GitHub, open **Settings → Developer settings → OAuth Apps → New OAuth App**.
2. Use `http://localhost:3000` as the homepage URL.
3. Use `http://localhost:8000/api/connectors/github/oauth/callback` as the authorization callback URL.
4. Put its client ID and client secret in `.env` as `WORKBENCH_GITHUB_OAUTH_CLIENT_ID` and `WORKBENCH_GITHUB_OAUTH_CLIENT_SECRET`.
5. Restart the API. Users can now select **Connect GitHub**, authorize access, and browse repositories available to that account.

The default OAuth scope is `read:user repo`, because cloning private repositories requires repository access. OAuth credentials are encrypted by the configured credential provider and are never passed into task sandboxes.

For unattended compatibility, `WORKBENCH_GITHUB_TOKEN` accepts a fine-grained personal access token. Restrict it to selected repositories. Read-only **Contents** and **Metadata** access is sufficient for discovery and cloning; token-authenticated publication also requires **Contents: Read and write**, and pull-request creation requires **Pull requests: Read and write**. Do not place credentials in task text.

Native development can still publish a branch with a local SSH key when no GitHub App, token, or OAuth credential is configured. GitHub projects are cloned over HTTPS, but publication uses `git@github.com:owner/repository.git` as the push-only URL. SSH authenticates Git pushes only; creating a pull request requires the GitHub App, legacy OAuth, or `WORKBENCH_GITHUB_TOKEN`.

## OIDC browser login

Set `WORKBENCH_AUTH_MODE=oidc` and configure issuer, audience, JWKS, authorization, token, client ID, client secret, and redirect URI values shown in `.env.example`. Register `http://localhost:3000/api/auth/callback` for native development. Set `WORKBENCH_SESSION_COOKIE_SECURE=false` only for local HTTP; hosted deployments must use HTTPS and leave it `true`.

The browser starts at `/login`. The callback creates an opaque session cookie and redirects to `WORKBENCH_WEB_APP_URL`. Admin users manage organization roles at `/admin`. Bearer authentication remains available for the CLI and external MCP clients.

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
