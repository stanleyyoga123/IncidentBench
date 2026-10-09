from fastapi.testclient import TestClient


CONTROL_HEADERS = {"Authorization": "Bearer control"}
RUN = {"run_id": "runner-feature-test"}


def test_runner_lifecycle_and_export_work_without_agent_workflow_dependencies(
    separated_client: TestClient,
) -> None:
    """Evaluation API contract: control and export never contact agent services."""
    client = separated_client
    assert client.get("/api/v1/evaluation", headers=CONTROL_HEADERS).json() == {
        "id": 1, "run_id": None, "maintenance": False, "reset_done": False,
    }

    for action in ("acquire", "reset", "resume", "pause"):
        response = client.post(f"/api/v1/evaluation/{action}", headers=CONTROL_HEADERS, json=RUN)
        assert response.status_code == 200, response.text

    exported = client.get("/api/v1/evaluation/export", headers=CONTROL_HEADERS, params=RUN)
    assert exported.status_code == 200, exported.text
    assert exported.json() == {
        "schema_version": 1,
        "run_id": RUN["run_id"],
        "sessions": {
            "anomaly": [], "rca_session": [], "remediation_run": [],
            "remediation_session": [], "learning_session": [], "workflow": [],
        },
    }
    released = client.post("/api/v1/evaluation/release", headers=CONTROL_HEADERS, json=RUN)
    assert released.status_code == 200
    assert released.json() == {
        "id": 1, "run_id": None, "maintenance": True, "reset_done": True,
    }
