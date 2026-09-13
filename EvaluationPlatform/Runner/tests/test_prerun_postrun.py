import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hooks.runtime import api, main, scale
from hooks.lifecycle import Lifecycle

ROOT = Path(__file__).resolve().parents[1]


def context(tmp_path):
    value = {'schema_version':1, 'run_id':'test-run', 'environment':{'orchestrator_url':'http://orchestrator', 'control_token_env':'TEST_CONTROL_TOKEN'}, 'scenario':{'integration':'example','deployments':[], 'prerun':['one','two'], 'postrun':['one','two']}}
    path = tmp_path / 'context.json'; path.write_text(json.dumps(value))
    return value, path


def test_named_hooks_are_ordered_and_postrun_continues_after_failure(tmp_path):
    _, path = context(tmp_path)
    calls = []
    def run(command, **kwargs):
        assert Path(command[1]).is_relative_to(ROOT / "hooks")
        calls.append(Path(command[1]).parent.name)
        return SimpleNamespace(returncode=1 if calls[-1]=='one' else 0)
    hooks = Lifecycle(ROOT, path, tmp_path, run=run)
    with pytest.raises(RuntimeError):
        hooks.hooks('prerun')
    assert calls == ['one']
    calls.clear()
    assert len(hooks.hooks('postrun', continue_on_error=True)) == 1
    assert calls == ['one','two']
    assert len(json.loads((tmp_path/'hooks.json').read_text())) == 3


def test_export_writes_compatible_files_without_credentials(tmp_path, monkeypatch):
    value, path = context(tmp_path)
    names = ('anomaly','rca_session','remediation_run','remediation_session','learning_session','workflow')
    response = {'schema_version':1, 'run_id':'test-run', 'sessions':{name:[] for name in names}}
    monkeypatch.setattr('sys.argv', ['helper','api-export',str(path),str(tmp_path)])
    with patch('hooks.runtime.api', return_value=response):
        main()
    assert sorted(p.stem for p in (tmp_path/'sessions').glob('*.json')) == sorted(names)
    assert all(json.loads(p.read_text()) == [] for p in (tmp_path/'sessions').glob('*.json'))


def test_api_uses_control_token_header_and_requires_it(tmp_path, monkeypatch):
    value, _ = context(tmp_path)
    monkeypatch.delenv('TEST_CONTROL_TOKEN', raising=False)
    with pytest.raises(ValueError, match='token'):
        api(value,'reset')
    monkeypatch.setenv('TEST_CONTROL_TOKEN','unit-test-token')
    with patch('hooks.runtime.urlopen') as open_url:
        open_url.return_value.__enter__.return_value.read.return_value = b'{}'
        api(value,'reset')
    request = open_url.call_args.args[0]
    assert request.headers['Authorization'] == 'Bearer unit-test-token'
    assert json.loads(request.data) == {'run_id':'test-run'}
    assert 'unit-test-token' not in request.full_url


def test_scale_waits_until_terminating_pods_are_gone(tmp_path):
    value, _ = context(tmp_path)
    value['scenario']['deployments'] = [{'namespace':'custom','name':'researcher-agent','replicas':3}]
    calls, sleeps = [], []
    pod_results = iter([{'items':[{'metadata':{'deletionTimestamp':'now'}}]}, {'items':[]}])
    def run(command, **kwargs):
        calls.append(command)
        if 'pods' in command:
            result = next(pod_results)
        else:
            result = {'spec':{'replicas':0, 'selector':{'matchLabels':{'app':'researcher-agent'}}}}
        return SimpleNamespace(stdout=json.dumps(result),returncode=0)
    scale(value, False, run=run, sleep=sleeps.append)
    assert sleeps == [2]
    scale(value, True, run=run, sleep=sleeps.append)
    assert any('--replicas=3' in command for command in calls)


def test_runner_contains_no_workflow_sql_or_database_client():
    for root in ('testbed','hooks'):
        for path in (ROOT/root).rglob('*'):
            if path.suffix in ('.py','.sh','.sql'):
                text = path.read_text()
                assert 'psycopg' not in text
                assert 'TRUNCATE ' not in text
                assert 'psql ' not in text


def test_upload_syncs_only_the_run_directory(tmp_path, monkeypatch):
    value, path = context(tmp_path)
    value['environment']['s3_results_uri'] = 's3://example-bucket/experiments/'
    path.write_text(json.dumps(value))
    monkeypatch.setattr('sys.argv', ['helper', 'upload', str(path), str(tmp_path)])
    with patch('hooks.runtime.subprocess.run') as execute:
        main()
    execute.assert_called_once_with(
        ['aws', 's3', 'sync', str(tmp_path) + '/',
         's3://example-bucket/experiments/' + tmp_path.name + '/',
         '--only-show-errors'], check=True)


def test_upload_skips_unconfigured_destination(tmp_path, monkeypatch, capsys):
    _, path = context(tmp_path)
    monkeypatch.setattr('sys.argv', ['helper', 'upload', str(path), str(tmp_path)])
    with patch('hooks.runtime.subprocess.run') as execute:
        main()
    execute.assert_not_called()
    assert 'S3 sync skipped' in capsys.readouterr().out


def test_upload_propagates_aws_failure(tmp_path, monkeypatch):
    import subprocess
    value, path = context(tmp_path)
    value['environment']['s3_results_uri'] = 's3://example-bucket/experiments'
    path.write_text(json.dumps(value))
    monkeypatch.setattr('sys.argv', ['helper', 'upload', str(path), str(tmp_path)])
    with patch('hooks.runtime.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'aws')):
        with pytest.raises(subprocess.CalledProcessError):
            main()
