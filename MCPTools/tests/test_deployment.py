from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def documents(name):
    return [
        item
        for item in yaml.safe_load_all((ROOT / name).read_text())
        if item
    ]


def test_owned_secrets_manifests_and_deploy_script_contract():
    secret_documents = documents("kubernetes/secret.yml")
    secrets = {
        item["metadata"]["name"]: set(item["stringData"])
        for item in secret_documents
    }
    assert secrets == {
        "mcp-tools-investigation-secrets": {"MCP_TOKEN"},
        "mcp-tools-remediation-secrets": {"MCP_TOKEN"},
    }
    assert all(
        set(item["stringData"].values()) == {"++++++++"}
        for item in secret_documents
    )

    expected = {
        "kubernetes/investigation.yaml": "mcp-tools-investigation-secrets",
        "kubernetes/remediation.yaml": "mcp-tools-remediation-secrets",
    }
    for path, secret_name in expected.items():
        deployment = next(
            item for item in documents(path) if item["kind"] == "Deployment"
        )
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert container["imagePullPolicy"] == "Always"
        assert container["envFrom"] == [{"secretRef": {"name": secret_name}}]

    deploy = (ROOT / "deploy.sh").read_text()
    assert "kubectl config current-context" in deploy
    assert "++++++++" in deploy
    assert all(
        name in deploy
        for name in (
            "secret.yml",
            "configmap.yaml",
            "rbac.yaml",
            "network-probes.yaml",
            "investigation.yaml",
            "remediation.yaml",
        )
    )
