FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install --yes --no-install-recommends \
        jq \
        make \
        ripgrep \
        shellcheck \
        sqlite3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER vscode