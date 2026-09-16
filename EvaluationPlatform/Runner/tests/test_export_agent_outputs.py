"""Runner preserves generated answers independently of agent success status."""
import json
import sys
from hooks import runtime


def test_session_export_keeps_failed_agent_outputs(monkeypatch, tmp_path):
    context_path = tmp_path / 'run-context.json'
    context_path.write_text(json.dumps({'environment': {}, 'run_id': 'output-validation'}))
    output = tmp_path / 'results'; output.mkdir()
    sessions = {
        'anomaly': [], 'workflow': [], 'remediation_session': [],
        'rca_session': [{'id': 'rca', 'status': 'failed', 'result': None,
                         'raw_output': 'Diagnosis generated before parse failure.'}],
        'remediation_run': [{'id': 'remediation', 'status': 'failed',
                             'result': {'summary': 'Recovery unverified'},
                             'raw_output': 'Final answer before verification rejection.',
                             'error': {'type': 'RuntimeError', 'message': 'recovery unverified'}}],
        'learning_session': [{'id': 'learning', 'status': 'failed', 'result': None,
                              'raw_output': 'Malformed lesson output retained.'}],
    }
    def export(context, action):
        assert action == 'export' and context['run_id'] == 'output-validation'
        return {'schema_version': 1, 'run_id': context['run_id'], 'sessions': sessions}
    monkeypatch.setattr(runtime, 'api', export)
    monkeypatch.setattr(sys, 'argv', ['runtime', 'api-export', str(context_path), str(output)])
    runtime.main()
    for name, expected in sessions.items():
        assert json.loads((output / 'sessions' / f'{name}.json').read_text()) == expected
    assert not list((output / 'sessions').glob('*.tmp'))
