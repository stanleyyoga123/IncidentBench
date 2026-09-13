#!/usr/bin/env bash
set -euo pipefail
python -m hooks.runtime api-export "$1" "$2"
