#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OUTPUT_DIR=""
POSTGRES_DSN="${POSTGRES_DSN:-}"
NAMESPACE="${NAMESPACE:-}"
AGENT_NAMESPACE="${AGENT_NAMESPACE:-agents}"
LOADGENERATOR=""
SCENARIO=""
HAS_SCENARIO=false
HELP_REQUESTED=false
TESTBED_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      HELP_REQUESTED=true
      TESTBED_ARGS+=("$1")
      shift
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      TESTBED_ARGS+=("$1" "${2:-}")
      shift 2
      ;;
    --output-dir=*)
      OUTPUT_DIR="${1#*=}"
      TESTBED_ARGS+=("$1")
      shift
      ;;
    --postgres-dsn)
      POSTGRES_DSN="${2:-}"
      shift 2
      ;;
    --postgres-dsn=*)
      POSTGRES_DSN="${1#*=}"
      shift
      ;;
    --namespace)
      NAMESPACE="${2:-}"
      TESTBED_ARGS+=("$1" "${2:-}")
      shift 2
      ;;
    --namespace=*)
      NAMESPACE="${1#*=}"
      TESTBED_ARGS+=("$1")
      shift
      ;;
    --agent-namespace)
      AGENT_NAMESPACE="${2:-}"
      TESTBED_ARGS+=("$1" "${2:-}")
      shift 2
      ;;
    --agent-namespace=*)
      AGENT_NAMESPACE="${1#*=}"
      TESTBED_ARGS+=("$1")
      shift
      ;;
    --loadgenerator)
      LOADGENERATOR="${2:-}"
      TESTBED_ARGS+=("$1" "${2:-}")
      shift 2
      ;;
    --loadgenerator=*)
      LOADGENERATOR="${1#*=}"
      TESTBED_ARGS+=("$1")
      shift
      ;;
    --scenario)
      HAS_SCENARIO=true
      SCENARIO="${2:-}"
      TESTBED_ARGS+=("$1" "${2:-}")
      shift 2
      ;;
    --scenario=*)
      HAS_SCENARIO=true
      SCENARIO="${1#*=}"
      TESTBED_ARGS+=("$1")
      shift
      ;;
    *)
      TESTBED_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ "$HELP_REQUESTED" == true || "$HAS_SCENARIO" != true || -z "$LOADGENERATOR" ]]; then
  exec "$SCRIPT_DIR/testbed/run.sh" "${TESTBED_ARGS[@]}"
fi

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="$SCRIPT_DIR/results/$(date +%Y%m%d-%H%M%S)-${LOADGENERATOR}"
  TESTBED_ARGS+=(--output-dir "$OUTPUT_DIR")
elif [[ "$OUTPUT_DIR" != /* ]]; then
  OUTPUT_DIR="$SCRIPT_DIR/$OUTPUT_DIR"
fi

export NAMESPACE AGENT_NAMESPACE POSTGRES_DSN SCENARIO OUTPUT_DIR
if [[ -n "${INFRASTRUCTURE_ROOT:-}" ]]; then
  export INFRASTRUCTURE_ROOT
fi

readonly -a AGENT_DEPLOYMENTS=(
  anomaly-detector agent-orchestrator learning-agent rca-agent
  remediator-agent mcp-tools-investigation mcp-tools-remediation
)

# Database cleanup must not race active workers. A previous interrupted run or
# a manual deployment may leave them running before prerun owns the lifecycle.
echo "Scaling agent platform down before prerun"
kubectl scale deployment "${AGENT_DEPLOYMENTS[@]}" \
  --namespace "$AGENT_NAMESPACE" --replicas=0 >/dev/null
for _ in {1..60}; do
  ready_replicas="$(kubectl get deployment "${AGENT_DEPLOYMENTS[@]}" \
    --namespace "$AGENT_NAMESPACE" \
    -o jsonpath='{range .items[*]}{.status.readyReplicas}{"\n"}{end}')"
  if ! grep -Eq '^[1-9][0-9]*$' <<<"$ready_replicas"; then
    break
  fi
  sleep 2
done
if grep -Eq '^[1-9][0-9]*$' <<<"$ready_replicas"; then
  echo "Agent platform did not scale to zero before prerun" >&2
  exit 1
fi

echo "Running prerun"
"$SCRIPT_DIR/prerun/run.sh"

testbed_returncode=0
echo "Running testbed"
"$SCRIPT_DIR/testbed/run.sh" "${TESTBED_ARGS[@]}" || testbed_returncode=$?

postrun_returncode=0
if [[ -d "$OUTPUT_DIR" ]]; then
  echo "Running postrun"
  "$SCRIPT_DIR/postrun/run.sh" --output-dir "$OUTPUT_DIR" || postrun_returncode=$?
else
  echo "Skipping postrun: output directory does not exist"
fi

if [[ "$postrun_returncode" -ne 0 ]]; then
  exit "$postrun_returncode"
fi
exit "$testbed_returncode"
