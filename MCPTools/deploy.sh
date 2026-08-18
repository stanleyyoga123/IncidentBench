#!/usr/bin/env bash
set -euo pipefail

if (( $# != 0 )); then
  echo "Usage: $0" >&2
  exit 2
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: kubectl is required." >&2
  exit 1
fi

context="$(kubectl config current-context 2>/dev/null || true)"
if [[ -z "$context" ]]; then
  echo "Error: kubectl has no current context." >&2
  exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
secret_file="$script_dir/kubernetes/secret.yml"
secret_example="$script_dir/kubernetes/secret.example.yml"

if [[ ! -f "$secret_file" ]]; then
  echo "Error: copy $secret_example to $secret_file and replace its placeholders." >&2
  exit 1
fi
if [[ "$(<"$secret_file")" == *"++++++++"* ]]; then
  echo "Error: replace every ++++++++ placeholder in $secret_file before deploying." >&2
  exit 1
fi

for namespace in agents utility online-boutique; do
  if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
    echo "Error: namespace '$namespace' is unavailable in context '$context'." >&2
    exit 1
  fi
done

kubectl apply -f "$secret_file"
kubectl apply -f "$script_dir/kubernetes/configmap.yaml"
kubectl apply -f "$script_dir/kubernetes/rbac.yaml"
kubectl apply -f "$script_dir/kubernetes/network-probes.yaml"
kubectl apply -f "$script_dir/kubernetes/investigation.yaml"
kubectl apply -f "$script_dir/kubernetes/remediation.yaml"

kubectl rollout status daemonset/mcp-tools-network-probe-overlay --namespace utility --timeout=5m
kubectl rollout status daemonset/mcp-tools-network-probe-underlay --namespace utility --timeout=5m
kubectl rollout status deployment/mcp-tools-investigation --namespace agents --timeout=5m
kubectl rollout status deployment/mcp-tools-remediation --namespace agents --timeout=5m
