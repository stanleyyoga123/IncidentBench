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
    assert secret["metadata"]["name"] == "anomaly-detector-secrets"
    assert set(secret["stringData"]) == {
        "AGENT_INGESTION_TOKEN",
        "DETECTOR_PROFILE_API_TOKEN",
    }
    assert set(secret["stringData"].values()) == {"++++++++"}

    deployment = documents("kubernetes/manifest.yaml")[0]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["imagePullPolicy"] == "Always"
    assert container["envFrom"] == [
        {"secretRef": {"name": "anomaly-detector-secrets"}}
    ]

    deploy = (ROOT / "deploy.sh").read_text()
    assert "kubectl config current-context" in deploy
    assert "++++++++" in deploy
    assert all(
        name in deploy
        for name in ("secret.example.yml", "secret.yml", "configmap.yaml", "manifest.yaml")
    )


def test_image_uses_runtime_mounted_env_instead_of_missing_config_directory():
    dockerfile = (ROOT / "Dockerfile").read_text()
    deployment = documents("kubernetes/manifest.yaml")[0]
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert "COPY src ./src" in dockerfile
    assert "COPY config" not in dockerfile
    assert {
        "name": "config",
        "mountPath": "/app/.env",
        "subPath": ".env",
        "readOnly": True,
    } in container["volumeMounts"]
    assert {
        "name": "config",
        "configMap": {"name": "anomaly-detector-config"},
    } in pod_spec["volumes"]
