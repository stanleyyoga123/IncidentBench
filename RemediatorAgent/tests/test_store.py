from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

import httpx

from config import Settings
from schema import RemediationJobRequest, RemediationResult
from store import RemediationJobStore


def store_with(handler) -> RemediationJobStore:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport,
        base_url="http://orchestrator",
        headers={"Authorization": "Bearer store"},
    )
    return RemediationJobStore("http://orchestrator", "store", client=client)


def approved_request() -> RemediationJobRequest:
    rca_result = {"remediation_required": True, "summary": "verified"}
    digest = hashlib.sha256(
        json.dumps(rca_result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return RemediationJobRequest(
        rca_job_id=uuid4(),
        rca_result=rca_result,
        rca_result_sha256=digest,
        approval={"actor": "operator", "reason": "evidence reviewed", "workflow_version": 1},
    )


def test_settings_require_orchestrator_not_database():
    settings = Settings.model_validate(
        {
            "orchestrator": {"base_url": "http://orchestrator", "token": "store"},
            "api": {"submit_token": "submit"},
            "mcp": {"url": "http://mcp/mcp", "token": "mcp"},
            "client": {"model": "test", "url": "http://model"},
        }
    )
    assert settings.orchestrator.token == "store"
    assert not hasattr(settings, "database")


def test_create_claim_artifacts_and_needs_review_use_orchestrator_http():
    job_id = uuid4()
    now = datetime.now(timezone.utc).isoformat()
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v1/internal/remediation/jobs":
            return httpx.Response(
                201,
                json={
                    "id": str(job_id),
                    "rca_job_id": str(uuid4()),
                    "status": "queued",
                    "version": 1,
                    "attempts": 0,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        if request.url.path == "/api/v1/internal/execution/claim":
            body = json.loads(request.content)
            assert body["service"] == "remediation"
            assert body["max_attempts"] == 3
            return httpx.Response(204)
        if request.url.path == f"/api/v1/internal/remediation/jobs/{job_id}/artifacts":
            return httpx.Response(200, json={"filenames": ["remediation.yml"]})
        if request.url.path == f"/api/v1/internal/remediation/jobs/{job_id}/tool-calls":
            return httpx.Response(204)
        if request.url.path == f"/api/v1/internal/remediation/jobs/{job_id}/finish":
            body = json.loads(request.content)
            assert body["status"] == "needs_review"
            return httpx.Response(
                200,
                json={
                    "id": str(job_id),
                    "rca_job_id": str(uuid4()),
                    "status": "needs_review",
                    "version": 2,
                    "attempts": 1,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return httpx.Response(404)

    store = store_with(handler)
    created = store.create(approved_request(), "key-1")
    assert created.id == job_id
    assert store.claim("worker", 60) is None
    assert store.list_artifacts(job_id) == ["remediation.yml"]
    store.record_tool_call(
        job_id,
        "remediator.write_file",
        {"filename": "remediation.yml", "content": "---\n"},
        {"ok": True},
    )
    store.needs_review(job_id, RuntimeError("ambiguous execution"))
    assert "/api/v1/internal/execution/claim" in paths
    assert f"/api/v1/internal/remediation/jobs/{job_id}/finish" in paths
