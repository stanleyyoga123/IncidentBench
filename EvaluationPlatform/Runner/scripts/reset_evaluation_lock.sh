#!/usr/bin/env bash
set -euo pipefail
runner_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${runner_root}${PYTHONPATH:+:${PYTHONPATH}}"
exec python -m hooks.reset_evaluation_lock "$@"
