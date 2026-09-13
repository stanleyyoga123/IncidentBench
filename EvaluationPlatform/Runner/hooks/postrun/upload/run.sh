#!/usr/bin/env bash
set -euo pipefail
python -m hooks.runtime upload "$1" "$2"
