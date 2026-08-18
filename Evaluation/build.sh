#!/usr/bin/env bash
set -euo pipefail

readonly IMAGE="stanleyyoga123/evaluation:dev"
readonly PLATFORM="${PLATFORM:-linux/amd64}"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

docker buildx build \
  --platform "${PLATFORM}" \
  --push \
  --file "${SCRIPT_DIR}/Dockerfile" \
  --tag "${IMAGE}" \
  "${ROOT_DIR}"
