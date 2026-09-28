#!/usr/bin/env bash
set -euo pipefail

if (( $# != 0 )); then
  echo "Usage: $0" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd -- "$script_dir/../../.." && pwd)"
source "$root_dir/deployment/image_config.sh"
validate_image_settings
render_image_manifest "$script_dir/../kubernetes/pod.yaml" "evaluation" >/dev/null

if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: kubectl is required." >&2
  exit 1
fi

context="$(kubectl config current-context 2>/dev/null || true)"
if [[ -z "$context" ]]; then
  echo "Error: kubectl has no current context." >&2
  exit 1
fi

secret_file="$script_dir/../kubernetes/secret.yml"
secret_example="$script_dir/../kubernetes/secret.example.yml"
pod_file="$script_dir/../kubernetes/pod.yaml"

if [[ ! -f "$secret_file" ]]; then
  echo "Error: copy $secret_example to $secret_file and replace its required placeholders." >&2
  exit 1
fi
if [[ ! -f "$pod_file" ]]; then
  echo "Error: missing $pod_file" >&2
  exit 1
fi

if ! kubectl get namespace agents >/dev/null 2>&1; then
  echo "Error: namespace 'agents' is unavailable in context '$context'." >&2
  exit 1
fi

if ! grep -q 'name: evaluation-runner-env' "$secret_file"; then
  echo "Error: secret.yml is missing evaluation-runner-env. Copy ORCHESTRATOR_CONTROL_TOKEN from $secret_example." >&2
  exit 1
fi

ssh_placeholders="$(
  awk '
    /^---[[:space:]]*$/ { exit }
    index($0, ": \"++++++++\"") { count++ }
    END { print count + 0 }
  ' "$secret_file"
)"
env_placeholders="$(
  awk '
    /^---[[:space:]]*$/ { doc++ }
    doc == 1 && index($0, ": \"++++++++\"") { count++ }
    END { print count + 0 }
  ' "$secret_file"
)"
s3_placeholders="$(
  awk '
    /^---[[:space:]]*$/ { doc++ }
    doc >= 2 && index($0, ": \"++++++++\"") { count++ }
    END { print count + 0 }
  ' "$secret_file"
)"

if (( ssh_placeholders != 0 )); then
  echo "Error: replace the SSH ++++++++ placeholders in $secret_file." >&2
  exit 1
fi
if (( env_placeholders != 0 )); then
  echo "Error: replace the ORCHESTRATOR_CONTROL_TOKEN ++++++++ placeholder in $secret_file." >&2
  exit 1
fi
if (( s3_placeholders != 0 && s3_placeholders != 4 )); then
  echo "Error: replace all four optional S3 placeholders or leave all four unchanged." >&2
  exit 1
fi


awk '
  /^---[[:space:]]*$/ { doc++ }
  doc < 2 { print }
' "$secret_file" | kubectl apply -f -

if (( s3_placeholders == 0 )); then
  awk '
    /^---[[:space:]]*$/ { doc++ }
    doc >= 2 { print }
  ' "$secret_file" | kubectl apply -f -
else
  echo "Optional S3 placeholders are unchanged; evaluation-runner-s3 will not be applied or removed."
fi

inventory_file="$script_dir/../../Initialization/ansible/inventory.ini"
if [[ ! -f "$inventory_file" ]]; then
  echo "Error: copy Initialization/ansible/inventory.example.ini to inventory.ini and fill node addresses." >&2
  exit 1
fi
kubectl -n agents create configmap evaluation-runner-inventory \
  --from-file="inventory.ini=$inventory_file" --dry-run=client -o yaml | kubectl apply -f -
render_image_manifest "$pod_file" "evaluation" | kubectl apply -f -
kubectl wait --for=condition=Ready pod/evaluation-runner \
  --namespace agents --timeout=5m
