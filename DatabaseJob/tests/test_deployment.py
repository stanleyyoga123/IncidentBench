from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_documents(name):
    path = ROOT / name
    return [document for document in yaml.safe_load_all(path.read_text()) if document]


def test_database_secret_has_exact_name_keys_and_placeholders():
    secret = load_documents("kubernetes/secret.yml")[0]

    assert secret["metadata"] == {
        "name": "anomaly-detector-postgres",
        "namespace": "agents",
    }
    assert set(secret["stringData"]) == {
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    }
    assert set(secret["stringData"].values()) == {"++++++++"}


def test_postgres_and_migration_reference_owned_secret_and_always_pull_job():
    postgres = {
        document["kind"]: document
        for document in load_documents("kubernetes/postgres.yaml")
    }
    statefulset = postgres["StatefulSet"]
    postgres_container = statefulset["spec"]["template"]["spec"]["containers"][0]
    assert postgres_container["envFrom"] == [
        {"secretRef": {"name": "anomaly-detector-postgres"}}
    ]

    job = load_documents("kubernetes/job.yaml")[0]
    job_container = job["spec"]["template"]["spec"]["containers"][0]
    assert job_container["imagePullPolicy"] == "Always"
    assert {
        item["valueFrom"]["secretKeyRef"]["key"]: item["valueFrom"]["secretKeyRef"][
            "name"
        ]
        for item in job_container["env"]
    } == {
        "POSTGRES_DB": "anomaly-detector-postgres",
        "POSTGRES_USER": "anomaly-detector-postgres",
        "POSTGRES_PASSWORD": "anomaly-detector-postgres",
    }


def test_compose_and_deploy_are_databasejob_owned_and_safe():
    compose = load_documents("compose/database.yml")[0]
    assert set(compose["services"]) == {"postgres", "migration"}
    assert compose["services"]["migration"]["build"] == {
        "context": "..",
        "dockerfile": "Dockerfile",
    }

    deploy = ROOT / "deploy.sh"
    content = deploy.read_text()
    assert deploy.stat().st_mode & 0o111
    assert "kubectl config current-context" in content
    assert "replace every ++++++++ placeholder" in content
    assert "ALLOW_AGENT_WORKFLOW_RESET" in content
    assert "kubernetes/postgres.yaml" in content
    assert "kubernetes/job.yaml" in content
    assert "database-secret-checksum" in content
    assert "\\password $POSTGRES_USER" in content
    assert "--context" not in content
