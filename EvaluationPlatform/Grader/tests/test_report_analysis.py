import pandas as pd
import pytest

from eda.report_analysis import fault_family, numeric_summaries
from eda.report_metrics import ReportConfig


def test_fault_family_classifies_archived_scenario_shapes():
    assert fault_family('teastore-node-loss-worker-1-one-hour') == 'Node packet loss'
    assert fault_family('sock-shop-pod-front-end-cpu-headroom-all-one-hour') == 'Pod CPU headroom'
    assert fault_family('online-boutique-pod-paymentservice-capacity-loss-one-hour') == 'Pod capacity loss'


def test_completed_cohort_excludes_failed_run_from_semantic_counts_and_keeps_audit():
    rows = []
    for run, completed, score, best in [('complete', True, .9, True),
                                        ('failed', False, .95, False)]:
        row = {'application': 'sock-shop', 'run': run, 'scenario': f'sock-shop-pod-carts-cpu-{run}',
               'run_completed': completed, 'archive_status': 'completed' if completed else 'failed',
               'grade_status': 'graded', 'best_holistic_pass': best,
               'best_p95_seconds_change_percent': 1.0}
        for kind in ('rca', 'remediation'):
            row.update({f'{kind}_has_successful_output': True,
                        f'{kind}_max_score': score, f'{kind}_average_score': score,
                        f'{kind}_sessions': 1, f'{kind}_time_to_first_highest_score_minutes': 3.0})
        rows.append(row)
    selected = pd.DataFrame(rows)
    jobs = pd.DataFrame([{'application': 'sock-shop', 'run': run, 'kind': kind,
                          'included_in_chaos': True, 'score': score, 'selected': True}
                         for run, score in [('complete', .9), ('failed', .95)]
                         for kind in ('rca', 'remediation')])

    summaries = numeric_summaries(selected.copy(), selected, jobs, ReportConfig())

    assert summaries['cohort'].iloc[0]['Completed analyzed'] == 1
    assert summaries['exclusions']['run'].tolist() == ['failed']
    rca = summaries['semantic'].query("Application == 'sock-shop' and Metric.str.startswith('Successful RCA sessions')")
    assert rca.iloc[0][['Success', 'Evaluable']].tolist() == [1, 1]
    assert summaries['performance'].iloc[0]['Best tolerance'] == '1/1'
    assert not any('worst' in column.lower() for column in summaries['performance'].columns)
    assert summaries['joint'].query("Output == 'rca' and `Semantic success` == True").iloc[0]['Total'] == 1


@pytest.mark.parametrize(('counts', 'expected_total', 'known'), [
    ([None, None], None, '0/2'),
    ([2, None], 2, '1/2'),
])
def test_session_summary_preserves_unknown_chaos_counts(counts, expected_total, known):
    rows = []
    for index, count in enumerate(counts):
        row = {'application': 'teastore', 'run': f'run-{index}',
               'scenario': f'teastore-pod-auth-cpu-{index}', 'run_completed': True,
               'archive_status': 'completed', 'grade_status': 'graded',
               'best_holistic_pass': None,
               'best_p95_seconds_change_percent': None}
        for kind in ('rca', 'remediation'):
            row.update({f'{kind}_has_successful_output': None,
                        f'{kind}_max_score': None, f'{kind}_average_score': None,
                        f'{kind}_sessions': count,
                        f'{kind}_time_to_first_highest_score_minutes': None})
        rows.append(row)
    selected = pd.DataFrame(rows)
    jobs = pd.DataFrame(columns=['application', 'run', 'kind', 'included_in_chaos',
                                 'score', 'selected'])

    summary = numeric_summaries(selected.copy(), selected, jobs, ReportConfig())['sessions']

    assert summary['Session counts known / runs'].tolist() == [known, known]
    if expected_total is None:
        assert summary['Known sessions'].isna().all()
    else:
        assert summary['Known sessions'].tolist() == [expected_total, expected_total]
