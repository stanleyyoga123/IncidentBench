from typing import Callable, Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from features.agent_workflow.workflow_coordinator import WorkflowCoordinator
from features.agent_workflow.workflow_store_client import WorkflowStoreClient
from infrastructure.maintenance_gate import MaintenanceGate
from infrastructure.workflow_conflict_error import WorkflowConflictError
from features.agent_workflow.schema import (
    AnomalyBatchRequest, DecisionRequest, IngestionResponse,
    RetryRequest, Workflow, WorkflowCollection,
)


def create_agent_router(
    store: WorkflowStoreClient,
    coordinator: WorkflowCoordinator,
    maintenance_gate: MaintenanceGate,
    ingestion_authorize: Callable,
    control_authorize: Callable,
) -> APIRouter:
    app = APIRouter()

    def mutation_guard(authorize: Callable) -> Callable:
        def guard(_authorization: None = Depends(authorize)) -> Iterator[None]:
            with maintenance_gate.running():
                yield

        return guard

    control_auth = Depends(control_authorize)
    ingest_mutation = Depends(mutation_guard(ingestion_authorize))
    control_mutation = Depends(mutation_guard(control_authorize))

    @app.post(
        "/api/v1/anomalies",
        response_model=IngestionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[ingest_mutation],
        operation_id="ingest_anomaly_events",
    )
    def ingest(request: AnomalyBatchRequest) -> IngestionResponse:
        accepted, duplicates, records = store.ingest(request.anomalies)
        return IngestionResponse(
            accepted=accepted,
            duplicates=duplicates,
            event_ids=[item.event_id for item in request.anomalies],
            records=records,
        )

    @app.get(
        "/api/v1/workflows",
        response_model=WorkflowCollection,
        dependencies=[control_auth],
        operation_id="list_agent_workflows",
    )
    def list_workflows() -> WorkflowCollection:
        return WorkflowCollection(
            workflows=[
                coordinator.enrich(workflow) for workflow in store.list_workflows()
            ]
        )

    @app.get(
        "/api/v1/workflows/{workflow_id}",
        response_model=Workflow,
        dependencies=[control_auth],
        operation_id="get_agent_workflow",
    )
    def get_workflow(workflow_id: UUID) -> Workflow:
        workflow = store.get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return coordinator.enrich(workflow, include_anomalies=True)

    def decision(workflow_id: UUID, request: DecisionRequest, value: str) -> Workflow:
        try:
            return coordinator.decide(workflow_id, request, value)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="workflow not found") from exc
        except WorkflowConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail="downstream job submission failed"
            ) from exc

    @app.post(
        "/api/v1/workflows/{workflow_id}/approve",
        response_model=Workflow,
        dependencies=[control_mutation],
        operation_id="approve_agent_workflow",
    )
    def approve(workflow_id: UUID, request: DecisionRequest) -> Workflow:
        return decision(workflow_id, request, "approved")

    @app.post(
        "/api/v1/workflows/{workflow_id}/decline",
        response_model=Workflow,
        dependencies=[control_mutation],
        operation_id="decline_agent_workflow",
    )
    def decline(workflow_id: UUID, request: DecisionRequest) -> Workflow:
        return decision(workflow_id, request, "declined")

    @app.post(
        "/api/v1/workflows/{workflow_id}/retry",
        response_model=Workflow,
        dependencies=[control_mutation],
        operation_id="retry_agent_workflow",
    )
    def retry(workflow_id: UUID, request: RetryRequest) -> Workflow:
        try:
            return coordinator.retry(workflow_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="workflow not found") from exc
        except WorkflowConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail="downstream retry submission failed"
            ) from exc

    return app
