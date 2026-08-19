#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --output-dir <dir>" >&2
}

OUTPUT_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --output-dir=*)
      OUTPUT_DIR="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$OUTPUT_DIR" ]]; then
  usage
  exit 2
fi

if [[ -z "${POSTGRES_DSN:-}" ]]; then
  echo "POSTGRES_DSN is required to export agent sessions." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSIONS_DIR="$OUTPUT_DIR/sessions"
mkdir -p "$SESSIONS_DIR"

dump_query() {
  local name="$1"
  local query_file="$SCRIPT_DIR/queries/${name}.sql"
  local destination="$SESSIONS_DIR/${name}.json"
  echo "Exporting ${name} to ${destination}"
  psql \
    -v ON_ERROR_STOP=1 \
    -At \
    -q \
    "$POSTGRES_DSN" \
    -f "$query_file" \
    > "$destination"
}

dump_query anomaly
dump_query rca_session
dump_query remediation_run
dump_query remediation_session
dump_query learning_session
dump_query workflow
