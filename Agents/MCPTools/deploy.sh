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

for namespace in agents utility; do
  if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
    echo "Error: namespace '$namespace' is unavailable in context '$context'." >&2
    exit 1
  fi
done

kubectl apply -f "$secret_file"
kubectl apply -f "$script_dir/kubernetes/configmap.yaml"
kubectl apply -f "$script_dir/kubernetes/rbac.yaml"
# Application installers own namespace creation and reapply the binding after
# every reset. This optional list exists only for already-running namespaces.
application_namespaces="${APPLICATION_NAMESPACES:-}"
for namespace in $application_namespaces; do
  if [[ ! "$namespace" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]]; then
    echo "Error: invalid namespace in APPLICATION_NAMESPACES: '$namespace'." >&2
    exit 1
  fi
  if kubectl get namespace "$namespace" >/dev/null 2>&1; then
    # Kubernetes does not allow changing roleRef in place. Remove the legacy
    # binding whose name previously referred to a namespaced Role, then create
    # the distinctly named ClusterRole binding below.
    kubectl delete rolebinding mcp-tools-remediation \
      --namespace "$namespace" \
      --ignore-not-found
    kubectl apply --namespace "$namespace" \
      -f "$script_dir/kubernetes/application-role-binding.yaml"
    for resource in deployments.apps horizontalpodautoscalers.autoscaling; do
      if ! kubectl auth can-i patch "$resource" \
        --namespace "$namespace" \
        --as system:serviceaccount:agents:mcp-tools-remediation \
        --quiet; then
        echo "Error: remediation ServiceAccount cannot patch $resource in namespace '$namespace'." >&2
        exit 1
      fi
    done
  else
    echo "Application namespace '$namespace' is not present; remediation access will be bound when the application is installed."
  fi
done
kubectl apply -f "$script_dir/kubernetes/network-probes.yaml"
kubectl apply -f "$script_dir/kubernetes/investigation.yaml"
kubectl apply -f "$script_dir/kubernetes/remediation.yaml"

kubectl rollout status daemonset/mcp-tools-network-probe-overlay --namespace utility --timeout=5m
kubectl rollout status daemonset/mcp-tools-network-probe-underlay --namespace utility --timeout=5m
kubectl rollout status deployment/mcp-tools-investigation --namespace agents --timeout=5m
kubectl rollout status deployment/mcp-tools-remediation --namespace agents --timeout=5m
