"""Protect chaos-only activity counts and run-level reporting denominators."""
import json

import pandas as pd
import pytest

from grader.time_scope import chaos_intervals
from reporting.report_activity import (
    activity_counts, activity_display, activity_summary, scenario_resource_fault,
)


def test_activity_counts_use_detection_and_finished_attempts_inside_capped_intervals(tmp_path):
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    intervals = chaos_intervals({'chaos_steps': [{
        'chaos': ['memory'], 'active_started_at': '2026-09-01T00:00:00Z',
        'cleanup_started_at': '2026-09-01T00:20:00Z', 'duration': 600,
    }, {
        'chaos': ['cpu'], 'active_started_at': '2026-09-01T00:30:00Z',
        'cleanup_started_at': '2026-09-01T00:35:00Z', 'duration': 600,
    }]})
    times = ['2026-08-31T23:59:59Z', '2026-09-01T00:00:00Z',
             '2026-09-01T00:09:59Z', '2026-09-01T00:10:00Z',
             '2026-09-01T00:30:00Z', '2026-09-01T00:35:00Z']
    (sessions / 'anomaly.json').write_text(json.dumps([{'detected_at': time} for time in times]))
    jobs = [{'status': 'failed' if index == 2 else 'succeeded',
             'completed_at': time} for index, time in enumerate(times)]
    jobs.append({'status': 'running', 'completed_at': '2026-09-01T00:01:00Z'})
    (sessions / 'rca_session.json').write_text(json.dumps(jobs))
    (sessions / 'remediation_run.json').write_text('[]')

    assert activity_counts(tmp_path, intervals) == {
        'anomaly_activity_count': 3, 'rca_activity_count': 3,
        'remediation_activity_count': 0,
    }


@pytest.mark.parametrize('payload', [None, '{}', '[', '[{}]',
                                   '[{"detected_at":"invalid"}]',
                                   '[{"detected_at":"2026-09-01T00:01:00"}]'])
def test_missing_or_unplaceable_anomaly_export_is_unknown_not_zero(tmp_path, payload):
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    if payload is not None:
        (sessions / 'anomaly.json').write_text(payload)
    (sessions / 'rca_session.json').write_text('[]')
    (sessions / 'remediation_run.json').write_text('[]')
    intervals = [(pd.Timestamp('2026-09-01T00:00:00Z').timestamp(),
                  pd.Timestamp('2026-09-01T00:10:00Z').timestamp())]

    counts = activity_counts(tmp_path, intervals)

    assert counts['anomaly_activity_count'] is None
    assert counts['rca_activity_count'] == counts['remediation_activity_count'] == 0
    assert all(value is None for value in activity_counts(tmp_path, []).values())


@pytest.mark.parametrize('record', [
    {'completed_at': '2026-09-01T00:01:00Z'},
    {'status': 'succeeded'}, {'status': 'failed', 'completed_at': 'invalid'},
])
def test_unplaceable_finished_job_export_is_unknown(tmp_path, record):
    (tmp_path / 'sessions').mkdir()
    (tmp_path / 'sessions/rca_session.json').write_text(json.dumps([record]))
    assert activity_counts(tmp_path, [(0, 2_000_000_000)])['rca_activity_count'] is None


@pytest.mark.parametrize(('application', 'scenario', 'expected'), [
    ('sock-shop', 'sock-shop-node-memory-worker-3-one-hour', ('node', 'memory')),
    ('teastore', 'teastore-node-loss-worker-1-one-hour', ('node', 'loss')),
    ('online-boutique', 'online-boutique-pod-paymentservice-capacity-loss-one-hour', ('pod', 'capacity-loss')),
    ('sock-shop', 'sock-shop-pod-front-end-cpu-headroom-all-one-hour', ('pod', 'cpu-headroom')),
    ('sock-shop', 'custom-scenario', ('Unknown', 'Unclassified')),
])
def test_activity_groups_preserve_application_resource_and_fault(application, scenario, expected):
    assert scenario_resource_fault(scenario, application) == expected


def test_activity_summary_includes_zero_runs_and_preserves_unknown_denominators():
    rows = []
    for index, (app, scope, completed, anomaly, rca, remediation) in enumerate([
        ('sock-shop', 'node', True, 0, 0, None),
        ('sock-shop', 'node', True, 4, 2, 3),
        ('sock-shop', 'node', False, 100, 100, 100),
        ('online-boutique', 'node', True, 29, 12, 6),
        ('sock-shop', 'pod-front-end', True, None, None, None),
    ]):
        rows.append({'application': app, 'scenario': f'{app}-{scope}-memory-worker-3',
                     'run': str(index), 'run_completed': completed,
                     'anomaly_activity_count': anomaly, 'rca_activity_count': rca,
                     'remediation_activity_count': remediation})

    summary = activity_summary(pd.DataFrame(rows))
    node = summary.query("application == 'sock-shop' and resource_type == 'node'").iloc[0]

    assert node.runs == 2
    assert node.anomaly_mean == 2
    assert node.anomaly_std == pytest.approx(8 ** .5)
    assert node.rca_mean == 1
    assert node.remediation_mean == 3 and node.remediation_n == 1
    display = activity_display(summary)
    node_display = display.query("Application == 'sock-shop' and `Resource type` == 'node'").iloc[0]
    assert node_display['Anomalies raised'] == '2.00 ± 2.83'
    assert node_display['Remediation attempts completed'] == '3.00 ± N/A'
    assert node_display['Remediation attempts completed: evaluable runs'] == '1/2'
    assert display.query("`Resource type` == 'pod'").iloc[0]['Anomalies raised'] == 'Unknown'
    assert display.query("Application == 'online-boutique'").iloc[0]['Anomalies raised'] == '29.00 ± N/A'


def test_report_activity_uses_same_repeat_selection_and_completed_cohort(tmp_path):
    from reporting.report_metrics import ReportConfig, build_report

    archives = tmp_path / 'archives'
    scenario = 'sock-shop-node-memory-worker-3-one-hour'
    for run, day, status, events in [('early', 1, 'completed', 1),
                                      ('latest', 2, 'completed', 0),
                                      ('failed', 3, 'failed', 9)]:
        archive = archives / run
        (archive / 'sessions').mkdir(parents=True)
        (archive / 'inputs').mkdir()
        (archive / 'inputs/scenario.json').write_text(json.dumps({'name': scenario}))
        (archive / 'metadata.json').write_text(json.dumps({
            'status': status, 'started_at': f'2026-09-0{day}T00:00:00Z',
            'chaos_steps': [{'chaos': ['memory'], 'duration': 600,
                             'active_started_at': '2026-09-01T00:00:00Z',
                             'cleanup_started_at': '2026-09-01T00:20:00Z'}],
        }))
        (archive / 'sessions/anomaly.json').write_text(json.dumps([
            {'detected_at': '2026-09-01T00:01:00Z'} for _ in range(events)]))
        (archive / 'sessions/rca_session.json').write_text('[]')
        (archive / 'sessions/remediation_run.json').write_text('[]')

    for policy, expected_runs, expected_mean in [('latest_completed_else_latest', 1, 0),
                                               ('all_runs', 2, .5)]:
        _, selected, _ = build_report(tmp_path / 'grades', archives,
                                     ReportConfig(repeat_policy=policy), include_ungraded=True)
        selected.insert(0, 'application', 'sock-shop')
        summary = activity_summary(selected)
        assert summary.iloc[0].runs == expected_runs
        assert summary.iloc[0].anomaly_mean == expected_mean
