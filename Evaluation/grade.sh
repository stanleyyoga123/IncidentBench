#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

exec python -m grader \
    --input results/long-scenario \
    --output grades/long-scenario \
    --ground-truth grader/ground_truth \
    --rubric grader/rubric.json \
    --penalties grader/penalties \
    --base-url http://172.28.168.104:8000/v1 \
    --model Qwen/Qwen3.6-35B-A3B \
    --token EMPTY \
    --verbose
