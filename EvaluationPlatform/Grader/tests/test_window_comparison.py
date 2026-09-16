import csv
import json
import pytest
from grader.window_comparison import compare_windows, time_average
from test_archive_metrics import archive
from test_research import stamp, write


def fixture(root):
    path = archive(root)
    m = json.loads((root/'metadata.json').read_text())
    m['chaos_steps'][0]['cleanup_started_at'] = stamp(900)
    write(root/'metadata.json', m)
    p = root/'metrics/response_time_p95_seconds.json'
    data = json.loads(p.read_text())
    for series in data['data']['result']:
        series['values'] = [[1700000000+t, .1 if t <= 300 else .8 if t <= 600 else .2] for t in range(0, 901, 15)]
    write(p, data)
    write(root/'metrics/http_5xx_rate.json', data)
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    for t, row in enumerate(rows):
        total_ms = min(t, 300)*100 + max(0, min(t-300, 300))*800 + max(0, t-600)*200
        row['Total Average Response Time'] = total_ms/t if t else 0
    with path.open('w', newline='') as handle:
        w = csv.DictWriter(handle, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def test_hand_calculated_values(tmp_path):
    fixture(tmp_path)
    result = compare_windows(tmp_path)
    assert result['candidate_windows'] == 21
    assert result['status'] == 'evaluable'
    for row in result['rows']:
        assert row['baseline']['value'] == pytest.approx(.1)
        assert row['best']['value'] == pytest.approx(.2)
        assert row['best']['start'] == stamp(600)
        assert row['worst']['value'] == pytest.approx(.8)
        assert row['worst']['start'] == stamp(300)
        assert row['worst']['relative_change'] == pytest.approx(7)


def test_duration_and_cleanup(tmp_path):
    fixture(tmp_path)
    result = compare_windows(tmp_path, 10)
    assert result['candidate_windows'] == 1
    assert result['rows'][0]['best']['value'] == pytest.approx(.5)
    assert compare_windows(tmp_path, 11)['status'] == 'not_evaluable'
    m = json.loads((tmp_path/'metadata.json').read_text())
    m['chaos_steps'][0]['cleanup_started_at'] = stamp(600)
    write(tmp_path/'metadata.json', m)
    result = compare_windows(tmp_path)
    assert result['candidate_windows'] == 1
    assert result['rows'][0]['best']['value'] == pytest.approx(.8)


def test_gaps():
    assert time_average([(15, 1), (300, 1)], 0, 300, 15)['value'] is None


def test_missing_metrics_and_cleanup(tmp_path):
    fixture(tmp_path)
    (tmp_path/'metrics/http_5xx_rate.json').unlink()
    result = compare_windows(tmp_path)
    assert result['status'] == 'partially_evaluable'
    row = next(r for r in result['rows'] if r['metric'] == 'http_5xx_rate')
    assert row['baseline']['value'] is None and row['best'] is None
    m = json.loads((tmp_path/'metadata.json').read_text())
    del m['chaos_steps'][0]['cleanup_started_at']
    write(tmp_path/'metadata.json', m)
    assert compare_windows(tmp_path)['candidate_windows'] == 0


def test_idle_gap(tmp_path):
    fixture(tmp_path)
    m = json.loads((tmp_path/'metadata.json').read_text())
    m['chaos_steps'] = [
        {'chaos':['cpu'], 'active_started_at':stamp(300), 'cleanup_started_at':stamp(500)},
        {'chaos':['cpu'], 'active_started_at':stamp(600), 'cleanup_started_at':stamp(900)}]
    write(tmp_path/'metadata.json', m)
    result = compare_windows(tmp_path)
    assert result['candidate_windows'] == 1
    assert result['rows'][0]['worst']['start'] == stamp(600)


def test_zero_baseline_and_ties(tmp_path):
    fixture(tmp_path)
    p = tmp_path/'metrics/http_5xx_rate.json'
    data = json.loads(p.read_text())
    for series in data['data']['result']:
        series['values'] = [[t, 0 if t <= 1700000300 else 1] for t, v in series['values']]
    write(p, data)
    row = next(r for r in compare_windows(tmp_path)['rows'] if r['metric'] == 'http_5xx_rate')
    assert row['best']['absolute_change'] == 1
    assert row['best']['relative_change'] is None
    assert row['best']['start'] == row['worst']['start'] == stamp(300)


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf')])
def test_invalid_configuration(value, tmp_path):
    with pytest.raises(ValueError):
        compare_windows(tmp_path, value)


def test_pipeline_reports(tmp_path):
    from grader.pipeline import GraderConfig, grade_runs
    from test_grader import _write_run, _write_jobs
    root = tmp_path/'results/run'; _write_run(root); _write_jobs(root); fixture(root)
    output = tmp_path/'grades'
    result = grade_runs(GraderConfig(input_path=root, output_path=output, operational_only=True, comparison_window_minutes=10), None)
    assert result[0]['window_comparison']['window_seconds'] == 600
    assert 'Baseline versus sliding chaos windows' in (output/'runs/run/report.md').read_text()
    with (output/'csvs/window_comparison.csv').open() as handle:
        rows = list(csv.DictReader(handle))
    assert float(rows[0]['baseline']) == pytest.approx(.1)
    assert float(rows[0]['value']) == pytest.approx(.5)
    assert json.loads((output/'runs/run/grade.json').read_text())['window_comparison']['candidate_windows'] == 1
