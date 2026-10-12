from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def documents(name):
    return [
        item
        for item in yaml.safe_load_all((ROOT / name).read_text())
        if item
    ]


def test_owned_secret_manifests_and_deploy_script_contract():
    secret = documents("kubernetes/secret.example.yml")[0]
    assert secret["metadata"]["name"] == "evaluation-orchestrator-secrets"
    assert set(secret["stringData"]) == {
        "DATABASE_DSN",
        "AGENT_CONTROL_TOKEN",
        "AGENT_STORE_TOKEN",
    }
    assert all("++++++++" in value for value in secret["stringData"].values())

    deployment = documents("kubernetes/manifest.yaml")[0]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["imagePullPolicy"] == "Always"
    assert container["envFrom"] == [
        {"secretRef": {"name": "evaluation-orchestrator-secrets"}}
    ]
    policy = documents("kubernetes/network-policy.yaml")[0]
    assert policy["metadata"]["name"] == "evaluation-orchestrator-ingress"

    deploy = (ROOT / "deploy.sh").read_text()
    assert "kubectl config current-context" in deploy
    assert "++++++++" in deploy
    assert all(
        name in deploy
        for name in (
            "secret.example.yml",
            "secret.yml",
            "configmap.yaml",
            "network-policy.yaml",
            "manifest.yaml",
        )
    )


def test_runner_can_reach_only_orchestrator_control_port():
    policy = documents("kubernetes/network-policy.yaml")[0]
    assert policy["spec"]["podSelector"] == {"matchLabels": {"app": "evaluation-orchestrator"}}
    assert policy["spec"]["ingress"] == [{
        "from": [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": "evaluation-runner"}}}],
        "ports": [{"protocol": "TCP", "port": 8080}],
    }]
