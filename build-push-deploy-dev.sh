#!/usr/bin/env bash
set -Eeuo pipefail

readonly DOCKERHUB_NAMESPACE="stanleyyoga123"
readonly IMAGE_TAG="dev"
readonly KUBE_NAMESPACE="agents"
readonly PLATFORM="${PLATFORM:-linux/amd64}"
readonly ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-5m}"
readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  echo "Usage: $0 <kubernetes-context>"
  echo
  echo "Builds and pushes the five agent images as stanleyyoga123/*:dev,"
  echo "then updates and restarts their existing Deployments in namespace agents."
}

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 2
fi

readonly KUBE_CONTEXT="$1"

for command in docker kubectl; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command not found: ${command}" >&2
    exit 1
  fi
done

if ! docker buildx version >/dev/null 2>&1; then
  echo "Docker Buildx is required to build and push ${PLATFORM} images." >&2
  exit 1
fi

context_found=false
while IFS= read -r context; do
  if [[ "${context}" == "${KUBE_CONTEXT}" ]]; then
    context_found=true
    break
  fi
done < <(kubectl config get-contexts -o name)

if [[ "${context_found}" != "true" ]]; then
  echo "Kubernetes context does not exist: ${KUBE_CONTEXT}" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is unavailable. Start Docker and authenticate to Docker Hub." >&2
  exit 1
fi

if ! kubectl --context "${KUBE_CONTEXT}" get namespace "${KUBE_NAMESPACE}" >/dev/null 2>&1; then
  echo "Namespace ${KUBE_NAMESPACE} is unavailable in context ${KUBE_CONTEXT}." >&2
  exit 1
fi

declare -a DEPLOYMENTS=(
  "mcp-tools-investigation"
  "mcp-tools-remediation"
  "rca-agent"
  "remediator-agent"
  "agent-orchestrator"
  "anomaly-detector"
)

for deployment in "${DEPLOYMENTS[@]}"; do
  if ! kubectl --context "${KUBE_CONTEXT}" --namespace "${KUBE_NAMESPACE}" \
    get deployment "${deployment}" >/dev/null 2>&1; then
    echo "Deployment ${KUBE_NAMESPACE}/${deployment} does not exist." >&2
    echo "Install the platform with Infrastructure Ansible before using this script." >&2
    exit 1
  fi
done

declare -a BUILDS=(
  "anomaly-detector|AnomalyDetector"
  "agent-orchestrator|AgentOrchestrator"
  "mcp-tools|MCPTools"
  "rca-agent|RCAAgent"
  "remediator-agent|RemediatorAgent"
)

build_and_push() {
  local image_name="$1"
  local context_dir="$2"
  local image="${DOCKERHUB_NAMESPACE}/${image_name}:${IMAGE_TAG}"

  echo "Building and pushing ${image}"
  docker buildx build \
    --platform "${PLATFORM}" \
    --tag "${image}" \
    --push \
    "${ROOT_DIR}/${context_dir}"
}

for build in "${BUILDS[@]}"; do
  IFS="|" read -r image_name context_dir <<<"${build}"
  build_and_push "${image_name}" "${context_dir}"
done

set_deployment_image() {
  local deployment="$1"
  local container="$2"
  local image_name="$3"
  local image="${DOCKERHUB_NAMESPACE}/${image_name}:${IMAGE_TAG}"

  kubectl --context "${KUBE_CONTEXT}" --namespace "${KUBE_NAMESPACE}" \
    get deployment "${deployment}" >/dev/null
  kubectl --context "${KUBE_CONTEXT}" --namespace "${KUBE_NAMESPACE}" \
    set image "deployment/${deployment}" "${container}=${image}"
  kubectl --context "${KUBE_CONTEXT}" --namespace "${KUBE_NAMESPACE}" \
    patch "deployment/${deployment}" --type=strategic \
    --patch "{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"${container}\",\"imagePullPolicy\":\"Always\"}]}}}}"
  kubectl --context "${KUBE_CONTEXT}" --namespace "${KUBE_NAMESPACE}" \
    rollout restart "deployment/${deployment}"
  kubectl --context "${KUBE_CONTEXT}" --namespace "${KUBE_NAMESPACE}" \
    rollout status "deployment/${deployment}" --timeout="${ROLLOUT_TIMEOUT}"
}

# Preserve the coordinated dependency order used by Infrastructure Ansible.
set_deployment_image "mcp-tools-investigation" "mcp-tools-investigation" "mcp-tools"
set_deployment_image "mcp-tools-remediation" "mcp-tools-remediation" "mcp-tools"
set_deployment_image "rca-agent" "rca-agent" "rca-agent"
set_deployment_image "remediator-agent" "remediator-agent" "remediator-agent"
set_deployment_image "agent-orchestrator" "agent-orchestrator" "agent-orchestrator"
set_deployment_image "anomaly-detector" "anomaly-detector" "anomaly-detector"

echo "All dev images are deployed in ${KUBE_CONTEXT}/${KUBE_NAMESPACE}."
