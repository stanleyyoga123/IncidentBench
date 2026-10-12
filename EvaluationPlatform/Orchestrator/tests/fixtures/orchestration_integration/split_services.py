from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from api import create_app
from config import Settings
from features.agent_workflow.schema import Workflow
from features.agent_workflow.workflow_store import WorkflowStore
from fixtures.evaluation.evaluation_database import EvaluationDatabase
from fixtures.orchestration_integration.isolated_runtime import isolated_runtime


WORKFLOW_ID = UUID("00000000-0000-0000-0000-000000000001")
RCA_ID = UUID("00000000-0000-0000-0000-000000000002")
REMEDIATION_ID = UUID("00000000-0000-0000-0000-000000000003")


def workflow(status: str, **fields: Any) -> Workflow:
    timestamp = datetime(2026, 10, 12, tzinfo=timezone.utc)
    return Workflow(id=WORKFLOW_ID, status=status, version=1,
                    created_at=timestamp, updated_at=timestamp, **fields)


@dataclass
class SplitServices:
    evaluation: TestClient
    repository: MagicMock
    coordinator: Any
    store_client: Any
    conflict_error: type[Exception]
    persistence_error: type[Exception]
    requests: list[httpx.Request] = field(default_factory=list)
    agent_responses: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    lose_responses: set[str] = field(default_factory=set)
    downstream_jobs: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)


@pytest.fixture
def split_services() -> Iterator[SplitServices]:
    """Real service routes and HTTP clients; database and agent APIs stay offline."""
    repository = create_autospec(WorkflowStore, instance=True, spec_set=True)
    repository.execution_available.return_value = True
    settings = Settings.model_validate({
        "database": {"dsn": "postgresql://unused"},
        "api": {"control_token": "control", "store_token": "store"},
    })
    database = EvaluationDatabase()
    app = create_app(settings, database=database, store=repository)
    with TestClient(app) as evaluation, isolated_runtime() as runtime:
        client_module = import_module("features.agent_workflow.workflow_store_client")
        agent_module = import_module("features.agent_workflow.agent_client")
        requests: list[httpx.Request] = []
        responses: dict[tuple[str, str], dict[str, Any]] = {}
        lose_responses: set[str] = set()
        downstream_jobs: dict[tuple[str, str], dict[str, Any]] = {}

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.host == "evaluation":
                response = evaluation.request(
                    request.method, request.url.path,
                    headers=dict(request.headers), content=request.content,
                )
                if request.url.path in lose_responses:
                    assert response.is_success, response.text
                    lose_responses.remove(request.url.path)
                    raise httpx.ReadTimeout("Response lost after server commit", request=request)
                return httpx.Response(response.status_code, content=response.content,
                                      headers=dict(response.headers))
            if request.method == "POST":
                key = (request.url.host, request.headers["Idempotency-Key"])
                payload = downstream_jobs.setdefault(key, responses[(request.method, request.url.path)])
                if request.url.path in lose_responses:
                    lose_responses.remove(request.url.path)
                    raise httpx.ReadTimeout("Job created but response lost", request=request)
                return httpx.Response(200, json=payload)
            return httpx.Response(200, json=responses[(request.method, request.url.path)])

        transport = httpx.MockTransport(handle)
        store_http = httpx.Client(base_url="http://evaluation", transport=transport,
                                  headers={"Authorization": "Bearer store"})
        store_client = client_module.WorkflowStoreClient(store_http)
        client_type = httpx.Client

        def offline_client(**kwargs: Any) -> httpx.Client:
            return client_type(**kwargs, transport=transport)

        with patch.object(agent_module.httpx, "Client", side_effect=offline_client):
            agents = [agent_module.AgentClient(f"http://{name}", name)
                      for name in ("rca", "remediator", "learning")]
        gate = runtime.MaintenanceGate(database)
        coordinator = runtime.WorkflowCoordinator(store_client, *agents, gate, batch_size=100)
        try:
            yield SplitServices(evaluation, repository, coordinator, store_client,
                                runtime.WorkflowConflictError, runtime.PersistenceUnavailableError,
                                requests, responses,
                                lose_responses, downstream_jobs)
        finally:
            store_client.close()
            for agent in agents:
                agent.close()
