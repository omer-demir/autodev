FROM node:22-bookworm-slim AS node-tools
RUN npm install --global @microsoft/vally-cli@0.17.0 @github/copilot@1.0.85

FROM docker:29-cli AS docker-tools

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git && rm -rf /var/lib/apt/lists/*
COPY --from=docker-tools /usr/local/bin/docker /usr/local/bin/docker
COPY --from=node-tools /usr/local/bin/node /usr/local/bin/node
COPY --from=node-tools /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
	&& ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
	&& ln -s ../lib/node_modules/@microsoft/vally-cli/dist/index.js /usr/local/bin/vally \
	&& ln -s ../lib/node_modules/@github/copilot/npm-loader.js /usr/local/bin/copilot
COPY scripts/install-waza.sh /tmp/install-waza.sh
RUN bash /tmp/install-waza.sh /usr/local/bin \
	&& rm /tmp/install-waza.sh \
	&& docker --version \
	&& copilot --version \
	&& vally --version \
	&& waza --version
COPY pyproject.toml ./
COPY apps/api ./apps/api
COPY cli ./cli
COPY agents ./agents
COPY skills ./skills
COPY harnesses ./harnesses
COPY capability-catalogs ./capability-catalogs
COPY mcp ./mcp
COPY workflows ./workflows
COPY evaluations ./evaluations
COPY policies ./policies
COPY prompts ./prompts
COPY docker/sandbox/Dockerfile ./docker/sandbox/Dockerfile
RUN test -f agents/developer.yaml \
	&& test -f skills/rpi-orchestrator.yaml \
	&& test -f harnesses/workspace.yaml \
	&& test -f capability-catalogs/governance.yaml \
	&& test -f mcp/servers/workspace.yaml \
	&& test -f workflows/sdlc.yaml \
	&& test -f evaluations/suites/baseline.yaml \
	&& test -f prompts/agent-system.prompty \
	&& test -f prompts/coding-task.prompty \
	&& pip install --no-cache-dir .
ENV PYTHONPATH=/app/apps/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]