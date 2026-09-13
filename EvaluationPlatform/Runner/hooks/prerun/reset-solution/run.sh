#!/usr/bin/env bash
set -euo pipefail
python -m hooks.runtime api-reset "$1" "$2"
