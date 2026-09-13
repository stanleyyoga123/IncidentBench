#!/usr/bin/env bash
set -euo pipefail

readonly IMAGE="stanleyyoga123/agent-orchestrator:dev"
readonly PLATFORM="${PLATFORM:-linux/amd64}"

docker buildx build \
  --platform "${PLATFORM}" \
  --push \
  --tag "${IMAGE}" \
  .
