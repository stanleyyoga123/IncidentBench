import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hooks.lifecycle import Lifecycle
from testbed.artifacts.configuration_snapshot import capture, archive
from testbed.configuration import ROOT, environment, resolve_scenario
from testbed.platform import run_one

SOURCE = ROOT / 'resources/scenarios/online-boutique-scenario/01-node-delay-worker-3.json'


def test_config_snapshot_keeps_original_layers_and_hashes_without_process_secrets(tmp_path, monkeypatch):
    documents = []
    spec = resolve_scenario(SOURCE, {'schema_version': 1, 'load': {'parameters': {'users': 77}}}, documents=documents)
    environment(ROOT / 'config/environment.example.json', documents=documents)
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret-not-to-archive')
    files = capture(ROOT, spec, documents)
    archive(tmp_path, files, {'run_index': 2, 'run_count': 3})
    manifest = json.loads((tmp_path / 'inputs/manifest.json').read_text())
    assert manifest['invocation']['run_index'] == 2
    for entry in manifest['files']:
        data = (tmp_path / entry['archive']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry['sha256']
        assert b'secret-not-to-archive' not in data
    assert (tmp_path / 'inputs/source/configuration/global.json').is_file()
    raw = json.loads((tmp_path / 'inputs/source/configuration/scenario.json').read_text())
    assert raw['global_config']
    assert spec['load']['parameters']['users'] == 77
    assert (tmp_path / 'inputs/source/hooks/postrun/upload/run.sh').is_file()
    assert (tmp_path / 'inputs/source/resources/applications/online-boutique/profile.yaml').is_file()


def test_input_and_live_status_exist_before_failed_preparation(tmp_path):
    documents = []
    spec = resolve_scenario(SOURCE, documents=documents)
    output = tmp_path / 'run'
    class FailedLifecycle:
        def __init__(self, *args): pass
        def integration(self, action):
            assert action == 'prepare'
            assert (output / 'inputs/manifest.json').is_file()
            status = json.loads((output / 'run-status.json').read_text())
            assert status['status'] == 'preparing'
            assert status['started_at']
            raise RuntimeError('owned by another run')
    with patch('testbed.platform.Lifecycle', FailedLifecycle), patch('testbed.platform.run_script') as cleanup:
        code, safe = run_one(spec, {}, output, lambda _: pytest.fail('must not execute'),
                             snapshot=capture(ROOT, spec, documents))
    cleanup.assert_not_called()
    assert code == 1 and not safe
    status = json.loads((output / 'run-status.json').read_text())
    assert status['status'] == 'failed' and status['finished_at'] and status['returncode'] == 1
    assert [json.loads(line)['phase'] for line in (output / 'events.jsonl').read_text().splitlines()] == ['preparing', 'finalizing', 'failed']


def test_hook_is_visible_while_running_and_records_failure(tmp_path):
    context = tmp_path / 'run-context.json'
    context.write_text(json.dumps({'scenario': {}}))
    def failing_hook(command, **kwargs):
        records = json.loads((tmp_path / 'hooks.json').read_text())
        assert records[0]['status'] == 'running'
        assert records[0]['started_at']
        assert (tmp_path / records[0]['log']).exists()
        return SimpleNamespace(returncode=9)
    lifecycle = Lifecycle(ROOT, context, tmp_path, run=failing_hook)
    with pytest.raises(RuntimeError):
        lifecycle.invoke('postrun', 'upload')
    records = json.loads((tmp_path / 'hooks.json').read_text())
    assert records[0]['status'] == 'failed' and records[0]['returncode'] == 9
    assert records[0]['finished_at']
    assert len((tmp_path / 'events.jsonl').read_text().splitlines()) == 2


def test_suite_snapshot_preserves_overrides_and_run_position(tmp_path):
    from testbed.cli import parse_args
    from testbed.platform import run
    suite = tmp_path / 'suite.json'
    suite.write_text(json.dumps({'schema_version': 1, 'name': 'visibility-test', 'inter_run_seconds': 0, 'runs': [
        {'scenario': str(SOURCE), 'overrides': {'agents_enabled': False}},
        {'scenario': str(SOURCE), 'overrides': {'agents_enabled': True}},
    ]}))
    args = parse_args(['--suite', str(suite), '--environment', str(ROOT / 'config/environment.example.json'),
                       '--output-dir', str(tmp_path / 'results')])
    with patch('testbed.platform.preflight'), patch('testbed.platform.run_one', return_value=(0, True)) as execute:
        assert run(args, lambda _: 0) == 0
    assert execute.call_count == 2
    for index, call in enumerate(execute.call_args_list, 1):
        assert call.kwargs['invocation']['run_index'] == index
        archived = json.loads(call.kwargs['snapshot']['configuration/suite.json'][1])
        assert len(archived['runs']) == 2
        assert call.args[0]['agents_enabled'] == (index == 2)
