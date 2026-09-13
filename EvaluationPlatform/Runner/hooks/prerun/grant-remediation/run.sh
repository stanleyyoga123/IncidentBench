#!/usr/bin/env bash
set -euo pipefail
python -m hooks.runtime grant-remediation "$1" "$2"
