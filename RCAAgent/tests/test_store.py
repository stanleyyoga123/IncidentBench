from datetime import datetime, timezone
from uuid import uuid4

import httpx

from config import Settings
from schema import RCAJobRequest, RCAResult
from store import RCAJobStore


def store_with(handler) -> RCAJobStore:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport,
        base_url="http://orchestrator",
        headers={"Authorization": "Bearer store"},
    )
    return RCAJobStore("http://orchestrator", "store", client=client)


def test_settings_require_orchestrator_not_database():
    settings = Settings.model_validate(
        {
            "orchestrator": {"base_url": "http://orchestrator", "token": "store"},
            "api": {"submit_token": "submit"},
            "mcp": {"url": "http://mcp/mcp", "token": "mcp"},
            "client": {"model": "test", "url": "http://model"},
        }
    )
    assert settings.orchestrator.base_url == "http://orchestrator"
    assert not hasattr(settings, "database")


def test_create_get_claim_and_tool_call_use_orchestrator_http():
    job_id = uuid4()
    now = datetime.now(timezone.utc).isoformat()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.method == "POST" and request.url.path == "/api/v1/internal/rca/jobs":
            assert request.headers["idempotency-key"] == "key-1"
            return httpx.Response(
                201,
                json={
                    "id": str(job_id),
                    "status": "queued",
                    "version": 1,
                    "attempts": 0,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        if request.method == "GET" and request.url.path == f"/api/v1/internal/rca/jobs/{job_id}":
            return httpx.Response(
                200,
                json={
                    "id": str(job_id),
                    "status": "queued",
                    "version": 1,
                    "attempts": 0,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        if request.method == "POST" and request.url.path == "/api/v1/internal/execution/claim":
            return httpx.Response(204)
        if request.url.path == f"/api/v1/internal/rca/jobs/{job_id}/tool-calls":
            return httpx.Response(204)
        if request.url.path == f"/api/v1/internal/rca/jobs/{job_id}/finish":
            return httpx.Response(
                200,
                json={
                    "id": str(job_id),
                    "status": "succeeded",
                    "version": 2,
                    "attempts": 1,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return httpx.Response(404)

    store = store_with(handler)
    created = store.create(RCAJobRequest(anomalies=[{"event_id": "a" * 64}]), "key-1")
    assert created.id == job_id
    assert store.get(job_id).status == "queued"
    assert store.claim("worker", 60, 3) is None
    store.record_tool_call(job_id, "kubectl.get", {"name": "pod"}, {"ok": True})
    store.succeed(job_id, RCAResult(remediation_required=False, summary="recovered"), "raw")
    assert all(authorization == "Bearer store" for _, _, authorization in calls)
    assert ("POST", "/api/v1/internal/execution/claim", "Bearer store") in calls
