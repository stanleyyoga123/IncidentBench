import csv
import json
from copy import deepcopy

import pytest

from grader.scenario_table import COLUMNS, table_row, write_scenario_table
from grader.window_comparison import compare_windows, paired_frontend_window
from test_window_comparison import fixture
from test_research import stamp, write


def frontend(root, p95=None, errors=None):
    fixture(root)
    for metric, value in [('response_time_p95_seconds', p95), ('http_5xx_rate', errors), ('traffic_rps', None)]:
        path = root / 'metrics' / (metric + '.json')
        data = json.loads(path.read_text())
        data['data']['result'] = data['data']['result'][:1]
        series = data['data']['result'][0]
        series['metric']['destination_workload'] = 'front-end'
        if value:
            series['values'] = [[1700000000 + t, value(t)] for t in range(0, 901, 15)]
        write(path, data)


def paired(root, minutes=5, **kwargs):
    kwargs.setdefault("baseline_ignore_minutes", 0)
    return paired_frontend_window(root, compare_windows(root, minutes), **kwargs)


def test_pair_uses_same_window_and_threshold(tmp_path):
    frontend(tmp_path, p95=lambda t: .1 if t <= 600 else .2,
             errors=lambda t: 0 if t <= 300 else 1 if t <= 600 else 0)
    r = paired(tmp_path)
    assert r['baseline']['p95_seconds'] == pytest.approx(.1)
    assert r['baseline']['http_5xx_rps'] == 0
    # Lowest latency alone would choose 300..600 with errors=1. The threshold
    # permits 450..750, where half the window has .1/1 and half has .2/0.
    assert r['best']['start'] == stamp(450)
    assert r['best']['end'] == stamp(750)
    assert r['best']['p95_seconds'] == pytest.approx(.15)
    assert r['best']['http_5xx_rps'] == pytest.approx(.5)


def test_ties_choose_earliest_not_lowest_error(tmp_path):
    frontend(tmp_path, p95=lambda t: .1,
             errors=lambda t: .4 if t <= 600 else .1)
    assert paired(tmp_path)['best']['start'] == stamp(300)


def test_no_threshold_candidate_is_unknown_not_fallback(tmp_path):
    frontend(tmp_path, errors=lambda t: 0 if t <= 300 else .6)
    r = paired(tmp_path)
    assert r['best'] is None
    assert r['baseline']['http_5xx_rps'] == 0
    assert r['covered_windows'] == 21 and r['eligible_windows'] == 0
    assert 'threshold' in r['reason']


def test_gap_missing_series_and_ambiguous_namespace(tmp_path):
    frontend(tmp_path)
    p = tmp_path / 'metrics/http_5xx_rate.json'
    data = json.loads(p.read_text())
    series = data['data']['result'][0]
    series['values'] = [v for v in series['values'] if v[0] <= 1700000300]
    write(p, data)
    r = paired(tmp_path)
    assert r['best'] is not None and r['covered_windows'] == 21
    assert r['best']['http_5xx_imputed_samples'] == 20
    other = deepcopy(series)
    other['metric']['destination_workload_namespace'] = 'other'
    data['data']['result'].append(other)
    write(p, data)
    assert 'ambiguous' in paired(tmp_path)['reason']
    assert paired(tmp_path, namespace='sock-shop')['namespace'] == 'sock-shop'
    p.unlink()
    r = paired(tmp_path)
    assert r['best'] is None
    assert r['baseline']['p95_seconds'] is not None
    assert r['baseline']['http_5xx_rps'] is None


def test_pair_respects_idle_cleanup_and_window_duration(tmp_path):
    frontend(tmp_path, errors=lambda t: 0)
    assert paired(tmp_path, 10)['candidate_windows'] == 1
    assert paired(tmp_path, 11)['best'] is None
    m = json.loads((tmp_path/'metadata.json').read_text())
    m['chaos_steps'] = [
        {'chaos': ['cpu'], 'active_started_at': stamp(300), 'cleanup_started_at': stamp(500)},
        {'chaos': ['cpu'], 'active_started_at': stamp(600), 'cleanup_started_at': stamp(900)},
    ]
    write(tmp_path/'metadata.json', m)
    r = paired(tmp_path)
    assert r['candidate_windows'] == 1
    assert r['best']['start'] == stamp(600)
    assert r['best']['end'] == stamp(900)


@pytest.mark.parametrize('threshold', [-1, float('nan'), float('inf')])
def test_invalid_threshold(tmp_path, threshold):
    with pytest.raises(ValueError, match='5xx'):
        paired_frontend_window(tmp_path, {}, max_5xx_rate=threshold)


def test_scores_counts_penalties_and_exact_columns(tmp_path):
    def job(status, score, verdict='aligned'):
        return {'status': status, 'alignment': {'verdict': verdict},
                'rubric': {'overall_score': score, 'rubric_score': 1}}
    g = {'run': 'run', 'scenario': 'scenario',
         'rca_jobs': [job('succeeded', .8), job('failed', .4), job('running', None)],
         'remediation_jobs': [job('failed', 0), job('succeeded', .6),
                              job('failed', 1, 'not_evaluable')]}
    row = table_row(g)
    assert row['max_rca_score'] == .8
    assert row['mean_rca_score'] == pytest.approx(.6)
    assert row['rca_sessions'] == row['remediation_sessions'] == 3
    assert row['mean_remediation_score'] == .3
    assert row['max_remediation_score'] == .6
    assert row['best_p95_seconds'] is row['best_5xx_rps'] is None
    write_scenario_table(tmp_path, [g, {**g, 'run': 'repeat'}])
    with (tmp_path/'scenario_table.csv').open() as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == [title for _, title in COLUMNS]
        assert len(reader.fieldnames) == 18
        assert len(list(reader)) == 2
    saved = json.loads((tmp_path/'scenario_table.json').read_text())
    assert saved['runs'][0]['remediation']['scored'] == 2
    before = (tmp_path/'scenario_table.md').read_bytes()
    write_scenario_table(tmp_path, [g, {**g, 'run': 'repeat'}])
    assert (tmp_path/'scenario_table.md').read_bytes() == before
    assert table_row({'run': 'empty'})['mean_rca_score'] is None


def test_pipeline_writes_table_with_zero_judge_calls(tmp_path):
    from grader.pipeline import GraderConfig, grade_runs
    from test_grader import _write_run, _write_jobs, StaticJudge
    root = tmp_path/'results/run'
    _write_run(root); _write_jobs(root); frontend(root, errors=lambda t: 0)
    judge = StaticJudge()
    out = tmp_path/'grades'
    grades = grade_runs(GraderConfig(input_path=root, output_path=out, operational_only=True, baseline_ignore_minutes=0), judge)
    assert not judge.calls and not judge.penalty_calls
    assert grades[0]['paired_window']['status'] == 'evaluable'
    assert (out/'csvs/scenario_table.csv').exists()
    assert not (out/'report.md').exists()
    assert {p.name for p in out.iterdir()} == {'runs', 'logs', 'csvs'}
    assert {p.name for p in (out/'csvs').iterdir()} == {'summary.csv', 'rca_rubric_score.csv', 'remediation_rubric_score.csv', 'window_comparison.csv', 'scenario_table.csv'}


def test_baseline_ignores_warmup_and_chaos_covers_full_hour(tmp_path):
    frontend(tmp_path)
    metadata = json.loads((tmp_path/'metadata.json').read_text())
    metadata['baseline_seconds'] = 1800
    metadata['metrics']['end'] = stamp(5400)
    metadata['chaos_steps'] = [{'chaos': ['cpu'], 'active_started_at': stamp(1800),
                                'cleanup_started_at': stamp(5400)}]
    write(tmp_path/'metadata.json', metadata)
    for name in ('response_time_p95_seconds', 'http_5xx_rate'):
        path = tmp_path/'metrics'/f'{name}.json'
        data = json.loads(path.read_text())
        values = []
        for t in range(0, 5401, 15):
            if name == 'response_time_p95_seconds':
                value = 9 if t <= 300 else .2 if t <= 1800 else 2 if t <= 2100 else .1 if t > 5100 else .5
            else:
                value = 3 if t <= 300 else .1 if t <= 1800 else 1 if t <= 2100 else .2
            values.append([1700000000 + t, value])
        data['data']['result'][0]['values'] = values
        write(path, data)
    comparison = compare_windows(tmp_path)
    r = paired_frontend_window(tmp_path, comparison)
    assert r['baseline']['start'] == stamp(300)
    assert r['baseline']['end'] == stamp(1800)
    assert r['baseline']['p95_seconds'] == pytest.approx(.2)
    assert r['baseline']['http_5xx_rps'] == pytest.approx(.1)
    assert r['candidate_windows'] == 221
    assert r['best']['start'] == stamp(5100)
    assert r['best']['end'] == stamp(5400)
    assert r['worst']['start'] == stamp(1800)
    assert r['worst']['p95_seconds'] == pytest.approx(2)
    assert r['worst']['http_5xx_rps'] == pytest.approx(1)  # Worst ignores best's ceiling.
    full = paired_frontend_window(tmp_path, comparison, baseline_ignore_minutes=0)
    assert full['baseline']['p95_seconds'] == pytest.approx((9 * 300 + .2 * 1500) / 1800)
    write(tmp_path/'sessions/remediation_run.json', [{'status': 'failed', 'completed_at': stamp(5200)}])
    assert paired_frontend_window(tmp_path, compare_windows(tmp_path)) == r


def test_missing_baseline_does_not_block_best_or_worst(tmp_path):
    frontend(tmp_path, errors=lambda t: .2)
    path = tmp_path/'metrics/http_5xx_rate.json'
    data = json.loads(path.read_text())
    data['data']['result'][0]['values'] = [v for v in data['data']['result'][0]['values'] if v[0] > 1700000300]
    write(path, data)
    r = paired(tmp_path)
    assert r['baseline']['http_5xx_rps'] == 0
    assert r['baseline']['http_5xx_imputed_samples'] == 20
    assert r['best'] is not None and r['worst'] is not None
    assert r['status'] == 'evaluable'
    # Excluding the entire short fixture baseline must also preserve chaos windows.
    empty = paired(tmp_path, baseline_ignore_minutes=5)
    assert empty['baseline'] is None and empty['best'] is not None
    assert 'no baseline interval' in empty['baseline_reason']


@pytest.mark.parametrize('minutes', [-1, float('nan'), float('inf')])
def test_invalid_baseline_exclusion(tmp_path, minutes):
    with pytest.raises(ValueError, match='baseline ignore'):
        paired_frontend_window(tmp_path, {}, baseline_ignore_minutes=minutes)


def test_absent_5xx_series_is_zero_with_recorded_traffic(tmp_path):
    frontend(tmp_path)
    write(tmp_path/'metrics/http_5xx_rate.json', {'status': 'success', 'data': {'result': []}})
    r = paired(tmp_path)
    assert r['baseline']['http_5xx_rps'] == 0
    assert r['best']['http_5xx_rps'] == r['worst']['http_5xx_rps'] == 0
    assert r['best']['http_5xx_imputed_samples'] == 20
    row = table_row({'run': 'run', 'paired_window': r})
    assert row['baseline_5xx_imputed_samples'] == 20
    comparison = compare_windows(tmp_path)
    error_row = next(r for r in comparison['rows'] if r['metric'] == 'http_5xx_rate')
    assert error_row['baseline']['value'] == error_row['best']['value'] == 0
    assert error_row['best']['imputed_samples'] == 20


def test_zero_imputation_does_not_fill_traffic_gaps_or_nonfinite_errors(tmp_path):
    frontend(tmp_path)
    write(tmp_path/'metrics/http_5xx_rate.json', {'status': 'success', 'data': {'result': []}})
    path = tmp_path/'metrics/traffic_rps.json'
    d = json.loads(path.read_text())
    d['data']['result'][0]['values'] = [v for v in d['data']['result'][0]['values'] if v[0] <= 1700000300]
    write(path, d)
    assert paired(tmp_path)['best'] is None
    frontend_dir = tmp_path/'other'; frontend_dir.mkdir(); frontend(frontend_dir)
    path = frontend_dir/'metrics/http_5xx_rate.json'
    d = json.loads(path.read_text())
    d['data']['result'][0]['values'] = [[t, 'NaN'] for t, _ in d['data']['result'][0]['values']]
    write(path, d)
    assert paired(frontend_dir)['best'] is None
