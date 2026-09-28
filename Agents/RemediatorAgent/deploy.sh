#!/usr/bin/env bash
set -euo pipefail

if (( $# != 0 )); then
  echo "Usage: $0" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd -- "$script_dir/../.." && pwd)"
source "$root_dir/deployment/image_config.sh"
validate_image_settings
render_image_manifest "$script_dir/kubernetes/manifest.yaml" "remediator-agent" >/dev/null

if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: kubectl is required." >&2
  exit 1
fi

context="$(kubectl config current-context 2>/dev/null || true)"
if [[ -z "$context" ]]; then
  echo "Error: kubectl has no current context." >&2
  exit 1
fi

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

if ! kubectl get namespace agents >/dev/null 2>&1; then
  echo "Error: namespace 'agents' is unavailable in context '$context'." >&2
  exit 1
fi


kubectl apply -f "$secret_file"
kubectl apply -f "$script_dir/kubernetes/configmap.yaml"
render_image_manifest "$script_dir/kubernetes/manifest.yaml" "remediator-agent" | kubectl apply -f -
kubectl rollout status deployment/remediator-agent --namespace agents --timeout=5m
