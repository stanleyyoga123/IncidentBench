#!/usr/bin/env bash
set -euo pipefail
if (( $# != 0 )); then
  echo "Usage: $0" >&2
  exit 2
fi
runner_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${runner_root}${PYTHONPATH:+:${PYTHONPATH}}"
if [[ -n "${KUBERNETES_SERVICE_HOST:-}" ]]; then
  exec python -m hooks.reset_evaluation_lock --current-owner
fi
# Execute the local recovery implementation inside the existing runner pod.
# Credentials stay in the pod; no rebuild, copied Secrets, or port-forward needed.
exec python - "$runner_root" <<'PY'
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
try:
    context = subprocess.check_output(['kubectl', 'config', 'current-context'], text=True).strip()
    if not context:
        raise ValueError('kubectl has no current context')
    runtime = (root / 'hooks/runtime.py').read_text()
    recovery = (root / 'hooks/reset_evaluation_lock.py').read_text()
    remote_root = '/workspace/EvaluationPlatform/Runner'
    payload = (
        'import os, sys, types\n'
        f'os.chdir({remote_root!r})\n'
        'sys.path.insert(0, os.getcwd())\n'
        'import hooks\n'
        'runtime = types.ModuleType("hooks.runtime")\n'
        f'exec({runtime!r}, runtime.__dict__)\n'
        'sys.modules["hooks.runtime"] = runtime\n'
        'sys.argv = ["clear-lock.sh", "--current-owner"]\n'
        f'exec(compile({recovery!r}, "clear-lock.sh", "exec"), '
        f'{{"__name__": "__main__", "__file__": {str(Path(remote_root)/"hooks/reset_evaluation_lock.py")!r}}})\n'
    )
    print(f'Clearing evaluation ownership via {context}: agents/evaluation-runner', flush=True)
    result = subprocess.run(['kubectl', '--context', context, '-n', 'agents', 'exec', '-i',
                             'evaluation-runner', '--', 'python', '-'], input=payload, text=True)
    raise SystemExit(result.returncode)
except (OSError, ValueError, subprocess.CalledProcessError) as exc:
    print(f'Cannot clear evaluation lock: {exc}', file=sys.stderr)
    raise SystemExit(1)
PY
