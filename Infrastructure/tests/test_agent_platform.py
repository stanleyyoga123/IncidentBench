from pathlib import Path

import yaml


INFRASTRUCTURE = Path(__file__).resolve().parents[1]
WORKSPACE = INFRASTRUCTURE.parent
MANIFEST_PATHS = [
    WORKSPACE / "MCPTools/kubernetes/rbac.yaml",
    WORKSPACE / "MCPTools/kubernetes/network-probes.yaml",
    WORKSPACE / "MCPTools/kubernetes/investigation.yaml",
    WORKSPACE / "MCPTools/kubernetes/remediation.yaml",
    WORKSPACE / "RCAAgent/kubernetes/manifest.yaml",
    WORKSPACE / "RemediatorAgent/kubernetes/manifest.yaml",
    WORKSPACE / "AgentOrchestrator/kubernetes/manifest.yaml",
    INFRASTRUCTURE / "kubernetes/agents/shared.yaml",
    WORKSPACE / "AnomalyDetector/kubernetes/manifest.yaml",
]


def load_documents(path):
    return [item for item in yaml.safe_load_all(path.read_text()) if item]


DOCS = [item for path in MANIFEST_PATHS for item in load_documents(path)]


def resources(kind):
    return {item["metadata"]["name"]: item for item in DOCS if item["kind"] == kind}


def test_component_manifest_paths_exist_and_old_bundles_are_removed():
    assert all(path.is_file() for path in MANIFEST_PATHS)
    assert not (INFRASTRUCTURE / "kubernetes/agents/agent-platform.yaml").exists()
    assert not (INFRASTRUCTURE / "kubernetes/agents/anomaly-detector.yaml").exists()


def test_resource_identities_are_unique_across_component_manifests():
    identities = [
        (
            item["kind"],
            item["metadata"].get("namespace"),
            item["metadata"]["name"],
        )
        for item in DOCS
    ]
    assert len(identities) == len(set(identities))


def test_split_deployments_services_pvc_and_probe_ownership():
    staged = {
        "agent-orchestrator",
        "rca-agent",
        "remediator-agent",
        "mcp-tools-investigation",
        "mcp-tools-remediation",
    }
    expected = staged | {"anomaly-detector"}
    deployments = resources("Deployment")
    services = resources("Service")

    assert expected == set(deployments)
    assert expected == set(services)
    assert all(services[name]["spec"]["type"] == "ClusterIP" for name in expected)
    assert all(deployments[name]["spec"]["replicas"] == 0 for name in staged)
    assert deployments["anomaly-detector"]["spec"]["replicas"] == 1
    assert "mcp-tools-remediation-artifacts" in resources("PersistentVolumeClaim")
    assert {
        "mcp-tools-network-probe-overlay",
        "mcp-tools-network-probe-underlay",
    } == set(resources("DaemonSet"))


def test_investigation_rbac_is_read_only_and_accounts_are_split():
    role = resources("ClusterRole")["mcp-tools-investigation"]
    assert {verb for rule in role["rules"] for verb in rule["verbs"]} == {
        "get",
        "list",
        "watch",
    }
    assert {
        "mcp-tools-investigation",
        "mcp-tools-remediation",
    } == set(resources("ServiceAccount"))
    deployments = resources("Deployment")
    assert (
        deployments["mcp-tools-investigation"]["spec"]["template"]["spec"][
            "serviceAccountName"
        ]
        == "mcp-tools-investigation"
    )
    assert (
        deployments["mcp-tools-remediation"]["spec"]["template"]["spec"][
            "serviceAccountName"
        ]
        == "mcp-tools-remediation"
    )


def test_remediation_pvc_and_secret_mount_contracts():
    deployments = resources("Deployment")
    remediation = deployments["mcp-tools-remediation"]
    assert remediation["spec"]["strategy"]["type"] == "Recreate"
    mounts = remediation["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]
    assert {"name": "artifacts", "mountPath": "/sessions"} in mounts

    expected_secrets = {
        "anomaly-detector": "anomaly-detector-config",
        "agent-orchestrator": "agent-orchestrator-config",
        "rca-agent": "rca-agent-config",
        "remediator-agent": "remediator-agent-config",
        "mcp-tools-investigation": "mcp-tools-investigation-config",
        "mcp-tools-remediation": "mcp-tools-remediation-config",
    }
    for name, secret_name in expected_secrets.items():
        volumes = deployments[name]["spec"]["template"]["spec"]["volumes"]
        assert any(
            volume.get("secret", {}).get("secretName") == secret_name
            for volume in volumes
        )


def test_dev_images_use_docker_hub_and_always_pull():
    expected_images = {
        "anomaly-detector": "stanleyyoga123/anomaly-detector:dev",
        "agent-orchestrator": "stanleyyoga123/agent-orchestrator:dev",
        "rca-agent": "stanleyyoga123/rca-agent:dev",
        "remediator-agent": "stanleyyoga123/remediator-agent:dev",
        "mcp-tools-investigation": "stanleyyoga123/mcp-tools:dev",
        "mcp-tools-remediation": "stanleyyoga123/mcp-tools:dev",
    }
    for name, image in expected_images.items():
        container = resources("Deployment")[name]["spec"]["template"]["spec"][
            "containers"
        ][0]
        assert container["image"] == image
        assert container["imagePullPolicy"] == "Always"


def test_infrastructure_shared_manifest_contains_only_platform_policy():
    shared = load_documents(INFRASTRUCTURE / "kubernetes/agents/shared.yaml")
    assert [
        (item["kind"], item["metadata"]["name"])
        for item in shared
    ] == [("NetworkPolicy", "agent-platform-ingress")]


def test_ansible_loads_every_component_manifest_and_preserves_rollout_order():
    tasks = (INFRASTRUCTURE / "ansible/roles/agents/tasks/main.yml").read_text()
    references = [
        "MCPTools/kubernetes/rbac.yaml",
        "MCPTools/kubernetes/network-probes.yaml",
        "MCPTools/kubernetes/investigation.yaml",
        "MCPTools/kubernetes/remediation.yaml",
        "RCAAgent/kubernetes/manifest.yaml",
        "RemediatorAgent/kubernetes/manifest.yaml",
        "AgentOrchestrator/kubernetes/manifest.yaml",
        "kubernetes/agents/shared.yaml",
        "AnomalyDetector/kubernetes/manifest.yaml",
    ]
    assert all(reference in tasks for reference in references)
    assert tasks.index("Start MCPTools deployments") < tasks.index(
        "Start RCA and Remediator services"
    )
    assert tasks.index("Start RCA and Remediator services") < tasks.index(
        "Start AgentOrchestrator"
    )
    assert tasks.index("Start AgentOrchestrator") < tasks.index(
        "Deploy AnomalyDetector after ingestion is ready"
    )
