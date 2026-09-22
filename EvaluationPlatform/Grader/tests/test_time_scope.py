import csv
import json
from datetime import datetime, timezone

import pytest

from grader.time_scope import chaos_intervals, job_scope
from grader.archive_metrics import evaluate_archive
from grader.research import policy, diagnostics
from grader.window_comparison import compare_windows


def at(seconds):
    return datetime.fromtimestamp(1700000000 + seconds, timezone.utc).isoformat()


def metadata():
    return {'metrics': {'start': at(0), 'end': at(1500), 'step_seconds': 15},
            'baseline_seconds': 300, 'phases': [{'name': 'baseline', 'status': 'completed'}],
            'chaos_steps': [{'chaos': ['fault'], 'active_started_at': at(300),
                             'cleanup_started_at': at(905), 'duration': 600}]}


def archive(root):
    m = metadata()
    (root/'metadata.json').write_text(json.dumps(m))
    (root/'loadgenerator').mkdir()
    with (root/'loadgenerator/app_stats_history.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['Name','Timestamp','Total Request Count','Total Failure Count'])
        writer.writerows(['Aggregated',1700000000+t,t*10,0] for t in range(1501))
    (root/'metrics').mkdir()
    for name in ['traffic_rps','response_time_p95_seconds','http_5xx_rate']:
        values = [[1700000000+t, str(10 if name=='traffic_rps' else 0 if name=='http_5xx_rate'
                                   else 4 if 300<t<=900 else 1)] for t in range(0,1501,15)]
        (root/'metrics'/f'{name}.json').write_text(json.dumps({'data':{'result':[
            {'metric':{'destination_workload_namespace':'test','destination_workload':'front-end'}, 'values':values}]}}))
    return m


def test_recorded_end_duration_and_missing_boundary():
    m=metadata()
    spans=chaos_intervals(m)
    assert spans[0][1]-spans[0][0]==600
    assert job_scope({'completed_at':at(300)},spans)['included']
    for completion in [at(299),at(900),at(1200),None]:
        assert not job_scope({'completed_at':completion},spans)['included']
    m['chaos_steps'][0]['cleanup_started_at']=at(600)
    assert chaos_intervals(m)[0][1]-spans[0][0]==300
    del m['chaos_steps'][0]['cleanup_started_at']
    with pytest.raises(ValueError): chaos_intervals(m)


def test_postchaos_recovery_and_diagnostics_ignored(tmp_path):
    m=archive(tmp_path)
    result=evaluate_archive(tmp_path,policy(),m)
    assert result['status']=='proxy_unresolved'
    assert result['observation_seconds']==600
    assert result['harm']['attempted']==6000
    assert result['client_observed_totals']['attempted']==6000
    assert result['client_summary'] is None
    assert all(row['end']<=at(900) for row in result['intervals'])
    comparison=compare_windows(tmp_path)
    assert comparison['candidate_windows']==21
    assert comparison['chaos_intervals']==[{'start':at(300),'end':at(900)}]
    # Post-chaos healthy latency cannot become the best window.
    p95=[r for r in comparison['rows'] if r['metric']=='response_time_p95_seconds']
    assert p95
    d=diagnostics(tmp_path)['response_time_p95_seconds'][0]
    assert d['last_timestamp'] < 1700000900
    assert d['maximum']==4


def test_idle_gap_outputs_excluded():
    m=metadata()
    m['chaos_steps'] += [{'chaos':['fault'], 'active_started_at':at(1200), 'cleanup_started_at':at(1500)}]
    spans=chaos_intervals(m)
    assert not job_scope({'completed_at':at(1000)},spans)['included']
    assert job_scope({'completed_at':at(1300)},spans)['included']


def test_excluded_output_never_calls_judge_or_uses_cache():
    from grader.pipeline import _grade_job, GraderConfig
    from grader.rubric import load_rubric, DEFAULT_RUBRIC_PATH
    class NoJudge:
        def __getattr__(self, name):
            raise AssertionError('Excluded job contacted judge')
    result=_grade_job('rca', {'id':'after','status':'succeeded','result':{'answer':'present'},
                            '_time_scope':{'included':False,'reason':'outside chaos'}},
                      'scenario',{},[],load_rubric(DEFAULT_RUBRIC_PATH),None,
                      GraderConfig(),NoJudge(),{})
    assert result['rubric'] is None
    assert result['alignment']['verdict']=='not_evaluable'
    assert result['status']=='succeeded'


def test_idle_gap_cannot_establish_recovery(tmp_path):
    m=archive(tmp_path)
    m['chaos_steps'][0]['cleanup_started_at']=at(600)
    m['chaos_steps'] += [{'chaos':['fault'],'active_started_at':at(1200),'cleanup_started_at':at(1500)}]
    result=evaluate_archive(tmp_path,policy(),m)
    assert result['observation_seconds']==600
    assert result['harm']['attempted']==6000
    assert all(row['end']<=at(600) or row['start']>=at(1200) for row in result['intervals'])


def test_portable_histograms_stop_at_chaos_end(tmp_path):
    from grader.research import operational
    m=archive(tmp_path)
    (tmp_path/'evidence').mkdir()
    rows=[{'schema_version':1,'run_id':'run','incident_id':'run',
           'start':at(t),'end':at(t+30),'attempted':300,'failed':0,'observed_seconds':30,
           'latency_histogram':[[4 if 300<=t<900 else 1,300]]} for t in range(0,1500,30)]
    (tmp_path/'evidence/client-intervals.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    events=[{'event_type':kind,'timestamp':at(t),'data':{'health_passed':True}}
            for kind,t in [('baseline_started',0),('baseline_completed',300),
                           ('fault_observed_active',300),('observation_completed',1500)]]
    result=operational(tmp_path,policy(),events,'run',m)
    assert result['status']=='unresolved'
    assert result['observation_seconds']==600
    assert result['harm']['attempted']==6000


def test_scope_changes_effective_policy_hash(tmp_path):
    from grader.research import evaluate_incident, digest
    archive(tmp_path)
    result=evaluate_incident(tmp_path)
    assert result['policy_hash']!=digest(result['policy'])
    assert result['source_policy_hash']==digest(result['policy'])
