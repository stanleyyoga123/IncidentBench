#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALLER_DIR="$PWD"
APPS=(online-boutique sock-shop teastore)
RESULTS_DIR="$ROOT/results"
OUTPUT_ROOT="$ROOT/output"
INPUT=""
APPS_SELECTED=false
GRADER_ARGS=()
REPORT_ARGS=()

usage() {
  cat <<'HELP'
Usage: ./grade.sh [--apps APP ... | --input PATH] [--output-root PATH] [-- GRADER_OPTIONS ...]

Run visualizer, grader, then reporting for online-boutique, sock-shop and teastore.
--apps selects application(s). --input selects one application directory named
online-boutique, sock-shop or teastore. Relative paths resolve from your working
directory. Outputs under output/: visualizations/<app>, grades/<app>, report/report.md.
--output-root puts these three folders under another directory.
Grader options follow --; use --operational-only for zero model calls.
PYTHON overrides the interpreter; otherwise .venv/bin/python, python or python3 is used.
HELP
}

fail() { printf '%s\n' "$*" >&2; exit 2; }
absolute_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$CALLER_DIR" "$1" ;;
  esac
}

while (($#)); do
  case "$1" in
    --apps)
      [[ -z "$INPUT" ]] || fail '--apps and --input are mutually exclusive'
      APPS_SELECTED=true
      APPS=()
      shift
      while (($#)) && [[ "$1" != --* ]]; do APPS+=("$1"); shift; done
      ((${#APPS[@]})) || fail '--apps requires at least one application'
      ;;
    --input)
      [[ "$APPS_SELECTED" == false && -z "$INPUT" ]] || fail 'Select either --apps or one --input'
      (($# >= 2)) && [[ "$2" != --* ]] || fail '--input requires an application directory'
      INPUT="$(absolute_path "$2")"
      shift 2
      ;;
    --output-root)
      (($# >= 2)) && [[ "$2" != --* ]] || fail '--output-root requires a directory'
      OUTPUT_ROOT="$(absolute_path "$2")"
      shift 2
      ;;
    --) shift; GRADER_ARGS=("$@"); break ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown pipeline option: $1. Put grader options after --." ;;
  esac
done

if [[ -n "$INPUT" ]]; then
  [[ -d "$INPUT" ]] || fail 'Input application directory does not exist'
  INPUT="$(cd "$INPUT" && pwd)"
  APPS=("${INPUT##*/}")
  RESULTS_DIR="${INPUT%/*}"
fi

for app in "${APPS[@]}"; do
  case "$app" in
    online-boutique|sock-shop|teastore) ;;
    *) fail "Unsupported application: $app" ;;
  esac
  [[ -d "$RESULTS_DIR/$app" ]] || fail "Missing input directory for $app"
done

# Accept full grader option names; pipeline-owned paths and identities cannot be overridden.
for arg in ${GRADER_ARGS[@]+"${GRADER_ARGS[@]}"}; do
  option="${arg%%=*}"
  case "$option" in
    --ground-truth|--rubric|--penalties|--base-url|--model|--token|--judge-timeout-seconds|--judge-max-tokens|--concurrency|--operational-only|--evaluation-policy|--comparison-window-minutes|--baseline-ignore-minutes|--table-max-5xx-rate|--model-revision|--refresh-judge|--verbose) ;;
    -h|--*) fail "Unsupported forwarded option: $option. Pipeline owns input/output and workload/namespace; use full grader option names." ;;
  esac
done

# Mirror paired-window measurement overrides in the aggregate report.
for ((i=0; i<${#GRADER_ARGS[@]}; i++)); do
  arg="${GRADER_ARGS[i]}"
  option="${arg%%=*}"
  case "$option" in
    --comparison-window-minutes) report_option=--window-minutes ;;
    --baseline-ignore-minutes) report_option=--baseline-ignore-minutes ;;
    --table-max-5xx-rate) report_option=--max-5xx-rps ;;
    --comparison*|--baseline*|--table-max*) fail 'Use full names for comparison and baseline overrides' ;;
    *) continue ;;
  esac
  if [[ "$arg" == *=* ]]; then
    value="${arg#*=}"
  else
    ((i + 1 < ${#GRADER_ARGS[@]})) || fail "$option requires a value"
    i=$((i + 1))
    value="${GRADER_ARGS[i]}"
  fi
  [[ -n "$value" && "$value" != --* ]] || fail "$option requires a value"
  REPORT_ARGS+=("$report_option" "$value")
done

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  elif command -v python >/dev/null 2>&1; then
    PYTHON=python
  else
    PYTHON=python3
  fi
fi
cd "$ROOT"

for app in "${APPS[@]}"; do
  printf 'Visualizing %s\n' "$app"
  "$PYTHON" -m visualizer --input "$RESULTS_DIR/$app" --output "$OUTPUT_ROOT/visualizations/$app"
done

for app in "${APPS[@]}"; do
  case "$app" in
    online-boutique) workload=frontend ;;
    sock-shop) workload=front-end ;;
    teastore) workload=teastore-webui ;;
  esac
  printf 'Grading %s\n' "$app"
  "$PYTHON" -m grader \
    --input "$RESULTS_DIR/$app" \
    --output "$OUTPUT_ROOT/grades/$app" \
    --ground-truth resources/ground_truth \
    --rubric resources/rubric.json \
    --penalties resources/penalties \
    --base-url "${JUDGE_URL:-http://172.28.168.104:8000/v1}" \
    --model "${JUDGE_MODEL:-Qwen/Qwen3.6-35B-A3B}" \
    --token "${JUDGE_TOKEN:-EMPTY}" \
    --judge-timeout-seconds "${JUDGE_TIMEOUT_SECONDS:-600}" \
    --judge-max-tokens "${JUDGE_MAX_TOKENS:-8192}" \
    --concurrency "${GRADER_CONCURRENCY:-5}" \
    --evaluation-policy resources/evaluation-policy.json \
    --table-workload "$workload" --table-namespace "$app" \
    --verbose ${GRADER_ARGS[@]+"${GRADER_ARGS[@]}"}
done

printf 'Generating Markdown report\n'
"$PYTHON" -m reporting.report \
  --results-dir "$RESULTS_DIR" --grades-dir "$OUTPUT_ROOT/grades" \
  --output "$OUTPUT_ROOT/report/report.md" --apps "${APPS[@]}" ${REPORT_ARGS[@]+"${REPORT_ARGS[@]}"}
