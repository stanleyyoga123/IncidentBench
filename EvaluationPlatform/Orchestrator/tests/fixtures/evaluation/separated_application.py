from collections.abc import Iterator
from unittest.mock import create_autospec

import pytest
from fastapi.testclient import TestClient

from api import create_app
from config import Settings
from features.agent_workflow.agent_client import AgentClient
from features.agent_workflow.workflow_store import WorkflowStore
from features.evaluation.evaluation_repository import EvaluationRepository
from features.evaluation.evaluation_service import EvaluationService
from infrastructure.maintenance_gate import MaintenanceGate

from fixtures.evaluation.evaluation_database import EvaluationDatabase


@pytest.fixture
def evaluation_database() -> EvaluationDatabase:
    return EvaluationDatabase()


@pytest.fixture
def separated_client(evaluation_database: EvaluationDatabase) -> Iterator[TestClient]:
    settings = Settings.model_validate({
        "database": {"dsn": "postgresql://unused"},
        "api": {"ingestion_token": "ingest", "control_token": "control", "store_token": "store"},
        "rca": {"base_url": "http://rca", "token": "rca"},
        "remediator": {"base_url": "http://remediator", "token": "remediator"},
        "learning": {"base_url": "http://learning", "token": "learning"},
    })
    store = create_autospec(WorkflowStore, instance=True, spec_set=True)
    agents = [create_autospec(AgentClient, instance=True, spec_set=True) for _ in range(3)]
    app = create_app(
        settings,
        start_loops=False,
        store=store,
        rca=agents[0],
        remediator=agents[1],
        learning=agents[2],
        database=evaluation_database,
        maintenance_gate=MaintenanceGate(evaluation_database),
        evaluation_service=EvaluationService(EvaluationRepository(evaluation_database)),
    )
    with TestClient(app) as client:
        yield client
        assert store.mock_calls == [], "Runner evaluation touched workflow persistence"
        for agent in agents:
            assert agent.mock_calls == [], "Runner evaluation contacted an agent"
