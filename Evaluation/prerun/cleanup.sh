#!/usr/bin/env bash
set -euo pipefail

DSN="${1:-${POSTGRES_DSN:-}}"

if [[ -z "$DSN" ]]; then
  echo "Usage: $0 <postgres-dsn>" >&2
  echo "Or set POSTGRES_DSN." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

psql \
  -v ON_ERROR_STOP=1 \
  "$DSN" \
  -f "$SCRIPT_DIR/cleanup.sql"
