#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SINGLE_SCRIPT="${RUN_SINGLE_SCRIPT:-$SCRIPT_DIR/run_single.sh}"

echo "Running real scenarios with the constant load generator"
"$RUN_SINGLE_SCRIPT" \
    "$SCRIPT_DIR/collections/real-scenario" \
    constant

echo
echo "Running long scenarios with the daily load generator"
"$RUN_SINGLE_SCRIPT" \
    "$SCRIPT_DIR/collections/long-scenario" \
    daily

echo
echo "Completed all real and long scenarios."
