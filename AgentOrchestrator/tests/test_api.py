from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from api import create_app
from config import Settings


class FakeStore:
    def __init__(self):
        self.ids = {}

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


class FakeClient:
    def close(self):
        pass


def settings():
    return Settings.model_validate(
        {
            "database": {"dsn": "postgresql://unused"},
            "api": {"ingestion_token": "ingest", "control_token": "control"},
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

    operation_ids = [
        value["operationId"]
        for path in app.openapi()["paths"].values()
        for value in path.values()
        if "operationId" in value
    ]
    assert len(operation_ids) == len(set(operation_ids)) == 7
