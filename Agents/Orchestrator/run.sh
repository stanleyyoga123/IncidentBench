#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$(pwd)/app"
python app/main.py
