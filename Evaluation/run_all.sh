#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SINGLE_SCRIPT="${RUN_SINGLE_SCRIPT:-$SCRIPT_DIR/run_single.sh}"

echo "Running TeaStore scenarios with the constant load generator"
"$RUN_SINGLE_SCRIPT" \
    "$SCRIPT_DIR/collections/teastore-scenario" \
    constant

echo "Running Online Boutique scenarios with the constant load generator"
"$RUN_SINGLE_SCRIPT" \
    "$SCRIPT_DIR/collections/online-boutique-scenario" \
    constant

echo
echo "Running Sock Shop scenarios with the constant load generator"
BASELINE_MINUTES="${SOCK_SHOP_BASELINE_MINUTES:-6}" "$RUN_SINGLE_SCRIPT" \
    "$SCRIPT_DIR/collections/sock-shop-scenario" \
    constant

echo
echo "Running long scenarios with the daily load generator"
"$RUN_SINGLE_SCRIPT" \
    "$SCRIPT_DIR/collections/long-scenario" \
    daily

echo
echo "Completed Online Boutique, TeaStore, Sock Shop, and long scenarios."
