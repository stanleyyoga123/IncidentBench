#!/usr/bin/env bash
set -euo pipefail

readonly PLATFORM="${PLATFORM:-linux/amd64}"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
source "$ROOT_DIR/deployment/image_config.sh"
validate_image_settings
readonly IMAGE="$(image_ref "evaluation")"

docker buildx build \
  --platform "${PLATFORM}" \
  --push \
  --file "${SCRIPT_DIR}/../Dockerfile" \
  --tag "${IMAGE}" \
  "${ROOT_DIR}"
