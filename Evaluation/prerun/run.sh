#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-online-boutique}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRASTRUCTURE_ROOT="${INFRASTRUCTURE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)/Infrastructure}"
KUSTOMIZE_DIR="${ONLINE_BOUTIQUE_KUSTOMIZE_DIR:-${INFRASTRUCTURE_ROOT}/kubernetes/online-boutique/kustomize}"
ROLE_BINDING="${INFRASTRUCTURE_ROOT}/kubernetes/online-boutique/role-binding.yaml"
POSTGRES_DSN="${1:-${POSTGRES_DSN:-}}"

for path in "$KUSTOMIZE_DIR/kustomization.yaml" "$ROLE_BINDING"; do
  [[ -r "$path" ]] || { echo "required infrastructure file is missing: $path" >&2; exit 2; }
done

echo "Cleanup the postgres"
if [[ -n "$POSTGRES_DSN" ]]; then
  "$SCRIPT_DIR/cleanup.sh" "$POSTGRES_DSN"
else
  echo "Postgres cleanup skipped: no DSN provided"
fi

kubectl delete ns "$NAMESPACE"
kubectl create ns "$NAMESPACE"

kubectl label namespace "$NAMESPACE" istio-injection=enabled
echo "Re-apply the role-binding"
kubectl apply -f "$ROLE_BINDING"

sleep 5
kubectl apply -k "$KUSTOMIZE_DIR" --namespace "$NAMESPACE"
