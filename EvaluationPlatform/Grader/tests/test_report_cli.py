import json
from eda.report import main, table
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


def test_markdown_escapes_values():
    text=table(pd.DataFrame({'Scenario':['a|b<script>'], 'Score':[None]}))
    assert 'a\\|b&lt;script&gt;' in text and 'Unknown' in text
