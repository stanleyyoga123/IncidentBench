import os
from pathlib import Path
import shutil
import subprocess

import pytest

WORKSPACE = Path(__file__).resolve().parents[3]
COMPONENTS = ['Agents/MCPTools', 'Agents/LearningAgent', 'Agents/RCAAgent',
              'Agents/RemediatorAgent', 'EvaluationPlatform/Orchestrator', 'Agents/AnomalyDetector']


def fixture_workspace(tmp_path):
    root = tmp_path / 'workspace'
    root.mkdir()
    shutil.copyfile(WORKSPACE / 'deploy.sh', root / 'deploy.sh')
    (root / 'deployment').mkdir()
    shutil.copyfile(WORKSPACE / 'deployment/image_config.sh', root / 'deployment/image_config.sh')
    for component in COMPONENTS:
        folder = root / component
        (folder / 'kubernetes').mkdir(parents=True)
        (folder / 'kubernetes/secret.yml').write_text('test-only-secret')
        (folder / 'kubernetes/configmap.yaml').write_text('test config')
        (folder / 'deploy.sh').write_text(
            '#!/usr/bin/env bash\nset -eu\n'
            f'echo "deploy {component}" >> "$LOG"\n'
            f'if [[ "${{FAIL_COMPONENT:-}}" == "{component}" ]]; then exit 22; fi\n')
    binary = tmp_path / 'bin'
    binary.mkdir()
    kubectl = binary / 'kubectl'
    kubectl.write_text('#!/usr/bin/env bash\nset -eu\n'
                       'echo "kubectl $*" >> "$LOG"\n'
                       'if [[ "$*" == "config current-context" ]]; then echo test-cluster; fi\n')
    kubectl.chmod(0o755)
    log = tmp_path / 'commands'
    env = {
        **os.environ,
        'PATH': str(binary) + ':' + os.environ['PATH'],
        'LOG': str(log),
        'IMAGE_REGISTRY': 'registry.example.test/team',
        'IMAGE_TAG': 'v1',
    }
    return root, log, env


def test_deploy_uses_component_owners_and_refreshes_all_agent_pods(tmp_path):
    root, log, env = fixture_workspace(tmp_path)
    result = subprocess.run(['bash', str(root / 'deploy.sh')], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    lines = log.read_text().splitlines()
    assert [line for line in lines if line.startswith('deploy ')] == ['deploy ' + component for component in COMPONENTS]
    workloads = ['mcp-tools-investigation', 'mcp-tools-remediation', 'learning-agent', 'rca-agent',
                 'remediator-agent', 'agent-orchestrator', 'anomaly-detector']
    for name in workloads:
        restart = f'kubectl rollout restart deployment/{name} --namespace agents'
        ready = f'kubectl rollout status deployment/{name} --namespace agents --timeout=5m'
        assert restart in lines and lines.index(ready) > lines.index(restart)
    assert not any('/Database' in line or '/Runner' in line for line in lines)


@pytest.mark.parametrize('bad_secret', ['missing', 'placeholder'])
def test_all_secrets_checked_before_any_component_deployment(tmp_path, bad_secret):
    root, log, env = fixture_workspace(tmp_path)
    secret = root / COMPONENTS[-1] / 'kubernetes/secret.yml'
    if bad_secret == 'missing': secret.unlink()
    else: secret.write_text('token: ++++++++')
    result = subprocess.run(['bash', str(root / 'deploy.sh')], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert not log.exists()
    assert 'test-only-secret' not in result.stdout + result.stderr


def test_component_failure_stops_later_deployments(tmp_path):
    root, log, env = fixture_workspace(tmp_path)
    env['FAIL_COMPONENT'] = 'Agents/RCAAgent'
    result = subprocess.run(['bash', str(root / 'deploy.sh')], env=env, capture_output=True, text=True)
    assert result.returncode == 22
    lines = log.read_text().splitlines()
    assert 'deploy Agents/RemediatorAgent' not in lines
    assert 'deploy Agents/AnomalyDetector' not in lines
    assert 'No automatic rollback' in result.stderr


@pytest.mark.parametrize(
    'settings',
    [
        {'IMAGE_REGISTRY': '', 'IMAGE_TAG': 'v1'},
        {'IMAGE_REGISTRY': 'registry.example.test/team', 'IMAGE_TAG': ''},
        {'IMAGE_REGISTRY': 'registry.example.test/team;bad', 'IMAGE_TAG': 'v1'},
        {'IMAGE_REGISTRY': 'registry.example.test/team', 'IMAGE_TAG': 'bad tag'},
    ],
)
def test_invalid_image_settings_stop_before_kubectl_or_component_deploy(tmp_path, settings):
    root, log, env = fixture_workspace(tmp_path)
    env.update(settings)

    result = subprocess.run(
        ['bash', str(root / 'deploy.sh')], env=env, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert 'IMAGE_' in result.stderr
    assert not log.exists()
