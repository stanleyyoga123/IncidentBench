import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from testbed.configuration import ROOT, resolve_scenario
from testbed.kubernetes.node_cleanup import uncordon_placement_nodes
from testbed.platform import run_one


def targets(output):
    path = output / 'inputs/placement/nodes.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(['worker-node-2', 'worker-node-1']))


@pytest.mark.parametrize('failure', [None, 'uncordon', 'verify', 'timeout'])
def test_uncordon_is_scoped_verified_and_continues_after_failure(tmp_path, failure):
    targets(tmp_path)
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        if command == ['kubectl', 'uncordon', 'worker-node-1'] and failure == 'timeout':
            raise TimeoutError('node command timed out')
        failed = failure == 'uncordon' and command == ['kubectl', 'uncordon', 'worker-node-1']
        return SimpleNamespace(returncode=1 if failed else 0, stderr='', stdout=json.dumps({
            'spec': {'unschedulable': failure == 'verify' and 'worker-node-1' in command},
        }))
    report = uncordon_placement_nodes(tmp_path, run=run)
    assert report['returncode'] == (1 if failure else 0)
    assert set(report['nodes']) == {'worker-node-1', 'worker-node-2'}
    assert report['nodes']['worker-node-2']['status'] == 'completed'
    assert ['kubectl', 'get', 'node', 'worker-node-2', '-o', 'json'] in commands
    assert json.loads((tmp_path / 'node-cleanup.json').read_text()) == report


def test_unresolved_placement_does_not_guess_cluster_nodes(tmp_path):
    with patch('subprocess.run') as run:
        report = uncordon_placement_nodes(tmp_path, run=run)
    run.assert_not_called()
    assert report['status'] == 'skipped'


@pytest.mark.parametrize('failure', [None, 'execution', 'interrupted', 'stop', 'chaos', 'uncordon', 'acquire'])
def test_final_uncordon_order_and_safety_gates(tmp_path, failure):
    spec = resolve_scenario(ROOT / 'resources/scenarios/online-boutique-scenario/01-node-delay-worker-3.json')
    spec['integration'] = 'bundled' if failure == 'acquire' else 'example'
    order = []
    class Lifecycle:
        def __init__(self, *args): pass
        def integration(self, action):
            order.append(action)
            if (action == 'prepare' and failure == 'acquire') or (action == 'stop' and failure == 'stop'):
                raise RuntimeError(action + ' failed')
        def hooks(self, phase, **kwargs):
            order.append(phase)
            return []
    def execute(args):
        targets(args.output_dir)
        if failure == 'execution': raise RuntimeError('execution failed')
        if failure == 'interrupted': raise KeyboardInterrupt()
        return 0
    def chaos(*args, **kwargs):
        order.append('chaos')
        return SimpleNamespace(returncode=1 if failure == 'chaos' else 0)
    def uncordon(output):
        order.append('uncordon')
        return {'status': 'failed' if failure == 'uncordon' else 'completed', 'returncode': int(failure == 'uncordon')}
    with patch('testbed.platform.Lifecycle', Lifecycle), patch('testbed.platform.run_script', chaos), patch('testbed.platform.uncordon_placement_nodes', uncordon):
        code, safe = run_one(spec, {'port_forward': False, 'port_forward_port': 8888}, tmp_path / 'run', execute)
    if failure in ('stop', 'chaos', 'acquire'):
        assert 'uncordon' not in order
    else:
        assert order.index('stop') < order.index('chaos') < order.index('uncordon') < order.index('postrun')
    if failure:
        assert code != 0 and not safe
        assert 'release' not in order
    else:
        assert code == 0 and safe and order[-1] == 'release'
    if failure == 'uncordon':
        status = json.loads((tmp_path / 'run/run-status.json').read_text())
        assert status['cleanup_safe'] is False
