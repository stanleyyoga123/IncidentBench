#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT_DIR/deployment/image_config.sh"
validate_image_settings

readonly IMAGE="$(image_ref "mcp-tools")"
readonly PLATFORM="${PLATFORM:-linux/amd64}"

docker buildx build \
  --platform "${PLATFORM}" \
  --push \
  --tag "${IMAGE}" \
  "${SCRIPT_DIR}"
