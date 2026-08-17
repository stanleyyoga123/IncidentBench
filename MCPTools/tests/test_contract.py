from pathlib import Path
from unittest.mock import Mock, patch

from config import Settings
from server import create_server
from tools.remediator import RemediatorTool


BASE = {
    "server": {"profile": "investigation", "token": "test-token"},
    "tools": {
        "kubectl": {},
        "prometheus": {"base_url": "http://prometheus"},
        "loki": {"base_url": "http://loki"},
        "jaeger": {"base_url": "http://jaeger"},
    },
}


def tools(profile):
    values = {**BASE, "server": {**BASE["server"], "profile": profile}}
    return {item.name: item for item in create_server(Settings.model_validate(values))._tool_manager.list_tools()}


def test_profile_tool_discovery_and_session_schema():
    investigation = tools("investigation")
    remediation = tools("remediation")

    assert "remediator.write_file" not in investigation
    assert "remediator.run_ansible" not in investigation
    assert set(remediation) == set(investigation) | {
        "remediator.write_file", "remediator.run_ansible"
    }
    assert "session_id" in remediation["remediator.write_file"].parameters["required"]
    assert "session_id" in remediation["remediator.run_ansible"].parameters["required"]


def test_investigation_profile_rejects_mutating_kubectl():
    result = tools("investigation")["kubectl"].fn("delete pod checkout")
    assert result["blocked"] is True
    assert result["ok"] is False


def test_ansible_live_execution_requires_matching_successful_check(tmp_path):
    tool = RemediatorTool(str(tmp_path))
    tool.write_file("job-a", "remediation.yml", "---\n- hosts: localhost\n")

    blocked = tool.run_ansible("job-a", check=False)
    assert blocked["executed"] is False

    runner = Mock(rc=0, status="successful", stats={"localhost": {"changed": 0}})
    with patch("tools.remediator.ansible_runner.run", return_value=runner):
        assert tool.run_ansible("job-a", check=True)["ok"] is True
        assert tool.run_ansible(
            "job-a", check=False, extra_vars={"target": "different"}
        )["executed"] is False
        assert tool.run_ansible("job-a", check=False)["ok"] is True

    Path(tmp_path / "job-a" / "remediation.yml").write_text("---\n- hosts: changed\n")
    changed = tool.run_ansible("job-a", check=False)
    assert changed["executed"] is False
    assert "changed after check mode" in changed["error"]
