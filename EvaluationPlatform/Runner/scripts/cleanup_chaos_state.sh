#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --yes" >&2
}

if [[ "${1:-}" != "--yes" ]]; then
  usage
  echo "Refusing to run cluster/host chaos cleanup without --yes." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRASTRUCTURE_ROOT="${INFRASTRUCTURE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)/Initialization}"
INVENTORY="${CHAOS_NODE_INVENTORY:-$INFRASTRUCTURE_ROOT/ansible/inventory.ini}"
SSH_USER="${CHAOS_NODE_SSH_USER:-chaos-cleaner}"
SSH_IDENTITY="${CHAOS_NODE_SSH_IDENTITY_FILE:-}"
SSH_KNOWN_HOSTS="${CHAOS_NODE_SSH_KNOWN_HOSTS_FILE:-}"

if [[ ! -r "$INVENTORY" ]]; then
  echo "service-node inventory is not readable: $INVENTORY" >&2
  exit 2
fi

ssh_base=(
  ssh
  -o BatchMode=yes
  -o ConnectTimeout=8
  -o IdentitiesOnly=yes
  -o PasswordAuthentication=no
  -o StrictHostKeyChecking=yes
)
if [[ -n "$SSH_IDENTITY" ]]; then
  ssh_base+=(-i "$SSH_IDENTITY")
fi
if [[ -n "$SSH_KNOWN_HOSTS" ]]; then
  ssh_base+=(-o "UserKnownHostsFile=$SSH_KNOWN_HOSTS")
fi

WORKERS=()
while IFS= read -r worker; do
  [[ -n "$worker" ]] && WORKERS+=("$worker")
done < <(
  awk '
    /^\[/ { section=$0; next }
    section == "[service_nodes]" && $1 !~ /^#/ && NF {
      split($0, parts, " ")
      host=""
      for (i = 2; i <= NF; i++) {
        if (parts[i] ~ /^ansible_host=/) {
          split(parts[i], kv, "=")
          host=kv[2]
        }
      }
      if (host != "") print host
    }
  ' "$INVENTORY"
)

if [[ ${#WORKERS[@]} -eq 0 ]]; then
  echo "service-node inventory has no hosts: $INVENTORY" >&2
  exit 2
fi

echo "Deleting Chaos Mesh experiment, Schedule, and Workflow resources"
KINDS=()
while IFS= read -r kind; do
  [[ -n "$kind" ]] && KINDS+=("$kind")
done < <(kubectl api-resources --api-group=chaos-mesh.org -o name)
for kind in "${KINDS[@]}"; do
  case "$kind" in
    physicalmachines.chaos-mesh.org|remoteclusters.chaos-mesh.org)
      continue
      ;;
  esac
  kubectl delete "$kind" --all --all-namespaces --timeout=90s || true
done

echo "Clearing finalizers on remaining terminating Chaos Mesh experiments"
for kind in "${KINDS[@]}"; do
  case "$kind" in
    physicalmachines.chaos-mesh.org|remoteclusters.chaos-mesh.org)
      continue
      ;;
  esac
  while read -r namespace name deletion; do
    [[ -n "$name" ]] || continue
    [[ -n "$deletion" ]] || continue
    kubectl patch "$kind" "$name" -n "$namespace" --type=merge \
      -p '{"metadata":{"finalizers":[]}}' || true
  done < <(
    kubectl get "$kind" --all-namespaces -o jsonpath \
      '{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.metadata.deletionTimestamp}{"\n"}{end}' \
      2>/dev/null || true
  )
done

clean_workers() {
  local pass="$1"
  local failed=0
  echo "Host chaos cleanup pass $pass"
  for host in "${WORKERS[@]}"; do
    echo "Cleaning $SSH_USER@$host"
    if ! "${ssh_base[@]}" "$SSH_USER@$host" \
      "sudo -n /usr/local/sbin/evaluation-clean-host-chaos"; then
      echo "host cleanup failed: $host" >&2
      failed=1
    fi
  done
  return "$failed"
}

verify_workers() {
  local failed=0
  echo "Verifying workers are clean"
  for host in "${WORKERS[@]}"; do
    echo "Checking $SSH_USER@$host"
    output="$("${ssh_base[@]}" "$SSH_USER@$host" \
      "sudo -n /usr/local/sbin/evaluation-check-host-chaos" || true)"
    printf '%s\n' "$output"
    if printf '%s\n' "$output" | grep -Eq 'qdisc (netem|tbf) '; then
      echo "residual network chaos remains on $host" >&2
      failed=1
    fi
    if printf '%s\n' "$output" | awk '
      $1 == "STRESS" {seen=1; next}
      seen && NF {found=1}
      END {exit found ? 0 : 1}
    '; then
      echo "residual CPU stress remains on $host" >&2
      failed=1
    fi
  done
  return "$failed"
}

host_failed=0
clean_workers 1 || host_failed=1
clean_workers 2 || host_failed=1
verify_workers || host_failed=1

if [[ "$host_failed" -ne 0 ]]; then
  echo "cluster or worker-node chaos cleanup failed" >&2
  exit 1
fi

echo "Cluster and worker-node chaos state is clean"
