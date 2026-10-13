#!/usr/bin/env bash
set -euo pipefail

version="0.38.10"
destination="${1:-${HOME}/.local/bin}"
architecture="$(uname -m)"

case "${architecture}" in
  x86_64|amd64)
    artifact="waza-linux-amd64"
    checksum="fae469af3b20ca63b789ad64e8f2c007a069d0843cc88d9e83d224de4f7077b3"
    ;;
  aarch64|arm64)
    artifact="waza-linux-arm64"
    checksum="0371e7d31da4aa9d5ddf4558ea3cd41490c7a4ca7d14ca4f13f842e99770e829"
    ;;
  *)
    printf 'Unsupported Waza architecture: %s\n' "${architecture}" >&2
    exit 1
    ;;
esac

mkdir -p "${destination}"
temporary="$(mktemp)"
trap 'rm -f "${temporary}"' EXIT
curl --fail --location --silent --show-error \
  "https://github.com/microsoft/waza/releases/download/v${version}/${artifact}" \
  --output "${temporary}"
printf '%s  %s\n' "${checksum}" "${temporary}" | sha256sum --check --status
install -m 0755 "${temporary}" "${destination}/waza"
"${destination}/waza" --version
