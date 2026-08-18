from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from api import create_app
from config import Settings


PUBLIC_OPERATION_IDS = {
    "get_agent_orchestrator_health",
    "ingest_anomaly_events",
    "list_agent_workflows",
    "get_agent_workflow",
    "approve_agent_workflow",
    "decline_agent_workflow",
    "retry_agent_workflow",
}

INTERNAL_OPERATION_IDS = {
    "create_internal_rca_job",
    "get_internal_rca_job",
    "create_internal_remediation_job",
    "get_internal_remediation_job",
    "claim_agent_execution",
    "renew_agent_execution",
    "finish_internal_rca_job",
    "finish_internal_remediation_job",
    "record_internal_rca_tool_call",
    "record_internal_remediation_tool_call",
    "upsert_internal_remediation_artifact",
    "list_internal_remediation_artifacts",
}


class FakeStore:
    def __init__(self):
        self.ids = {}
        self.rca_jobs = {}
        self.claimed = None
        self.tool_calls = []

    def execution_available(self):
        return True

    def ingest(self, anomalies):
        accepted = 0
        records = []
        for item in anomalies:
            duplicate = item.event_id in self.ids
            if not duplicate:
                self.ids[item.event_id] = uuid4()
                accepted += 1
            records.append(
                {"id": self.ids[item.event_id], "event_id": item.event_id,
                 "duplicate": duplicate}
            )
        duplicates = len(anomalies) - accepted
        return accepted, duplicates, records

    def list_workflows(self):
        return []

    def create_rca_job(self, request, idempotency_key):
        now = datetime.now(timezone.utc)
        job = {
            "id": uuid4(),
            "workflow_id": request.get("workflow_id"),
            "status": "queued",
            "version": 1,
            "request": request,
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.rca_jobs[job["id"]] = job
        self.rca_jobs[idempotency_key] = job
        return job

    def get_rca_job(self, job_id):
        return self.rca_jobs.get(job_id)

    def claim_execution(self, service, owner, lease_seconds, max_attempts):
        self.claimed = (service, owner, lease_seconds, max_attempts)
        return None

    def record_tool_call(self, service, job_id, tool_name, arguments, result):
        self.tool_calls.append((service, job_id, tool_name, arguments, result))


class FakeClient:
    def close(self):
        pass


def settings():
    return Settings.model_validate(
        {
            "database": {"dsn": "postgresql://unused"},
            "api": {
                "ingestion_token": "ingest",
                "control_token": "control",
                "store_token": "store",
            },
            "rca": {"base_url": "http://rca", "token": "rca"},
            "remediator": {"base_url": "http://remediator", "token": "remediator"},
        }
    )


def event():
    return {
        "event_id": "a" * 64,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "resource": "deployment",
        "name": "checkout",
        "metric": "latency",
        "method": "z_score",
        "detail": "bounded evidence",
    }


def operation_ids(app):
    return {
        value["operationId"]
        for path in app.openapi()["paths"].values()
        for value in path.values()
        if "operationId" in value
    }


def test_token_separation_idempotency_and_operation_ids():
    app = create_app(
        settings(), start_loops=False, store=FakeStore(),
        rca=FakeClient(), remediator=FakeClient(),
    )
    with TestClient(app) as client:
        assert client.post("/api/v1/anomalies", json={"anomalies": [event()]}).status_code == 401
        assert client.post(
            "/api/v1/anomalies",
            headers={"Authorization": "Bearer control"},
            json={"anomalies": [event()]},
        ).status_code == 401
        response = client.post(
            "/api/v1/anomalies",
            headers={"Authorization": "Bearer ingest"},
            json={"anomalies": [event()]},
        )
        assert response.status_code == 201
        assert response.json()["accepted"] == 1
        duplicate = client.post(
            "/api/v1/anomalies",
            headers={"Authorization": "Bearer ingest"},
            json={"anomalies": [event()]},
        )
        assert duplicate.json()["duplicates"] == 1
        assert client.get(
            "/api/v1/workflows", headers={"Authorization": "Bearer ingest"}
        ).status_code == 401
        assert client.get(
            "/api/v1/workflows", headers={"Authorization": "Bearer control"}
        ).status_code == 200
        assert client.post(
            "/api/v1/internal/rca/jobs",
            headers={"Authorization": "Bearer ingest"},
            json={"anomalies": [{"event_id": "a" * 64}]},
        ).status_code == 401
        assert client.post(
            "/api/v1/internal/rca/jobs",
            headers={"Authorization": "Bearer control"},
            json={"anomalies": [{"event_id": "a" * 64}]},
        ).status_code == 401

    ids = operation_ids(app)
    assert ids == PUBLIC_OPERATION_IDS | INTERNAL_OPERATION_IDS
    assert len(ids) == len(set(ids)) == 19


def test_store_token_owns_internal_job_routes():
    store = FakeStore()
    app = create_app(
        settings(), start_loops=False, store=store,
        rca=FakeClient(), remediator=FakeClient(),
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/internal/rca/jobs",
            headers={"Authorization": "Bearer store", "Idempotency-Key": "key-1"},
            json={"anomalies": [{"event_id": "a" * 64}]},
        )
        assert created.status_code == 201
        job_id = created.json()["id"]
        fetched = client.get(
            f"/api/v1/internal/rca/jobs/{job_id}",
            headers={"Authorization": "Bearer store"},
        )
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "queued"
        claim = client.post(
            "/api/v1/internal/execution/claim",
            headers={"Authorization": "Bearer store"},
            json={
                "service": "rca",
                "owner": "worker",
                "lease_seconds": 60,
                "max_attempts": 3,
            },
        )
        assert claim.status_code == 204
        assert store.claimed == ("rca", "worker", 60, 3)
        tool = client.post(
            f"/api/v1/internal/rca/jobs/{job_id}/tool-calls",
            headers={"Authorization": "Bearer store"},
            json={"tool_name": "kubectl.get", "arguments": {"name": "pod"}, "result": {"ok": True}},
        )
        assert tool.status_code == 204
        assert store.tool_calls[0][0] == "rca"
