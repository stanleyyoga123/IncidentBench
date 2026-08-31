#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <scenario-folder>" >&2
    echo "Example: $0 ./collections/online-boutique-scenario" >&2
}

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

CALLER_DIR="$PWD"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO_DIR="$1"

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

LOADGENERATOR="${LOADGENERATOR:-burst}"
BASELINE_MINUTES="${BASELINE_MINUTES:-60}"
TARGET_HOST="${TARGET_HOST:-}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://prometheus-server.monitoring.svc.cluster.local}"
POSTGRES_DSN="${POSTGRES_DSN:-postgresql://anomaly_detector:anomaly_detector@postgres.agents.svc.cluster.local:5432/anomaly_detector}"
S3_RESULTS_URI="${S3_RESULTS_URI:-}"
INTER_RUN_DELAY_SECONDS="${INTER_RUN_DELAY_SECONDS:-60}"

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
    local mode="$2"
    local run_id
    local scenario_name
    local output_dir
    local destination
    local run_returncode=0
    local upload_returncode=0

    scenario_name="$(basename "$scenario" .json)"
    run_id="$(date -u +%Y%m%d-%H%M%S)-${scenario_name}-${mode}-${LOADGENERATOR}"
    output_dir="$SCRIPT_DIR/results/$run_id"
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

    if [[ "$mode" == "skip-agents" ]]; then
        command+=(--skip-agents)
    fi

    echo
    echo "Running $(basename "$scenario") [$mode]"
    "${command[@]}" || run_returncode=$?

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

    return "$run_returncode"
}

echo "Found ${#SCENARIOS[@]} scenario(s) in $SCENARIO_DIR"
echo "Each scenario will run first with agents, then with --skip-agents."
if [[ -n "$S3_RESULTS_URI" ]]; then
    echo "Completed run artifacts will be uploaded to ${S3_RESULTS_URI%/}/<run-id>/"
else
    echo "S3 upload is disabled; set S3_RESULTS_URI to enable it."
fi

FAILED_RUNS=()
TOTAL_RUNS=$((${#SCENARIOS[@]} * 2))
COMPLETED_RUNS=0

for scenario in "${SCENARIOS[@]}"; do
    for mode in agents skip-agents; do
        if run_scenario "$scenario" "$mode"; then
            echo "Completed $(basename "$scenario") [$mode]"
        else
            returncode=$?
            FAILED_RUNS+=("$(basename "$scenario") [$mode] (exit $returncode)")
            echo "Scenario run failed; continuing with the batch: $(basename "$scenario") [$mode] (exit $returncode)" >&2
        fi

        COMPLETED_RUNS=$((COMPLETED_RUNS + 1))
        if (( COMPLETED_RUNS < TOTAL_RUNS && INTER_RUN_DELAY_SECONDS > 0 )); then
            echo "Waiting ${INTER_RUN_DELAY_SECONDS}s before the next test case..."
            sleep "$INTER_RUN_DELAY_SECONDS"
        fi
    done
done

echo
if [[ ${#FAILED_RUNS[@]} -eq 0 ]]; then
    echo "Completed all ${#SCENARIOS[@]} scenario(s) in both modes."
    exit 0
fi

echo "Completed the batch with ${#FAILED_RUNS[@]} failed run(s):" >&2
for failed_run in "${FAILED_RUNS[@]}"; do
    echo "  - $failed_run" >&2
done
exit 1
