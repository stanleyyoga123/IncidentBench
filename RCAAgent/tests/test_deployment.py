from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def documents(name):
    return [
        item
        for item in yaml.safe_load_all((ROOT / name).read_text())
        if item
    ]


def test_owned_secret_manifest_and_deploy_script_contract():
    secret = documents("kubernetes/secret.example.yml")[0]
    assert secret["metadata"]["name"] == "rca-agent-secrets"
    assert set(secret["stringData"]) == {
        "DATABASE_DSN",
        "RCA_SUBMIT_TOKEN",
        "MCP_TOKEN",
        "CLIENT_URL",
        "CLIENT_TOKEN",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
    }
    assert all("++++++++" in value for value in secret["stringData"].values())

    deployment = documents("kubernetes/manifest.yaml")[0]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["imagePullPolicy"] == "Always"
    assert container["envFrom"] == [
        {"secretRef": {"name": "rca-agent-secrets"}}
    ]

    deploy = (ROOT / "deploy.sh").read_text()
    assert "kubectl config current-context" in deploy
    assert "++++++++" in deploy
    assert all(
        name in deploy
        for name in ("secret.example.yml", "secret.yml", "configmap.yaml", "manifest.yaml")
    )
