.PHONY: dev dev-infra install test lint build security doctor platform-up platform-down platform-scale azure-session-image

install:
	npm install
	.venv/bin/pip install -e ".[dev]"
	bash scripts/install-waza.sh

dev-infra:
	docker compose stop api web worker
	docker compose up -d --wait postgres redis otel-collector prometheus
	@if docker inspect "$$(hostname)" >/dev/null 2>&1; then \
		docker network connect autodev_control "$$(hostname)" 2>/dev/null || true; \
	fi

dev: dev-infra
	@if docker inspect "$$(hostname)" >/dev/null 2>&1; then \
		OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
		WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 npm run dev; \
	else \
		OTEL_EXPORTER_OTLP_ENDPOINT=$${WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4318} \
		WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT=$${WORKBENCH_OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4318} npm run dev; \
	fi

test:
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

platform-up:
	docker compose up -d --build

platform-down:
	docker compose down

platform-scale:
	docker compose up -d --scale worker=4

azure-session-image:
	docker build -f docker/azure-session/Dockerfile -t autodev-session:local .