import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from api import create_app
from config import Settings
from schema import LearningJob


class Store:
    def __init__(self):
        self.jobs = {}
        self.keys = {}

    def create(self, request, key):
        if key in self.keys:
            return self.keys[key]
        job = LearningJob(
            id=uuid4(), workflow_id=request.workflow_id, status="queued", version=1,
            request=request.model_dump(mode="json"), attempts=0,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        self.jobs[job.id] = job
        self.keys[key] = job
        return job

    def get(self, job_id):
        return self.jobs.get(job_id)

    def close(self):
        pass


def settings():
    return Settings.model_validate({
        "orchestrator": {"base_url": "http://orchestrator", "token": "store"},
        "api": {"submit_token": "submit"},
        "client": {"model": "test", "url": "http://model/v1"},
    })


def request():
    workflow_id = uuid4()
    source = {
        "workflow_id": str(workflow_id),
        "completion_type": "no_action",
        "anomalies": [{"event_id": "a" * 64}],
        "rca": {"job_id": str(uuid4()), "result": {"summary": "recovered"}},
        "remediation": None,
        "tool_calls": [],
    }
    canonical = json.dumps(source, sort_keys=True, separators=(",", ":"))
    return {
        "workflow_id": str(workflow_id),
        "source": source,
        "source_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    }


def test_auth_jobs_and_operation_ids():
    store = Store()
    app = create_app(settings(), start_worker=False, store=store, engine=object())
    with TestClient(app) as client:
        assert client.post("/api/v1/learning/jobs", json=request()).status_code == 401
        created = client.post(
            "/api/v1/learning/jobs",
            headers={"Authorization": "Bearer submit", "Idempotency-Key": "one"},
            json=request(),
        )
        assert created.status_code == 202
        duplicate = client.post(
            "/api/v1/learning/jobs",
            headers={"Authorization": "Bearer submit", "Idempotency-Key": "one"},
            json=request(),
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == created.json()["id"]
        fetched = client.get(
            f"/api/v1/learning/jobs/{created.json()['id']}",
            headers={"Authorization": "Bearer submit"},
        )
        assert fetched.status_code == 200

    ids = {
        value["operationId"]
        for path in app.openapi()["paths"].values()
        for value in path.values()
        if "operationId" in value
    }
    assert ids == {
        "get_learning_agent_health", "create_learning_job", "get_learning_job"
    }


def test_rejects_source_hash_mismatch():
    app = create_app(settings(), start_worker=False, store=Store(), engine=object())
    payload = request()
    payload["source_sha256"] = "0" * 64
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/learning/jobs",
            headers={"Authorization": "Bearer submit"},
            json=payload,
        )
    assert response.status_code == 422
