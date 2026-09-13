#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  echo "Usage: $0"
  echo
  echo "Builds, pushes, and deploys the six agent-platform components using kubectl's"
  echo "current context. Database migrations remain a separate DatabaseJob workflow."
}

if (( $# != 0 )); then
  usage >&2
  exit 2
fi

declare -ar COMPONENTS=(
  "Agents/MCPTools"
  "Agents/LearningAgent"
  "Agents/RCAAgent"
  "Agents/RemediatorAgent"
  "EvaluationPlatform/Orchestrator"
  "Agents/AnomalyDetector"
)

for command in docker kubectl; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Error: required command not found: ${command}" >&2
    exit 1
  fi
done

if ! docker buildx version >/dev/null 2>&1; then
  echo "Error: Docker Buildx is required to build and push the agent images." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is unavailable. Start Docker and authenticate to Docker Hub." >&2
  exit 1
fi

context="$(kubectl config current-context 2>/dev/null || true)"
if [[ -z "${context}" ]]; then
  echo "Error: kubectl has no current context." >&2
  exit 1
fi

for namespace in agents utility online-boutique; do
  if ! kubectl get namespace "${namespace}" >/dev/null 2>&1; then
    echo "Error: namespace '${namespace}' is unavailable in current context '${context}'." >&2
    exit 1
  fi
done

for component in "${COMPONENTS[@]}"; do
  for script in build.sh deploy.sh; do
    script_path="${ROOT_DIR}/${component}/${script}"
    if [[ ! -f "${script_path}" ]]; then
      echo "Error: required component script not found: ${script_path}" >&2
      exit 1
    fi
    if [[ ! -x "${script_path}" ]]; then
      echo "Error: required component script is not executable: ${script_path}" >&2
      exit 1
    fi
  done
done

for component in "${COMPONENTS[@]}"; do
  echo "==> Building and pushing ${component}"
  (cd "${ROOT_DIR}/${component}" && ./build.sh) || {
    status=$?
    echo "Error: building and pushing ${component} failed (exit status ${status})." >&2
    exit "${status}"
  }
done

for component in "${COMPONENTS[@]}"; do
  echo "==> Deploying ${component} to context ${context}"
  (cd "${ROOT_DIR}/${component}" && ./deploy.sh) || {
    status=$?
    echo "Error: deploying ${component} failed (exit status ${status})." >&2
    exit "${status}"
  }
done

echo "All six agent-platform dev images were built, pushed, and deployed to context ${context}."
echo "DatabaseJob was not run; execute migrations separately and explicitly."
