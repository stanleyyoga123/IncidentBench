#!/usr/bin/env bash
set -Eeuo pipefail

readonly NAMESPACE="agents"
declare -ar DEPLOYMENTS=(
  "mcp-tools-investigation"
  "mcp-tools-remediation"
  "learning-agent"
  "rca-agent"
  "remediator-agent"
  "agent-orchestrator"
  "anomaly-detector"
)

usage() {
  echo "Usage: $0"
  echo
  echo "Restarts the agent, MCP, Orchestrator, and AnomalyDetector deployments"
  echo "in kubectl's current context so they pull the latest pushed images."
  echo "Does not build, push, apply manifests, or run DatabaseJob."
}

if (( $# != 0 )); then
  usage >&2
  exit 2
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: kubectl is required." >&2
  exit 1
fi

context="$(kubectl config current-context 2>/dev/null || true)"
if [[ -z "${context}" ]]; then
  echo "Error: kubectl has no current context." >&2
  exit 1
fi

if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  echo "Error: namespace '${NAMESPACE}' is unavailable in current context '${context}'." >&2
  exit 1
fi

for deployment in "${DEPLOYMENTS[@]}"; do
  if ! kubectl get deployment "${deployment}" --namespace "${NAMESPACE}" >/dev/null 2>&1; then
    echo "Error: deployment '${deployment}' is unavailable in namespace '${NAMESPACE}'." >&2
    exit 1
  fi
done

echo "==> Restarting deployments in context ${context} namespace ${NAMESPACE}"
for deployment in "${DEPLOYMENTS[@]}"; do
  echo "==> Restarting ${deployment}"
  kubectl rollout restart "deployment/${deployment}" --namespace "${NAMESPACE}"
done

for deployment in "${DEPLOYMENTS[@]}"; do
  echo "==> Waiting for ${deployment}"
  kubectl rollout status "deployment/${deployment}" --namespace "${NAMESPACE}" --timeout=5m
done

echo "Restarted ${#DEPLOYMENTS[@]} deployments in context ${context} so they pull the latest images."
