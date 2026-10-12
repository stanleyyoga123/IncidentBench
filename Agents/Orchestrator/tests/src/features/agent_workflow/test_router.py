from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from api import create_app
from config import Settings
from features.agent_workflow.workflow_store_client import WorkflowStoreClient


def test_ingestion_preserves_acknowledgements_token_separation_and_workflow_routes():
    event = {
        "event_id": "a" * 64, "detected_at": datetime.now(timezone.utc).isoformat(),
        "namespace": "shop", "resource": "deployment", "name": "checkout",
        "metric": "latency", "method": "z_score", "detail": "bounded evidence",
    }
    identifier = uuid4()
    store = MagicMock(spec=WorkflowStoreClient)
    store.ingest.side_effect = [
        (1, 0, [{"id": identifier, "event_id": event["event_id"], "duplicate": False}]),
        (0, 1, [{"id": identifier, "event_id": event["event_id"], "duplicate": True}]),
    ]
    store.list_workflows.return_value = []
    settings = Settings.model_validate({
        "database": {"dsn": "postgresql://unused"},
        "api": {"ingestion_token": "ingest", "control_token": "control"},
        "store": {"base_url": "http://store", "token": "store"},
        **{key: {"base_url": f"http://{key}", "token": key} for key in ["rca", "remediator", "learning"]},
    })
    app = create_app(settings, start_loops=False, store=store, maintenance_gate=SimpleNamespace(running=nullcontext),
                     rca=MagicMock(), remediator=MagicMock(), learning=MagicMock())
    with TestClient(app) as client:
        for token in [None, "control", "store"]:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            assert client.post("/api/v1/anomalies", headers=headers, json={"anomalies": [event]}).status_code == 401
        for duplicate in [False, True]:
            response = client.post("/api/v1/anomalies", headers={"Authorization": "Bearer ingest"}, json={"anomalies": [event]})
            assert response.status_code == 201
            assert response.json()["event_ids"] == [event["event_id"]]
            assert response.json()["records"] == [{"id": str(identifier), "event_id": event["event_id"], "duplicate": duplicate}]
            assert response.json()["duplicates"] == int(duplicate)
        invalid = dict(event)
        invalid.pop("namespace")
        assert client.post("/api/v1/anomalies", headers={"Authorization": "Bearer ingest"}, json={"anomalies": [invalid]}).status_code == 422
        assert client.get("/api/v1/workflows", headers={"Authorization": "Bearer ingest"}).status_code == 401
        assert client.get("/api/v1/workflows", headers={"Authorization": "Bearer control"}).json() == {"workflows": []}
        assert client.post("/api/v1/internal/rca/jobs", json={}).status_code == 404
    ids = {value["operationId"] for path in app.openapi()["paths"].values() for value in path.values() if "operationId" in value}
    assert ids == {"get_agent_orchestrator_health", "ingest_anomaly_events", "list_agent_workflows", "get_agent_workflow",
                   "approve_agent_workflow", "decline_agent_workflow", "retry_agent_workflow"}
