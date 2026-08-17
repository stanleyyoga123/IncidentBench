from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    item for item in yaml.safe_load_all(
        (ROOT / "kubernetes/agents/agent-platform.yaml").read_text()
    ) if item
]


def resources(kind):
    return {item["metadata"]["name"]: item for item in DOCS if item["kind"] == kind}


def test_split_deployments_services_pvc_and_probe_ownership():
    expected = {
        "agent-orchestrator", "rca-agent", "remediator-agent",
        "mcp-tools-investigation", "mcp-tools-remediation",
    }
    assert expected <= set(resources("Deployment"))
    assert expected <= set(resources("Service"))
    assert all(resources("Service")[name]["spec"]["type"] == "ClusterIP" for name in expected)
    assert "mcp-tools-remediation-artifacts" in resources("PersistentVolumeClaim")
    assert {
        "mcp-tools-network-probe-overlay", "mcp-tools-network-probe-underlay"
    } <= set(resources("DaemonSet"))


def test_investigation_rbac_is_read_only_and_accounts_are_split():
    role = resources("ClusterRole")["mcp-tools-investigation"]
    assert {verb for rule in role["rules"] for verb in rule["verbs"]} == {
        "get", "list", "watch"
    }
    assert {
        "mcp-tools-investigation", "mcp-tools-remediation"
    } <= set(resources("ServiceAccount"))
    deployments = resources("Deployment")
    assert deployments["mcp-tools-investigation"]["spec"]["template"]["spec"]["serviceAccountName"] == "mcp-tools-investigation"
    assert deployments["mcp-tools-remediation"]["spec"]["template"]["spec"]["serviceAccountName"] == "mcp-tools-remediation"


def test_ansible_orders_service_groups_before_detector():
    tasks = (ROOT / "ansible/roles/agents/tasks/main.yml").read_text()
    assert tasks.index("Start MCPTools deployments") < tasks.index("Start RCA and Remediator services")
    assert tasks.index("Start RCA and Remediator services") < tasks.index("Start AgentOrchestrator")
    assert tasks.index("Start AgentOrchestrator") < tasks.index("Deploy AnomalyDetector after ingestion is ready")
