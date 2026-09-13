import json
from pathlib import Path


def test_bundled_deployments_live_in_config_and_keep_orchestrator_available():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root/'config/bundled.json').read_text())
    names = {item['name'] for item in config['deployments']}
    assert names == {'anomaly-detector','learning-agent','rca-agent','remediator-agent','mcp-tools-investigation','mcp-tools-remediation'}
    assert 'agent-orchestrator' not in names
    for path in (root/'testbed').rglob('*.py'):
        if path.name not in ('configuration.py',):
            assert 'mcp-tools-investigation' not in path.read_text()
