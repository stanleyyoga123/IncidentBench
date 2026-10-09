from unittest.mock import create_autospec

import pytest

from features.agent_workflow.agent_client import AgentClient
from features.agent_workflow.workflow_coordinator import WorkflowCoordinator
from features.agent_workflow.workflow_store import WorkflowStore
from features.evaluation.evaluation_repository import EvaluationRepository
from features.evaluation.evaluation_service import EvaluationService
from infrastructure.maintenance_gate import MaintenanceGate
from infrastructure.workflow_conflict_error import WorkflowConflictError

from fixtures.evaluation.evaluation_database import EvaluationDatabase


@pytest.mark.parametrize("operation", ["intake_once", "reconcile_once"])
def test_scheduler_dispatch_is_blocked_by_maintenance_without_http(
    evaluation_database: EvaluationDatabase, operation: str,
) -> None:
    """Evaluation API contract: scheduler loops cannot bypass maintenance."""
    EvaluationService(EvaluationRepository(evaluation_database)).command("acquire", "runner-feature-test")
    store = create_autospec(WorkflowStore, instance=True, spec_set=True)
    agents = [create_autospec(AgentClient, instance=True, spec_set=True) for _ in range(3)]
    coordinator = WorkflowCoordinator(
        store, *agents, MaintenanceGate(evaluation_database), batch_size=100,
    )

    with pytest.raises(WorkflowConflictError):
        if operation == "intake_once":
            coordinator.intake_once()
        else:
            coordinator.reconcile_once()

    assert store.mock_calls == []
    assert all(agent.mock_calls == [] for agent in agents)
