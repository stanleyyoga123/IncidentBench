#!/usr/bin/env bash
set -euo pipefail
python -m hooks.runtime install "$1" "$2"
