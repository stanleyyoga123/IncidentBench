#!/usr/bin/env bash
set -euo pipefail
# Replace these lifecycle cases with your solution commands.
case "$1" in
  prepare|activate|stop|release) echo "example integration: $1" ;;
  *) exit 2 ;;
esac
