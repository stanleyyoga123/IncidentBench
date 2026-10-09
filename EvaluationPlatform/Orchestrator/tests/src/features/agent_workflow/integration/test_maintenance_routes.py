import pytest
from fastapi.testclient import TestClient


JOB_ID = "00000000-0000-0000-0000-000000000001"
MUTATIONS = [
    ("/api/v1/anomalies", "ingest"),
    *[(f"/api/v1/workflows/{JOB_ID}/{action}", "control") for action in ("approve", "decline", "retry")],
    *[(f"/api/v1/lessons/{JOB_ID}/{action}", "control") for action in ("enable", "disable")],
    *[(f"/api/v1/internal/{service}/jobs", "store") for service in ("rca", "remediation", "learning")],
    *[(f"/api/v1/internal/{service}/jobs/{JOB_ID}/{action}", "store")
      for service in ("rca", "remediation", "learning") for action in ("output", "finish")],
    *[(f"/api/v1/internal/{service}/jobs/{JOB_ID}/tool-calls", "store") for service in ("rca", "remediation")],
    (f"/api/v1/internal/remediation/jobs/{JOB_ID}/artifacts", "store"),
    *[(f"/api/v1/internal/execution/{action}", "store") for action in ("claim", "renew")],
]


@pytest.mark.parametrize("path,token", MUTATIONS)
def test_maintenance_blocks_agent_mutations_after_authentication(
    separated_client: TestClient, path: str, token: str,
) -> None:
    """Evaluation API contract gates every agent write, preserving token separation."""
    client = separated_client
    control = {"Authorization": "Bearer control"}
    run = {"run_id": "runner-feature-test"}
    assert client.post("/api/v1/evaluation/acquire", headers=control, json=run).status_code == 200

    wrong_token = "control" if token != "control" else "store"
    assert client.post(path, headers={"Authorization": f"Bearer {wrong_token}"}, json={}).status_code == 401
    # The gate must reject writes before handlers or body validation can run.
    blocked = client.post(path, headers={"Authorization": f"Bearer {token}"}, json={})
    assert blocked.status_code == 409, blocked.text

    # Runner controls remain usable while the separate workflow feature is gated.
    assert client.post("/api/v1/evaluation/reset", headers=control, json=run).status_code == 200
