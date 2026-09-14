#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0"
  echo "Scale all seven agent-platform Deployments to zero in namespace agents."
  echo "Uses kubectl's current context. Run when evaluations and agent jobs are idle."
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if (( $# != 0 )); then
  usage >&2
  exit 2
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: kubectl is required." >&2
  exit 1
fi

readonly CONTEXT="$(kubectl config current-context)"
if [[ -z "$CONTEXT" ]]; then
  echo "Error: kubectl has no current context." >&2
  exit 1
fi

deployments=(
  anomaly-detector
  agent-orchestrator
  rca-agent
  remediator-agent
  learning-agent
  mcp-tools-investigation
  mcp-tools-remediation
)

# Check every target before changing replicas, and pin the selected context.
kubectl --context "$CONTEXT" --namespace agents get deployment "${deployments[@]}" >/dev/null
echo "Scaling the agent platform to zero in context: $CONTEXT (namespace: agents)"
kubectl --context "$CONTEXT" --namespace agents scale deployment "${deployments[@]}" --replicas=0
