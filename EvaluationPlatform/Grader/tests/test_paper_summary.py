from copy import deepcopy
import csv
import json

import pytest

from grader.paper_summary import build_summary, markdown, write_paper_summary


def job(score, verdict='aligned', penalty=0):
    return {'status': 'succeeded', 'result': {'summary': 'final'}, 'alignment': {'verdict': verdict, 'reason': 'judge failed' if verdict == 'not_evaluable' else 'ok'},
            'rubric': {'overall_score': score, 'penalty_total': penalty,
                       'criteria': {'correctness': {'score': score}}}}


def grade(name, jobs, status='proxy_unresolved', basis='archive_service_recovery_proxy', policy='a'):
    return {'run': name, 'scenario': name, 'status': 'graded', 'rca_jobs': jobs, 'remediation_jobs': jobs,
            'research': {'policy_hash': policy, 'safe_recovery': None,
                         'safety': {'status': 'unverified'}, 'execution': {'status': 'unverified'},
                         'operational': {'status': status, 'measurement_basis': basis}}}


def test_run_balancing_and_failed_penalty_exclusion():
    # Nine perfect jobs in one run do not outweigh one failed-quality job in another.
    grades = [grade('many', [job(1)] * 9), grade('one', [job(0)]),
              grade('judge_failure', [job(1, 'not_evaluable')]), grade('missing', [])]
    data = build_summary(grades)
    m = data['strata'][0]['semantic']['remediation']
    assert m['run_balanced_mean'] == .5
    assert m['criteria']['correctness'] == {'run_balanced_mean': .5, 'runs': 2}
    assert (m['evaluable_jobs'], m['exported_jobs'], m['runs_with_scores']) == (10, 11, 2)
    assert data['runs'][2]['remediation']['mean_score'] is None
    assert '2/4 runs with scores' in markdown(data)


def test_outcome_denominators_and_strata():
    statuses = ['proxy_recovered', 'proxy_unresolved', 'not_evaluable', 'no_observed_degradation', 'invalid']
    grades = [grade(str(i), [], status) for i, status in enumerate(statuses)]
    grades += [grade('other_policy', [], policy='b'), grade('histogram', [], 'recovered', 'portable_client_histograms')]
    data = build_summary(grades)
    assert len(data['strata']) == 3
    a = data['strata'][0]['archive_counts']
    assert a['recovery_denominator'] == 3
    assert a['evaluable_recovery_rate'] == .5
    assert a['lower_bound'] == pytest.approx(1/3)
    assert a['upper_bound'] == pytest.approx(2/3)
    assert a['invalid'] == a['no_observed_degradation'] == 1


def test_artifacts_unknown_values_and_no_input_mutation(tmp_path):
    grades = [grade('missing', []), grade('penalized', [job(.25, penalty=.5)])]
    original = deepcopy(grades)
    (tmp_path/'report.md').write_text('# Detailed report\n')
    write_paper_summary(tmp_path, grades)
    assert grades == original
    data = json.loads((tmp_path/'research_summary.json').read_text())
    assert data['runs'][0]['client_failure_ratio'] is None
    assert data['strata'][0]['semantic']['remediation']['penalized_jobs'] == 1
    with (tmp_path/'paper_metrics.csv').open() as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]['client_failure_ratio'] == ''
    assert rows[0]['remediation_mean_score'] == ''
    assert rows[1]['remediation_mean_score'] == '0.25'
    assert 'research_summary.md' in (tmp_path/'report.md').read_text()
    assert 'unknown (0/0)' in (tmp_path/'research_summary.md').read_text()


def test_empty_summary(tmp_path):
    (tmp_path/'report.md').write_text('')
    write_paper_summary(tmp_path, [])
    assert (tmp_path/'paper_metrics.csv').read_text().strip() == 'run,scenario'
    assert build_summary([])['strata'] == []


def test_final_result_availability_is_independent_of_judging():
    skipped = job(1, 'not_evaluable')
    missing = job(1, 'not_evaluable'); missing['result'] = {}
    data = build_summary([grade('skipped', [skipped, missing])])
    m = data['strata'][0]['semantic']['rca']
    assert m['eligible_final_results'] == m['runs_with_final_results'] == 1
    assert m['evaluable_jobs'] == 0
    assert '1/2 exported jobs; 1/1 runs' in markdown(data)


def test_tiny_nonzero_failure_is_not_displayed_as_zero():
    from grader.paper_summary import percent
    assert percent(.00001) == '<0.1%'
    assert percent(0) == '0.0%'


def test_proxy_blockers_keep_overlapping_checks_separate():
    from grader.paper_summary import proxy_checks
    op = {'measurement_basis': 'archive_service_recovery_proxy',
          'limits': {'failure_ratio': .01, 'successful_rps': 9,
                     'service_latency_multiplier': 1.2, 'service_traffic_fraction': .9},
          'services': [{'namespace': 'app', 'workload': 'cart', 'baseline_p95_time_median_seconds': .1,
                        'baseline_rps_time_median': 10}],
          'intervals': [{'qualified': True, 'healthy': False, 'failure_ratio': .02, 'successful_rps': 8,
                         'services': [{'namespace': 'app', 'workload': 'cart',
                                       'maximum_p95_seconds': .2, 'minimum_rps': 7}]},
                        {'qualified': False, 'healthy': False}]}
    checks = proxy_checks(op)
    assert checks['qualified_bins'] == checks['unqualified_bins'] == checks['unhealthy_qualified_bins'] == 1
    assert checks['client_checks_failed'] == {'client_failure_ratio': 1, 'client_throughput': 1}
    assert checks['workload_checks_failed'] == {'app/cart:service_latency': 1, 'app/cart:service_traffic': 1}


def test_summary_regeneration_is_deterministic(tmp_path):
    (tmp_path/'report.md').write_text('# Details\n')
    grades = [grade('one', [job(.75)])]
    write_paper_summary(tmp_path, grades)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    write_paper_summary(tmp_path, grades)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_operational_only_pipeline_produces_repeatable_summary(tmp_path):
    from grader.pipeline import GraderConfig, grade_runs
    from test_grader import _write_run, _write_jobs, StaticJudge
    from test_archive_metrics import archive
    run = tmp_path/'input'/'run'
    _write_run(run); _write_jobs(run); archive(run)
    judge = StaticJudge()
    outputs = [tmp_path/'first', tmp_path/'second']
    for output in outputs:
        grade_runs(GraderConfig(input_path=tmp_path/'input', output_path=output, operational_only=True), judge)
    assert not judge.calls
    first, second = outputs
    for path in first.rglob('*'):
        if path.is_file():
            assert path.read_bytes() == (second/path.relative_to(first)).read_bytes()
    saved = json.loads((first/'runs/run/grade.json').read_text())
    data = build_summary([saved])
    assert not (first/'research_summary.json').exists()
    assert data['strata'][0]['archive_counts']['proxy_recovered'] == 1
    assert data['strata'][0]['semantic']['rca']['evaluable_jobs'] == 0
    assert data['strata'][0]['semantic']['rca']['eligible_final_results'] > 0


def test_throughput_retention_uses_measured_baseline_and_unknown_zero():
    g = grade('one', [])
    g['research']['operational'].update(baseline={'successful_rps': 10}, harm={'successful_rps': 8})
    assert build_summary([g])['runs'][0]['successful_throughput_fraction_of_baseline'] == .8
    g['research']['operational']['baseline']['successful_rps'] = 0
    assert build_summary([g])['runs'][0]['successful_throughput_fraction_of_baseline'] is None
