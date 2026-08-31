#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [scenario-folder] [loadgenerator]" >&2
    echo "Default: $0 ./collections/online-boutique-scenario constant" >&2
}

if [[ $# -gt 2 ]]; then
    usage
    exit 2
fi

CALLER_DIR="$PWD"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO_DIR="${1:-$SCRIPT_DIR/collections/online-boutique-scenario}"
LOADGENERATOR_ARGUMENT="${2:-}"

if [[ "$SCENARIO_DIR" != /* ]]; then
    SCENARIO_DIR="$CALLER_DIR/$SCENARIO_DIR"
fi

if [[ ! -d "$SCENARIO_DIR" ]]; then
    echo "Scenario folder not found: $SCENARIO_DIR" >&2
    exit 2
fi

cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

LOADGENERATOR="${LOADGENERATOR_ARGUMENT:-${LOADGENERATOR:-constant}}"
BASELINE_MINUTES="${BASELINE_MINUTES:-60}"
TARGET_HOST="${TARGET_HOST:-}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://prometheus-server.monitoring.svc.cluster.local}"
POSTGRES_DSN="${POSTGRES_DSN:-postgresql://anomaly_detector:anomaly_detector@postgres.agents.svc.cluster.local:5432/anomaly_detector}"
S3_RESULTS_URI="${S3_RESULTS_URI:-}"
INTER_RUN_DELAY_SECONDS="${INTER_RUN_DELAY_SECONDS:-60}"
LAST_RUN_CLEANUP_FAILED=false

case "$LOADGENERATOR" in
    constant|burst|sinus|daily) ;;
    *)
        echo "Unsupported load generator: $LOADGENERATOR" >&2
        exit 2
        ;;
esac

if [[ ! "$INTER_RUN_DELAY_SECONDS" =~ ^[0-9]+$ ]]; then
    echo "INTER_RUN_DELAY_SECONDS must be a non-negative integer" >&2
    exit 2
fi

if [[ -n "$S3_RESULTS_URI" ]]; then
    if [[ "$S3_RESULTS_URI" != s3://* ]]; then
        echo "S3_RESULTS_URI must start with s3://: $S3_RESULTS_URI" >&2
        exit 2
    fi
    if ! command -v aws >/dev/null 2>&1; then
        echo "AWS CLI is required when S3_RESULTS_URI is set." >&2
        exit 2
    fi
fi

shopt -s nullglob
SCENARIOS=("$SCENARIO_DIR"/*.json)
shopt -u nullglob

if [[ ${#SCENARIOS[@]} -eq 0 ]]; then
    echo "No JSON scenario files found in: $SCENARIO_DIR" >&2
    exit 2
fi

run_scenario() {
    local scenario="$1"
    local scenario_name
    local run_id
    local output_dir
    local destination
    local run_returncode=0
    local upload_returncode=0
    local cleanup_returncode=0

    LAST_RUN_CLEANUP_FAILED=false

    scenario_name="$(basename "$scenario" .json)"
    run_id="$(date -u +%Y%m%d-%H%M%S)-${scenario_name}-agents-${LOADGENERATOR}"
    output_dir="$SCRIPT_DIR/results/$run_id"

    echo
    echo "Running $(basename "$scenario") [agents, $LOADGENERATOR load]"
    local command=(
        ./run.sh
        --loadgenerator "$LOADGENERATOR"
        --scenario "$scenario"
        --output-dir "$output_dir"
        --baseline-minutes "$BASELINE_MINUTES"
        --prometheus-url "$PROMETHEUS_URL"
        --postgres-dsn "$POSTGRES_DSN"
    )
    if [[ -n "$TARGET_HOST" ]]; then
        command+=(--host "$TARGET_HOST")
    fi
    "${command[@]}" || run_returncode=$?

    echo "Running authoritative post-scenario chaos cleanup"
    "$SCRIPT_DIR/cleanup_chaos_state.sh" --yes \
        || cleanup_returncode=$?
    if [[ $cleanup_returncode -ne 0 ]]; then
        LAST_RUN_CLEANUP_FAILED=true
        echo "Post-scenario chaos cleanup failed (exit $cleanup_returncode)" >&2
    fi

    if [[ -n "$S3_RESULTS_URI" && -d "$output_dir" ]]; then
        destination="${S3_RESULTS_URI%/}/$run_id/"
        echo "Uploading $output_dir to $destination"
        aws s3 sync "$output_dir/" "$destination" --only-show-errors \
            || upload_returncode=$?
        if [[ $upload_returncode -ne 0 ]]; then
            echo "S3 upload failed for $output_dir (exit $upload_returncode)" >&2
            return "$upload_returncode"
        fi
        echo "Uploaded results to $destination"
    fi

    if [[ $cleanup_returncode -ne 0 ]]; then
        return "$cleanup_returncode"
    fi

    return "$run_returncode"
}

echo "Found ${#SCENARIOS[@]} scenario(s) in $SCENARIO_DIR"
echo "Each scenario will run once with agents enabled and $LOADGENERATOR load."
if [[ -n "$S3_RESULTS_URI" ]]; then
    echo "Completed run artifacts will be uploaded to ${S3_RESULTS_URI%/}/<run-id>/"
else
    echo "S3 upload is disabled; set S3_RESULTS_URI to enable it."
fi

FAILED_RUNS=()
COMPLETED_RUNS=0

for scenario in "${SCENARIOS[@]}"; do
    if run_scenario "$scenario"; then
        echo "Completed $(basename "$scenario") [agents, $LOADGENERATOR load]"
    else
        returncode=$?
        FAILED_RUNS+=("$(basename "$scenario") (exit $returncode)")
        if [[ "$LAST_RUN_CLEANUP_FAILED" == true ]]; then
            echo "Aborting the batch because cleanup did not prove the cluster clean." >&2
            break
        fi
        echo "Scenario run failed after a successful cleanup; continuing with the batch: $(basename "$scenario") (exit $returncode)" >&2
    fi

    COMPLETED_RUNS=$((COMPLETED_RUNS + 1))
    if (( COMPLETED_RUNS < ${#SCENARIOS[@]} && INTER_RUN_DELAY_SECONDS > 0 )); then
        echo "Waiting ${INTER_RUN_DELAY_SECONDS}s before the next test case..."
        sleep "$INTER_RUN_DELAY_SECONDS"
    fi
done

echo
if [[ ${#FAILED_RUNS[@]} -eq 0 ]]; then
    echo "Completed all ${#SCENARIOS[@]} scenario(s) with agents and $LOADGENERATOR load."
    exit 0
fi

echo "Completed the batch with ${#FAILED_RUNS[@]} failed run(s):" >&2
for failed_run in "${FAILED_RUNS[@]}"; do
    echo "  - $failed_run" >&2
done
exit 1
