from unittest.mock import MagicMock, patch

import pytest

from features.agent_workflow.agent_client import AgentClient
from features.agent_workflow.workflow_coordinator import WorkflowCoordinator
from features.agent_workflow.workflow_store_client import WorkflowStoreClient
from fixtures.infrastructure.gate_database import GateDatabase
from infrastructure.database import Database
from infrastructure.maintenance_gate import MaintenanceGate
from infrastructure.workflow_conflict_error import WorkflowConflictError




@pytest.mark.parametrize("operation", ["intake_once", "reconcile_once"])
@pytest.mark.parametrize("gate_state", [{"maintenance": True}, {"locked": False}])
def test_dispatch_rejects_maintenance_before_persistence_or_agents(operation, gate_state):
    store = MagicMock(spec=WorkflowStoreClient)
    agents = [MagicMock(spec=AgentClient) for _ in range(3)]
    coordinator = WorkflowCoordinator(store, *agents, MaintenanceGate(GateDatabase(**gate_state)), batch_size=100)
    with pytest.raises(WorkflowConflictError):
        getattr(coordinator, operation)()
    assert store.mock_calls == []
    assert all(agent.mock_calls == [] for agent in agents)


def test_dispatch_holds_database_gate_across_downstream_submission():
    from datetime import datetime, timezone
    from uuid import uuid4
    from features.agent_workflow.schema import DownstreamJob, Workflow

    stamp = datetime.now(timezone.utc)
    workflow = Workflow(id=uuid4(), status="rca_submitting", version=1, created_at=stamp, updated_at=stamp)
    db = GateDatabase()
    store = MagicMock(spec=WorkflowStoreClient)
    store.execution_available.return_value = True
    store.claim_pending.return_value = (workflow, [{"event_id": "a" * 64}])
    store.retrieve_lessons.return_value = []
    rca = MagicMock(spec=AgentClient)

    def submit(*args, **kwargs):
        assert db.open, "maintenance lock was released before HTTP submission"
        return DownstreamJob(id=uuid4(), status="queued")

    rca.create_rca.side_effect = submit
    coordinator = WorkflowCoordinator(store, rca, MagicMock(spec=AgentClient), MagicMock(spec=AgentClient), MaintenanceGate(db), batch_size=100)
    assert coordinator.intake_once() == 1
    assert not db.open
    assert "pg_try_advisory_xact_lock_shared" in db.queries[0]
    store.attach_rca_job.assert_called_once()


def test_database_connection_enforces_read_only_before_gate_sql():
    connection = MagicMock()
    connection.__enter__.return_value = connection
    with patch("infrastructure.database.Connection.connect", return_value=connection):
        with Database("postgresql://unused").connection() as actual:
            assert actual is connection
            assert actual.read_only is True
            actual.cursor.assert_not_called()
