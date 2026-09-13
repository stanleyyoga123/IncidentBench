from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def documents(name):
    return [
        item
        for item in yaml.safe_load_all((ROOT / name).read_text())
        if item
    ]


def test_evaluation_owns_runner_secrets_playbook_and_deploy_script():
    secrets = {
        item["metadata"]["name"]: set(item["stringData"])
        for item in documents("kubernetes/secret.example.yml")
    }
    assert secrets == {
        "evaluation-runner-ssh": {"id_ed25519", "known_hosts"},
        "evaluation-runner-env": {"POSTGRES_DSN"},
        "evaluation-runner-s3": {
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_DEFAULT_REGION",
            "S3_RESULTS_URI",
        },
    }

    pod_docs = {
        item["kind"]: item
        for item in documents("kubernetes/pod.yaml")
    }
    assert set(pod_docs) == {"ServiceAccount", "ClusterRoleBinding", "Pod"}
    pod = pod_docs["Pod"]
    assert pod["metadata"]["name"] == "evaluation-runner"
    assert pod["metadata"]["namespace"] == "agents"
    assert pod["spec"]["serviceAccountName"] == "evaluation-runner"
    assert pod["spec"]["nodeSelector"] == {"role": "tools"}
    container = pod["spec"]["containers"][0]
    assert container["image"] == "stanleyyoga123/evaluation:dev"
    assert container["workingDir"] == "/app"
    env = {item["name"]: item["value"] for item in container["env"]}
    assert "POSTGRES_DSN" not in env
    assert env["INFRASTRUCTURE_ROOT"] == "/infrastructure"
    assert env["ONLINE_BOUTIQUE_ROOT"] == "/app/applications/online-boutique"
    assert env["TEASTORE_ROOT"] == "/app/applications/teastore"
    assert env["SOCK_SHOP_ROOT"] == "/app/applications/sock-shop"
    assert "TRAIN_TICKET_ROOT" not in env
    assert env["CHAOS_NODE_SSH_USER"] == "chaos-cleaner"
    assert env["CHAOS_NODE_SSH_IDENTITY_FILE"] == (
        "/var/run/evaluation-runner/ssh/id_ed25519"
    )
    env_from = [item["secretRef"]["name"] for item in container["envFrom"]]
    assert env_from[0] == "evaluation-runner-env"
    assert env_from[1] == "evaluation-runner-s3"
    assert container["volumeMounts"][0]["mountPath"] == (
        "/var/run/evaluation-runner/ssh"
    )
    assert pod["spec"]["volumes"][0]["secret"]["secretName"] == (
        "evaluation-runner-ssh"
    )

    deploy = (ROOT / "deploy.sh").read_text()
    assert "kubectl config current-context" in deploy
    assert "++++++++" in deploy
    assert "secret.example.yml" in deploy
    assert "secret.yml" in deploy
    assert "kubernetes/pod.yaml" in deploy

    build = (ROOT / "build.sh").read_text()
    assert "stanleyyoga123/evaluation:dev" in build
    assert "Evaluation/Dockerfile" in build or "Dockerfile" in build
    assert "--push" in build
