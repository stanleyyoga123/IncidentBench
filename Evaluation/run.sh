#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OUTPUT_DIR=""
POSTGRES_DSN="${POSTGRES_DSN:-}"
NAMESPACE="${NAMESPACE:-online-boutique}"
LOADGENERATOR=""
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
      TESTBED_ARGS+=("$1" "${2:-}")
      shift 2
      ;;
    --scenario=*)
      HAS_SCENARIO=true
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

export NAMESPACE POSTGRES_DSN
if [[ -n "${INFRASTRUCTURE_ROOT:-}" ]]; then
  export INFRASTRUCTURE_ROOT
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
