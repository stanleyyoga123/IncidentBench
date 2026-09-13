from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def documents(name):
    return [item for item in yaml.safe_load_all((ROOT / name).read_text()) if item]


def test_manifest_and_secret_contract():
    secret = documents("kubernetes/secret.example.yml")[0]
    assert set(secret["stringData"]) == {
        "AGENT_STORE_TOKEN", "LEARNING_SUBMIT_TOKEN", "CLIENT_URL", "CLIENT_TOKEN",
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL",
    }
    assert all(value == "++++++++" for value in secret["stringData"].values())
    deployment, service = documents("kubernetes/manifest.yaml")
    pod = deployment["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert deployment["spec"]["replicas"] == 1
    assert service["spec"]["type"] == "ClusterIP"


def test_deploy_and_build_scripts_are_guarded():
    deploy = (ROOT / "deploy.sh").read_text()
    assert "kubectl config current-context" in deploy
    assert "++++++++" in deploy
    assert "stanleyyoga123/learning-agent:dev" in (ROOT / "build.sh").read_text()
