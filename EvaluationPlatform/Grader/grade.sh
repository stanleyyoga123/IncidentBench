#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec python -m grader \
  --input ./results/sock-shop-1 \
  --output ./grades/sock-shop-1-20260916 \
  --ground-truth resources/ground_truth \
  --rubric resources/rubric.json \
  --penalties resources/penalties \
  --base-url http://localhost:8000/v1 \
  --model Qwen/Qwen3.6-35B-A3B \
  --token EMPTY \
  --judge-timeout-seconds 600 \
  --judge-max-tokens 8192 \
  --concurrency 5 \
  --evaluation-policy resources/evaluation-policy.json \
  --verbose