.PHONY: dev dev-copilot dev-infra docker-workspace install test lint build security doctor platform-up platform-down platform-scale azure-session-image

install:
	npm install
	.venv/bin/pip install -e ".[dev]"
	bash scripts/install-waza.sh

docker-workspace:
	node scripts/configure-docker-workspace.mjs

dev-infra: docker-workspace
	docker compose stop api web worker
	docker compose up -d --wait postgres redis otel-collector prometheus
	@if docker inspect "$$(hostname)" >/dev/null 2>&1; then \
		docker network connect autodev_control "$$(hostname)" 2>/dev/null || true; \
	fi

dev: dev-infra
	@if docker inspect "$$(hostname)" >/dev/null 2>&1; then \
		OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
		WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
		WORKBENCH_DATABASE_URL=postgresql+psycopg://autodev:autodev-local@postgres:5432/autodev \
		WORKBENCH_REDIS_URL=redis://redis:6379/0 \
		WORKBENCH_AGENT_IDENTITY_DIR=.workspaces/.agentmesh npm run dev; \
	else \
		OTEL_EXPORTER_OTLP_ENDPOINT=$${WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4318} \
		WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT=$${WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4318} npm run dev; \
	fi

dev-copilot:
	.venv/bin/python -c 'import os, sys; from dotenv import dotenv_values; env = {**os.environ, **{key: value for key, value in dotenv_values(".copilot.env").items() if value is not None}}; env.pop("WORKBENCH_DOCKER_WORKSPACE_HOST", None); os.execvpe(sys.argv[1], [sys.argv[1], "dev"], env)' $(MAKE)

test:
	node --test scripts/configure-docker-workspace.test.mjs
	.venv/bin/pytest

lint:
	npm run lint
	.venv/bin/ruff check apps/api cli

build:
	npm run build

security:
	semgrep scan --config auto .
	trivy fs .
	gitleaks detect --source .

doctor:
	PYTHONPATH=apps/api:cli .venv/bin/python -m agentctl.main doctor

platform-up: docker-workspace
	docker compose up -d --build

platform-down:
	docker compose down

platform-scale: docker-workspace
	docker compose up -d --scale worker=4

azure-session-image:
	docker build -f docker/azure-session/Dockerfile -t autodev-session:local .