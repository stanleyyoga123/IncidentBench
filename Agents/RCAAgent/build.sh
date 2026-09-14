#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

readonly IMAGE="stanleyyoga123/rca-agent:dev"
readonly PLATFORM="${PLATFORM:-linux/amd64}"

docker buildx build \
  --platform "${PLATFORM}" \
  --push \
  --tag "${IMAGE}" \
  "${SCRIPT_DIR}"
