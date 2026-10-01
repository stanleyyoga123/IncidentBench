"""Verify pipeline selection and fail-fast behavior at the process boundary."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
APPS = ['online-boutique', 'sock-shop', 'teastore']


@pytest.fixture
def pipeline(tmp_path):
    root = tmp_path / 'checkout'
    root.mkdir()
    shutil.copyfile(ROOT / 'grade.sh', root / 'grade.sh')
    for app in APPS:
        (root / 'results' / app).mkdir(parents=True)
    fake_python = tmp_path / 'record-python'
    fake_python.write_text(
        f'#!{sys.executable}\n' +
        (ROOT / 'tests/fixtures/pipeline/record_python.py').read_text()
    )
    fake_python.chmod(0o755)
    log = tmp_path / 'calls.jsonl'
    environment = {**os.environ, 'PYTHON': str(fake_python), 'PIPELINE_CALL_LOG': str(log)}
    return root, log, environment


def run_pipeline(pipeline, *arguments, fail_module=None):
    root, log, environment = pipeline
    if fail_module:
        environment = {**environment, 'PIPELINE_FAIL_MODULE': fail_module}
    result = subprocess.run(
        ['bash', str(root / 'grade.sh'), *arguments], cwd=root.parent,
        env=environment, text=True, capture_output=True,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return result, calls


def option(call, name):
    return call[call.index(name) + 1]


def test_default_pipeline_visualizes_then_grades_three_apps_then_reports(pipeline):
    root, _, _ = pipeline
    result, calls = run_pipeline(pipeline, '--', '--operational-only')
    assert result.returncode == 0, result.stderr
    assert [call[1] for call in calls] == ['visualizer'] * 3 + ['grader'] * 3 + ['reporting.report']
    for index, app in enumerate(APPS):
        assert option(calls[index], '--input') == str(root / 'results' / app)
        assert option(calls[index + 3], '--input') == str(root / 'results' / app)
        assert option(calls[index], '--output') == str(root / 'output/visualizations' / app)
        assert option(calls[index + 3], '--output') == str(root / 'output/grades' / app)
        assert option(calls[index + 3], '--table-namespace') == app
        assert '--operational-only' in calls[index + 3]
    assert [option(call, '--table-workload') for call in calls[3:6]] == ['frontend', 'front-end', 'teastore-webui']
    assert calls[-1][calls[-1].index('--apps') + 1:] == APPS
    assert option(calls[-1], '--output') == str(root / 'output/report/report.md')


def test_selected_apps_and_fresh_output_root_apply_to_all_stages(pipeline):
    root, _, _ = pipeline
    result, calls = run_pipeline(pipeline, '--apps', 'teastore', '--output-root', 'fresh',
                                 '--', '--comparison-window-minutes', '3',
                                 '--baseline-ignore-minutes=0', '--table-max-5xx-rate', '0.2')
    assert result.returncode == 0, result.stderr
    assert [call[1] for call in calls] == ['visualizer', 'grader', 'reporting.report']
    assert option(calls[0], '--output') == str(root.parent / 'fresh/visualizations/teastore')
    assert option(calls[1], '--output') == str(root.parent / 'fresh/grades/teastore')
    assert option(calls[2], '--output') == str(root.parent / 'fresh/report/report.md')
    assert calls[-1][calls[-1].index('--apps') + 1] == 'teastore'
    assert option(calls[-1], '--window-minutes') == '3'
    assert option(calls[-1], '--baseline-ignore-minutes') == '0'
    assert option(calls[-1], '--max-5xx-rps') == '0.2'


def test_input_directory_resolves_from_callers_working_directory(pipeline):
    root, _, _ = pipeline
    result, calls = run_pipeline(pipeline, '--input', 'checkout/results/sock-shop/', '--', '--operational-only')
    assert result.returncode == 0, result.stderr
    assert option(calls[0], '--input') == str(root / 'results/sock-shop')
    assert option(calls[-1], '--results-dir') == str(root / 'results')
    assert calls[-1][-1] == 'sock-shop'


@pytest.mark.parametrize('module,expected', [('visualizer', ['visualizer']),
                                           ('grader', ['visualizer', 'grader'])])
def test_stage_failure_stops_pipeline_before_report(pipeline, module, expected):
    result, calls = run_pipeline(pipeline, '--apps', 'sock-shop', fail_module=module)
    assert result.returncode == 7
    assert [call[1] for call in calls] == expected


@pytest.mark.parametrize('arguments', [
    ['--', '-h'], ['--apps', 'unknown'], ['--apps'], ['--apps', 'teastore', '--input', 'somewhere'],
    ['--', '--input', '/tmp/other'], ['--', '--out=/tmp/other'],
    ['--', '--table-workload', 'other'], ['--', '--table-namespace=other'],
])
def test_invalid_or_desynchronizing_options_fail_before_processing(pipeline, arguments):
    result, calls = run_pipeline(pipeline, *arguments)
    assert result.returncode == 2
    assert calls == []


def test_missing_application_fails_preflight_before_visualization(pipeline):
    root, _, _ = pipeline
    (root / 'results/teastore').rmdir()
    result, calls = run_pipeline(pipeline)
    assert result.returncode == 2
    assert calls == []
