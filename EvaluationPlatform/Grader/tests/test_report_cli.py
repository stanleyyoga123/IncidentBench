import json
from pathlib import Path
from reporting.report import main, table
import pandas as pd


def test_report_ungraded_and_future_application(tmp_path):
    archive=tmp_path/'results/sock-shop/run'
    (archive/'inputs').mkdir(parents=True)
    (archive/'sessions').mkdir()
    (archive/'metadata.json').write_text(json.dumps({'status':'completed','chaos_steps':[
        {'chaos':['fault'],'active_started_at':'2026-09-18T00:00:00Z','cleanup_started_at':'2026-09-18T01:00:00Z'}]}))
    (archive/'inputs/scenario.json').write_text('{"name":"sample-scenario"}')
    (archive/'sessions/rca_session.json').write_text(json.dumps([
        {'id':'in','status':'succeeded','completed_at':'2026-09-18T00:10:00Z'},
        {'id':'out','status':'succeeded','completed_at':'2026-09-18T01:10:00Z'}]))
    output=tmp_path/'report.md'
    assert main(['--results-dir',str(tmp_path/'results'),'--grades-dir',str(tmp_path/'grades'),
                 '--output',str(output),'--window-minutes','3'])==0
    text=output.read_text()
    assert 'sample-scenario' in text and 'not_graded' in text
    assert '**3 minutes**' in text and '## teastore' in text
    assert 'Unknown' in text and 'No archived runs or grades available yet' in text
    assert 'worst window' not in text.lower()
    assert '## Completed-run analysis' in text
    assert (tmp_path/'report-applications.png').is_file()
    assert str(tmp_path) not in text
    assert 'external input (sock-shop)' in text


def test_synthetic_demo_reports_semantic_counts_and_unknown_telemetry(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / 'examples' / 'report-demo'
    output = tmp_path / 'demo.md'

    assert main(['--results-dir', str(fixture / 'results'),
                 '--grades-dir', str(fixture / 'grades'),
                 '--apps', 'sock-shop', 'online-boutique',
                 '--output', str(output)]) == 0

    text = output.read_text()
    assert 'demo-network-delay' in text and 'demo-cpu-stress' in text
    assert 'Successful RCA sessions (score &gt; 0.8)' in text
    assert 'Unknown' in text
    assert 'worst window' not in text.lower()
    assert 'examples/report-demo/results/sock-shop' in text
    assert str(fixture.resolve()) not in text
    assert (tmp_path / 'demo-applications.png').is_file()


def test_markdown_escapes_values():
    text=table(pd.DataFrame({'Scenario':['a|b<script>'], 'Score':[None]}))
    assert 'a\\|b&lt;script&gt;' in text and 'Unknown' in text
