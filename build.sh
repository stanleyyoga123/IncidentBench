#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPONENTS="mcp-tools learning-agent rca-agent remediator-agent agent-orchestrator anomaly-detector database-job runner"

usage() {
  echo "Usage: $0 [all | COMPONENT ...]"
  echo "Build and push component images (default: all)."
  echo "Components: $COMPONENTS"
  echo "Set PLATFORM to override linux/amd64. Requires Docker Buildx and registry login."
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if (( $# == 0 )) || [[ $# == 1 && "$1" == "all" ]]; then
  read -r -a selected <<< "$COMPONENTS"
else
  selected=("$@")
fi

# Resolve every selection before starting any build.
scripts=()
for component in "${selected[@]}"; do
  case "$component" in
    mcp-tools) script="Agents/MCPTools/build.sh" ;;
    learning-agent) script="Agents/LearningAgent/build.sh" ;;
    rca-agent) script="Agents/RCAAgent/build.sh" ;;
    remediator-agent) script="Agents/RemediatorAgent/build.sh" ;;
    agent-orchestrator) script="EvaluationPlatform/Orchestrator/build.sh" ;;
    anomaly-detector) script="Agents/AnomalyDetector/build.sh" ;;
    database-job) script="EvaluationPlatform/Orchestrator/Database/build.sh" ;;
    runner) script="EvaluationPlatform/Runner/scripts/build.sh" ;;
    *) echo "Error: unknown component '$component'." >&2; usage >&2; exit 2 ;;
  esac
  if [[ ! -f "$ROOT/$script" ]]; then
    echo "Error: missing $script." >&2
    exit 1
  fi
  scripts+=("$script")
done

for script in "${scripts[@]}"; do
  echo "Building and pushing: $script"
  bash "$ROOT/$script"
done
