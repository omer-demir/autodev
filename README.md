---
title: AutoDev
description: Run and develop AutoDev, a governed software development workbench for coding agents.
---

AutoDev runs coding agents in isolated workspaces and governs their repository
tools, approvals, and publication actions. The project includes a web
application, API, durable worker, command-line client, and Docker-based task
sandboxes.

## Technology stack

* Python 3.11+, FastAPI, SQLModel, and Pydantic for the API and worker
* PostgreSQL for durable application state and Redis Streams for realtime events
* Next.js 16, React 19, TypeScript, and Tailwind CSS for the web application
* Microsoft Agent Framework with GitHub Copilot, Ollama, and optional Foundry Responses
* Docker or Azure Container Apps dynamic sessions for task execution
* GitHub App, OAuth, or scoped token integrations for repository access

## Prerequisites

* Python 3.11 or newer
* Node.js 22.12 or newer and npm
* Git and Docker with a running daemon
* A supported model provider: Ollama, GitHub Copilot, or Microsoft Foundry

The API controls task containers through the Docker socket. Use local Docker
development on a trusted machine.

## Run locally

Create a virtual environment, install dependencies, configure `.env`, and start
the application:

```bash
python3 -m venv .venv
make install
cp .env.example .env
make dev
```

`make dev` starts PostgreSQL, Redis, and local telemetry services through
Docker, then runs the API, web application, and worker natively. The Docker
workspace mapping is prepared automatically.

Open the web application at <http://localhost:3000>. The API health check is at
<http://localhost:8000/health>, and the OpenAPI interface is at
<http://localhost:8000/docs>.

## Run with Docker Compose

Prepare the workspace mount and start the services:

```bash
make docker-workspace
docker compose up --build --force-recreate
```

Compose starts the web application, API, worker, PostgreSQL, Redis, and
observability services. It does not start Ollama. For an Ollama server on the
host, set `WORKBENCH_OLLAMA_URL=http://host.docker.internal:11434` in `.env`.
Use `docker compose down` to stop the stack.

## Configure models and integrations

Copy `.env.example` to `.env` and set values for your environment. The sample
selects Ollama with `gemma4:e2b`; start Ollama and pull that model, or change
`WORKBENCH_MODEL_PROVIDER` and `WORKBENCH_MODEL_NAME`.

* For Ollama, configure `WORKBENCH_OLLAMA_URL` and install the selected model.
* For GitHub Copilot, authenticate the Copilot CLI or set
  `COPILOT_GITHUB_TOKEN`. Use `make dev-copilot` to run with the local
  `.copilot.env` profile.
* For Microsoft Foundry, set `WORKBENCH_MODEL_PROVIDER=foundry`,
  `WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT`, and `WORKBENCH_FOUNDRY_MODEL`.
  In the devcontainer, run `az login` and then `make dev`. This starts the API
  and worker in the devcontainer, where `DefaultAzureCredential` can use the
  Azure CLI login.
* Connect GitHub from the application for private repositories and publication.
  The token and OAuth settings in `.env` are compatibility options.
* Local authentication is the default. Configure the `WORKBENCH_OIDC_*`
  settings only when using an OIDC identity provider.

See [local setup](docs/local-setup.md) for provider configuration, GitHub
onboarding, Docker file sharing, and authentication details. Keep secrets in
`.env` or a secret manager, not in task messages or repository files.

## Development commands

Run the common checks from the repository root:

```bash
make test
make lint
make build
make doctor
```

`make test` runs the JavaScript workspace-mapping tests and the Python API
suite. `make lint` runs ESLint and Ruff. `make build` builds the web
application. `make doctor` checks local runtime readiness.

For focused processes, use `npm run dev:api`, `npm run dev:web`, or
`npm run dev:worker`. The worker requires durable execution dispatch and the
same database configuration as the API. Read the
[developer guide](DEVELOPMENT.md) for debugging, model setup, and targeted test
commands.

## Repository layout

* `apps/api/` contains the FastAPI application, worker, and API tests.
* `apps/web/` contains the Next.js application.
* `cli/` contains the `agentctl` command-line client.
* `agents/`, `skills/`, `policies/`, and related directories contain versioned
  runtime definitions.
* `docs/` contains setup, product, architecture, and operations documentation.
* `scripts/` contains local setup and validation utilities.

## Documentation

* [Local setup](docs/local-setup.md) for environment configuration and startup
* [Developer guide](DEVELOPMENT.md) for development and debugging
* [Features and how-to](docs/product/features-and-how-to.md) for product workflows
* [Architecture](docs/architecture.md) and [design deep dives](docs/design/README.md)
* [Architecture decision records](docs/adr/README.md)
* [Azure deployment](docs/azure-deployment.md)
* [Product documentation](docs/product/README.md)
* [Implementation story backlog](docs/stories/README.md)
