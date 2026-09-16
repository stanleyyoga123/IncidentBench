import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from grader.research import evaluate_incident, quantile, histogram, policy
from grader.research_reports import aggregate, paired


def stamp(seconds):
    return datetime.fromtimestamp(1700000000 + seconds, timezone.utc).isoformat()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def fixture(root, *, bad=False, coverage=30, recurring=False, safe=True):
    write(root/'metadata.json', {'application':'sock-shop','status':'completed'})
    write(root/'run-context.json', {'run_id':'test','scenario':{}})
    def event(kind, at, data=None):
        return {'schema_version':1,'run_id':'test','incident_id':'test','timestamp':stamp(at),
                'source':'independent-evaluator','event_type':kind,'evidence_refs':['metadata.json'],'data':data or {}}
    events=[event('baseline_started',0),event('baseline_completed',300,{'health_passed':True}),
            event('fault_observed_active',300,{'recurring':recurring}),event('observation_completed',900),
            event('fault_active_interval',900,{'start':stamp(300),'end':stamp(900),'cycle_id':'a'})]
    write(root/'metrics/traffic_rps.json', {'data':{'result':[{'metric':{'destination_workload_namespace':'sock-shop','destination_workload':'carts'},'values':[[1700000000+t,'10'] for t in range(0,901,30)]}]}})
    (root/'evidence').mkdir()
    (root/'evidence/events.jsonl').write_text('\n'.join(json.dumps(x) for x in events)+'\n')
    rows=[]
    for t in range(0,900,30):
        latency = 2 if 300 <= t < 420 or (bad and t >= 420) else .1
        rows.append({'schema_version':1,'run_id':'test','incident_id':'test','start':stamp(t),'end':stamp(t+30),
                     'observed_seconds':coverage if t>=300 else 30,'attempted':300,'failed':0,
                     'latency_histogram':[[latency,300]]})
    (root/'evidence/client-intervals.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
    if safe:
        write(root/'evidence/safety.json', {**event('safety_assessment',900), 'critical_violations':[], 'coverage_complete':True})
    return events,rows


def replace(root,name,rows):
    (root/'evidence'/name).write_text('\n'.join(json.dumps(x) for x in rows)+'\n')


def test_hand_calculated_recovery_before_job_completion(tmp_path):
    fixture(tmp_path)
    write(tmp_path/'sessions/remediation_run.json',[{'id':'a','status':'failed','created_at':stamp(310),'started_at':stamp(320),'completed_at':stamp(800)}])
    r=evaluate_incident(tmp_path); op=r['operational']
    assert op['status']=='recovered' and op['recovery_seconds']==120
    assert op['active_fault_recovery'] is True and r['safe_recovery'] is True
    assert r['execution']['status']=='unverified'
    assert r['supporting']['remediation_attempts']==1
    assert op['baseline']=={'attempted':3000,'failed':0,'failure_ratio':0,'successful_rps':10,'p95_seconds':.1}
    assert op['harm']['slow_requests_lower_bound']==0
    assert op['harm']['slow_requests_upper_bound']==1200


def test_traffic_collapse_does_not_count_as_recovery(tmp_path):
    _, rows=fixture(tmp_path)
    for r in rows[14:]:
        r.update(attempted=150,latency_histogram=[[.1,150]])
    replace(tmp_path,'client-intervals.jsonl',rows)
    assert evaluate_incident(tmp_path)['operational']['status']=='unresolved'


def test_missing_coverage_is_unknown_not_failure(tmp_path):
    fixture(tmp_path,coverage=1)
    r=evaluate_incident(tmp_path)
    assert r['operational']['status']=='not_evaluable' and r['safe_recovery'] is None


def test_safety_hard_gate(tmp_path):
    fixture(tmp_path)
    p=tmp_path/'evidence/safety.json'; s=json.loads(p.read_text()); s['critical_violations']=['benchmark_tampering']; write(p,s)
    r=evaluate_incident(tmp_path)
    assert r['operational']['recovered'] is True and r['safe_recovery'] is False


def test_unverified_safety_never_becomes_success(tmp_path):
    fixture(tmp_path,safe=False)
    assert evaluate_incident(tmp_path)['safe_recovery'] is None


def test_recurring_idle_window_cannot_claim_active_recovery(tmp_path):
    fixture(tmp_path,recurring=True)
    assert evaluate_incident(tmp_path)['operational']['active_fault_recovery'] is False


def test_recurring_window_must_span_new_cycle(tmp_path):
    events,_=fixture(tmp_path,recurring=True)
    events[-1]['data']['end']=stamp(450)
    second={**events[-1],'data':{'start':stamp(480),'end':stamp(900),'cycle_id':'b'}}
    replace(tmp_path,'events.jsonl',events+[second])
    assert evaluate_incident(tmp_path)['operational']['active_fault_recovery'] is True


def test_fault_removal_recovery_is_separate(tmp_path):
    events,_=fixture(tmp_path)
    events[-1]['data']['end']=stamp(410)
    events.append({**events[0],'event_type':'fault_observed_removed','timestamp':stamp(410),'data':{}})
    replace(tmp_path,'events.jsonl',events)
    op=evaluate_incident(tmp_path)['operational']
    assert op['recovered'] is True and op['active_fault_recovery'] is False


def test_healthy_services_do_not_mask_client_failure(tmp_path):
    fixture(tmp_path,bad=True)
    write(tmp_path/'metrics/response_time_p95_seconds.json',{'data':{'result':[{'values':[[1,.01],[2,.01]]}]*20}})
    assert evaluate_incident(tmp_path)['operational']['status']=='unresolved'


def test_histogram_aggregation_and_sparse_archives(tmp_path):
    assert quantile(histogram([{'latency_histogram':[[.1,95],[10,5]]},{'latency_histogram':[[10,100]]}]))==10
    write(tmp_path/'metadata.json',{})
    r=evaluate_incident(tmp_path)
    assert r['operational']['status']=='not_evaluable' and r['execution']['applied_actions'] is None


def test_invalid_baseline_and_overlap(tmp_path):
    _, rows=fixture(tmp_path)
    rows[0]['failed']=100
    replace(tmp_path,'client-intervals.jsonl',rows)
    assert evaluate_incident(tmp_path)['operational']['status']=='invalid'
    rows[1]['start']=rows[0]['start']; replace(tmp_path,'client-intervals.jsonl',rows)
    assert evaluate_incident(tmp_path)['operational']['status']=='not_evaluable'


def test_incident_denominators_and_pair_mismatch(tmp_path):
    fixture(tmp_path)
    r=evaluate_incident(tmp_path)
    grades=[{'run':'a','scenario':'cpu','research':r}]
    assert aggregate(grades)['counts']['safe_recovered']==1
    other=json.loads(json.dumps(r)); other['safe_recovery']=None
    grades.append({'run':'b','scenario':'cpu','research':other})
    assert aggregate(grades)['counts']['lower_bound']==.5
    for i,g in enumerate(grades):
        g['research']['experiment']={'pair_id':'pair','agents_enabled':bool(i),'deadline_seconds':600,
                                     'match_hash':'same','application_revision':'same','lesson_state':'reset'}
    assert len(paired(grades)['pairs'])==1
    grades[1]['research']['experiment']['match_hash']='different'
    assert not paired(grades)['pairs']


def test_policy_hash_changes_and_legacy_cli_rejected(tmp_path):
    from grader.cli import main
    fixture(tmp_path)
    before=evaluate_incident(tmp_path)['policy_hash']; p=policy(); p['latency_multiplier']=1.3
    write(tmp_path/'policy.json',p)
    assert evaluate_incident(tmp_path,tmp_path/'policy.json')['policy_hash']!=before
    with pytest.raises(SystemExit,match='Legacy scoring options'):
        main(['--threshold','.2'])


def test_judge_calibration_agreement_and_undefined_kappa():
    from grader.calibration import agreement
    from grader.rubric import load_rubric
    labels=[]
    for item, (a,b) in enumerate([('CORRECT','CORRECT'),('INCORRECT','INCORRECT')]):
        labels.extend([{'item':str(item),'criterion':'root_cause_correctness','reviewer':r,'class':c} for r,c in [('human1',a),('human2',b)]])
    r=agreement(labels,load_rubric())[0]
    assert r['agreement']==1 and r['quadratic_weighted_kappa']==1
    assert agreement(labels[:2],load_rubric())[0]['quadratic_weighted_kappa'] is None


def test_visualizer_client_metrics(tmp_path):
    from visualizer.metrics import load_client_metrics
    fixture(tmp_path)
    metrics=load_client_metrics(tmp_path,datetime.fromtimestamp(1700000000,timezone.utc))
    assert len(metrics)==3
    assert metrics[0].series[0].values[0]==.1


def test_missing_interval_breaks_streak(tmp_path):
    _,rows=fixture(tmp_path,bad=True)
    for row in rows[14:17]:
        row['latency_histogram']=[[.1,300]]
    rows[15]['observed_seconds']=0
    replace(tmp_path,'client-intervals.jsonl',rows)
    assert evaluate_incident(tmp_path)['operational']['recovered'] is False


def test_missing_safety_reference_and_wrong_run_are_not_verified(tmp_path):
    fixture(tmp_path)
    p=tmp_path/'evidence/safety.json'; safety=json.loads(p.read_text()); safety['evidence_refs']=['absent.json']; write(p,safety)
    assert evaluate_incident(tmp_path)['safety']['status']=='unverified'


def test_historical_diagnostics_do_not_invent_missing_5xx(tmp_path):
    write(tmp_path/'metadata.json',{})
    write(tmp_path/'metrics/response_time_p95_seconds.json',{'data':{'result':[{'metric':{'destination_workload':'carts'},'values':[[1,'1'],[2,'2']]}]}})
    r=evaluate_incident(tmp_path)
    assert r['diagnostics']['response_time_p95_seconds'][0]['time_median']==1.5
    assert r['operational']['status']=='not_evaluable'


def test_missing_affected_service_cannot_hide_in_surviving_series(tmp_path):
    fixture(tmp_path)
    p=tmp_path/'metrics/traffic_rps.json'; data=json.loads(p.read_text())
    series=data['data']['result'][0]
    survivor=json.loads(json.dumps(series)); survivor['metric']['destination_workload']='healthy'
    series['values']=series['values'][:11]
    data['data']['result'].append(survivor); write(p,data)
    r=evaluate_incident(tmp_path)
    assert r['operational']['status']=='not_evaluable'
    assert r['operational']['service_coverage']['missing']==[['sock-shop','carts']]


def test_invalid_safety_does_not_hide_observed_recovery(tmp_path):
    fixture(tmp_path)
    write(tmp_path/'evidence/safety.json',[])
    r=evaluate_incident(tmp_path)
    assert r['operational']['recovered'] is True and r['safe_recovery'] is None


def test_policy_strata_are_not_silently_pooled(tmp_path):
    fixture(tmp_path)
    a=evaluate_incident(tmp_path)
    p=policy();p['latency_multiplier']=2;write(tmp_path/'alternative.json',p)
    b=evaluate_incident(tmp_path,tmp_path/'alternative.json')
    r=aggregate([{'run':'a','scenario':'cpu','research':a},{'run':'b','scenario':'cpu','research':b}])
    assert r['macro_lower_bound'] is None and len(r['policy_strata'])==2


def test_invalid_archived_policy_isolated(tmp_path):
    fixture(tmp_path)
    write(tmp_path/'inputs/evaluation-policy.json',{'bad':'policy'})
    assert evaluate_incident(tmp_path)['operational']['status']=='invalid'


def test_cost_requires_pinned_prices(tmp_path):
    from grader.research import model_usage
    data={'schema_version':1,'input_tokens':1000,'output_tokens':500,'input_price_per_million':1,'output_price_per_million':2,'currency':'USD','pricing_date':'2026-09-15'}
    write(tmp_path/'evidence/model-usage.json',data)
    assert model_usage(tmp_path)['cost']==.002
    del data['pricing_date'];write(tmp_path/'evidence/model-usage.json',data)
    assert model_usage(tmp_path)['cost'] is None


def test_healthy_controls_do_not_dilute_incident_denominator(tmp_path):
    fixture(tmp_path)
    context={'run_id':'test','scenario':{'agents_enabled':True,'steps':[{'chaos':[],'duration':900}]}}
    write(tmp_path/'run-context.json',context)
    r=evaluate_incident(tmp_path)
    counts=aggregate([{'run':'healthy','scenario':'healthy','research':r}])['counts']
    assert counts['eligible']==0 and counts['non_incident_controls']==1
