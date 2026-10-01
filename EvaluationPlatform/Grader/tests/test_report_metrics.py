import json
import pandas as pd
import pytest
from reporting.report_metrics import ReportConfig, job_summary, performance, build_report, aggregate_report


def job(score, completed='2026-09-18T00:02:00Z', status='succeeded', id='a'):
    return {'id':id, 'status':status, 'completed_at':completed,
            'rubric':{'overall_score':score}, 'alignment':{'verdict':'aligned'}}


def test_score_ties_and_strict_threshold():
    r=job_summary([job(.8),job(.9,'2026-09-18T00:03:00Z',id='later'),job(.9,status='failed',id='earlier'),job(1,status='running')],pd.Timestamp('2026-09-18T00:00:00Z'),.8)
    assert r['max_score']==.9 and r['average_score']==pytest.approx(2.6/3)
    assert r['sessions']==4 and r['scored_sessions']==3 and r['successful_sessions']==2
    assert r['first_highest_score_job_id']=='earlier' and r['time_to_first_highest_score_seconds']==120


def test_missing_and_prechaos_times():
    origin=pd.Timestamp('2026-09-18T00:03:00Z')
    r=job_summary([job(.9),job(.9,None)],origin,.8)
    assert r['time_to_first_highest_score_seconds'] is None
    assert r['timing_status']=='missing_top_score_completion_time'
    r=job_summary([job(.9)],origin,.8)
    assert r['time_to_first_highest_score_seconds']==-60 and r['timing_status']=='before_chaos_start'
    assert job_summary([],origin,.8)['max_score'] is None


def test_performance_boundary_zero_and_unknown():
    cfg=ReportConfig()
    r=performance({'baseline':{'p95_seconds':1.,'http_5xx_rps':0.},'best':{'p95_seconds':1.19,'http_5xx_rps':.5},'worst':{'p95_seconds':1.2,'http_5xx_rps':.5}},cfg)
    assert r['best_p95_seconds_change_percent']==pytest.approx(19)
    assert r['best_p95_seconds_difference']==pytest.approx(.19)
    assert r['best_5xx_rps_difference']==.5 and r['best_5xx_rps_change_percent'] is None
    assert r['best_holistic_pass'] is True
    assert not any(key.startswith('worst_') for key in r)
    assert performance({'baseline':{'p95_seconds':1},'best':{'p95_seconds':1.2,'http_5xx_rps':.5}},cfg)['best_holistic_pass'] is False
    assert performance({'baseline':{'p95_seconds':0},'best':{'p95_seconds':0,'http_5xx_rps':0}},cfg)['best_holistic_pass'] is None
    assert performance({'baseline':{'p95_seconds':1},'covered_windows':2},cfg)['best_holistic_pass'] is False
    assert performance({'baseline':{'p95_seconds':1},'covered_windows':0},cfg)['best_holistic_pass'] is None


def test_repeat_selection_export_counts_and_denominators(tmp_path,monkeypatch):
    import reporting.report_metrics as module
    grades,archives=tmp_path/'grades',tmp_path/'archives'
    for run,state,score,day in [('completed','completed',.9,1),('later-failed','failed',.2,2)]:
        g=grades/'runs'/run; a=archives/run
        g.mkdir(parents=True); (a/'sessions').mkdir(parents=True)
        (g/'grade.json').write_text(json.dumps({'run':run,'scenario':'same','rca_jobs':[job(score)],'remediation_jobs':[]}))
        (a/'metadata.json').write_text(json.dumps({'status':state,'started_at':f'2026-09-{day:02d}T00:00:00Z','chaos_steps':[{'chaos':['fault'],'active_started_at':'2026-09-18T00:00:00Z','cleanup_started_at':'2026-09-18T01:00:00Z'}]}))
        (a/'sessions/rca_session.json').write_text(json.dumps([{'completed_at':'2026-09-18T00:02:00Z'}, {'completed_at':'2026-09-18T00:03:00Z'}, {'completed_at':'2026-09-18T01:02:00Z'}]))
    seen=[]
    monkeypatch.setattr(module,'compare_windows',lambda root,minutes:seen.append(minutes) or {})
    monkeypatch.setattr(module,'paired_frontend_window',lambda *args:{})
    all_runs,selected,jobs=build_report(grades,archives,ReportConfig(window_minutes=3))
    assert selected['run'].tolist()==['completed'] and selected.iloc[0]['rca_sessions']==2
    assert selected.iloc[0]['rca_excluded_sessions']==1
    assert len(all_runs)==2 and seen==[3,3]
    a=aggregate_report(selected,jobs,ReportConfig())
    assert a.iloc[0]['count']==a.iloc[0]['evaluable']==1
    h=a[a.metric.str.startswith('Holistic')]
    assert (h['evaluable']==0).all() and h['percent_of_evaluable'].isna().all()


@pytest.mark.parametrize('kwargs',[{'score_threshold':2},{'window_minutes':0},{'max_5xx_rps':float('nan')},{'repeat_policy':'best_score'}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError): ReportConfig(**kwargs)
