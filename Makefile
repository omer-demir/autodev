.PHONY: dev install test lint build security doctor azure-session-image

install:
	npm install
	.venv/bin/pip install -e ".[dev]"

dev:
	npm run dev

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

azure-session-image:
	docker build -f docker/azure-session/Dockerfile -t autodev-session:local .