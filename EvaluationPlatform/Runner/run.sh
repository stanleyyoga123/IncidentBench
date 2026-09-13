#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec python -m testbed.main \
  --suite resources/suites/all.json \
  --environment config/environment.json
