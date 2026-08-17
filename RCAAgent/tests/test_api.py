from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from api import create_app
from config import Settings
from schema import RCAJob


class Store:
    def __init__(self):
        self.job = None
        self.key = None

    def create(self, request, key):
        self.key = key
        now = datetime.now(timezone.utc)
        self.job = RCAJob(
            id=uuid4(), workflow_id=request.workflow_id, status="queued",
            version=1, request=request.model_dump(mode="json"),
            created_at=now, updated_at=now,
        )
        return self.job

    def get(self, job_id):
        return self.job if self.job and self.job.id == job_id else None


def test_rca_api_auth_idempotency_status_and_openapi():
    settings = Settings.model_validate({
        "database": {"dsn": "postgresql://unused"},
        "api": {"submit_token": "submit"},
        "mcp": {"url": "http://mcp/mcp", "token": "mcp"},
        "client": {"model": "test", "url": "http://model"},
    })
    store = Store()
    app = create_app(settings, start_worker=False, store=store, engine=object())
    body = {"anomalies": [{"event_id": "a" * 64}]}
    with TestClient(app) as client:
        assert client.post("/api/v1/rca/jobs", json=body).status_code == 401
        response = client.post(
            "/api/v1/rca/jobs", json=body,
            headers={"Authorization": "Bearer submit", "Idempotency-Key": "key-1"},
        )
        assert response.status_code == 202
        assert store.key == "key-1"
        job_id = response.json()["id"]
        assert client.get(
            f"/api/v1/rca/jobs/{job_id}",
            headers={"Authorization": "Bearer submit"},
        ).json()["status"] == "queued"
    assert {value["operationId"] for path in app.openapi()["paths"].values() for value in path.values() if "operationId" in value} == {
        "create_rca_job", "get_rca_job", "get_rca_agent_health"
    }
