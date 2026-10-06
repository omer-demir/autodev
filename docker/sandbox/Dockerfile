FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl python3 python3-pytest && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 sandbox
WORKDIR /workspace/project
USER sandbox
CMD ["sleep", "infinity"]