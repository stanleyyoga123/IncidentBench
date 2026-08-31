from pathlib import Path

import yaml


INFRASTRUCTURE = Path(__file__).resolve().parents[1]
WORKSPACE = INFRASTRUCTURE.parent
MANIFEST_PATHS = [
    WORKSPACE / "MCPTools/kubernetes/configmap.yaml",
    WORKSPACE / "MCPTools/kubernetes/rbac.yaml",
    WORKSPACE / "MCPTools/kubernetes/network-probes.yaml",
    WORKSPACE / "MCPTools/kubernetes/investigation.yaml",
    WORKSPACE / "MCPTools/kubernetes/remediation.yaml",
    WORKSPACE / "RCAAgent/kubernetes/configmap.yaml",
    WORKSPACE / "RCAAgent/kubernetes/manifest.yaml",
    WORKSPACE / "RemediatorAgent/kubernetes/configmap.yaml",
    WORKSPACE / "RemediatorAgent/kubernetes/manifest.yaml",
    WORKSPACE / "LearningAgent/kubernetes/configmap.yaml",
    WORKSPACE / "LearningAgent/kubernetes/manifest.yaml",
    WORKSPACE / "AgentOrchestrator/kubernetes/configmap.yaml",
    WORKSPACE / "AgentOrchestrator/kubernetes/network-policy.yaml",
    WORKSPACE / "AgentOrchestrator/kubernetes/manifest.yaml",
    WORKSPACE / "AnomalyDetector/kubernetes/configmap.yaml",
    WORKSPACE / "AnomalyDetector/kubernetes/manifest.yaml",
]
SECRET_CONTRACTS = {
    "AnomalyDetector": {
        "anomaly-detector-secrets": {
            "AGENT_INGESTION_TOKEN",
            "DETECTOR_PROFILE_API_TOKEN",
        }
    },
    "AgentOrchestrator": {
        "agent-orchestrator-secrets": {
            "DATABASE_DSN",
            "AGENT_INGESTION_TOKEN",
            "AGENT_CONTROL_TOKEN",
            "AGENT_STORE_TOKEN",
            "RCA_SUBMIT_TOKEN",
            "REMEDIATOR_SUBMIT_TOKEN",
            "LEARNING_SUBMIT_TOKEN",
        }
    },
    "RCAAgent": {
        "rca-agent-secrets": {
            "AGENT_STORE_TOKEN",
            "RCA_SUBMIT_TOKEN",
            "MCP_TOKEN",
            "CLIENT_URL",
            "CLIENT_TOKEN",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_BASE_URL",
        }
    },
    "RemediatorAgent": {
        "remediator-agent-secrets": {
            "AGENT_STORE_TOKEN",
            "REMEDIATOR_SUBMIT_TOKEN",
            "MCP_TOKEN",
            "CLIENT_URL",
            "CLIENT_TOKEN",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_BASE_URL",
        }
    },
    "LearningAgent": {
        "learning-agent-secrets": {
            "AGENT_STORE_TOKEN",
            "LEARNING_SUBMIT_TOKEN",
            "CLIENT_URL",
            "CLIENT_TOKEN",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_BASE_URL",
        }
    },
    "MCPTools": {
        "mcp-tools-investigation-secrets": {"MCP_TOKEN"},
        "mcp-tools-remediation-secrets": {"MCP_TOKEN"},
    },
}


def load_documents(path):
    return [item for item in yaml.safe_load_all(path.read_text()) if item]


DOCS = [item for path in MANIFEST_PATHS for item in load_documents(path)]


def resources(kind):
    return {item["metadata"]["name"]: item for item in DOCS if item["kind"] == kind}


def test_component_manifest_paths_exist_and_central_bundles_are_removed():
    assert all(path.is_file() for path in MANIFEST_PATHS)
    assert not (INFRASTRUCTURE / "kubernetes/agents/agent-platform.yaml").exists()
    assert not (INFRASTRUCTURE / "kubernetes/agents/anomaly-detector.yaml").exists()
    assert not (INFRASTRUCTURE / "kubernetes/agents/shared.yaml").exists()
    assert not (INFRASTRUCTURE / "kubernetes/database/postgres.yaml").exists()
    assert not (INFRASTRUCTURE / "kubernetes/online-boutique").exists()
    assert (
        WORKSPACE / "Evaluation/applications/online-boutique/kustomize/kustomization.yaml"
    ).is_file()
    assert not (INFRASTRUCTURE / "compose/database.yml").exists()


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
    expected = {
        "agent-orchestrator",
        "rca-agent",
        "remediator-agent",
        "learning-agent",
        "mcp-tools-investigation",
        "mcp-tools-remediation",
        "anomaly-detector",
    }
    deployments = resources("Deployment")
    services = resources("Service")

    assert expected == set(deployments)
    assert expected == set(services)
    assert all(services[name]["spec"]["type"] == "ClusterIP" for name in expected)
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


def test_remediation_pvc_configmap_and_secret_contracts():
    deployments = resources("Deployment")
    remediation = deployments["mcp-tools-remediation"]
    assert remediation["spec"]["strategy"]["type"] == "Recreate"
    mounts = remediation["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]
    assert {"name": "artifacts", "mountPath": "/sessions"} in mounts

    expected_configmaps = {
        "anomaly-detector": "anomaly-detector-config",
        "agent-orchestrator": "agent-orchestrator-config",
        "rca-agent": "rca-agent-config",
        "remediator-agent": "remediator-agent-config",
        "learning-agent": "learning-agent-config",
        "mcp-tools-investigation": "mcp-tools-investigation-config",
        "mcp-tools-remediation": "mcp-tools-remediation-config",
    }
    for name, configmap_name in expected_configmaps.items():
        volumes = deployments[name]["spec"]["template"]["spec"]["volumes"]
        assert any(
            volume.get("configMap", {}).get("name") == configmap_name
            for volume in volumes
        )
        container = deployments[name]["spec"]["template"]["spec"]["containers"][0]
        assert container["envFrom"] == [
            {"secretRef": {"name": configmap_name.replace("-config", "-secrets")}}
        ]

    configmaps = resources("ConfigMap")
    assert set(expected_configmaps.values()) == set(configmaps)
    assert all(".env" in configmap["data"] for configmap in configmaps.values())


def test_component_owned_secrets_have_exact_names_keys_and_placeholders():
    for component, expected_contract in SECRET_CONTRACTS.items():
        path = WORKSPACE / component / "kubernetes/secret.example.yml"
        actual_contract = {
            document["metadata"]["name"]: set(document["stringData"])
            for document in load_documents(path)
        }
        assert actual_contract == expected_contract
        assert "++++++++" in path.read_text()


def test_pairwise_tokens_are_declared_by_matching_consumers():
    keys_by_component = {
        component: set().union(*contracts.values())
        for component, contracts in SECRET_CONTRACTS.items()
    }
    assert "AGENT_INGESTION_TOKEN" in keys_by_component["AnomalyDetector"]
    assert "AGENT_INGESTION_TOKEN" in keys_by_component["AgentOrchestrator"]
    assert "AGENT_STORE_TOKEN" in keys_by_component["AgentOrchestrator"]
    assert "AGENT_STORE_TOKEN" in keys_by_component["RCAAgent"]
    assert "AGENT_STORE_TOKEN" in keys_by_component["RemediatorAgent"]
    assert "RCA_SUBMIT_TOKEN" in keys_by_component["AgentOrchestrator"]
    assert "RCA_SUBMIT_TOKEN" in keys_by_component["RCAAgent"]
    assert "REMEDIATOR_SUBMIT_TOKEN" in keys_by_component["AgentOrchestrator"]
    assert "REMEDIATOR_SUBMIT_TOKEN" in keys_by_component["RemediatorAgent"]
    assert "LEARNING_SUBMIT_TOKEN" in keys_by_component["AgentOrchestrator"]
    assert "LEARNING_SUBMIT_TOKEN" in keys_by_component["LearningAgent"]
    assert "AGENT_STORE_TOKEN" in keys_by_component["LearningAgent"]
    assert "DATABASE_DSN" in keys_by_component["AgentOrchestrator"]
    assert "DATABASE_DSN" not in keys_by_component["RCAAgent"]
    assert "DATABASE_DSN" not in keys_by_component["RemediatorAgent"]
    assert "MCP_TOKEN" in keys_by_component["RCAAgent"]
    assert "MCP_TOKEN" in keys_by_component["RemediatorAgent"]
    assert {
        "mcp-tools-investigation-secrets",
        "mcp-tools-remediation-secrets",
    } == set(SECRET_CONTRACTS["MCPTools"])


def test_component_deploy_scripts_own_manifests_and_refuse_placeholders():
    expected_references = {
        "AnomalyDetector": {
            "secret.example.yml",
            "secret.yml",
            "configmap.yaml",
            "manifest.yaml",
        },
        "AgentOrchestrator": {
            "secret.example.yml",
            "secret.yml",
            "configmap.yaml",
            "network-policy.yaml",
            "manifest.yaml",
        },
        "RCAAgent": {
            "secret.example.yml",
            "secret.yml",
            "configmap.yaml",
            "manifest.yaml",
        },
        "RemediatorAgent": {
            "secret.example.yml",
            "secret.yml",
            "configmap.yaml",
            "manifest.yaml",
        },
        "LearningAgent": {
            "secret.example.yml",
            "secret.yml",
            "configmap.yaml",
            "manifest.yaml",
        },
        "MCPTools": {
            "secret.example.yml",
            "secret.yml",
            "configmap.yaml",
            "rbac.yaml",
            "network-probes.yaml",
            "investigation.yaml",
            "remediation.yaml",
        },
    }
    for component, references in expected_references.items():
        script = WORKSPACE / component / "deploy.sh"
        content = script.read_text()
        assert script.stat().st_mode & 0o111
        assert "kubectl config current-context" in content
        assert "++++++++" in content
        assert all(reference in content for reference in references)
        assert "--context" not in content


def test_dev_images_use_docker_hub_and_always_pull():
    expected_images = {
        "anomaly-detector": "stanleyyoga123/anomaly-detector:dev",
        "agent-orchestrator": "stanleyyoga123/agent-orchestrator:dev",
        "learning-agent": "stanleyyoga123/learning-agent:dev",
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


def test_network_policy_is_owned_by_agent_orchestrator():
    policies = resources("NetworkPolicy")
    assert set(policies) == {"agent-platform-ingress"}
    assert (
        policies["agent-platform-ingress"]["metadata"]["namespace"] == "agents"
    )


def test_infrastructure_site_is_platform_only():
    site = (INFRASTRUCTURE / "ansible/site.yml").read_text()
    assert "playbooks/cluster.yml" in site
    assert "playbooks/platform.yml" in site
    assert "playbooks/node-chaosd.yml" in site
    assert "playbooks/node-cleaner.yml" in site
    for deleted_playbook in ("applications.yml", "secrets.yml"):
        assert deleted_playbook not in site
        assert not (INFRASTRUCTURE / "ansible/playbooks" / deleted_playbook).exists()


def test_platform_bootstraps_only_shared_platform_namespaces():
    variables = yaml.safe_load(
        (INFRASTRUCTURE / "ansible/group_vars/all.yml").read_text()
    )
    platform = (INFRASTRUCTURE / "ansible/playbooks/platform.yml").read_text()

    for key, namespace in {
        "agents_namespace": "agents",
        "utility_namespace": "utility",
    }.items():
        assert variables[key] == namespace
        assert key in platform
    assert "application_namespaces" not in variables
    assert "+ application_namespaces" not in platform
    assert "online-boutique" not in platform
    assert "teastore" not in platform
    assert "train-ticket" not in platform


def test_istio_is_pinned_and_keeps_metrics_and_tracing_providers():
    variables = yaml.safe_load(
        (INFRASTRUCTURE / "ansible/group_vars/all.yml").read_text()
    )
    platform = (INFRASTRUCTURE / "ansible/playbooks/platform.yml").read_text()
    dedicated_playbook = (
        INFRASTRUCTURE / "ansible/playbooks/istio.yml"
    ).read_text()
    tasks = (INFRASTRUCTURE / "ansible/roles/istio/tasks/main.yml").read_text()
    telemetry = load_documents(INFRASTRUCTURE / "values/jaeger/telemetry.yaml")[0]

    assert variables["istio_chart_version"] == "1.29.2"
    assert "name: istio" in platform
    assert "role: istio" in dedicated_playbook
    assert 'chart_version: "{{ istio_chart_version }}"' in tasks
    assert "chart_ref: istio/base" in tasks
    assert "chart_ref: istio/istiod" in tasks
    assert "chart_ref: istio/gateway" in tasks
    assert "metrics:" in tasks
    assert "- prometheus" in tasks
    assert "tracing:" in tasks
    assert "- jaeger" in tasks
    assert telemetry["spec"]["metrics"] == [
        {"providers": [{"name": "prometheus"}]}
    ]


def test_cluster_and_observability_versions_are_explicitly_pinned():
    variables = yaml.safe_load(
        (INFRASTRUCTURE / "ansible/group_vars/all.yml").read_text()
    )

    assert {
        "k3s_version": variables["k3s_version"],
        "prometheus_chart_version": variables["prometheus_chart_version"],
        "grafana_chart_version": variables["grafana_chart_version"],
        "loki_chart_version": variables["loki_chart_version"],
        "alloy_chart_version": variables["alloy_chart_version"],
    } == {
        "k3s_version": "v1.34.6+k3s1",
        "prometheus_chart_version": "29.25.0",
        "grafana_chart_version": "12.10.4",
        "loki_chart_version": "18.9.0",
        "alloy_chart_version": "1.11.1",
    }


def test_platform_storage_and_terminal_pod_growth_are_bounded():
    variables = yaml.safe_load(
        (INFRASTRUCTURE / "ansible/group_vars/all.yml").read_text()
    )
    cluster = (INFRASTRUCTURE / "ansible/playbooks/cluster.yml").read_text()
    platform = (INFRASTRUCTURE / "ansible/playbooks/platform.yml").read_text()
    prometheus = yaml.safe_load(
        (INFRASTRUCTURE / "values/prometheus/values.yaml").read_text()
    )
    loki = yaml.safe_load((INFRASTRUCTURE / "values/loki/values.yaml").read_text())
    alloy = (INFRASTRUCTURE / "values/alloy/values.yaml").read_text()
    rules = yaml.safe_load(
        (INFRASTRUCTURE / "values/prometheus/recording-rules.values.yaml").read_text()
    )

    assert variables["terminated_pod_gc_threshold"] == 500
    assert "terminated-pod-gc-threshold={{ terminated_pod_gc_threshold }}" in cluster
    assert "tools_node_min_root_free_gb" in platform
    assert prometheus["server"]["retentionSize"] == "4GB"
    assert loki["loki"]["ingester"]["wal"] == {
        "checkpoint_duration": "1m",
        "flush_on_shutdown": True,
    }
    assert loki["loki"]["limits_config"]["ingestion_rate_mb"] == 2
    assert '__meta_kubernetes_pod_phase' in alloy
    alerts = rules["serverFiles"]["alerting_rules.yml"]["groups"][0]["rules"]
    assert {rule["alert"] for rule in alerts} == {
        "ToolsNodeRootDiskLow",
        "ToolsNodeDiskPressure",
        "TerminalPodBacklog",
    }
