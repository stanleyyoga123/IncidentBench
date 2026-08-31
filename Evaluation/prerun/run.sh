#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO="${SCENARIO:-}"

if [[ -z "$SCENARIO" ]]; then
  echo "SCENARIO is required for application-aware prerun" >&2
  exit 2
fi

cd "$SCRIPT_DIR/.."
exec python -m testbed.applications.prerun --scenario "$SCENARIO"
