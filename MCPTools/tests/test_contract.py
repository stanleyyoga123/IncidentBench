from pathlib import Path
from unittest.mock import Mock, patch

from starlette.testclient import TestClient

from config import Settings
from server import create_app, create_server
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


def test_streamable_http_uses_exact_mcp_route_and_explicit_allowed_hosts():
    values = {
        **BASE,
        "server": {
            **BASE["server"],
            "allowed_hosts": ["mcp-tools-investigation.agents.svc.cluster.local:8090"],
        },
    }
    wrapped = create_app(Settings.model_validate(values))
    app = wrapped.app

    assert [route.path for route in app.routes] == ["/mcp", "/health"]
    security = app.routes[0].endpoint.session_manager.security_settings
    assert security.enable_dns_rebinding_protection is True
    assert "localhost:*" in security.allowed_hosts
    assert (
        "mcp-tools-investigation.agents.svc.cluster.local:8090"
        in security.allowed_hosts
    )

    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "contract-test", "version": "1"},
        },
    }
    headers = {
        "Authorization": "Bearer test-token",
        "Accept": "application/json, text/event-stream",
    }
    service_url = "http://mcp-tools-investigation.agents.svc.cluster.local:8090"
    with TestClient(wrapped, base_url=service_url) as client:
        response = client.post("/mcp", headers=headers, json=initialize)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    invalid_host_app = create_app(Settings.model_validate(values))
    with TestClient(invalid_host_app, base_url="http://invalid:8090") as client:
        assert client.post("/mcp", headers=headers, json=initialize).status_code == 421


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


def test_write_file_accepts_session_relative_basename(tmp_path):
    tool = RemediatorTool(str(tmp_path))
    written = tool.write_file(
        "job-a", "remediation/remediation.yml", "---\n- hosts: localhost\n"
    )
    assert written["ok"] is True
    assert written["filename"] == "remediation.yml"
    assert (tmp_path / "job-a" / "remediation.yml").exists()
    assert tool.write_file("job-a", "../escape.yml", "nope")["ok"] is False
