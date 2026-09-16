import csv
import json
from datetime import datetime, timezone

import pytest

from grader.research import evaluate_incident
from grader.research_reports import aggregate
from grader.archive_metrics import counter_window
from test_research import stamp, write


def archive(root, *, bad_until=420, collapse=False, healthy=False):
    write(root/'metadata.json', {'application':'sock-shop', 'status':'completed', 'baseline_seconds':300,
        'baseline_health':{'passed':True}, 'phases':[{'name':'baseline','status':'completed'}],
        'metrics':{'start':stamp(0),'end':stamp(900),'step_seconds':15},
        'chaos_steps':[{'chaos':['cpu'],'active_started_at':stamp(300),'cleanup_started_at':stamp(800),'finished_at':stamp(810)}]})
    path=root/'loadgenerator/constant_stats_history.csv';path.parent.mkdir()
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['Timestamp','Name','Total Request Count','Total Failure Count','95%']);writer.writeheader()
        count=0
        for t in range(901):
            count += (1 if collapse and t>300 else 10) if t else 0
            writer.writerow({'Timestamp':1700000000+t,'Name':'Aggregated','Total Request Count':count,
                             'Total Failure Count':max(0,min(t-300,120)), '95%':'999999'})
    for name in ['traffic_rps','response_time_p95_seconds']:
        rows=[]
        for svc in ['affected','healthy']:
            values=[[1700000000+t, 10 if name=='traffic_rps' else
                     2 if svc=='affected' and 300<t<=bad_until and not healthy else .1] for t in range(0,901,15)]
            rows.append({'metric':{'destination_workload_namespace':'sock-shop','destination_workload':svc},'values':values})
        write(root/'metrics'/f'{name}.json',{'data':{'result':rows}})
    return path


def test_archive_hand_worked_proxy_and_real_counters(tmp_path):
    archive(tmp_path)
    r=evaluate_incident(tmp_path);o=r['operational']
    assert o['status']=='proxy_recovered'
    assert o['proxy_recovery_seconds']==120
    assert o['recovery_seconds'] is None and o['active_fault_recovery'] is None
    assert r['safe_recovery'] is None
    assert o['baseline']['attempted']==3000 and o['baseline']['successful_rps']==10
    assert o['harm']['failed']==120 and o['harm']['failure_ratio']==.02
    assert o['harm']['slow_requests_upper_bound'] is None
    assert o['harm']['successful_rps']==9.8
    assert o['recovery_schedule_phase']=='during_scheduled_chaos'
    assert o['baseline']['source_lines'] == [2,302]


def test_archive_traffic_collapse_is_not_recovery(tmp_path):
    archive(tmp_path,collapse=True)
    assert evaluate_incident(tmp_path)['operational']['status']=='proxy_unresolved'


def test_archive_harmed_service_not_hidden(tmp_path):
    archive(tmp_path,bad_until=900)
    assert evaluate_incident(tmp_path)['operational']['status']=='proxy_unresolved'


def test_archive_missing_affected_service_is_unknown(tmp_path):
    archive(tmp_path)
    p=tmp_path/'metrics/response_time_p95_seconds.json';d=json.loads(p.read_text());d['data']['result'][0]['values']=d['data']['result'][0]['values'][:21];write(p,d)
    assert evaluate_incident(tmp_path)['operational']['status']=='not_evaluable'


def test_archive_gap_breaks_last_possible_streak(tmp_path):
    path=archive(tmp_path,bad_until=780)
    rows=list(csv.DictReader(path.open()))
    rows=[r for r in rows if not 1700000840 <= int(r['Timestamp']) <= 1700000855]
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    assert evaluate_incident(tmp_path)['operational']['status']=='proxy_unresolved'


def test_archive_one_sample_cannot_grade(tmp_path):
    path=archive(tmp_path)
    lines=path.read_text().splitlines();path.write_text('\n'.join(lines[:2])+'\n')
    assert evaluate_incident(tmp_path)['operational']['status']=='not_evaluable'


def test_archive_counter_reset_is_unknown_not_zero():
    rows=[{'t':i,'attempted':n,'failed':0,'line':i+2} for i,n in [(0,100),(1,0),(2,200)]]
    result=counter_window(rows,0,2)
    assert result['counter_reset'] and result['failed'] is None


def test_archive_job_completion_cannot_change_recovery(tmp_path):
    archive(tmp_path)
    write(tmp_path/'sessions/remediation_run.json',[{'id':'a','status':'failed','created_at':stamp(310),'started_at':stamp(320),'completed_at':stamp(880)}, {'id':'b','status':'running'}])
    r=evaluate_incident(tmp_path)
    assert r['operational']['proxy_recovery_seconds']==120
    assert r['supporting']['remediation_attempts']==2
    assert r['supporting']['job_timings'][1]['execution_seconds'] is None


def test_archive_recovery_after_cleanup_is_labelled(tmp_path):
    archive(tmp_path,bad_until=780)
    p=tmp_path/'metadata.json';m=json.loads(p.read_text());m['chaos_steps'][0]['cleanup_started_at']=stamp(600);write(p,m)
    o=evaluate_incident(tmp_path)['operational']
    assert o['status']=='proxy_recovered' and o['recovery_schedule_phase']=='after_schedule_cleanup'
    assert o['active_fault_recovery'] is None


def test_archive_reports_and_visualizer_use_original_files(tmp_path):
    from visualizer.metrics import load_client_metrics
    archive(tmp_path)
    r=evaluate_incident(tmp_path)
    counts=aggregate([{'run':'a','scenario':'cpu','research':r}])['archive_counts']
    assert counts['proxy_recovered']==1 and counts['evaluable_recovery_rate']==1
    metrics=load_client_metrics(tmp_path,datetime.fromtimestamp(1700000000,timezone.utc))
    assert len(metrics)==2 and all('p95' not in m.name for m in metrics)


def test_archive_baseline_failure_rejected(tmp_path):
    archive(tmp_path)
    p=tmp_path/'metadata.json';m=json.loads(p.read_text());m['baseline_health']['passed']=False;write(p,m)
    assert evaluate_incident(tmp_path)['operational']['status']=='invalid'


def test_archive_missing_5xx_not_fabricated(tmp_path):
    archive(tmp_path)
    r=evaluate_incident(tmp_path)
    assert all(x['time_median'] is None for x in r['diagnostics']['derived_http_5xx_ratio'])


def test_archive_no_degradation_not_claimed_recovery(tmp_path):
    p=archive(tmp_path,healthy=True)
    rows=list(csv.DictReader(p.open()))
    for r in rows:r['Total Failure Count']='0'
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    r=evaluate_incident(tmp_path)
    assert r['operational']['status']=='no_observed_degradation'
    assert aggregate([{'research':r}])['archive_counts']['recovery_denominator']==0


def test_archive_optional_cleanup_timing_does_not_suppress_outcome(tmp_path):
    archive(tmp_path)
    p=tmp_path/'metadata.json';m=json.loads(p.read_text());del m['chaos_steps'][0]['cleanup_started_at'];write(p,m)
    o=evaluate_incident(tmp_path)['operational']
    assert o['status']=='proxy_recovered' and o['recovery_schedule_phase']=='unknown'


def test_archive_full_pipeline_operational_only_without_judge(tmp_path):
    from grader.pipeline import GraderConfig, grade_runs
    from test_grader import _write_run, _write_jobs, StaticJudge
    run = tmp_path/'results/run'
    _write_run(run)
    _write_jobs(run)
    # Real original-format fixture replaces metadata but preserves archived semantic inputs.
    archive(run)
    judge=StaticJudge()
    grades=grade_runs(GraderConfig(input_path=tmp_path/'results',output_path=tmp_path/'grades',operational_only=True),judge)
    assert not judge.calls
    assert grades[0]['research']['operational']['status']=='proxy_recovered'
    assert not (tmp_path/'grades/incidents.csv').exists()
    assert (tmp_path/'grades/csvs/scenario_table.csv').exists()
