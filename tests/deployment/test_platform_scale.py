"""Platform stop keeps both orchestrators explicit and leaves PostgreSQL running."""

import os
from pathlib import Path
import subprocess


WORKSPACE = Path(__file__).resolve().parents[2]


def test_platform_scale_checks_all_targets_and_stops_both_orchestrators(tmp_path):
    binary = tmp_path / 'bin'
    binary.mkdir()
    log = tmp_path / 'kubectl.log'
    kubectl = binary / 'kubectl'
    kubectl.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$KUBECTL_LOG"\n'
        'if [[ "$*" == "config current-context" ]]; then echo test-context; fi\n'
    )
    kubectl.chmod(0o755)
    result = subprocess.run(
        ['bash', str(WORKSPACE / 'scale.sh')],
        env={**os.environ, 'PATH': f'{binary}:{os.environ["PATH"]}', 'KUBECTL_LOG': str(log)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert len(calls) == 3
    expected = (
        'anomaly-detector agent-orchestrator evaluation-orchestrator rca-agent '
        'remediator-agent learning-agent mcp-tools-investigation mcp-tools-remediation'
    )
    assert calls[1] == f'--context test-context --namespace agents get deployment {expected}'
    assert calls[2] == f'--context test-context --namespace agents scale deployment {expected} --replicas=0'
