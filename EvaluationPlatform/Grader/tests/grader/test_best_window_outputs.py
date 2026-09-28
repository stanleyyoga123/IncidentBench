"""Offline contract tests for selected chaos-window measurements."""
import csv
import json
from datetime import datetime, timezone

import pytest

from grader.scenario_table import table_row, write_scenario_table
from grader.window_comparison import compare_windows, paired_frontend_window, write_comparisons


BASE = 1_700_000_000


def at(seconds):
    return datetime.fromtimestamp(BASE + seconds, timezone.utc).isoformat()


def archive(tmp_path, *, error_rate=0.1, missing_errors=False,
            p95_values=None, missing_baseline_p95=False):
    """Two-minute baseline and three-minute chaos at a 30-second scrape step."""
    root = tmp_path / 'run'
    metrics = root / 'metrics'
    metrics.mkdir(parents=True)
    (root / 'metadata.json').write_text(json.dumps({
        'metrics': {'start': at(0), 'end': at(300), 'step_seconds': 30},
        'baseline_seconds': 120,
        'phases': [{'name': 'baseline', 'status': 'completed'}],
        'chaos_steps': [{'chaos': ['fault'], 'active_started_at': at(120),
                         'cleanup_started_at': at(300)}],
    }))
    points = list(range(0, 301, 30))
    p95 = p95_values or [1, 1, 1, 1, 1, 1.3, 1.3, 1.1, 1.1, 1.8, 1.8]
    errors = [0] * 5 + [error_rate] * 6
    for name, values in [('response_time_p95_seconds', p95),
                         ('http_5xx_rate', errors),
                         ('traffic_rps', [10] * len(points))]:
        if missing_errors and name == 'http_5xx_rate':
            continue
        (metrics / f'{name}.json').write_text(json.dumps({'status': 'success', 'data': {'result': [{
            'metric': {'destination_workload_namespace': 'shop',
                       'destination_workload': 'front-end'},
            'values': [[BASE + second, str(value)] for second, value in zip(points, values)
                       if not (missing_baseline_p95 and name == 'response_time_p95_seconds'
                               and second <= 120)],
        }]}}))
    return root


def test_independent_and_paired_windows_select_lowest_covered_value(tmp_path):
    root = archive(tmp_path)

    comparison = compare_windows(root, 1)
    row = next(row for row in comparison['rows'] if row['metric'] == 'response_time_p95_seconds')
    paired = paired_frontend_window(root, comparison, 'front-end', 'shop', .5, 0)

    assert row['baseline']['value'] == pytest.approx(1)
    assert row['best']['value'] == pytest.approx(1.1)
    assert row['best']['start'] == at(180)
    assert row['best']['end'] == at(240)
    assert 'worst' not in row
    assert paired['status'] == 'evaluable'
    assert paired['candidate_windows'] == 5
    assert paired['covered_windows'] == paired['eligible_windows'] == 5
    assert paired['best']['p95_seconds'] == pytest.approx(1.1)
    assert paired['best']['http_5xx_rps'] == pytest.approx(.1)
    assert paired['best']['start'] == at(180)
    assert 'worst' not in paired


def test_paired_window_reports_rejected_covered_candidates_without_best(tmp_path):
    root = archive(tmp_path, error_rate=.7)

    comparison = compare_windows(root, 1)
    paired = paired_frontend_window(root, comparison, 'front-end', 'shop', .5, 0)

    assert paired['status'] == 'not_evaluable'
    assert paired['covered_windows'] == 5
    assert paired['eligible_windows'] == 0
    assert paired['best'] is None
    assert '5xx' in paired['reason']


def test_missing_error_evidence_does_not_create_a_selected_window(tmp_path):
    root = archive(tmp_path, missing_errors=True)
    (root / 'metrics' / 'traffic_rps.json').unlink()

    comparison = compare_windows(root, 1)
    paired = paired_frontend_window(root, comparison, 'front-end', 'shop', .5, 0)

    assert paired['covered_windows'] == 0
    assert paired['best'] is None
    assert paired['status'] == 'not_evaluable'


def test_equal_best_windows_use_earliest_time_and_partial_baseline_stays_visible(tmp_path):
    root = archive(tmp_path, p95_values=[1] * 5 + [1.1] * 6,
                   missing_baseline_p95=True)

    comparison = compare_windows(root, 1)
    paired = paired_frontend_window(root, comparison, 'front-end', 'shop', .5, 0)

    assert paired['status'] == 'partially_evaluable'
    assert paired['baseline']['p95_seconds'] is None
    assert paired['best']['p95_seconds'] == pytest.approx(1.1)
    assert paired['best']['start'] == at(120)
    assert paired['covered_windows'] == paired['eligible_windows'] == 5


def test_renderers_show_only_best_even_when_old_grade_contains_extra_window(tmp_path):
    root = archive(tmp_path)
    comparison = compare_windows(root, 1)
    for row in comparison['rows']:
        row['worst'] = {'value': 999, 'start': at(240), 'end': at(300)}
    old_limitation = ('Best/worst are independent per metric and workload; '
                      'ties select the earliest window.')
    comparison['limitations'].append(old_limitation)
    output = tmp_path / 'output'
    (output / 'runs' / 'run').mkdir(parents=True)
    (output / 'runs' / 'run' / 'report.md').write_text('# Run\n')

    write_comparisons(output, [{'run': 'run', 'window_comparison': comparison}])
    report = (output / 'runs' / 'run' / 'report.md').read_text()
    with (output / 'csvs' / 'window_comparison.csv').open(newline='') as handle:
        windows = list(csv.DictReader(handle))
    assert '| best |' in report
    assert 'worst' not in report.lower()
    assert old_limitation in comparison['limitations']
    assert windows and {row['selection'] for row in windows} == {'best'}

    paired = paired_frontend_window(root, comparison, 'front-end', 'shop', .5, 0)
    paired['worst'] = {'p95_seconds': 999, 'http_5xx_rps': 999,
                       'start': at(240), 'end': at(300)}
    paired['worst_selection'] = 'highest_p95_across_all_covered_windows_then_earliest'
    paired['description'] += '; worst is highest mean P95 without 5xx ceiling'
    grade = {'run': 'run', 'scenario': 'example', 'paired_window': paired,
             'rca_jobs': [], 'remediation_jobs': []}
    assert not any(key.startswith('worst') for key in table_row(grade))
    write_scenario_table(output / 'csvs', [grade])
    with (output / 'csvs' / 'scenario_table.csv').open(newline='') as handle:
        scenarios = list(csv.DictReader(handle))
    assert len(scenarios[0]) == 14
    assert not any('worst' in title.lower() for title in scenarios[0])
    assert scenarios[0]['Best rolling window p95 response time (s)'] == '1.1'
    scenario_markdown = (output / 'csvs' / 'scenario_table.md').read_text()
    scenario_json = (output / 'csvs' / 'scenario_table.json').read_text()
    assert 'worst' not in scenario_markdown.lower()
    assert 'worst' not in scenario_json.lower()
    assert paired['worst']['p95_seconds'] == 999
    assert 'worst' in paired['description']
    assert json.loads(scenario_json)['runs'][0]['paired_window']['status'] == 'evaluable'


def test_legacy_rejected_window_provenance_is_not_evaluable_without_mutating_input(tmp_path):
    root = archive(tmp_path, error_rate=.7)
    comparison = compare_windows(root, 1)
    paired = paired_frontend_window(root, comparison, 'front-end', 'shop', .5, 0)
    assert paired['best'] is None and paired['covered_windows'] > 0
    assert paired['eligible_windows'] == 0
    paired['status'] = 'partially_evaluable'
    paired['worst'] = {'p95_seconds': 1.8, 'http_5xx_rps': .7,
                       'start': at(240), 'end': at(300)}
    paired['worst_selection'] = 'highest_p95_across_all_covered_windows_then_earliest'
    paired['description'] += '; worst is highest mean P95 without 5xx ceiling'
    paired['reason'] = ('No covered window meets the mean 5xx-rate threshold; '
                        'worst window remains available.')
    output = tmp_path / 'scenario'

    write_scenario_table(output, [{'run': 'run', 'scenario': 'example',
                                   'paired_window': paired, 'rca_jobs': [],
                                   'remediation_jobs': []}])

    emitted = json.loads((output / 'scenario_table.json').read_text())['runs'][0]['paired_window']
    markdown = (output / 'scenario_table.md').read_text()
    assert emitted['status'] == 'not_evaluable'
    assert emitted['best'] is None
    assert emitted['covered_windows'] > 0 and emitted['eligible_windows'] == 0
    assert 'worst' not in json.dumps(emitted).lower()
    assert 'status=not_evaluable' in markdown
    assert 'worst' not in markdown.lower()
    assert paired['status'] == 'partially_evaluable'
    assert 'worst' in paired and 'worst' in paired['reason']
