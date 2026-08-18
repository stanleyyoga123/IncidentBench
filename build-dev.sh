#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
declare -ar COMPONENTS=(
  "MCPTools"
  "RCAAgent"
  "RemediatorAgent"
  "AgentOrchestrator"
  "AnomalyDetector"
)

usage() {
  echo "Usage: $0"
  echo
  echo "Builds and pushes the five agent :dev images. Does not deploy, restart"
  echo "workloads, or run DatabaseJob. Use ./restart-dev.sh after a successful push."
}

if (( $# != 0 )); then
  usage >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is required." >&2
  exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
  echo "Error: Docker Buildx is required to build and push the agent images." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is unavailable. Start Docker and authenticate to Docker Hub." >&2
  exit 1
fi

for component in "${COMPONENTS[@]}"; do
  script_path="${ROOT_DIR}/${component}/build.sh"
  if [[ ! -f "${script_path}" ]]; then
    echo "Error: required component script not found: ${script_path}" >&2
    exit 1
  fi
  if [[ ! -x "${script_path}" ]]; then
    echo "Error: required component script is not executable: ${script_path}" >&2
    exit 1
  fi
done

for component in "${COMPONENTS[@]}"; do
  echo "==> Building and pushing ${component}"
  (cd "${ROOT_DIR}/${component}" && ./build.sh) || {
    status=$?
    echo "Error: building and pushing ${component} failed (exit status ${status})." >&2
    exit "${status}"
  }
done

echo "All five agent dev images were built and pushed."
echo "DatabaseJob was not run. Deployments were not restarted; run ./restart-dev.sh to pull the new images."
