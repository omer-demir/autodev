FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ARG UV_VERSION=0.13.0

RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install --yes --no-install-recommends \
        curl \
        jq \
        make \
        ripgrep \
        shellcheck \
        sqlite3 \
    && curl --fail --location --silent --show-error \
        "https://astral.sh/uv/${UV_VERSION}/install.sh" \
        | env UV_UNMANAGED_INSTALL=/usr/local/bin sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER vscode