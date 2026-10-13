#!/usr/bin/env bash
set -euo pipefail

git config --global --add safe.directory "${PWD}"

if [[ -d /mnt/host-ssh ]]; then
  install -d -m 700 "${HOME}/.ssh"
  find "${HOME}/.ssh" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  cp -a /mnt/host-ssh/. "${HOME}/.ssh/"
  find "${HOME}/.ssh" -type d -exec chmod 700 {} +
  find "${HOME}/.ssh" -type f -exec chmod 600 {} +
  find "${HOME}/.ssh" -type f -name '*.pub' -exec chmod 644 {} +
fi

if [[ -f package-lock.json ]]; then
  npm ci
fi

if [[ -f pyproject.toml ]]; then
  uv sync --all-extras --dev
fi

if [[ -f scripts/install-waza.sh ]]; then
  bash scripts/install-waza.sh
fi

printf '\nAgentic SDLC Workbench development environment\n'
printf '  Python: %s\n' "$(python --version 2>&1)"
printf '  Node:   %s\n' "$(node --version)"
printf '  npm:    %s\n' "$(npm --version)"
printf '  uv:     %s\n' "$(uv --version)"
printf '  Git:    %s\n' "$(git --version)"

if [[ -d "${HOME}/.ssh" ]]; then
  printf '  SSH:    host keys available with container permissions\n'
fi

if docker version >/dev/null 2>&1; then
  printf '  Docker: reachable\n'
else
  printf '  Docker: unavailable (start Docker Desktop, then rebuild the container)\n'
fi

if curl --fail --silent --max-time 2 "${OLLAMA_HOST}/api/version" >/dev/null 2>&1; then
  printf '  Ollama: reachable at %s\n' "${OLLAMA_HOST}"
else
  printf '  Ollama: not running at %s (optional for initial setup)\n' "${OLLAMA_HOST}"
fi