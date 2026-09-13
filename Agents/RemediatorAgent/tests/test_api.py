from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from api import create_app
from config import Settings
from schema import RemediationJob


class Store:
    def __init__(self):
        self.job = None

    def create(self, request, _key):
        now = datetime.now(timezone.utc)
        self.job = RemediationJob(
            id=uuid4(), workflow_id=request.workflow_id,
            rca_job_id=request.rca_job_id, status="queued", version=1,
            request=request.model_dump(mode="json"), created_at=now, updated_at=now,
        )
        return self.job

    def get(self, job_id):
        return self.job if self.job and self.job.id == job_id else None


def test_remediation_requires_approval_plan_and_matching_hash():
    settings = Settings.model_validate({
        "orchestrator": {"base_url": "http://orchestrator", "token": "store"},
        "api": {"submit_token": "submit"},
        "mcp": {"url": "http://mcp/mcp", "token": "mcp"},
        "client": {"model": "test", "url": "http://model"},
    })
    app = create_app(settings, start_worker=False, store=Store(), engine=object())
    result = {"remediation_required": True, "summary": "verified incident"}
    digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    body = {
        "rca_job_id": str(uuid4()), "rca_result": result,
        "rca_result_sha256": digest,
        "approval": {"actor": "operator", "reason": "evidence reviewed", "workflow_version": 2},
    }
    with TestClient(app) as client:
        assert client.post("/api/v1/remediation/jobs", json=body).status_code == 401
        bad = {**body, "rca_result_sha256": "0" * 64}
        assert client.post(
            "/api/v1/remediation/jobs", json=bad,
            headers={"Authorization": "Bearer submit"},
        ).status_code == 422
        response = client.post(
            "/api/v1/remediation/jobs", json=body,
            headers={"Authorization": "Bearer submit", "Idempotency-Key": "key-1"},
        )
        assert response.status_code == 202
        job_id = response.json()["id"]
        assert client.get(
            f"/api/v1/remediation/jobs/{job_id}",
            headers={"Authorization": "Bearer submit"},
        ).json()["status"] == "queued"
