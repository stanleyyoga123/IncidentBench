#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly NAMESPACE="agents"
readonly SECRET_FILE="${SCRIPT_DIR}/kubernetes/secret.yml"
readonly SECRET_EXAMPLE="${SCRIPT_DIR}/kubernetes/secret.example.yml"
readonly POSTGRES_FILE="${SCRIPT_DIR}/kubernetes/postgres.yaml"
readonly CONFIGMAP_FILE="${SCRIPT_DIR}/kubernetes/configmap.yaml"
readonly JOB_FILE="${SCRIPT_DIR}/kubernetes/job.yaml"
readonly POSTGRES_STATEFULSET="anomaly-detector-postgres"
readonly CURRENT_JOB="database-migration-20260817-0002"
readonly OBSOLETE_JOB="database-migration-20260817-0001"
readonly ALLOW_AGENT_WORKFLOW_RESET="${ALLOW_AGENT_WORKFLOW_RESET:-false}"

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

command -v kubectl >/dev/null 2>&1 || fail "kubectl is required"

current_context="$(kubectl config current-context 2>/dev/null || true)"
[[ -n "${current_context}" ]] || fail "kubectl has no current context"
kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 ||
  fail "namespace ${NAMESPACE} is unavailable in current context ${current_context}"

case "${ALLOW_AGENT_WORKFLOW_RESET}" in
  true | false) ;;
  *) fail "ALLOW_AGENT_WORKFLOW_RESET must be exactly true or false" ;;
esac

[[ -f "${SECRET_FILE}" ]] ||
  fail "copy ${SECRET_EXAMPLE} to ${SECRET_FILE} and replace its placeholders"

if awk '
  /^[[:space:]]+POSTGRES_(DB|USER|PASSWORD):[[:space:]]*["'"'"']?\+{8}["'"'"']?[[:space:]]*$/ {
    found = 1
  }
  END { exit(found ? 0 : 1) }
' "${SECRET_FILE}"; then
  fail "replace every ++++++++ placeholder in kubernetes/secret.yml before deploying"
fi

legacy_agent_present=false
if kubectl get deployment cloudagent -n "${NAMESPACE}" >/dev/null 2>&1; then
  legacy_agent_present=true
fi

if [[ "${legacy_agent_present}" == "true" && "${ALLOW_AGENT_WORKFLOW_RESET}" != "true" ]]; then
  fail "existing cloudagent requires ALLOW_AGENT_WORKFLOW_RESET=true; migration can delete non-empty workflow tables"
fi

if [[ "${legacy_agent_present}" == "true" ]]; then
  for workload in cloudagent anomaly-detector; do
    if kubectl get deployment "${workload}" -n "${NAMESPACE}" >/dev/null 2>&1; then
      kubectl scale deployment "${workload}" -n "${NAMESPACE}" --replicas=0
      kubectl rollout status deployment "${workload}" -n "${NAMESPACE}" --timeout=5m
    fi
  done
fi

kubectl apply -f "${SECRET_FILE}"
kubectl apply -f "${POSTGRES_FILE}"

if command -v sha256sum >/dev/null 2>&1; then
  secret_checksum="$(sha256sum "${SECRET_FILE}" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  secret_checksum="$(shasum -a 256 "${SECRET_FILE}" | awk '{print $1}')"
else
  fail "sha256sum or shasum is required"
fi

kubectl patch statefulset "${POSTGRES_STATEFULSET}" \
  -n "${NAMESPACE}" \
  --type=merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"agent-platform/database-secret-checksum\":\"${secret_checksum}\"}}}}}" \
  >/dev/null
unset secret_checksum

kubectl rollout status "statefulset/${POSTGRES_STATEFULSET}" \
  -n "${NAMESPACE}" \
  --timeout=10m

# PostgreSQL initializes a persisted role only once. Feed the replacement
# password over stdin to psql's local-socket session so it never appears in
# this script's command arguments or output.
kubectl exec -n "${NAMESPACE}" "${POSTGRES_STATEFULSET}-0" -- \
  /bin/sh -ec \
  'printf "%s\n%s\n" "$POSTGRES_PASSWORD" "$POSTGRES_PASSWORD" |
   psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "\\password $POSTGRES_USER" >/dev/null'

kubectl apply -f "${CONFIGMAP_FILE}"
kubectl patch configmap database-job-config \
  -n "${NAMESPACE}" \
  --type=merge \
  -p "{\"data\":{\"ALLOW_AGENT_WORKFLOW_RESET\":\"${ALLOW_AGENT_WORKFLOW_RESET}\"}}" \
  >/dev/null

kubectl delete job "${CURRENT_JOB}" "${OBSOLETE_JOB}" \
  -n "${NAMESPACE}" \
  --ignore-not-found=true \
  --wait=true
kubectl apply -f "${JOB_FILE}"

if ! kubectl wait "job/${CURRENT_JOB}" \
  -n "${NAMESPACE}" \
  --for=condition=complete \
  --timeout=10m; then
  printf 'Database migration did not complete. Safe diagnostics follow.\n' >&2
  kubectl get job "${CURRENT_JOB}" -n "${NAMESPACE}" -o wide >&2 || true
  kubectl describe job "${CURRENT_JOB}" -n "${NAMESPACE}" >&2 || true
  kubectl get pods -n "${NAMESPACE}" \
    -l job-name="${CURRENT_JOB}" \
    -o wide >&2 || true
  kubectl get events -n "${NAMESPACE}" \
    --field-selector "involvedObject.kind=Job,involvedObject.name=${CURRENT_JOB}" \
    --sort-by=.lastTimestamp >&2 || true
  fail "database migration failed or timed out; logs were withheld because they may contain sensitive values"
fi

printf 'Database migration %s completed in context %s.\n' \
  "${CURRENT_JOB}" "${current_context}"
