#!/usr/bin/env bash
set -euo pipefail

if (( $# != 0 )); then echo "Usage: $0" >&2; exit 2; fi
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd -- "$script_dir/../.." && pwd)"
source "$root_dir/deployment/image_config.sh"
validate_image_settings
render_image_manifest "$script_dir/kubernetes/manifest.yaml" "learning-agent" >/dev/null

command -v kubectl >/dev/null 2>&1 || { echo "Error: kubectl is required." >&2; exit 1; }
context="$(kubectl config current-context 2>/dev/null || true)"
[[ -n "$context" ]] || { echo "Error: kubectl has no current context." >&2; exit 1; }
secret_file="$script_dir/kubernetes/secret.yml"
secret_example="$script_dir/kubernetes/secret.example.yml"
[[ -f "$secret_file" ]] || { echo "Error: copy $secret_example to $secret_file." >&2; exit 1; }
[[ "$(<"$secret_file")" != *"++++++++"* ]] || { echo "Error: replace placeholders." >&2; exit 1; }

kubectl apply -f "$secret_file"
kubectl apply -f "$script_dir/kubernetes/configmap.yaml"
render_image_manifest "$script_dir/kubernetes/manifest.yaml" "learning-agent" | kubectl apply -f -
kubectl rollout status deployment/learning-agent --namespace agents --timeout=5m
