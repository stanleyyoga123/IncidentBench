#!/usr/bin/env bash
set -euo pipefail
action="$1"
context="$2"
output="$3"
case "$action" in
  prepare)
    python -m hooks.runtime api-acquire "$context" "$output"
    python -m hooks.runtime api-pause "$context" "$output"
    python -m hooks.runtime scale-down "$context" "$output"
    ;;
  activate)
    python -m hooks.runtime scale-up "$context" "$output"
    python -m hooks.runtime api-resume "$context" "$output"
    ;;
  stop)
    python -m hooks.runtime api-pause "$context" "$output"
    python -m hooks.runtime scale-down "$context" "$output"
    ;;
  release)
    python -m hooks.runtime api-release "$context" "$output"
    ;;
  *) exit 2 ;;
esac
