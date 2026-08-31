#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

python -m grader \
    --input results/result-3 \
    --output grades \
    --ground-truth grader/ground_truth \
    --base-url http://172.28.168.104:8000/v1 \
    --model Qwen/Qwen3.6-35B-A3B \
    --token EMPTY \
    --verbose
