#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: $0"
  echo "Apply current agent manifests and restart deployments in kubectl's current context."
  echo "Requires installed platform/database prerequisites and populated component Secrets."
  exit 0
fi
if (( $# != 0 )); then
  echo "Usage: $0" >&2
  exit 2
fi

readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/deployment/image_config.sh"
validate_image_settings
# Component scripts own their Secrets, ConfigMaps, RBAC, Services and workloads.
components=(
  'Agents/MCPTools|mcp-tools-investigation mcp-tools-remediation'
  'Agents/LearningAgent|learning-agent'
  'Agents/RCAAgent|rca-agent'
  'Agents/RemediatorAgent|remediator-agent'
  'EvaluationPlatform/Orchestrator|agent-orchestrator'
  'Agents/AnomalyDetector|anomaly-detector'
)

# Validate all local inputs before applying the first component.
for entry in "${components[@]}"; do
  IFS='|' read -r component deployments <<< "$entry"
  for required in deploy.sh kubernetes/configmap.yaml kubernetes/secret.yml; do
    if [[ ! -f "$ROOT/$component/$required" ]]; then
      echo "Error: missing $component/$required. Populate component Secrets from secret.example.yml first." >&2
      exit 1
    fi
  done
  if [[ "$(<"$ROOT/$component/kubernetes/secret.yml")" == *"++++++++"* ]]; then
    echo "Error: replace required placeholders in $component/kubernetes/secret.yml." >&2
    exit 1
  fi
done

if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: kubectl is required." >&2
  exit 1
fi
readonly CONTEXT="$(kubectl config current-context)"
if [[ -z "$CONTEXT" ]]; then
  echo "Error: kubectl has no current context." >&2
  exit 1
fi
for namespace in agents utility; do
  kubectl get namespace "$namespace" >/dev/null
done

echo "Deploying agent platform to context: $CONTEXT"
trap 'echo "Deployment stopped after an error; earlier components may already be updated. No automatic rollback was performed." >&2' ERR
for entry in "${components[@]}"; do
  IFS='|' read -r component deployments <<< "$entry"
  if [[ "$(kubectl config current-context)" != "$CONTEXT" ]]; then
    echo "Error: kubectl context changed during deployment; stopping." >&2
    exit 1
  fi
  echo "Deploying $component"
  bash "$ROOT/$component/deploy.sh"
  # Mounted .env ConfigMaps and Secret environment values load at startup.
  # Restart also refreshes mutable image tags when imagePullPolicy is Always.
  for deployment in $deployments; do
    kubectl rollout restart "deployment/$deployment" --namespace agents
    kubectl rollout status "deployment/$deployment" --namespace agents --timeout=5m
  done
done

echo "All agent deployments updated and ready in context: $CONTEXT"
